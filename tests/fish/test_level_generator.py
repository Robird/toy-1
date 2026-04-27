"""tests/fish/test_level_generator.py — M3-06 LevelGenerator + LevelDirector.

\u8986\u76d6\uff1a
- LevelGenerator \u51b3\u5b9a\u6027\uff08\u540c seed+difficulty \u2192 \u540c LevelConfig\uff09
- LevelGenerator \u591a seed \u4e0b 5 \u6761\u786c\u7ea6\u675f\u5168\u90e8\u6ee1\u8db3
- \u6821\u9a8c\u5931\u8d25\u91cd\u8bd5 \u2192 \u8d85\u9650 raise LevelGenerationError
- LevelDirector \u9636\u6bb5\u5207\u6362\uff08\u8ba1\u65f6\u5668 + \u987a\u5e8f\uff09
- LevelDirector \u5728 BOSS \u9636\u6bb5\u62d1\u5236\u666e\u901a\u9c7c\u5237\u65b0
- get_active_population_target \u5728\u4e0d\u540c\u9636\u6bb5\u8fd4\u56de\u4e0d\u540c\u503c
- World.is_finished \u4ec5\u4f9d game_result\uff08\u88c1\u51b3 #4\uff09
- 30s headless \u8dd1\u4e24\u6b21 snapshot_hash \u5e8f\u5217\u4e00\u81f4\uff08\u51b3\u5b9a\u6027\uff09
- REVENGE \u8d85\u65f6 \u2192 game_result = VICTORY
"""

from __future__ import annotations

import pytest

from toy_engine.input import InputFrame
from toy_engine.rng import SeededRng

from fish.config.constants import (
    BOSS_APPEAR_TIME_RANGE_S,
    DT,
    PHASE_PRESSURE_DURATION_RANGE_S,
    PHASE_TIER4_POPULATION_MAX,
    PHASE_WARMUP_DURATION_RANGE_S,
    Phase,
    REVENGE_PHASE_TIMEOUT_S,
    TIER_GIANT,
    TIMEOUT_S,
)
from fish.systems.level_generator import (
    LevelGenerationError,
    LevelGenerator,
    Violation,
    validate,
)
from fish.world import GameResult, World


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _NullInput:
    def poll(self, world_state):  # noqa: ARG002
        return InputFrame()


def _gen(seed: int = 0, difficulty: float = 0.5):
    return LevelGenerator.generate(seed=seed, difficulty=difficulty, rng=SeededRng(seed))


# ---------------------------------------------------------------------------
# 1. \u51b3\u5b9a\u6027
# ---------------------------------------------------------------------------


class TestLevelGeneratorDeterminism:
    def test_same_seed_difficulty_same_config(self) -> None:
        a = _gen(42, 0.5)
        b = _gen(42, 0.5)
        assert a == b

    def test_different_seed_different_config(self) -> None:
        a = _gen(0, 0.5)
        b = _gen(1, 0.5)
        # \u4e25\u683c\u4e0d\u7b49\uff1aphases / boss \u5747\u91c7\u6837\uff0c\u51e0\u4e4e\u4e0d\u53ef\u80fd\u9047\u5230\u4ec5\u4ec5 seed \u53d8\u53d8\u51fa\u540c\u8868
        assert a != b

    def test_different_difficulty_different_config(self) -> None:
        a = _gen(0, 0.2)
        b = _gen(0, 0.8)
        assert a != b

    def test_returns_independent_objects(self) -> None:
        # frozen=True \u4f46\u5d4c\u5957 dict \u4ecd\u53ef\u53d8\uff1b\u4ed8\u8d39\u4e8e\u7eaa\u5f8b\u3002
        # \u6b64\u5904\u4ec5\u9a8c\u8bc1\u4e24\u6b21\u751f\u6210\u4e0d\u662f\u540c\u4e00\u4e2a\u5f15\u7528\u3002
        a = _gen(42, 0.5)
        b = _gen(42, 0.5)
        assert a is not b


# ---------------------------------------------------------------------------
# 2. \u786c\u7ea6\u675f
# ---------------------------------------------------------------------------


