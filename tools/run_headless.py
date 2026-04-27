#!/usr/bin/env python
"""tools/run_headless.py — see toy-engine/mvp/08-tools.md §3, §5.

支持单局 / 批量 / ``--determinism-check`` 三种模式；输出 JSON。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python tools/run_headless.py ...` from repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from toy_engine.input import InputFrame  # noqa: E402
from toy_engine.loop import GameLoop, HashableSteppable  # noqa: E402
from toy_engine.recorder import Recorder  # noqa: E402
from toy_engine.rng import SeededRng  # noqa: E402
from toy_engine.tools_lib import (  # noqa: E402
    DEFAULT_DT,
    DEFAULT_MAX_SIM_SECONDS,
    aggregate_runs,
    load_factory,
    run_single_headless,
)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_headless",
        description="Headless run for toy-engine games.",
    )
    p.add_argument("--factory", default=None, help="MOD:ATTR override")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--seeds",
        type=int,
        default=None,
        help="batch run N games starting from --seed-base",
    )
    p.add_argument("--seed-base", type=int, default=0)
    p.add_argument("--difficulty", type=float, default=0.5)
    p.add_argument("--bot", default=None)
    p.add_argument("--max-sim-seconds", type=float, default=DEFAULT_MAX_SIM_SECONDS)
    p.add_argument("--out", default=None, help="path or '-' for stdout")
    p.add_argument("--record-dir", default=None)
    p.add_argument(
        "--determinism-check",
        type=int,
        default=None,
        metavar="N",
        help="Run N seeds twice and compare snapshot hashes.",
    )
    p.add_argument("--quiet", action="store_true")
    return p


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _write_json(payload: dict, out: str | None, default_filename: str) -> None:
    """Write ``payload`` to ``out`` per CLI conventions.

    - ``out is None`` → write to ``cwd / default_filename``
    - ``out == '-'`` → write to ``sys.stdout``
    - else → write to that path; parent must exist
    """
    if out == "-":
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return
    if out is None:
        path = Path.cwd() / default_filename
    else:
        path = Path(out)
        if not path.parent.exists():
            raise SystemExit(
                f"--out parent directory does not exist: {path.parent}"
            )
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)


# ---------------------------------------------------------------------------
# --determinism-check (08-tools.md §5)
# ---------------------------------------------------------------------------


def _collect_hashes(
    factory,
    seed: int,
    difficulty: float,
    sim_seconds: float,
    dt: float,
    bot_name: str | None,
) -> tuple[list[str], str]:
    level_config = factory.make_level_config(seed=seed, difficulty=difficulty)
    config_hash = Recorder(
        level_config,
        seed=seed,
        config_serializer=factory.serialize_config,
    ).config_hash
    world = factory.make_world(level_config=level_config, seed=seed)
    if not isinstance(world, HashableSteppable):
        raise SystemExit(
            "--determinism-check requires World.snapshot_hash() (see "
            "toy-engine/mvp/08-tools.md §5); got a world without it."
        )

    if bot_name is None or bot_name == "":
        class _Idle:
            def poll(self, ws):  # noqa: ARG002
                return InputFrame(desired_dir=None, dash=False)

        input_source = _Idle()
    else:
        rng = SeededRng(seed).spawn("bot")
        input_source = factory.make_bot(name=bot_name, world=world, rng=rng)

    hashes: list[str] = []

    def on_frame(_snap):
        # 文档规定：每个逻辑帧 step 后立即调用 snapshot_hash，不抽样
        hashes.append(world.snapshot_hash())

    loop = GameLoop(
        world,
        input_source,
        dt=dt,
        on_frame=on_frame,
        max_sim_seconds=sim_seconds,
    )
    loop.run_headless()
    return hashes, config_hash


def cmd_determinism_check(factory, args) -> int:
    n = int(args.determinism_check)
    if n <= 0:
        raise SystemExit("--determinism-check N must be > 0")
    base = args.seed_base
    difficulty = args.difficulty
    dt = DEFAULT_DT
    sim_seconds = 60.0
    expected_frames = int(round(sim_seconds / dt))

    for seed in range(base, base + n):
        hashes_a, config_hash_a = _collect_hashes(
            factory, seed, difficulty, sim_seconds, dt, args.bot
        )
        hashes_b, _config_hash_b = _collect_hashes(
            factory, seed, difficulty, sim_seconds, dt, args.bot
        )

        if len(hashes_a) != len(hashes_b):
            sys.stderr.write(
                "DETERMINISM_LENGTH_MISMATCH "
                f"seed={seed} difficulty={difficulty} "
                f"len_a={len(hashes_a)} len_b={len(hashes_b)} "
                f"last_hash_a={hashes_a[-1] if hashes_a else None} "
                f"last_hash_b={hashes_b[-1] if hashes_b else None}\n"
            )
            return 1
        for i, (ha, hb) in enumerate(zip(hashes_a, hashes_b)):
            if ha != hb:
                prev_a = hashes_a[i - 1] if i > 0 else None
                prev_b = hashes_b[i - 1] if i > 0 else None
                sys.stderr.write(
                    "DETERMINISM_MISMATCH "
                    f"seed={seed} difficulty={difficulty} "
                    f"frame={i} sim_t={i * dt:.4f} "
                    f"config_hash={config_hash_a} "
                    f"prev_a={prev_a} prev_b={prev_b} "
                    f"hash_a={ha} hash_b={hb}\n"
                )
                return 1

    out = {"ok": True, "n_seeds": n, "frames_per_run": expected_frames}
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not 0.0 <= args.difficulty <= 1.0:
        raise SystemExit("--difficulty must be in [0, 1]")
    factory = load_factory(args.factory)

    if args.determinism_check is not None:
        return cmd_determinism_check(factory, args)

    if args.seeds is not None:
        if args.seeds <= 0:
            raise SystemExit("--seeds must be > 0")
        seeds = list(range(args.seed_base, args.seed_base + args.seeds))
        per_run: list[dict] = []
        wall_times: list[float] = []

        record_dir: Path | None = None
        if args.record_dir:
            record_dir = Path(args.record_dir)
            if not record_dir.exists():
                raise SystemExit(f"--record-dir does not exist: {record_dir}")

        for seed in seeds:
            record_path = (
                str(record_dir / f"seed_{seed}.json.gz") if record_dir else None
            )
            env, wall = run_single_headless(
                factory,
                seed=seed,
                difficulty=args.difficulty,
                bot_name=args.bot,
                max_sim_seconds=args.max_sim_seconds,
                record_path=record_path,
            )
            per_run.append(env)
            wall_times.append(wall)
            if not args.quiet:
                sys.stderr.write(f"[run_headless] seed={seed} done\n")

        agg = aggregate_runs(
            per_run, wall_times, difficulty=args.difficulty, seeds=seeds
        )
        # batch + 未传 --out → stdout (08-tools.md §3.2)
        out = args.out if args.out is not None else "-"
        _write_json(agg, out, "metrics.json")
        return 0

    # --- 单局 ---
    record_path: str | None = None
    if args.record_dir:
        rd = Path(args.record_dir)
        if not rd.exists():
            raise SystemExit(f"--record-dir does not exist: {rd}")
        record_path = str(rd / f"seed_{args.seed}.json.gz")

    env, _wall = run_single_headless(
        factory,
        seed=args.seed,
        difficulty=args.difficulty,
        bot_name=args.bot,
        max_sim_seconds=args.max_sim_seconds,
        record_path=record_path,
    )
    _write_json(env, args.out, "metrics.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
