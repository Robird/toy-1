#!/usr/bin/env python
"""tools/param_sweep.py — see toy-engine/mvp/08-tools.md §4.

CSV 输出，每行 = 一个 difficulty。固定字段 union 自动追加的 ``extra_<name>`` 列。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from toy_engine.tools_lib import (  # noqa: E402
    DEFAULT_MAX_SIM_SECONDS,
    aggregate_runs,
    load_factory,
    run_single_headless,
)


# 按 08-tools.md §4 定义的固定字段顺序
FIXED_FIELDS: list[str] = [
    "difficulty",
    "n_runs",
    "seed_base",
    "fail_rate",
    "victory_rate",
    "timeout_rate",
    "entered_boss_rate",
    "counter_kill_rate",
    "duration_s_mean",
    "duration_s_p50",
    "duration_s_p95",
    "headless_wall_s_mean",
    "first_growth_time_mean",
    "starvation_ratio_mean",
    "near_miss_count_mean",
    "boss_ttk_mean",
]

# 固定 metric mean 列 → metrics.<name> key
_FIXED_METRIC_MEANS = {
    "first_growth_time_mean": "first_growth_time",
    "starvation_ratio_mean": "starvation_ratio",
    "near_miss_count_mean": "near_miss_count",
    "boss_ttk_mean": "boss_ttk",
}


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="param_sweep")
    p.add_argument("--factory", default=None)
    p.add_argument(
        "--difficulty",
        required=True,
        help="comma-separated list, e.g. 0.3,0.5,0.7",
    )
    p.add_argument("--seeds", type=int, required=True)
    p.add_argument("--seed-base", type=int, default=0)
    p.add_argument("--bot", default=None)
    p.add_argument("--max-sim-seconds", type=float, default=DEFAULT_MAX_SIM_SECONDS)
    p.add_argument("--out", default=None, help="path or '-' for stdout (default)")
    p.add_argument("--quiet", action="store_true")
    return p


def _row_for_difficulty(
    factory, difficulty: float, seeds: list[int], args
) -> tuple[dict[str, object], set[str]]:
    per_run: list[dict] = []
    wall_times: list[float] = []
    for seed in seeds:
        env, wall = run_single_headless(
            factory,
            seed=seed,
            difficulty=difficulty,
            bot_name=args.bot,
            max_sim_seconds=args.max_sim_seconds,
        )
        per_run.append(env)
        wall_times.append(wall)

    agg = aggregate_runs(per_run, wall_times, difficulty=difficulty, seeds=seeds)

    def _event_rate(name: str) -> float:
        if not per_run:
            return 0.0
        hit = sum(
            1
            for r in per_run
            if (r.get("events") or {}).get(name, {}).get("count", 0) > 0
        )
        return hit / len(per_run)

    duration_stats = agg["aggregate"]["duration_s"]
    row: dict[str, object] = {
        "difficulty": difficulty,
        "n_runs": len(seeds),
        "seed_base": seeds[0] if seeds else args.seed_base,
        "fail_rate": agg["aggregate"]["fail_rate"],
        "victory_rate": agg["aggregate"]["victory_rate"],
        "timeout_rate": agg["aggregate"]["timeout_rate"],
        "entered_boss_rate": _event_rate("entered_boss"),
        "counter_kill_rate": _event_rate("counter_kill"),
        "duration_s_mean": duration_stats.get("mean", ""),
        "duration_s_p50": duration_stats.get("p50", ""),
        "duration_s_p95": duration_stats.get("p95", ""),
        "headless_wall_s_mean": agg["wall_time_s"]["mean_per_run"],
    }
    metrics_agg = agg["aggregate"]["metrics"]
    for col, mname in _FIXED_METRIC_MEANS.items():
        if mname in metrics_agg:
            row[col] = metrics_agg[mname].get("mean", "")
        else:
            row[col] = ""

    extras: set[str] = set()
    for mname, stats in metrics_agg.items():
        if mname in _FIXED_METRIC_MEANS.values():
            continue
        col = f"extra_{mname}"
        row[col] = stats.get("mean", "")
        extras.add(col)
    return row, extras


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        diffs = [float(x) for x in args.difficulty.split(",") if x.strip() != ""]
    except ValueError as exc:
        raise SystemExit(
            "--difficulty must be a comma-separated list of floats"
        ) from exc
    if not diffs:
        raise SystemExit("--difficulty must be a non-empty comma-separated list")
    if any(d < 0.0 or d > 1.0 for d in diffs):
        raise SystemExit("--difficulty values must be in [0, 1]")
    if args.seeds <= 0:
        raise SystemExit("--seeds must be > 0")

    factory = load_factory(args.factory)

    rows: list[dict[str, object]] = []
    extra_cols: set[str] = set()
    for d in diffs:
        seeds = list(range(args.seed_base, args.seed_base + args.seeds))
        row, ec = _row_for_difficulty(factory, d, seeds, args)
        rows.append(row)
        extra_cols.update(ec)
        if not args.quiet:
            sys.stderr.write(f"[param_sweep] difficulty={d} done\n")

    fieldnames = list(FIXED_FIELDS) + sorted(extra_cols)

    if args.out and args.out != "-":
        path = Path(args.out)
        if not path.parent.exists():
            raise SystemExit(f"--out parent directory does not exist: {path.parent}")
        fh = path.open("w", encoding="utf-8", newline="")
        owns = True
    else:
        fh = sys.stdout
        owns = False

    try:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})
    finally:
        if owns:
            fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
