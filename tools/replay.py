#!/usr/bin/env python
"""tools/replay.py — see toy-engine/mvp/08-tools.md §6.

读取 ``Recorder`` 录像 JSON / JSON.gz，构建 :class:`ReplayInput` 驱动
``GameLoop``。默认 / ``--render`` 走 GUI（``run_realtime``），``--headless`` 无窗口。
``--force`` 把 ``ConfigDriftError`` 降级为 warning 并继续。
"""

from __future__ import annotations

import argparse
import gzip as _gzip
import json
import sys
import warnings
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from toy_engine.input import InputFrame, ReplayInput  # noqa: E402
from toy_engine.loop import GameLoop  # noqa: E402
from toy_engine.metrics import MetricsCollector  # noqa: E402
from toy_engine.recorder import (  # noqa: E402
    ConfigDriftError,
    Recorder,
    Recording,
)
from toy_engine.tools_lib import (  # noqa: E402
    DEFAULT_DT,
    load_factory,
)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="replay")
    p.add_argument("recording")
    p.add_argument("--factory", default=None)
    p.add_argument("--render", action="store_true")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--out", default=None)
    return p


def _force_load(path: Path, factory) -> Recording:
    """Bypass ``config_hash`` 一致性校验，按文件原样构造 :class:`Recording`。

    仅在 ``--force`` 下走此路径；保留 ``Recorder.load`` 的其它结构校验是为
    避免重复实现解析逻辑：先做一次"宽松读"，hash 不匹配就在内存里把
    file 端 hash 重写为 canonical hash 后写入临时文件，再交回
    ``Recorder.load``。这样仍能复用稀疏→稠密展开、字段白名单等所有校验。
    """
    import os

    from toy_engine.recorder import _canonical_hash  # 内部 helper

    with open(path, "rb") as fh:
        head = fh.read(2)
        fh.seek(0)
        if head == b"\x1f\x8b":
            with _gzip.open(fh, "rt", encoding="utf-8") as gz:
                data = json.load(gz)
        else:
            data = json.load(fh)

    if "config" not in data or "config_hash" not in data:
        raise SystemExit(
            "recording file is missing required fields; --force cannot recover"
        )
    data["config_hash"] = _canonical_hash(data["config"])

    # 写到 tmp 文件再交给 Recorder.load 复用所有校验逻辑
    import tempfile

    suffix = ".json.gz" if str(path).lower().endswith(".gz") else ".json"
    tmp = tempfile.NamedTemporaryFile("wb", suffix=suffix, delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        if suffix == ".json.gz":
            with _gzip.open(tmp_path, "wt", encoding="utf-8") as gz:
                json.dump(data, gz, ensure_ascii=False)
        else:
            with open(tmp_path, "w", encoding="utf-8") as text_fh:
                json.dump(data, text_fh, ensure_ascii=False)
        return Recorder.load(tmp_path, config_deserializer=factory.deserialize_config)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _load_recording(path: Path, factory, force: bool) -> Recording:
    try:
        return Recorder.load(path, config_deserializer=factory.deserialize_config)
    except ConfigDriftError as exc:
        if not force:
            raise
        warnings.warn(
            f"replay: ignoring ConfigDriftError due to --force: {exc}",
            RuntimeWarning,
            stacklevel=1,
        )
        return _force_load(path, factory)


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.render and args.headless:
        raise SystemExit("--render and --headless are mutually exclusive")
    headless = args.headless

    factory = load_factory(args.factory)
    path = Path(args.recording)

    try:
        rec = _load_recording(path, factory, args.force)
    except ConfigDriftError as exc:
        sys.stderr.write(f"ConfigDriftError: {exc} (re-run with --force to ignore)\n")
        return 2

    seed = rec.seed
    world = factory.make_world(level_config=rec.level_config, seed=seed)
    input_source = ReplayInput(rec.frames, strict_end=False)
    replay_seconds = len(rec.frames) * DEFAULT_DT

    metrics = MetricsCollector()
    metrics.set_scalar("seed", seed, top_level=True)

    def on_frame(_snap):
        metrics.tick(DEFAULT_DT)

    loop = GameLoop(
        world,
        input_source,
        dt=DEFAULT_DT,
        on_frame=on_frame,
        max_sim_seconds=replay_seconds,
        speed=max(0.0, args.speed) if not headless else 1.0,
    )

    if headless:
        loop.run_headless()
        if metrics.final_report().get("result") is None:
            metrics.finish("REPLAY_DONE")
        env = metrics.final_report()
        out_path = args.out or "metrics.json"
        if out_path == "-":
            json.dump(env, sys.stdout, ensure_ascii=False)
            sys.stdout.write("\n")
        else:
            op = Path(out_path)
            if not op.parent.exists():
                raise SystemExit(f"--out parent directory does not exist: {op.parent}")
            with op.open("w", encoding="utf-8") as fh:
                json.dump(env, fh, ensure_ascii=False)
        return 0

    # GUI mode
    loop.run_realtime()
    return 0


# Used to silence the unused-import warning on InputFrame in some linters; the
# real reason it is imported is to keep the public symbol in scope for tools
# that monkey-patch InputSource implementations during tests.
_ = InputFrame


if __name__ == "__main__":
    raise SystemExit(main())
