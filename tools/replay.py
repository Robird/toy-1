#!/usr/bin/env python
"""tools/replay.py - see toy-engine/mvp/08-tools.md section 6.

Read a Recorder JSON / JSON.gz, build a ReplayInput, drive a GameLoop.
Default / --render uses GUI (run_realtime); --headless runs without a window.
--force downgrades ConfigDriftError to ConfigDriftWarning and continues
(via Recorder.load(strict_hash=False)).
"""

from __future__ import annotations

import argparse
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
    ConfigDriftWarning,
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


def _load_recording(path: Path, factory, force: bool) -> Recording:
    """Wrap Recorder.load and surface ConfigDriftWarning to stderr."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConfigDriftWarning)
        rec = Recorder.load(
            path,
            config_deserializer=factory.deserialize_config,
            strict_hash=not force,
        )
    for w in caught:
        warnings.warn(w.message, w.category, stacklevel=1)
        if issubclass(w.category, ConfigDriftWarning):
            sys.stderr.write(
                f"replay: ConfigDriftError tolerated due to --force: {w.message}\n"
            )
    return rec


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

    loop.run_realtime()
    return 0


_ = InputFrame


if __name__ == "__main__":
    raise SystemExit(main())
