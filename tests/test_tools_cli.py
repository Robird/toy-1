"""Tests for the three CLI scripts under ``tools/`` (08-tools.md §3-§6)."""

from __future__ import annotations

import csv
import gzip
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from tools import param_sweep, replay, run_headless


_FACTORY_FLAG = ["--factory", "tests._mock_factory:DET_FACTORY"]
_NON_DET_FLAG = ["--factory", "tests._mock_factory:NON_DET_FACTORY"]


# ---------------------------------------------------------------------------
# run_headless: single + batch + JSON IO
# ---------------------------------------------------------------------------


def _run_main(main_fn, argv: list[str]):
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main_fn(argv)
    return rc, out.getvalue(), err.getvalue()


def test_run_headless_single_to_stdout():
    rc, stdout, _stderr = _run_main(
        run_headless.main,
        _FACTORY_FLAG
        + [
            "--seed",
            "0",
            "--difficulty",
            "0.4",
            "--max-sim-seconds",
            "0.05",
            "--out",
            "-",
            "--quiet",
        ],
    )
    assert rc == 0
    payload = json.loads(stdout)
    assert payload["seed"] == 0
    assert payload["difficulty"] == 0.4
    assert payload["result"] in ("DONE", "TIMEOUT")
    assert "metrics" in payload
    assert "events" in payload