class TestLevelGeneratorConstraints:
    @pytest.mark.parametrize("seed", list(range(40)))
    def test_constraints_on_many_seeds(self, seed: int) -> None:
        cfg = _gen(seed, 0.5)
        violations = validate(cfg)
        assert violations == [], f"seed={seed} got violations={violations}"

    def test_warmup_no_tier3_or_tier4(self) -> None:
        for s in range(20):
            cfg = _gen(s, 0.5)
            warmup = cfg.phases[Phase.WARMUP]
            assert warmup.population_target.get(3, 0) == 0
            assert warmup.population_target.get(4, 0) == 0

    def test_warmup_has_at_least_one_edible(self) -> None:
        # \u73a9\u5bb6\u521d\u59cb tier=0\uff0ccan_eat \u53ea\u80fd\u5403 tier<=1
        for s in range(20):
            cfg = _gen(s, 0.5)
            warmup = cfg.phases[Phase.WARMUP]
            assert warmup.population_target.get(1, 0) >= 1

    def test_tier4_under_cap(self) -> None:
        for s in range(20):
            cfg = _gen(s, 0.9)  # \u9ad8\u96be\u5ea6\u4e5f\u4e0d\u80fd\u8d85\u9650
            for ph_cfg in cfg.phases.values():
                assert (
                    ph_cfg.population_target.get(4, 0)
                    <= PHASE_TIER4_POPULATION_MAX
                )

    def test_boss_appear_time_in_range(self) -> None:
        lo, hi = BOSS_APPEAR_TIME_RANGE_S
        for s in range(20):
            cfg = _gen(s, 0.5)
            assert lo <= cfg.boss.appear_time_s <= hi

    def test_phase_durations_in_range(self) -> None:
        wlo, whi = PHASE_WARMUP_DURATION_RANGE_S
        plo, phi = PHASE_PRESSURE_DURATION_RANGE_S
        for s in range(20):
            cfg = _gen(s, 0.5)
            assert wlo <= cfg.phases[Phase.WARMUP].duration_s <= whi
            assert plo <= cfg.phases[Phase.PRESSURE].duration_s <= phi

    def test_boss_and_revenge_have_nonzero_fallback_duration(self) -> None:
        cfg = _gen(0, 0.5)
        assert cfg.phases[Phase.BOSS].duration_s > 0.0
        assert cfg.phases[Phase.REVENGE].duration_s > 0.0

    def test_validate_rejects_pressure_without_reachable_edible_target(self) -> None:
        cfg = _gen(0, 0.5)
        cfg.phases[Phase.PRESSURE].population_target = {1: 0, 2: 0, 3: 0, 4: 1}
        violations = validate(cfg)
        assert any(
            v.code == "C1" and "PRESSURE" in v.message and "max edible tier" in v.message
            for v in violations
        )

    def test_validate_rejects_nonfinite_numbers_with_context(self) -> None:
        cfg = _gen(0, 0.5)
        cfg.phases[Phase.WARMUP].duration_s = float("nan")
        cfg.phases[Phase.PRESSURE].population_target[2] = float("inf")
        cfg.phases[Phase.BOSS].spawn_rate[1] = float("nan")
        cfg.boss.appear_time_s = float("inf")
        messages = [v.message for v in validate(cfg)]
        assert any("WARMUP" in m and "duration_s" in m for m in messages)
        assert any("PRESSURE" in m and "population_target[2]" in m for m in messages)
        assert any("BOSS" in m and "spawn_rate[1]" in m for m in messages)
        assert any("boss.appear_time_s" in m and "not finite" in m for m in messages)

    def test_validate_c5_reports_jump_context_and_allowed_value(self) -> None:
        cfg = _gen(0, 0.5)
        cfg.phases[Phase.WARMUP].population_target[1] = 1
        cfg.phases[Phase.PRESSURE].population_target[1] = 8
        violations = validate(cfg)
        assert any(
            v.code == "C5"
            and "WARMUP->PRESSURE" in v.message
            and "allowed <= 3" in v.message
            for v in violations
        )


# ---------------------------------------------------------------------------
# 3. \u91cd\u8bd5 / \u62a5\u9519
# ---------------------------------------------------------------------------


