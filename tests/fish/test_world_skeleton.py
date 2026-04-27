"""tests/fish/test_world_skeleton.py — M3-02 World 骨架契约测试。

验证：
1. 构造 + snapshot 字段完整
2. step N 帧推进 frame_count / elapsed_s
3. snapshot_hash 同状态稳定，状态变更后变化
4. is_finished 初始 False，elapsed_s 推到 total_duration 后 True；
   game_result 写入后 True
5. 集成测试：toy_engine.GameLoop（headless）能驱动 World 而不报错，
   证明 Steppable 协议适配（参考 tests/test_loop.py）
"""

from __future__ import annotations

import pytest

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.loop import GameLoop, HashableSteppable, Steppable
from toy_engine.rng import SeededRng

from fish.config.constants import DT, WORLD_H, WORLD_W
from fish.config.level_config import LevelConfig
from fish.world import GameResult, World, _normalize_for_hash


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg() -> LevelConfig:
    return LevelConfig.default()


@pytest.fixture
def world(cfg: LevelConfig) -> World:
    return World(cfg, SeededRng(seed=cfg.seed))


class _NullInput:
    def poll(self, world_state):  # noqa: ARG002
        return InputFrame()


# ---------------------------------------------------------------------------
# 1. 构造 + snapshot 字段完整
# ---------------------------------------------------------------------------


class TestSnapshotShape:
    def test_snapshot_has_required_fields(self, world: World) -> None:
        snap = world.snapshot()
        assert isinstance(snap, dict)
        for key in ("player_pos", "frame_count", "elapsed_s", "entities", "game_result"):
            assert key in snap, f"snapshot missing required field: {key}"

    def test_player_pos_starts_at_world_center(self, world: World) -> None:
        # M3-03：player_pos 来自实际 Player，初始位置为世界中心。
        px, py = world.snapshot()["player_pos"]
        assert (px, py) == (WORLD_W / 2.0, WORLD_H / 2.0)
        assert isinstance(px, float) and isinstance(py, float)

    def test_initial_state(self, world: World) -> None:
        snap = world.snapshot()
        assert snap["frame_count"] == 0
        assert snap["elapsed_s"] == 0.0
        # M3-03: entities 仅含 player 占位；M3-04 起 Spawner 追加鱼。
        assert isinstance(snap["entities"], list)
        assert len(snap["entities"]) == 1
        assert snap["entities"][0]["kind"] == "player"
        assert snap["game_result"] is None


# ---------------------------------------------------------------------------
# 2. step 推进
# ---------------------------------------------------------------------------


class TestStep:
    def test_step_increments_counters(self, world: World) -> None:
        N = 7
        for _ in range(N):
            world.step(DT, InputFrame())
        assert world.frame_count == N
        assert world.elapsed_s == pytest.approx(N * DT)

    def test_step_caches_last_input(self, world: World) -> None:
        ifr = InputFrame(desired_dir=Vec2(1.0, 0.0))
        world.step(DT, ifr)
        assert world.last_input_frame is ifr
        assert world.last_effective_dt == pytest.approx(DT)


# ---------------------------------------------------------------------------
# 3. snapshot_hash 稳定性
# ---------------------------------------------------------------------------


class TestSnapshotHash:
    def test_hash_is_string(self, world: World) -> None:
        h = world.snapshot_hash()
        assert isinstance(h, str) and len(h) > 0

    def test_hash_stable_for_same_state(self, world: World) -> None:
        h1 = world.snapshot_hash()
        h2 = world.snapshot_hash()
        assert h1 == h2

    def test_hash_changes_after_step(self, world: World) -> None:
        h0 = world.snapshot_hash()
        world.step(DT, InputFrame())
        h1 = world.snapshot_hash()
        assert h0 != h1

    def test_hash_changes_when_game_result_set(self, world: World) -> None:
        h0 = world.snapshot_hash()
        world.game_result = GameResult.DEAD
        h1 = world.snapshot_hash()
        assert h0 != h1

    def test_normalize_handles_nested_containers_and_none(self) -> None:
        raw = {
            "tuple": (1.23456789, None),
            "list": [GameResult.DEAD, {"pos": Vec2(1.0, 2.0)}],
        }
        assert _normalize_for_hash(raw) == {
            "tuple": [1.234568, None],
            "list": ["DEAD", {"pos": [1.0, 2.0]}],
        }

    def test_normalize_handles_non_finite_floats(self) -> None:
        assert _normalize_for_hash(float("nan")) == "__float__:nan"
        assert _normalize_for_hash(float("inf")) == "__float__:+inf"
        assert _normalize_for_hash(float("-inf")) == "__float__:-inf"

    def test_snapshot_hash_stable_with_non_finite_float(self, world: World) -> None:
        world.elapsed_s = float("nan")
        assert world.snapshot_hash() == world.snapshot_hash()

    def test_normalize_rejects_too_deep_nesting(self) -> None:
        nested: object = None
        for _ in range(80):
            nested = [nested]
        with pytest.raises(ValueError, match="nested deeper"):
            _normalize_for_hash(nested)


# ---------------------------------------------------------------------------
# 4. is_finished
# ---------------------------------------------------------------------------


class TestIsFinished:
    def test_initial_not_finished(self, world: World) -> None:
        assert world.is_finished() is False

    def test_finished_when_total_duration_reached(self, world: World) -> None:
        total = sum(p.duration_s for p in world.config.phases.values())
        assert total > 0.0  # 默认 LevelConfig 应有正向时长
        world.elapsed_s = total
        assert world.is_finished() is True

    def test_finished_when_game_result_set(self, world: World) -> None:
        world.game_result = GameResult.VICTORY
        assert world.is_finished() is True


# ---------------------------------------------------------------------------
# 5. Steppable 协议 + GameLoop 集成
# ---------------------------------------------------------------------------


class TestGameLoopIntegration:
    def test_world_satisfies_steppable(self, world: World) -> None:
        assert isinstance(world, Steppable)

    def test_world_satisfies_hashable_steppable(self, world: World) -> None:
        assert isinstance(world, HashableSteppable)

    def test_gameloop_headless_drives_world(self, world: World) -> None:
        N = 30
        loop = GameLoop(
            world=world,
            input_source=_NullInput(),
            max_sim_seconds=N * DT,
        )
        loop.run_headless()
        # GameLoop 在 step 后才检查 max_sim_seconds，故实际可能多走 0~1 帧；
        # 关键是协议适配 + 计数器被推进到至少 N 帧。
        assert world.frame_count >= N
        assert world.elapsed_s >= N * DT - 1e-9

    def test_gameloop_stops_at_total_duration(self, cfg: LevelConfig) -> None:
        # 用一个极小 total_duration 验证 is_finished 触发循环退出。
        w = World(cfg, SeededRng(seed=cfg.seed))
        # 直接缩短：把 _total_duration_s 设小，模拟 LevelDirector 之外的早停。
        w._total_duration_s = 5 * DT
        loop = GameLoop(world=w, input_source=_NullInput())
        loop.run_headless()
        assert w.is_finished() is True
        # 至少推进到触发上限的那一帧
        assert w.frame_count >= 5
