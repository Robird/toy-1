"""tests/fish/test_tools_integration.py — 子进程跑 tools/run_headless + tools/param_sweep。"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(args, timeout=120):
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.mark.slow
class TestRunHeadlessCli:
    def test_single_run_produces_envelope(self, tmp_path):
        out = tmp_path / "metrics.json"
        proc = _run([
            "tools.run_headless",
            "--factory", "fish:make_factory",
            "--seed", "0",
            "--difficulty", "0.5",
            "--max-sim-seconds", "20",
            "--out", str(out),
            "--quiet",
        ])
        assert proc.returncode == 0, f"stderr={proc.stderr}"
        assert out.exists()
        env = json.loads(out.read_text(encoding="utf-8"))
        # 顶层字段
        for key in ("seed", "difficulty", "result", "duration_s",
                    "player_max_tier", "death_cause"):
            assert key in env
        assert env["seed"] == 0
        assert env["result"] in ("DEAD", "VICTORY", "TIMEOUT")
        # metrics 段
        assert "metrics" in env
        for name in ("fail_rate", "first_growth_time", "starvation_ratio",
                     "near_miss_count", "boss_ttk"):
            assert name in env["metrics"]


@pytest.mark.slow
class TestParamSweepCli:
    def test_5_seeds_yields_one_row(self, tmp_path):
        out = tmp_path / "sweep.csv"
        proc = _run([
            "tools.param_sweep",
            "--factory", "fish:make_factory",
            "--difficulty", "0.5",
            "--seeds", "5",
            "--max-sim-seconds", "20",
            "--out", str(out),
            "--bot", "heuristic",
            "--quiet",
        ], timeout=240)
        assert proc.returncode == 0, f"stderr={proc.stderr}"
        assert out.exists()
        with out.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        # 一个 difficulty → 1 行
        assert len(rows) == 1
        row = rows[0]
        assert int(row["n_runs"]) == 5
        assert float(row["difficulty"]) == 0.5
        # fail/victory/timeout rate 之和 ≤ 1（DONE 不计入；不应出现 DONE）
        rate_sum = (
            float(row["fail_rate"]) + float(row["victory_rate"]) + float(row["timeout_rate"])
        )
        assert 0.0 <= rate_sum <= 1.0 + 1e-9
        assert abs(rate_sum - 1.0) < 1e-6, f"DONE leaked into result: rate_sum={rate_sum}"
