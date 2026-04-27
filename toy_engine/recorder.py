"""Recorder — 输入录像与回放 (toy-engine MVP / 04-recorder.md)。

只录 ``(seed, level_config, input_frames)``，不录世界状态；回放靠确定性。

设计要点：
- 仅依赖标准库 (``json``, ``gzip``, ``hashlib``, ``dataclasses``, ``datetime``,
  ``enum``)；与 ``toy_engine.input.InputFrame`` 共用 ``to_wire/from_wire``。
- 帧压缩：``record(i, frame)`` 内部比较与上一帧的差异，相同则不写文件；
  第一帧无条件写入。
- 持久化使用流式 ``json.dump`` / ``gzip.GzipFile`` 写入，不在内存里拼接巨型
  字符串。
- ``load`` 信任文件头魔数 (``0x1f8b``) 而非后缀；并对原始 ``config`` 重算
  canonical hash，与文件内 ``config_hash`` 不匹配抛 ``ConfigDriftError``。
- 默认 ``to_jsonable`` 仅支持 dict/list/tuple/str/int/float/bool/None/Enum/
  dataclass；遇到未知对象抛 ``TypeError``，禁止 ``str(obj)`` 静默糊弄。
"""

from __future__ import annotations

import dataclasses
import gzip as _gzip
import hashlib
import io
import json
import math
import os
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from os import PathLike
from typing import Any, Callable, Generic, TypeVar

from toy_engine.input import InputFrame

__all__ = [
    "Recorder",
    "Recording",
    "ConfigDriftError",
    "ConfigDriftWarning",
    "EngineVersionWarning",
    "EmptyRecordingError",
    "to_jsonable",
]


ConfigT = TypeVar("ConfigT")

_DEFAULT_ENGINE_VERSION = "0.1.0"
_REQUIRED_TOPLEVEL = frozenset(
    {"engine_version", "seed", "config_hash", "config", "meta", "frames"}
)


# ---------------------------------------------------------------------------
# 异常 / 警告
# ---------------------------------------------------------------------------


class ConfigDriftError(RuntimeError):
    """录像文件 ``config_hash`` 与 ``config`` 重算结果不一致。"""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            f"config_hash mismatch: file={expected!r}, recomputed={actual!r}"
        )
        self.expected = expected
        self.actual = actual


class EngineVersionWarning(UserWarning):
    """录像与当前引擎主版本号不一致；仅警告，不阻塞。"""


class ConfigDriftWarning(UserWarning):
    """``Recorder.load(strict_hash=False)`` 时 ``config_hash`` 不匹配的告警。"""


class EmptyRecordingError(RuntimeError):
    """``Recorder.save`` 时检测到 ``frames == []``，避免落地废录像。"""


# ---------------------------------------------------------------------------
# 默认 JSON 化
# ---------------------------------------------------------------------------


def to_jsonable(obj: Any) -> Any:
    """递归把 Python 对象转成 JSON 原生类型。

    支持：``None`` / ``bool`` / ``int`` / ``float`` / ``str`` / ``list`` /
    ``tuple`` / ``dict`` / ``Enum`` / ``dataclass``（非 ``Enum`` 也非
    ``dataclass`` 的未知对象抛 ``TypeError``）。

    - ``dict`` 的 key 必须是 ``str`` 或 ``Enum``（取 ``Enum.name``）；其它
      类型 key 抛 ``TypeError``。
    - ``float`` 中的 ``NaN`` / ``Inf`` 会立刻抛 ``ValueError``；最终
      ``json.dumps(..., allow_nan=False)`` 仍作为文件写出前的兜底。
    """
    # 顺序很重要：bool 是 int 子类，必须先判
    if obj is None or isinstance(obj, bool):
        return obj
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"to_jsonable: float must be finite, got {obj!r}")
        return obj
    if isinstance(obj, str):
        return obj
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: to_jsonable(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
        }
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(k, Enum):
                key = k.name
            elif isinstance(k, str):
                key = k
            else:
                raise TypeError(
                    f"to_jsonable: dict key must be str or Enum, "
                    f"got {type(k).__name__}"
                )
            if key in out:
                raise ValueError(
                    f"to_jsonable: duplicate dict key after normalization: {key!r}"
                )
            out[key] = to_jsonable(v)
        return out
    raise TypeError(
        f"to_jsonable: cannot serialize object of type {type(obj).__name__}; "
        "provide a config_serializer or extend the type."
    )


