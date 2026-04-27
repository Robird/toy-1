"""MetricsCollector — 单局指标采集与 JSON 输出 (toy-engine MVP / 05-metrics.md).

本模块只提供采集与序列化框架，不内置具体指标语义；fish 5 大指标
(`first_growth_time` / `starvation_ratio` / `near_miss_count` / `boss_ttk` /
`fail_rate`) 由业务在 `metrics` 段写入。

设计要点：
- envelope 结构与 fish-doc 07 §6 对齐：6 个固定顶层字段 + `metrics` +
  `engine_version` + `duration_frames` + `events` + `extra`
- 三种采集语义：`scalar` / `event` / `tick(gauges)`
- `tick` 中的 gauges 不直接出现在 envelope；业务通过 `gauge_*` 读取派生为
  `metrics.<name>` 的 scalar
- 所有写入值必须 JSON 可序列化；NaN / Infinity / 未知对象在 ``debug`` 模式
  抛 ``MetricsPayloadError``，否则丢字段并 ``warnings.warn``
- ``final_report()`` 内部做一次 ``json.dumps`` 干跑，把序列化错误前置到调用点
- 使用 Kahan 累加保证长局浮点精度
"""

from __future__ import annotations

import dataclasses
import json
import math
import warnings
from enum import Enum
from pathlib import Path
from typing import Any

from . import __version__ as _ENGINE_VERSION

__all__ = [
    "MetricsCollector",
    "MetricsPayloadError",
    "TOP_LEVEL_KEYS",
]

#: fish-doc 07 §6 envelope 顶层 6 个固定字段（``set_scalar(top_level=True)``
#: 仅允许这些键）。
TOP_LEVEL_KEYS: tuple[str, ...] = (
    "seed",
    "difficulty",
    "result",
    "duration_s",
    "player_max_tier",
    "death_cause",
)
_TOP_LEVEL_SET = frozenset(TOP_LEVEL_KEYS)


class MetricsPayloadError(Exception):
    """payload 在 debug 模式下不可 JSON 序列化时抛出。"""


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


class _Kahan:
    """Kahan 补偿求和；避免 5000+ 帧累加 dt 的浮点漂移。"""

    __slots__ = ("sum", "_c")

    def __init__(self) -> None:
        self.sum: float = 0.0
        self._c: float = 0.0

    def add(self, x: float) -> None:
        y = x - self._c
        t = self.sum + y
        self._c = (t - self.sum) - y
        self.sum = t


class _GaugeAcc:
    """单个 gauge 的时间加权累计：``(sum(v*dt), sum(dt), min, max, dt|v>0)``。"""

    __slots__ = ("weighted", "total_dt", "above_zero_dt", "min", "max", "samples")

    def __init__(self) -> None:
        self.weighted = _Kahan()
        self.total_dt = _Kahan()
        self.above_zero_dt = _Kahan()
        self.min: float | None = None
        self.max: float | None = None
        self.samples = 0

    def update(self, value: float, dt: float) -> None:
        self.weighted.add(value * dt)
        self.total_dt.add(dt)
        if self.min is None or value < self.min:
            self.min = value
        if self.max is None or value > self.max:
            self.max = value
        if value > 0.0:
            self.above_zero_dt.add(dt)
        self.samples += 1

    def mean(self) -> float | None:
        if self.total_dt.sum <= 0.0:
            return None
        return self.weighted.sum / self.total_dt.sum

    def ratio_above_zero(self) -> float | None:
        if self.total_dt.sum <= 0.0:
            return None
        return self.above_zero_dt.sum / self.total_dt.sum