class TestLevelGeneratorRetries:
    def test_raises_when_validate_always_fails(self, monkeypatch) -> None:
        # \u5f3a\u5236 validate \u603b\u662f\u8fd4\u56de\u4e00\u6761 violation\uff0c\u9a8c\u8bc1\u8d85 N \u6b21 raise
        from fish.systems import level_generator as mod

        def _always_fail(cfg):  # noqa: ARG001
            return [Violation("CX", "forced failure for test")]

        monkeypatch.setattr(mod, "validate", _always_fail)
        with pytest.raises(LevelGenerationError) as excinfo:
            LevelGenerator.generate(seed=0, difficulty=0.5, rng=SeededRng(0))
        assert excinfo.value.attempts == LevelGenerator.MAX_RETRIES
        assert len(excinfo.value.last_violations) >= 1

    def test_retry_counter_advances_until_validation_passes(self, monkeypatch) -> None:
        from fish.systems import level_generator as mod

        calls = []

        def _fail_twice(cfg):
            calls.append(cfg)
            if len(calls) <= 2:
                return [Violation("CX", f"forced failure #{len(calls)}")]
            return []

        monkeypatch.setattr(mod, "validate", _fail_twice)
        cfg = LevelGenerator.generate(seed=0, difficulty=0.5, rng=SeededRng(0))
        assert cfg.seed == 0
        assert len(calls) == 3

    def test_succeeds_on_first_attempt_in_normal_case(self) -> None:
        # \u6b63\u5e38\u91c7\u6837 0 \u96be\u5ea6\u4e0b\uff0cdefault \u91c7\u6837\u5728\u9996\u6b21\u5c31\u8fc7\uff0c\u4e0d\u4f1a\u91cd\u8bd5
        cfg = _gen(0, 0.5)
        assert validate(cfg) == []


# ---------------------------------------------------------------------------
# 4. LevelDirector \u9636\u6bb5\u5207\u6362
# ---------------------------------------------------------------------------


