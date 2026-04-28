"""tests/fish/test_metrics_adapter.py — envelope schema + JSON serializability."""

from __future__ import annotations

import json

import pytest

from toy_engine.input import InputFrame
from toy_engine.loop import GameLoop
from toy_engine.metrics import MetricsCollector, TOP_LEVEL_KEYS
from toy_engine.rng import SeededRng

from fish.ai.bot_player import BotInput
from fish.ai.boss_ai import BossState
from fish.config.constants import BOSS_TIER, DT
from fish.factory import FishGameFactory
from fish.systems.level_generator import LevelGenerator
from fish.world import World


def _run_one(seed=0, difficulty=0.5, max_sim_seconds=30.0):
    factory = FishGameFactory()
    cfg = factory.make_level_config(seed=seed, difficulty=difficulty)
    world = factory.make_world(level_config=cfg, seed=seed)
    metrics = MetricsCollector()
    metrics.set_scalar("seed", seed, top_level=True)
    metrics.set_scalar("difficulty", difficulty, top_level=True)
    factory.bind_metrics(world, metrics)
    bot = BotInput(SeededRng(seed).spawn("bot"))
    loop = GameLoop(world, bot, dt=DT, max_sim_seconds=max_sim_seconds)
    loop.run_headless()
    return world, metrics


class TestEnvelopeSchema:
    def test_top_level_keys_present(self):
        _, metrics = _run_one()
        env = metrics.final_report()
        for key in TOP_LEVEL_KEYS:
            assert key in env, f"missing top-level key {key}"

    def test_metrics_segment_has_5_metrics(self):
        _, metrics = _run_one()
        env = metrics.final_report()
        assert "metrics" in env
        for name in ("fail_rate", "first_growth_time", "starvation_ratio",
                     "near_miss_count", "boss_ttk"):
            assert name in env["metrics"], f"missing metrics.{name}"

    def test_engine_extras_present(self):
        _, metrics = _run_one()
        env = metrics.final_report()
        for key in ("engine_version", "duration_frames", "events", "extra"):
            assert key in env

    def test_result_in_known_set(self):
        _, metrics = _run_one()
        env = metrics.final_report()
        assert env["result"] in ("DEAD", "VICTORY", "TIMEOUT")

    def test_fail_rate_is_null_in_single_run(self):
        _, metrics = _run_one()
        env = metrics.final_report()
        assert env["metrics"]["fail_rate"] is None

    def test_envelope_json_serializable(self):
        _, metrics = _run_one()
        env = metrics.final_report()
        s = json.dumps(env, allow_nan=False)
        assert isinstance(s, str) and len(s) > 0


class TestDerivedMetrics:
    def test_starvation_ratio_in_unit_interval(self):
        _, metrics = _run_one()
        env = metrics.final_report()
        v = env["metrics"]["starvation_ratio"]
        assert v is None or 0.0 <= v <= 1.0

    def test_near_miss_count_non_negative_int(self):
        _, metrics = _run_one()
        env = metrics.final_report()
        v = env["metrics"]["near_miss_count"]
        assert isinstance(v, int) and v >= 0

    def test_duration_s_matches_world(self):
        world, metrics = _run_one()
        env = metrics.final_report()
        assert abs(env["duration_s"] - world.elapsed_s) < 1e-6


class TestEQ12HookInvoked:
    """证明 bind_metrics 实际接管了 metrics.tick：duration_frames > 0。"""

    def test_duration_frames_positive(self):
        _, metrics = _run_one()
        env = metrics.final_report()
        assert env["duration_frames"] > 0

    def test_entered_boss_event_recorded_by_frame_hook(self):
        factory = FishGameFactory()
        cfg = factory.make_level_config(seed=0, difficulty=0.5)
        world = factory.make_world(level_config=cfg, seed=0)
        metrics = MetricsCollector()
        factory.bind_metrics(world, metrics)

        world.spawn_boss()
        world.step(DT, InputFrame())

        env = metrics.final_report()
        assert env["duration_frames"] == 1
        assert env["events"]["entered_boss"]["count"] == 1

    def test_counter_kill_event_recorded_from_world_listener(self):
        factory = FishGameFactory()
        cfg = factory.make_level_config(seed=0, difficulty=0.5)
        world = factory.make_world(level_config=cfg, seed=0)
        metrics = MetricsCollector()
        factory.bind_metrics(world, metrics)

        boss = world.spawn_boss()
        world.on_boss_killed(boss)

        env = metrics.final_report()
        assert env["events"]["boss_killed"]["count"] == 1
        assert env["events"]["counter_kill"]["count"] == 1


class TestDeathCauseSchema:
    def test_fish_death_cause_uses_tier_name(self):
        factory = FishGameFactory()
        cfg = factory.make_level_config(seed=0, difficulty=0.5)
        world = factory.make_world(level_config=cfg, seed=0)
        metrics = MetricsCollector()
        factory.bind_metrics(world, metrics)

        world.stats["death_cause_tier"] = 4
        world._metrics_listener.write_envelope_before_finish(world)  # type: ignore[attr-defined]

        assert metrics.final_report()["death_cause"] == "Barracuda"

    def test_boss_death_cause_distinguishes_charge(self):
        factory = FishGameFactory()
        cfg = factory.make_level_config(seed=0, difficulty=0.5)
        world = factory.make_world(level_config=cfg, seed=0)
        metrics = MetricsCollector()
        factory.bind_metrics(world, metrics)

        boss = world.spawn_boss()
        boss.state = BossState.CHARGE
        world.stats["death_cause_tier"] = BOSS_TIER
        world._metrics_listener.write_envelope_before_finish(world)  # type: ignore[attr-defined]

        assert metrics.final_report()["death_cause"] == "Boss_charge"


class TestMetricsListenerIsolation:
    def test_frame_end_exception_warns_and_does_not_break_world(self, monkeypatch):
        factory = FishGameFactory()
        cfg = factory.make_level_config(seed=0, difficulty=0.5)
        world = factory.make_world(level_config=cfg, seed=0)
        metrics = MetricsCollector()
        factory.bind_metrics(world, metrics)

        def boom(_dt):
            raise RuntimeError("boom")

        monkeypatch.setattr(world._metrics_listener, "on_frame_end", boom)  # type: ignore[attr-defined]

        with pytest.warns(RuntimeWarning, match="frame-end"):
            world.step(DT, InputFrame())
        assert world.frame_count == 1

    def test_finish_exception_warns_and_keeps_fallback_result(self, monkeypatch):
        factory = FishGameFactory()
        cfg = factory.make_level_config(seed=0, difficulty=0.5)
        world = factory.make_world(level_config=cfg, seed=0)
        metrics = MetricsCollector()
        factory.bind_metrics(world, metrics)

        def boom(_world):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            world._metrics_listener,  # type: ignore[attr-defined]
            "write_envelope_before_finish",
            boom,
        )

        with pytest.warns(RuntimeWarning, match="finalizing envelope"):
            metrics.finish("TIMEOUT")
        assert metrics.final_report()["result"] == "TIMEOUT"