def test_run_headless_single_to_file(tmp_path):
    out = tmp_path / "out.json"
    rc, _stdout, _stderr = _run_main(
        run_headless.main,
        _FACTORY_FLAG
        + [
            "--seed",
            "1",
            "--difficulty",
            "0.5",
            "--max-sim-seconds",
            "0.05",
            "--out",
            str(out),
            "--quiet",
        ],
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["seed"] == 1


def test_run_headless_out_parent_missing(tmp_path):
    bad = tmp_path / "no_such_dir" / "out.json"
    with pytest.raises(SystemExit):
        run_headless.main(
            _FACTORY_FLAG
            + [
                "--seed",
                "0",
                "--difficulty",
                "0.5",
                "--max-sim-seconds",
                "0.05",
                "--out",
                str(bad),
                "--quiet",
            ]
        )


def test_run_headless_rejects_difficulty_out_of_range():
    with pytest.raises(SystemExit):
        run_headless.main(
            _FACTORY_FLAG
            + [
                "--seed",
                "0",
                "--difficulty",
                "1.5",
                "--max-sim-seconds",
                "0.05",
                "--quiet",
            ]
        )


def test_run_headless_batch_aggregates(tmp_path):
    rc, stdout, _stderr = _run_main(
        run_headless.main,
        _FACTORY_FLAG
        + [
            "--seeds",
            "3",
            "--seed-base",
            "10",
            "--difficulty",
            "0.5",
            "--max-sim-seconds",
            "0.05",
            "--quiet",
        ],
    )
    assert rc == 0
    payload = json.loads(stdout)
    assert payload["n_runs"] == 3
    assert payload["difficulty"] == 0.5
    assert payload["seeds"] == [10, 11, 12]
    assert "aggregate" in payload
    assert {"fail_rate", "victory_rate", "timeout_rate", "duration_s"} <= set(
        payload["aggregate"].keys()
    )
    assert len(payload["per_run"]) == 3


def test_run_headless_batch_with_record_dir(tmp_path):
    rec_dir = tmp_path / "rec"
    rec_dir.mkdir()
    rc, _stdout, _stderr = _run_main(
        run_headless.main,
        _FACTORY_FLAG
        + [
            "--seeds",
            "2",
            "--seed-base",
            "0",
            "--difficulty",
            "0.5",
            "--max-sim-seconds",
            "0.05",
            "--record-dir",
            str(rec_dir),
            "--quiet",
        ],
    )
    assert rc == 0
    files = sorted(p.name for p in rec_dir.iterdir())
    assert files == ["seed_0.json.gz", "seed_1.json.gz"]


# ---------------------------------------------------------------------------
# --determinism-check
# ---------------------------------------------------------------------------


def test_determinism_check_pass():
    rc, stdout, stderr = _run_main(
        run_headless.main,
        _FACTORY_FLAG
        + [
            "--determinism-check",
            "1",
            "--seed-base",
            "5",
            "--difficulty",
            "0.5",
            "--quiet",
        ],
    )
    assert rc == 0, f"stderr={stderr}"
    payload = json.loads(stdout)
    assert payload == {"ok": True, "n_seeds": 1, "frames_per_run": 3600}


def test_determinism_check_detects_break():
    rc, _stdout, stderr = _run_main(
        run_headless.main,
        _NON_DET_FLAG
        + [
            "--determinism-check",
            "1",
            "--seed-base",
            "0",
            "--difficulty",
            "0.5",
            "--quiet",
        ],
    )
    assert rc == 1
    assert "DETERMINISM_MISMATCH" in stderr
    assert "seed=0" in stderr
    assert "config_hash=sha256:" in stderr


# ---------------------------------------------------------------------------
# param_sweep
# ---------------------------------------------------------------------------


def test_param_sweep_csv_to_stdout():
    rc, stdout, _stderr = _run_main(
        param_sweep.main,
        _FACTORY_FLAG
        + [
            "--difficulty",
            "0.3,0.5,0.7",
            "--seeds",
            "2",
            "--max-sim-seconds",
            "0.05",
            "--quiet",
        ],
    )
    assert rc == 0
    reader = csv.DictReader(io.StringIO(stdout))
    rows = list(reader)
    assert len(rows) == 3
    diffs = [float(r["difficulty"]) for r in rows]
    assert diffs == [0.3, 0.5, 0.7]
    # Fixed columns from 08-tools.md §4 must all be present
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
    # n_runs filled correctly
    assert all(int(r["n_runs"]) == 2 for r in rows)


def test_param_sweep_csv_to_file(tmp_path):
    out = tmp_path / "sweep.csv"
    rc, _stdout, _stderr = _run_main(
        param_sweep.main,
        _FACTORY_FLAG
        + [
            "--difficulty",
            "0.5",
            "--seeds",
            "2",
            "--max-sim-seconds",
            "0.05",
            "--out",
            str(out),
            "--quiet",
        ],
    )
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "difficulty" in text.splitlines()[0]
    assert len(text.strip().splitlines()) == 2  # header + 1 row


def test_param_sweep_rejects_bad_difficulty():
    with pytest.raises(SystemExit):
        param_sweep.main(
            _FACTORY_FLAG
            + [
                "--difficulty",
                "0.3,banana",
                "--seeds",
                "2",
                "--max-sim-seconds",
                "0.05",
                "--quiet",
            ]
        )


def test_param_sweep_rejects_difficulty_out_of_range():
    with pytest.raises(SystemExit):
        param_sweep.main(
            _FACTORY_FLAG
            + [
                "--difficulty",
                "0.3,1.5",
                "--seeds",
                "2",
                "--max-sim-seconds",
                "0.05",
                "--quiet",
            ]
        )


def test_param_sweep_extra_metric_column_schema(monkeypatch):
    def fake_load_factory(_spec):
        return object()

    def fake_run_single_headless(_factory, *, seed, difficulty, **_kwargs):
        return (
            {
                "seed": seed,
                "difficulty": difficulty,
                "result": "DONE",
                "duration_s": 1.0,
                "metrics": {"bonus_score": float(seed)},
                "events": {},
            },
            0.01,
        )

    monkeypatch.setattr(param_sweep, "load_factory", fake_load_factory)
    monkeypatch.setattr(param_sweep, "run_single_headless", fake_run_single_headless)

    rc, stdout, _stderr = _run_main(
        param_sweep.main,
        ["--difficulty", "0.5", "--seeds", "2", "--quiet"],
    )
    assert rc == 0
    reader = csv.DictReader(io.StringIO(stdout))
    rows = list(reader)
    assert "extra_bonus_score" in (reader.fieldnames or [])
    assert "extra_bonus_score_mean" not in (reader.fieldnames or [])
    assert rows[0]["extra_bonus_score"] == "0.5"


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def _make_recording(tmp_path: Path) -> Path:
    """Build a recording from a single headless run via tools_lib helper."""
    from toy_engine.tools_lib import run_single_headless
    from tests._mock_factory import MockFactory

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


def test_replay_headless_ok(tmp_path):
    rec_path = _make_recording(tmp_path)
    out = tmp_path / "metrics.json"
    rc, _stdout, _stderr = _run_main(
        replay.main,
        _FACTORY_FLAG
        + [
            str(rec_path),
            "--headless",
            "--out",
            str(out),
        ],
    )
    assert rc == 0
    env = json.loads(out.read_text(encoding="utf-8"))
    assert env["seed"] == 42
    assert env["result"] in ("REPLAY_DONE", "DONE")
    assert env["duration_frames"] == 8


def test_replay_default_is_render_mode(tmp_path, monkeypatch):
    rec_path = _make_recording(tmp_path)
    calls: list[str] = []

    class FakeGameLoop:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            calls.append(f"max_sim_seconds={kwargs['max_sim_seconds']}")

        def run_headless(self):
            calls.append("headless")

        def run_realtime(self):
            calls.append("render")

    monkeypatch.setattr(replay, "GameLoop", FakeGameLoop)
    rc, _stdout, _stderr = _run_main(replay.main, _FACTORY_FLAG + [str(rec_path)])

    assert rc == 0
    assert calls == [f"max_sim_seconds={8 / 60}", "render"]


def test_replay_render_and_headless_mutually_exclusive(tmp_path):
    rec_path = _make_recording(tmp_path)
    with pytest.raises(SystemExit):
        replay.main(
            _FACTORY_FLAG + [str(rec_path), "--render", "--headless"]
        )


def _drift_recording(rec_path: Path) -> None:
    """Mutate the recording file's config so its hash no longer matches."""
    text = rec_path.read_text(encoding="utf-8")
    data = json.loads(text)
    # Change difficulty inside config; config_hash stays untouched → drift
    assert "difficulty" in data["config"]
    data["config"]["difficulty"] = data["config"]["difficulty"] + 0.1
    rec_path.write_text(json.dumps(data), encoding="utf-8")


def test_replay_drift_without_force_returns_2(tmp_path):
    rec_path = _make_recording(tmp_path)
    _drift_recording(rec_path)
    rc, _stdout, stderr = _run_main(
        replay.main,
        _FACTORY_FLAG
        + [
            str(rec_path),
            "--headless",
            "--out",
            str(tmp_path / "m.json"),
        ],
    )
    assert rc == 2
    assert "ConfigDriftError" in stderr


def test_replay_drift_with_force_succeeds(tmp_path, recwarn):
    rec_path = _make_recording(tmp_path)
    _drift_recording(rec_path)
    out = tmp_path / "m.json"
    rc, _stdout, _stderr = _run_main(
        replay.main,
        _FACTORY_FLAG
        + [
            str(rec_path),
            "--headless",
            "--force",
            "--out",
            str(out),
        ],
    )
    assert rc == 0
    env = json.loads(out.read_text(encoding="utf-8"))
    assert env["seed"] == 42
    # The --force path should have warned at least once
    msgs = [str(w.message) for w in recwarn.list]
    assert any("ConfigDriftError" in m for m in msgs)