def _canonical_hash(raw_config: Any) -> str:
    """文档 §3.2 的 canonical config hash 算法。"""
    canonical = json.dumps(
        raw_config,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _major(version: str) -> str:
    return version.split(".", 1)[0]


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


@dataclass
class Recording(Generic[ConfigT]):
    """一局录像的内存表示（详见 04-recorder.md §2）。

    ``frames`` 是按帧号索引的稠密 ``list[InputFrame]``，可直接传给
    ``ReplayInput(rec.frames)``。
    """

    level_config: ConfigT
    seed: int
    frames: list[InputFrame]
    config_hash: str
    engine_version: str
    meta: dict = field(default_factory=dict)
    #: 文件中读到的原始 ``config_hash``；与 :attr:`config_hash` 不一致时
    #: 说明加载时使用了 ``strict_hash=False`` 容忍了漂移，仅作 in-memory 诊断，
    #: 不参与 ``save`` / ``to_wire``。默认 ``None`` 表示与 :attr:`config_hash` 相同。
    file_config_hash: str | None = None


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


class Recorder(Generic[ConfigT]):
    """单局输入录像器（详见 04-recorder.md §2）。"""

    __slots__ = (
        "_level_config",
        "_seed",
        "_engine_version",
        "_config_serializer",
        "_raw_config",
        "_config_hash",
        "_sparse_frames",
        "_last_frame",
        "_last_frame_idx",
        "_saved",
        "_max_frame_idx",
    )

    def __init__(
        self,
        level_config: ConfigT,
        seed: int | None = None,
        engine_version: str = _DEFAULT_ENGINE_VERSION,
        config_serializer: Callable[[ConfigT], dict] | None = None,
    ) -> None:
        self._level_config = level_config
        self._engine_version = str(engine_version)
        self._config_serializer = config_serializer

        # seed: 显式参数优先；否则尝试 level_config.seed；否则 ValueError。
        if seed is None:
            cfg_seed = getattr(level_config, "seed", None)
            if cfg_seed is None and isinstance(level_config, dict):
                cfg_seed = level_config.get("seed")
            if cfg_seed is None:
                raise ValueError(
                    "Recorder seed=None and level_config has no `seed` "
                    "attribute/key; pass seed= explicitly."
                )
            seed = cfg_seed
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError(f"seed must be int, got {type(seed).__name__}")
        self._seed: int = seed

        # 立刻 freeze config snapshot，避免后续业务改 level_config 偷换 hash。
        if config_serializer is not None:
            raw = to_jsonable(config_serializer(level_config))
        else:
            raw = to_jsonable(level_config)
        if not isinstance(raw, dict):
            # 顶级 config 字段在文件里固定为 dict。
            raise TypeError(
                f"level_config must serialize to a JSON dict, "
                f"got {type(raw).__name__}"
            )
        self._raw_config: Any = raw
        self._config_hash: str = _canonical_hash(raw)

        self._sparse_frames: list[dict] = []
        self._last_frame: InputFrame | None = None
        self._last_frame_idx: int = -1
        self._max_frame_idx: int = -1
        self._saved: bool = False

    # ---- 只读属性（测试观察用） ----
    @property
    def seed(self) -> int:
        return self._seed

    @property
    def config_hash(self) -> str:
        return self._config_hash

    @property
    def engine_version(self) -> str:
        return self._engine_version

    @property
    def sparse_frames(self) -> list[dict]:
        # 返回每条变化点的拷贝，避免外部 mutation。
        return [dict(entry) for entry in self._sparse_frames]

    # ----------------------------------------------------------------- record
    def record(self, frame_idx: int, input_frame: InputFrame) -> None:
        if self._saved:
            raise RuntimeError(
                "Recorder is frozen after save(); construct a new instance "
                "to record another run."
            )
        if not isinstance(frame_idx, int) or isinstance(frame_idx, bool):
            raise TypeError(
                f"frame_idx must be int, got {type(frame_idx).__name__}"
            )
        if not isinstance(input_frame, InputFrame):
            raise TypeError(
                f"input_frame must be InputFrame, got {type(input_frame).__name__}"
            )
        if self._last_frame_idx < 0:
            if frame_idx != 0:
                raise ValueError(
                    f"first frame_idx must be 0, got {frame_idx}"
                )
        else:
            if frame_idx <= self._last_frame_idx:
                raise ValueError(
                    f"frame_idx must be strictly increasing; "
                    f"got {frame_idx} after {self._last_frame_idx}"
                )

        # 第一帧无条件写；后续仅在与上一帧不同时写。
        if self._last_frame is None or input_frame != self._last_frame:
            entry = {"i": frame_idx, **input_frame.to_wire()}
            self._sparse_frames.append(entry)
            self._last_frame = input_frame

        self._last_frame_idx = frame_idx
        if frame_idx > self._max_frame_idx:
            self._max_frame_idx = frame_idx

    # ------------------------------------------------------------------- save
    def save(
        self,
        path: str | PathLike[str],
        gzip: bool | None = None,
    ) -> None:
        if self._saved:
            raise RuntimeError("Recorder.save() may only be called once.")
        if not self._sparse_frames:
            raise EmptyRecordingError(
                "no frames recorded; refuse to save an empty recording."
            )

        if gzip is None:
            gzip = os.fspath(path).lower().endswith(".gz")

        meta = {
            "recorded_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "duration_frames": int(self._max_frame_idx) + 1,
        }

        payload = {
            "engine_version": self._engine_version,
            "seed": self._seed,
            "config_hash": self._config_hash,
            "config": self._raw_config,
            "meta": meta,
            "frames": self._sparse_frames,
        }

        # 流式写入；不构造巨型字符串。
        if gzip:
            with _gzip.open(os.fspath(path), "wb") as raw_fh:
                with io.TextIOWrapper(raw_fh, encoding="utf-8") as text_fh:
                    json.dump(
                        payload,
                        text_fh,
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    )
        else:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(
                    payload,
                    fh,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )

        self._saved = True

    # --------------------------------------------------------------- classload
    @classmethod
    def load(
        cls,
        path: str | PathLike[str],
        config_deserializer: Callable[[dict], ConfigT] | None = None,
        *,
        strict_hash: bool = True,
    ) -> "Recording[ConfigT]":
        with open(path, "rb") as fh:
            head = fh.read(2)
            fh.seek(0)
            if head == b"\x1f\x8b":
                with _gzip.open(fh, "rt", encoding="utf-8") as gz:
                    data = json.load(gz)
            else:
                with io.TextIOWrapper(fh, encoding="utf-8") as text_fh:
                    data = json.load(text_fh)

        if not isinstance(data, dict):
            raise ValueError(
                f"recording at {os.fspath(path)!r} must be a JSON object, "
                f"got {type(data).__name__}"
            )

        # 顶层字段白名单
        keys = set(data.keys())
        missing = _REQUIRED_TOPLEVEL - keys
        if missing:
            raise ValueError(
                f"recording missing required top-level fields: "
                f"{sorted(missing)!r}"
            )
        unknown = keys - _REQUIRED_TOPLEVEL
        if unknown:
            raise ValueError(
                f"recording has unknown top-level fields: {sorted(unknown)!r}"
            )

        engine_version = data["engine_version"]
        if not isinstance(engine_version, str):
            raise TypeError(
                f"engine_version must be str, got {type(engine_version).__name__}"
            )
        if _major(engine_version) != _major(_DEFAULT_ENGINE_VERSION):
            warnings.warn(
                f"recording engine_version={engine_version!r} differs in MAJOR "
                f"from current {_DEFAULT_ENGINE_VERSION!r}; replay determinism "
                "is not guaranteed.",
                EngineVersionWarning,
                stacklevel=2,
            )

        seed = data["seed"]
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError(f"seed must be int, got {type(seed).__name__}")

        raw_config = data["config"]
        if not isinstance(raw_config, dict):
            raise TypeError(
                f"config must be dict, got {type(raw_config).__name__}"
            )
        file_hash = data["config_hash"]
        if not isinstance(file_hash, str):
            raise TypeError(
                f"config_hash must be str, got {type(file_hash).__name__}"
            )
        recomputed = _canonical_hash(raw_config)
        effective_hash = file_hash
        diagnostic_file_hash: str | None = None
        if recomputed != file_hash:
            if strict_hash:
                raise ConfigDriftError(file_hash, recomputed)
            warnings.warn(
                f"ConfigDriftError tolerated (strict_hash=False): "
                f"file={file_hash!r}, recomputed={recomputed!r}",
                ConfigDriftWarning,
                stacklevel=2,
            )
            effective_hash = recomputed
            diagnostic_file_hash = file_hash

        meta = data["meta"]
        if not isinstance(meta, dict):
            raise TypeError(f"meta must be dict, got {type(meta).__name__}")
        if "duration_frames" not in meta:
            raise ValueError("meta missing required field 'duration_frames'")
        duration = meta["duration_frames"]
        if not isinstance(duration, int) or isinstance(duration, bool):
            raise TypeError(
                f"meta.duration_frames must be int, got {type(duration).__name__}"
            )
        if duration < 0:
            raise ValueError(
                f"meta.duration_frames must be >= 0, got {duration}"
            )

        sparse = data["frames"]
        if not isinstance(sparse, list):
            raise TypeError(
                f"frames must be list, got {type(sparse).__name__}"
            )

        # 校验稀疏帧严格按 i 递增、第一条为 0（若非空）
        if sparse:
            prev = -1
            required_frame_keys = {"i", "dir", "dash"}
            for k, entry in enumerate(sparse):
                if not isinstance(entry, dict):
                    raise TypeError(
                        f"frames[{k}] must be dict, got {type(entry).__name__}"
                    )
                frame_keys = set(entry.keys())
                missing_frame_keys = required_frame_keys - frame_keys
                if missing_frame_keys:
                    raise ValueError(
                        f"frames[{k}] missing required fields: "
                        f"{sorted(missing_frame_keys)!r}"
                    )
                unknown_frame_keys = frame_keys - required_frame_keys
                if unknown_frame_keys:
                    raise ValueError(
                        f"frames[{k}] has unknown fields: "
                        f"{sorted(unknown_frame_keys)!r}"
                    )
                idx = entry["i"]
                if not isinstance(idx, int) or isinstance(idx, bool):
                    raise TypeError(
                        f"frames[{k}].i must be int, got {type(idx).__name__}"
                    )
                if k == 0 and idx != 0:
                    raise ValueError(
                        f"frames[0].i must be 0, got {idx}"
                    )
                if idx <= prev and k > 0:
                    raise ValueError(
                        f"frames[{k}].i={idx} must be > previous {prev}"
                    )
                if idx >= duration:
                    raise ValueError(
                        f"frames[{k}].i={idx} >= meta.duration_frames={duration}"
                    )
                prev = idx

        # 展开稠密 list[InputFrame]
        dense: list[InputFrame] = []
        last_frame = InputFrame(desired_dir=None, dash=False)
        sparse_iter = iter(sparse)
        next_change = next(sparse_iter, None)
        for i in range(duration):
            while next_change is not None and int(next_change["i"]) == i:
                last_frame = InputFrame.from_wire(next_change)
                next_change = next(sparse_iter, None)
            dense.append(last_frame)

        if config_deserializer is not None:
            level_config: Any = config_deserializer(raw_config)
        else:
            level_config = raw_config

        return Recording(
            level_config=level_config,
            seed=seed,
            frames=dense,
            config_hash=effective_hash,
            engine_version=engine_version,
            meta=meta,
            file_config_hash=diagnostic_file_hash,
        )