class TestLevelDirectorTransitions:
    def _make_world(self, seed: int = 0) -> World:
        cfg = _gen(seed, 0.5)
        return World(cfg, SeededRng(seed=cfg.seed))

    def test_initial_phase_is_warmup(self) -> None:
        w = self._make_world()
        assert w.director.current_phase == Phase.WARMUP
        assert w.director.phase_elapsed_s == 0.0

    def test_warmup_to_pressure_by_duration(self) -> None:
        w = self._make_world()
        warmup_dur = w.config.phases[Phase.WARMUP].duration_s
        # \u8dd1\u8db3\u591f\u5e27\u8d85\u8fc7 warmup duration
        n = int(warmup_dur / DT) + 2
        for _ in range(n):
            w.step(DT, InputFrame())
            if w.director.current_phase != Phase.WARMUP:
                break
        assert w.director.current_phase == Phase.PRESSURE
        # \u5207\u6362\u540e phase_elapsed_s \u91cd\u7f6e
        assert w.director.phase_elapsed_s < warmup_dur

    def test_pressure_to_boss_by_player_tier(self) -> None:
        w = self._make_world()
        # 手动推进到 PRESSURE
        w.director.current_phase = Phase.PRESSURE
        w.director.phase_elapsed_s = 0.0
        w.player.tier = 2  # 触发「player.tier >= 2 → BOSS」
        w.director.step(w, DT)
        assert w.director.current_phase == Phase.BOSS

    def test_pressure_to_boss_by_boss_appear_time_after_pressure_duration(self) -> None:
        w = self._make_world()
        w.director.current_phase = Phase.PRESSURE
        w.director.phase_elapsed_s = w.config.phases[Phase.PRESSURE].duration_s
        pressure_dur = w.config.phases[Phase.PRESSURE].duration_s
        assert pressure_dur > 0.0
        w.elapsed_s = w.config.boss.appear_time_s - DT * 0.5
        w.director.step(w, DT)
        assert w.director.current_phase == Phase.BOSS

    def test_pressure_duration_alone_does_not_enter_boss_before_appear_time(self) -> None:
        w = self._make_world()
        w.director.current_phase = Phase.PRESSURE
        w.director.phase_elapsed_s = w.config.phases[Phase.PRESSURE].duration_s
        w.elapsed_s = w.config.boss.appear_time_s - DT * 2.0
        w.player.tier = 0
        w.director.step(w, DT)
        assert w.director.current_phase == Phase.PRESSURE

    def test_boss_to_revenge_by_player_tier_giant(self) -> None:
        w = self._make_world()
        w.director.current_phase = Phase.BOSS
        w.director.phase_elapsed_s = 0.0
        w.player.tier = TIER_GIANT
        w.director.step(w, DT)
        assert w.director.current_phase == Phase.REVENGE

    def test_revenge_timeout_sets_victory(self) -> None:
        w = self._make_world()
        w.director.current_phase = Phase.REVENGE
        w.director.phase_elapsed_s = 0.0
        # \u8dd1\u8d85\u8fc7 REVENGE \u8d85\u65f6
        n = int(REVENGE_PHASE_TIMEOUT_S / DT) + 2
        for _ in range(n):
            w.director.step(w, DT)
            if w.game_result is not None:
                break
        assert w.game_result == GameResult.VICTORY

    def test_global_timeout_sets_timeout_result(self) -> None:
        w = self._make_world()
        # \u76f4\u63a5\u628a\u4eff\u771f\u65f6\u95f4\u63a8\u5230 TIMEOUT_S \u9644\u8fd1
        w.elapsed_s = TIMEOUT_S
        w.director.step(w, DT)
        assert w.game_result == GameResult.TIMEOUT

    def test_transition_log_records_phase_changes(self) -> None:
        w = self._make_world()
        # \u624b\u52a8\u63a8\u8fdb\u5230 PRESSURE \u89e6\u53d1\u4e00\u6b21\u5207\u6362
        w.player.tier = 2
        w.director.current_phase = Phase.PRESSURE
        w.director.phase_elapsed_s = 0.0
        w.director.step(w, DT)
        log = w.director.transition_log
        assert len(log) >= 1
        at_s, old, new = log[-1]
        assert old == Phase.PRESSURE
        assert new == Phase.BOSS


# ---------------------------------------------------------------------------
# 5. get_active_population_target
# ---------------------------------------------------------------------------


class TestGetActivePopulationTarget:
    def _world(self) -> World:
        cfg = _gen(0, 0.5)
        return World(cfg, SeededRng(seed=cfg.seed))

    def test_warmup_returns_warmup_target(self) -> None:
        w = self._world()
        assert (
            w.director.get_active_population_target()
            == w.config.phases[Phase.WARMUP].population_target
        )

    def test_pressure_returns_pressure_target(self) -> None:
        w = self._world()
        w.director.current_phase = Phase.PRESSURE
        assert (
            w.director.get_active_population_target()
            == w.config.phases[Phase.PRESSURE].population_target
        )

    def test_boss_returns_zero_target(self) -> None:
        w = self._world()
        w.director.current_phase = Phase.BOSS
        target = w.director.get_active_population_target()
        assert all(v == 0 for v in target.values())

    def test_revenge_returns_revenge_target(self) -> None:
        w = self._world()
        w.director.current_phase = Phase.REVENGE
        assert (
            w.director.get_active_population_target()
            == w.config.phases[Phase.REVENGE].population_target
        )

    def test_warmup_pressure_targets_differ(self) -> None:
        w = self._world()
        w_target = dict(w.director.get_active_population_target())
        w.director.current_phase = Phase.PRESSURE
        p_target = dict(w.director.get_active_population_target())
        assert w_target != p_target


# ---------------------------------------------------------------------------
# 6. Spawner \u5728 BOSS \u9636\u6bb5\u4e0d\u5237\u666e\u901a\u9c7c
# ---------------------------------------------------------------------------