def _coerce(value: Any) -> Any:
    """把 value 转为 JSON 可序列化的原生对象。

    支持：``None / bool / int / float (有限) / str / list / tuple / dict /
    Enum / pathlib.Path / dataclass``。其他类型抛 ``TypeError``；
    ``NaN`` / ``Infinity`` 抛 ``ValueError``。
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        v = value.value
        if v is None or isinstance(v, (bool, int, float, str)):
            return _coerce(v)
        return value.name
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float not allowed: {value!r}")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(
                    f"dict key must be str, got {type(k).__name__}"
                )
            out[k] = _coerce(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_coerce(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _coerce(dataclasses.asdict(value))
    raise TypeError(
        f"value of type {type(value).__name__} is not JSON-serializable"
    )


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


class MetricsCollector:
    """单局指标采集器。详细契约见 ``toy-engine/mvp/05-metrics.md``。"""

    def __init__(
        self,
        *,
        sample_limit: int = 20,
        sample_policy: str = "first",
        debug: bool = False,
    ) -> None:
        if not isinstance(sample_limit, int) or sample_limit < 0:
            raise ValueError("sample_limit must be a non-negative int")
        if sample_policy not in ("first", "ring"):
            raise ValueError(
                f"sample_policy must be 'first' or 'ring', got {sample_policy!r}"
            )
        self._sample_limit = sample_limit
        self._sample_policy = sample_policy
        self._debug = bool(debug)

        self._top_level: dict[str, Any] = {}
        self._metrics: dict[str, Any] = {}
        self._events: dict[str, dict[str, Any]] = {}
        self._gauges: dict[str, _GaugeAcc] = {}
        self._extra: dict[str, Any] = {}

        self._frame_idx: int = 0
        self._sim_time = _Kahan()
        self._duration_s_explicit: bool = False

    # ------------------------------------------------------------------
    # 内部 helper
    # ------------------------------------------------------------------
    def _drop_or_raise(self, where: str, exc: Exception) -> None:
        """debug → 抛 MetricsPayloadError；release → 丢字段并 warning。"""
        if self._debug:
            raise MetricsPayloadError(f"{where}: {exc}") from exc
        warnings.warn(
            f"metrics: dropped {where}: {exc}",
            RuntimeWarning,
            stacklevel=3,
        )

    # ------------------------------------------------------------------
    # scalar
    # ------------------------------------------------------------------
    def set_scalar(
        self,
        name: str,
        value: Any,
        *,
        top_level: bool = False,
    ) -> None:
        """写入一个标量。

        - ``top_level=True`` → envelope 顶层；name 必须 ∈ ``TOP_LEVEL_KEYS``，
          否则 ``ValueError``。
        - ``top_level=False`` → ``metrics.<name>``。
        - 同名重复写入会覆盖前值，并 ``warnings.warn`` 一次。
        """
        if not isinstance(name, str) or not name:
            raise ValueError("scalar name must be a non-empty str")
        if top_level and name not in _TOP_LEVEL_SET:
            raise ValueError(
                f"top-level scalar {name!r} not in whitelist "
                f"{sorted(_TOP_LEVEL_SET)}"
            )
        try:
            coerced = _coerce(value)
        except (TypeError, ValueError) as exc:
            self._drop_or_raise(f"set_scalar({name!r})", exc)
            return

        bucket = self._top_level if top_level else self._metrics
        if name in bucket:
            warnings.warn(
                f"metrics: scalar {name!r} overwritten "
                f"(top_level={top_level})",
                RuntimeWarning,
                stacklevel=2,
            )
        bucket[name] = coerced
        if top_level and name == "duration_s":
            self._duration_s_explicit = True

    # ------------------------------------------------------------------
    # event
    # ------------------------------------------------------------------
    def record_event(self, name: str, value: Any = None) -> None:
        """记录一个离散事件。

        引擎只保留 ``count / first_t / last_t``；带 ``value`` 的样本占用
        ``sample_limit`` 配额（``sample_policy='first'`` 保留最早 N 条；
        ``'ring'`` 保留最近 N 条）。
        """
        if not isinstance(name, str) or not name:
            raise ValueError("event name must be a non-empty str")
        t = self._sim_time.sum
        rec = self._events.get(name)
        if rec is None:
            rec = {"count": 0, "first_t": t, "last_t": t}
            self._events[name] = rec
        rec["count"] += 1
        rec["last_t"] = t

        if value is None:
            return

        try:
            coerced = _coerce(value)
        except (TypeError, ValueError) as exc:
            self._drop_or_raise(f"record_event({name!r})", exc)
            return

        if self._sample_limit == 0:
            return

        sample = {"t": t, "v": coerced}
        samples = rec.get("samples")
        if samples is None:
            samples = []
            rec["samples"] = samples
        if len(samples) < self._sample_limit:
            samples.append(sample)
        elif self._sample_policy == "ring" and self._sample_limit > 0:
            samples.pop(0)
            samples.append(sample)
        # else: "first" policy → 丢弃溢出的 sample

    # 兼容别名（M2 实现期保留）
    event = record_event

    # ------------------------------------------------------------------
    # tick
    # ------------------------------------------------------------------
    def tick(
        self,
        dt: float,
        gauges: dict[str, float] | None = None,
    ) -> None:
        """推进一个逻辑帧；可选 ``gauges`` 做时间加权累计。"""
        if not isinstance(dt, (int, float)) or isinstance(dt, bool):
            raise TypeError(f"dt must be a number, got {type(dt).__name__}")
        dt_f = float(dt)
        if not math.isfinite(dt_f) or dt_f < 0.0:
            raise ValueError(f"dt must be a finite non-negative number, got {dt!r}")

        self._frame_idx += 1
        self._sim_time.add(dt_f)

        if not gauges:
            return
        for k, v in gauges.items():
            if not isinstance(k, str) or not k:
                raise ValueError("gauge name must be a non-empty str")
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                self._drop_or_raise(
                    f"tick gauge {k!r}",
                    TypeError(f"gauge value must be number, got {type(v).__name__}"),
                )
                continue
            if not math.isfinite(v):
                self._drop_or_raise(
                    f"tick gauge {k!r}",
                    ValueError(f"non-finite gauge value: {v!r}"),
                )
                continue
            acc = self._gauges.get(k)
            if acc is None:
                acc = _GaugeAcc()
                self._gauges[k] = acc
            acc.update(float(v), dt_f)

    # ------------------------------------------------------------------
    # 只读 gauge / event 读取（不写 envelope）
    # ------------------------------------------------------------------
    def gauge_mean(self, name: str) -> float | None:
        acc = self._gauges.get(name)
        return None if acc is None else acc.mean()

    def gauge_max(self, name: str) -> float | None:
        acc = self._gauges.get(name)
        return None if acc is None else acc.max

    def gauge_min(self, name: str) -> float | None:
        acc = self._gauges.get(name)
        return None if acc is None else acc.min

    def gauge_ratio_above_zero(self, name: str) -> float | None:
        acc = self._gauges.get(name)
        return None if acc is None else acc.ratio_above_zero()

    def event_count(self, name: str) -> int:
        rec = self._events.get(name)
        return 0 if rec is None else int(rec["count"])

    def event_first_t(self, name: str) -> float | None:
        rec = self._events.get(name)
        return None if rec is None else float(rec["first_t"])

    def event_last_t(self, name: str) -> float | None:
        rec = self._events.get(name)
        return None if rec is None else float(rec["last_t"])

    # ------------------------------------------------------------------
    # finish + 输出
    # ------------------------------------------------------------------
    def finish(self, result: str, **extra: Any) -> None:
        """终局：写 ``result`` 到顶层；``extra`` 按白名单分流。

        - 命中 ``TOP_LEVEL_KEYS`` → 顶层
        - 否则若 ``metrics`` 中已存在同名 scalar → 覆盖到 ``metrics`` 段
        - 其余 → ``extra`` 兜底容器
        """
        self.set_scalar("result", result, top_level=True)
        for k, v in extra.items():
            if k in _TOP_LEVEL_SET:
                self.set_scalar(k, v, top_level=True)
            elif k in self._metrics:
                self.set_scalar(k, v, top_level=False)
            else:
                try:
                    self._extra[k] = _coerce(v)
                except (TypeError, ValueError) as exc:
                    self._drop_or_raise(f"finish extra {k!r}", exc)

    def final_report(self) -> dict[str, Any]:
        """产出最终 envelope（dict）。

        - 顶层固定 6 个字段 + ``metrics`` + ``engine_version`` +
          ``duration_frames`` + ``events`` + ``extra``，**仅这些键**
        - ``duration_s`` 业务未显式写则用 ``sum(dt)`` 兜底
        - 内部做一次 ``json.dumps(..., allow_nan=False)`` 干跑：
          debug → 抛 ``MetricsPayloadError``；release → 警告并尽量回退
        """
        envelope: dict[str, Any] = {}
        for key in TOP_LEVEL_KEYS:
            if key == "duration_s" and not self._duration_s_explicit:
                envelope[key] = self._sim_time.sum
            else:
                envelope[key] = self._top_level.get(key)

        envelope["metrics"] = dict(self._metrics)
        envelope["engine_version"] = _ENGINE_VERSION
        envelope["duration_frames"] = self._frame_idx
        envelope["events"] = {
            name: {sk: (list(sv) if isinstance(sv, list) else sv)
                   for sk, sv in rec.items()}
            for name, rec in self._events.items()
        }
        envelope["extra"] = dict(self._extra)

        # 干跑：把序列化错误前置到 final_report 调用点
        try:
            json.dumps(envelope, allow_nan=False)
        except (TypeError, ValueError) as exc:
            if self._debug:
                raise MetricsPayloadError(
                    f"final_report: payload not JSON-serializable: {exc}"
                ) from exc
            warnings.warn(
                f"metrics: final_report payload had unserializable fields: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
        return envelope

    # 兼容别名
    to_dict = final_report

    def dump(self, path: str | Path) -> None:
        """把 ``final_report()`` 写到 ``path``（UTF-8 / ``allow_nan=False``）。"""
        report = self.final_report()
        p = Path(path)
        with p.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, allow_nan=False)
