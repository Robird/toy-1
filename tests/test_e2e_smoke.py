"""End-to-end smoke pipeline for ``tools/*.py`` (M2-10).

Drives the three CLI scripts via :mod:`subprocess` (real ``python tools/...``
invocations) using the shared mock factory at
``tests._mock_factory:MOCK_FACTORY``. This complements ``test_tools_cli.py``
(which calls each ``main()`` in-process) by exercising the actual CLI surface
end-to-end: argv parsing, exit codes, stdout/stderr separation, JSON/CSV file
IO, and ``ConfigDriftError`` plumbing through ``replay.py --force``.
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
FACTORY_SPEC = "tests._mock_factory:MOCK_FACTORY"


def _env() -> dict[str, str]:
    """Subprocess env that makes ``tests._mock_factory`` importable."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    )
    # Inherit headless SDL drivers from conftest.py so any rendered tools are safe.
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    return env


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(REPO_ROOT / "tools" / script), *args]
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )


# ---------------------------------------------------------------------------
# run_headless: batch aggregation + determinism-check
# ---------------------------------------------------------------------------


def test_e2e_run_headless_batch_aggregate_shape():
    cp = _run(
        "run_headless.py",
        "--factory", FACTORY_SPEC,
        "--seeds", "5",
        "--difficulty", "0.5",
        "--quiet",
    )
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout)
    # 08-tools.md §3.2 schema
    assert payload["n_runs"] == 5
    assert payload["difficulty"] == 0.5
    assert payload["seeds"] == [0, 1, 2, 3, 4]
    assert {"fail_rate", "victory_rate", "timeout_rate", "duration_s"} <= set(
        payload["aggregate"].keys()
    )
    assert "total" in payload["wall_time_s"]
    assert "mean_per_run" in payload["wall_time_s"]
    assert len(payload["per_run"]) == 5
    for entry in payload["per_run"]:
        assert "seed" in entry and "result" in entry


def test_e2e_run_headless_determinism_check_passes():
    cp = _run(
        "run_headless.py",
        "--factory", FACTORY_SPEC,
        "--determinism-check", "3",
        "--quiet",
    )
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout)
    assert payload == {"ok": True, "n_seeds": 3, "frames_per_run": 3600}


# ---------------------------------------------------------------------------
# run_headless --record-dir → replay round-trip
# ---------------------------------------------------------------------------


def _record_one(tmp_path: Path) -> Path:
    rec_dir = tmp_path / "rec"
    rec_dir.mkdir()
    cp = _run(
        "run_headless.py",
        "--factory", FACTORY_SPEC,
        "--seed", "42",
        "--difficulty", "0.5",
        "--record-dir", str(rec_dir),
        "--out", str(tmp_path / "metrics.json"),
        "--quiet",
    )
    assert cp.returncode == 0, cp.stderr
    files = list(rec_dir.iterdir())
    assert len(files) == 1, f"expected one recording, got {files}"
    rec = files[0]
    assert rec.name == "seed_42.json.gz"
    return rec


def test_e2e_replay_headless_roundtrip(tmp_path):
    rec = _record_one(tmp_path)
    out = tmp_path / "replay_metrics.json"
    cp = _run(
        "replay.py",
        "--factory", FACTORY_SPEC,
        str(rec),
        "--headless",
        "--out", str(out),
    )
    assert cp.returncode == 0, cp.stderr
    env = json.loads(out.read_text(encoding="utf-8"))
    assert env["seed"] == 42
    assert env["result"] in ("REPLAY_DONE", "DONE")
    assert env["duration_frames"] >= 1


def _record_one_plain_json(tmp_path: Path) -> Path:
    """Make a plain-JSON recording (writable in place) using tools_lib in-proc.

    The CLI defaults to ``.json.gz`` which we cannot easily mutate field-wise;
    use the library helper for the drift fixture so we can hand-edit the file.
    """
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from tests._mock_factory import MockFactory  # type: ignore
        from toy_engine.tools_lib import run_single_headless
    finally:
        sys.path.remove(str(REPO_ROOT))

    factory = MockFactory(max_frames=8)
    rec_path = tmp_path / "rec.json"
    run_single_headless(
        factory,
        seed=42,
        difficulty=0.5,
        max_sim_seconds=10.0,
        record_path=str(rec_path),
    )
    assert rec_path.exists()
    return rec_path


def _drift(rec_path: Path) -> None:
    data = json.loads(rec_path.read_text(encoding="utf-8"))
    data["config"]["difficulty"] = float(data["config"]["difficulty"]) + 0.25
    rec_path.write_text(json.dumps(data), encoding="utf-8")


def test_e2e_replay_drift_without_force_fails(tmp_path):
    rec = _record_one_plain_json(tmp_path)
    _drift(rec)
    cp = _run(
        "replay.py",
        "--factory", FACTORY_SPEC,
        str(rec),
        "--headless",
        "--out", str(tmp_path / "m.json"),
    )
    assert cp.returncode != 0
    assert "ConfigDriftError" in cp.stderr


def test_e2e_replay_drift_with_force_succeeds(tmp_path):
    rec = _record_one_plain_json(tmp_path)
    _drift(rec)
    out = tmp_path / "m.json"
    cp = _run(
        "replay.py",
        "--factory", FACTORY_SPEC,
        str(rec),
        "--headless",
        "--force",
        "--out", str(out),
    )
    assert cp.returncode == 0, cp.stderr
    env = json.loads(out.read_text(encoding="utf-8"))
    assert env["seed"] == 42


# ---------------------------------------------------------------------------
# param_sweep
# ---------------------------------------------------------------------------


def test_e2e_param_sweep_csv_header_and_rows(tmp_path):
    out = tmp_path / "sweep.csv"
    cp = _run(
        "param_sweep.py",
        "--factory", FACTORY_SPEC,
        "--difficulty", "0.3,0.7",
        "--seeds", "2",
        "--out", str(out),
        "--quiet",
    )
    assert cp.returncode == 0, cp.stderr
    assert out.exists()

    reader = csv.DictReader(io.StringIO(out.read_text(encoding="utf-8")))
    rows = list(reader)
    assert len(rows) == 2
    assert [float(r["difficulty"]) for r in rows] == [0.3, 0.7]
    expected_cols = {
        "difficulty", "n_runs", "seed_base",
        "fail_rate", "victory_rate", "timeout_rate",
        "entered_boss_rate", "counter_kill_rate",
        "duration_s_mean", "duration_s_p50", "duration_s_p95",
        "headless_wall_s_mean",
        "first_growth_time_mean", "starvation_ratio_mean",
        "near_miss_count_mean", "boss_ttk_mean",
    }
    assert expected_cols <= set(reader.fieldnames or [])
    assert all(int(r["n_runs"]) == 2 for r in rows)