class TestSpawnerSuppressedInBoss:
    def test_boss_phase_does_not_spawn_new_fish(self) -> None:
        cfg = _gen(0, 0.5)
        w = World(cfg, SeededRng(seed=cfg.seed))
        # \u624b\u52a8\u8fdb\u5165 BOSS \u9636\u6bb5\u3001\u6e05\u7a7a\u5df2\u5237\u9c7c
        w.director.current_phase = Phase.BOSS
        w.director.phase_elapsed_s = 0.0
        w.fishes.clear()
        w.entities = [w.player]

        # \u8dd1 5s\uff0c\u8db3\u591f\u8ba9 spawner \u68c0\u67e5\u591a\u6b21\uff083s/0.5s = 6 \u6b21\uff09
        for _ in range(int(5.0 / DT)):
            w.step(DT, InputFrame())
            # \u8df3\u8fc7\u9636\u6bb5\u53ef\u80fd\u88ab\u5176\u4ed6\u6761\u4ef6\u63a8\u8fdb\u5230\u522b\u5904\u7684\u60c5\u51b5
            if w.director.current_phase != Phase.BOSS:
                # \u5f3a\u5236\u62c9\u56de
                w.director.current_phase = Phase.BOSS
        assert w.fishes == []

    def test_revenge_phase_resumes_spawning_and_refreshes_cached_target(self) -> None:
        cfg = _gen(0, 0.5)
        w = World(cfg, SeededRng(seed=cfg.seed))
        w.director.current_phase = Phase.BOSS
        w.director.phase_elapsed_s = 0.0
        w.fishes.clear()
        w.entities = [w.player]

        # BOSS -> REVENGE 发生在 director，本帧 spawner 应立即读取 REVENGE target，
        # 不再沿用 BOSS 阶段的全 0 target。
        w.player.tier = TIER_GIANT
        w.step(DT, InputFrame())
        assert w.director.current_phase == Phase.REVENGE
        assert len(w.fishes) > 0


# ---------------------------------------------------------------------------
# 7. World.is_finished \u88c1\u51b3 #4 \u843d\u5b9e
# ---------------------------------------------------------------------------


class TestIsFinishedRulingFour:
    def test_is_finished_only_via_game_result(self) -> None:
        cfg = _gen(0, 0.5)
        w = World(cfg, SeededRng(seed=cfg.seed))
        # elapsed_s \u8d85\u8fc7\u4efb\u610f\u9636\u6bb5\u65f6\u957f\u4f46 game_result=None \u2192 \u4e0d\u5b8c\u7ed3
        w.elapsed_s = 1e6
        assert w.is_finished() is False
        w.game_result = GameResult.DEAD
        assert w.is_finished() is True

    def test_snapshot_phase_fields_are_string_and_hash_stable(self) -> None:
        cfg = _gen(0, 0.5)
        a = World(cfg, SeededRng(seed=cfg.seed))
        b = World(cfg, SeededRng(seed=cfg.seed))
        snap = a.snapshot()
        assert snap["phase"] == Phase.WARMUP.name
        assert isinstance(snap["phase_elapsed_s"], float)
        assert a.snapshot_hash() == b.snapshot_hash()


# ---------------------------------------------------------------------------
# 8. \u51b3\u5b9a\u6027\uff1a30s headless \u8dd1\u4e24\u6b21 snapshot_hash \u5e8f\u5217\u4e00\u81f4
# ---------------------------------------------------------------------------


class TestHeadlessDeterminism:
    def _run(self, seed: int, frames: int) -> list[str]:
        cfg = LevelGenerator.generate(
            seed=seed, difficulty=0.5, rng=SeededRng(seed)
        )
        w = World(cfg, SeededRng(seed=cfg.seed))
        hashes: list[str] = []
        for _ in range(frames):
            w.step(DT, InputFrame())
            hashes.append(w.snapshot_hash())
            if w.is_finished():
                break
        return hashes

    def test_30s_two_runs_match(self) -> None:
        frames = int(30.0 / DT)
        a = self._run(seed=7, frames=frames)
        b = self._run(seed=7, frames=frames)
        assert a == b
        assert len(a) > 0

    def test_different_seed_diverges(self) -> None:
        frames = int(5.0 / DT)
        a = self._run(seed=7, frames=frames)
        b = self._run(seed=11, frames=frames)
        assert a != b
