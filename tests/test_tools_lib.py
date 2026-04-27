"""Tests for ``toy_engine.tools_lib`` (08-tools.md §2 / §3)."""

from __future__ import annotations

import os

import pytest

from toy_engine.tools_lib import (
    DEFAULT_FACTORY_SPEC,
    FactoryResolutionError,
    GameFactory,
    aggregate_runs,
    load_factory,
    run_single_headless,
)
from tests._mock_factory import DET_FACTORY, MockFactory


# ---------------------------------------------------------------------------
# GameFactory protocol compliance
# ---------------------------------------------------------------------------


def test_game_factory_protocol_runtime_checkable():
    assert isinstance(MockFactory(), GameFactory)


def test_game_factory_rejects_non_factory():
    class NotAFactory:
        pass

    assert not isinstance(NotAFactory(), GameFactory)


# ---------------------------------------------------------------------------
# load_factory resolution priority: CLI > env > default
# ---------------------------------------------------------------------------


def test_load_factory_explicit_spec_wins():
    f = load_factory("tests._mock_factory:DET_FACTORY")
    assert f is DET_FACTORY


def test_load_factory_env_var(monkeypatch):
    monkeypatch.setenv("TOY_ENGINE_GAME_FACTORY", "tests._mock_factory:DET_FACTORY")
    f = load_factory(None)
    assert f is DET_FACTORY


def test_load_factory_env_overridden_by_explicit(monkeypatch):
    monkeypatch.setenv("TOY_ENGINE_GAME_FACTORY", "tests._mock_factory:NON_DET_FACTORY")
    f = load_factory("tests._mock_factory:DET_FACTORY")
    assert f is DET_FACTORY


def test_load_factory_default_spec_constant():
    assert DEFAULT_FACTORY_SPEC == "fish.__main__:FISH_FACTORY"


def test_load_factory_bad_spec_format():
    with pytest.raises(FactoryResolutionError):
        load_factory("no_colon_here")


def test_load_factory_missing_attr():
    with pytest.raises(FactoryResolutionError):
        load_factory("tests._mock_factory:NO_SUCH_NAME")


def test_load_factory_missing_module():
    with pytest.raises(FactoryResolutionError):
        load_factory("nonexistent_module_xyz:foo")


# ---------------------------------------------------------------------------
# run_single_headless
# ---------------------------------------------------------------------------


def test_run_single_headless_basic():
    factory = MockFactory(max_frames=12)
    env, wall = run_single_headless(
        factory,
        seed=7,
        difficulty=0.4,
        max_sim_seconds=10.0,
    )
    assert env["seed"] == 7
    assert env["difficulty"] == 0.4
    assert env["result"] == "DONE"
    assert env["duration_frames"] == 12
    assert wall >= 0.0


def test_run_single_headless_timeout_when_world_never_finishes():
    factory = MockFactory(max_frames=None)
    env, _ = run_single_headless(
        factory,
        seed=1,
        difficulty=0.5,
        max_sim_seconds=0.05,  # 3 frames at 1/60
    )
    assert env["result"] == "TIMEOUT"
    assert env["duration_frames"] >= 3


def test_run_single_headless_writes_recording(tmp_path):
    factory = MockFactory(max_frames=8)
    rec_path = tmp_path / "rec.json"
    env, _ = run_single_headless(
        factory,
        seed=3,
        difficulty=0.5,
        max_sim_seconds=10.0,
        record_path=str(rec_path),
    )
    assert env["result"] == "DONE"
    assert rec_path.exists()
    # Recording loadable
    from toy_engine.recorder import Recorder

    rec = Recorder.load(rec_path)
    assert rec.seed == 3
    assert len(rec.frames) == 8


def test_run_single_headless_uses_bot():
    factory = MockFactory(max_frames=4)
    env, _ = run_single_headless(
        factory,
        seed=0,
        difficulty=0.5,
        bot_name="heuristic",
        max_sim_seconds=10.0,
    )
    assert env["result"] == "DONE"


def test_run_single_headless_unknown_bot_raises():
    factory = MockFactory(max_frames=4)
    with pytest.raises(ValueError):
        run_single_headless(
            factory,
            seed=0,
            difficulty=0.5,
            bot_name="banana",
            max_sim_seconds=10.0,
        )


def test_run_single_headless_rejects_non_steppable():
    class BadFactory(MockFactory):
        def make_world(self, *, level_config, seed):  # noqa: ARG002
            return object()

    with pytest.raises(TypeError):
        run_single_headless(
            BadFactory(),
            seed=0,
            difficulty=0.5,
            max_sim_seconds=1.0,
        )


# ---------------------------------------------------------------------------
# aggregate_runs (08-tools.md §3.2 schema)
# ---------------------------------------------------------------------------


def test_aggregate_runs_shape():
    per_run = [
        {
            "seed": 0,
            "result": "VICTORY",
            "duration_s": 30.0,
            "metrics": {"first_growth_time": 5.0, "near_miss_count": 10},
            "events": {"ate_fish": {"count": 3}},
        },
        {
            "seed": 1,
            "result": "DEAD",
            "duration_s": 20.0,
            "metrics": {"first_growth_time": 7.0, "near_miss_count": 4},
            "events": {"ate_fish": {"count": 1}},
        },
        {
            "seed": 2,
            "result": "TIMEOUT",
            "duration_s": 60.0,
            "metrics": {"first_growth_time": 6.0},
            "events": {},
        },
    ]
    wall_times = [0.1, 0.2, 0.3]
    agg = aggregate_runs(per_run, wall_times, difficulty=0.5, seeds=[0, 1, 2])

    assert agg["n_runs"] == 3
    assert agg["difficulty"] == 0.5
    assert agg["seeds"] == [0, 1, 2]
    assert agg["wall_time_s"]["total"] == pytest.approx(0.6)
    assert agg["wall_time_s"]["mean_per_run"] == pytest.approx(0.2)

    a = agg["aggregate"]
    assert a["fail_rate"] == pytest.approx(1 / 3)
    assert a["victory_rate"] == pytest.approx(1 / 3)
    assert a["timeout_rate"] == pytest.approx(1 / 3)
    assert "mean" in a["duration_s"]
    assert "p50" in a["duration_s"]
    assert "p95" in a["duration_s"]

    # Union of metric names across runs
    assert "first_growth_time" in a["metrics"]
    assert "near_miss_count" in a["metrics"]
    # near_miss_count appears in only 2 runs; mean over those 2
    assert a["metrics"]["near_miss_count"]["mean"] == pytest.approx(7.0)
    # Events
    assert a["events"]["ate_fish"]["mean_count"] == pytest.approx((3 + 1 + 0) / 3)

    # per_run summaries
    assert len(agg["per_run"]) == 3
    assert agg["per_run"][0] == {
        "seed": 0,
        "result": "VICTORY",
        "duration_s": 30.0,
        "metrics_path": None,
    }


def test_aggregate_runs_empty_input():
    agg = aggregate_runs([], [], difficulty=0.5, seeds=[])
    assert agg["n_runs"] == 0
    assert agg["aggregate"]["fail_rate"] == 0.0
    assert agg["aggregate"]["duration_s"] == {}
