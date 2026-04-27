"""tests/fish/test_movement.py — M3-03 Player + MovementSystem 契约测试。

覆盖：
- Player 工厂构造在世界中央，按 tier 初始化运动学参数
- 持续 ``Vec2(1,0)`` 输入：x 单调增、y 不变、速度收敛于 max_speed
- ``desired_dir`` 突变 90°：每帧 heading 变化不超过 turn_rate * dt
- ``desired_dir is None``：vel 模长单调下降
- ``Vec2(0,0)`` 防御：即使绕过 InputFrame 校验也按无输入衰减，不产生 NaN
- 边界反射：四个方向均做位置 clamp + 速度翻转 + damping
- snapshot.player_pos 等于 player.pos 的 tuple（契约 #2）
- 决定性：两个 World 相同 seed + 相同输入序列平行跑 30 帧 → 相同 snapshot_hash 序列
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.rng import SeededRng

from fish.config.constants import (
    DT,
    PLAYER_ACCEL,
    PLAYER_DRAG,
    PLAYER_MAX_SPEED,
    PLAYER_RADIUS,
    PLAYER_TURN_RATE,
    TIER_FRY,
    WALL_BOUNCE_DAMPING,
    WORLD_H,
    WORLD_W,
)
from fish.config.level_config import LevelConfig
from fish.entities.player import Player
from fish.systems.movement import MovementSystem
from fish.world import World


# ---------------------------------------------------------------------------
# Player 工厂
# ---------------------------------------------------------------------------


class TestPlayerFactory:
    def test_player_starts_at_world_center(self) -> None:
        cfg = LevelConfig.default()
        p = Player.from_config(cfg, eid=0)
        assert p.pos.x == pytest.approx(WORLD_W / 2.0)
        assert p.pos.y == pytest.approx(WORLD_H / 2.0)
        assert p.vel.x == 0.0 and p.vel.y == 0.0
        assert p.heading == 0.0
        assert p.tier == TIER_FRY
        assert p.radius == float(PLAYER_RADIUS[TIER_FRY])
        assert p.max_speed == float(PLAYER_MAX_SPEED[TIER_FRY])
        assert p.accel == PLAYER_ACCEL
        assert p.turn_rate_rad_s == PLAYER_TURN_RATE
        assert p.alive is True
        assert p.eid == 0


# ---------------------------------------------------------------------------
# 直线推进
# ---------------------------------------------------------------------------


class TestForwardMotion:
    def test_steady_x_input_moves_right_and_y_stable(self) -> None:
        cfg = LevelConfig.default()
        world = World(cfg, SeededRng(seed=cfg.seed))
        ifr = InputFrame(desired_dir=Vec2(1.0, 0.0))

        prev_x = world.player.pos.x
        for _ in range(60):
            world.step(DT, ifr)
            assert world.player.pos.x >= prev_x - 1e-9, "x must be monotonic non-decreasing"
            prev_x = world.player.pos.x

        # 起始 heading=0 已对齐目标 → y 不变
        assert world.player.pos.y == pytest.approx(WORLD_H / 2.0)
        assert world.player.vel.y == pytest.approx(0.0, abs=1e-9)

    def test_speed_converges_to_max_speed(self) -> None:
        cfg = LevelConfig.default()
        world = World(cfg, SeededRng(seed=cfg.seed))
        ifr = InputFrame(desired_dir=Vec2(1.0, 0.0))

        # 推进足够多帧让速度饱和（max=235, accel=900 → 约 0.26s 到顶）
        for _ in range(120):
            world.step(DT, ifr)
        speed = math.hypot(world.player.vel.x, world.player.vel.y)
        assert speed == pytest.approx(world.player.max_speed, rel=1e-6)


# ---------------------------------------------------------------------------
# 转向 turn_rate 限制
# ---------------------------------------------------------------------------


class TestTurnRate:
    def test_heading_change_capped_per_frame(self) -> None:
        cfg = LevelConfig.default()
        world = World(cfg, SeededRng(seed=cfg.seed))
        # 先持续 +x 让 heading=0 稳定
        for _ in range(10):
            world.step(DT, InputFrame(desired_dir=Vec2(1.0, 0.0)))
        assert world.player.heading == pytest.approx(0.0)

        # 突变到 +y（90°）：每帧最多旋转 turn_rate * dt
        max_step = world.player.turn_rate_rad_s * DT
        assert max_step < math.pi / 2  # 否则不会被限制
        ifr = InputFrame(desired_dir=Vec2(0.0, 1.0))

        prev = world.player.heading
        for _ in range(5):
            world.step(DT, ifr)
            delta = abs(world.player.heading - prev)
            assert delta <= max_step + 1e-9, f"heading jumped by {delta} > {max_step}"
            prev = world.player.heading

        # 仍未到达目标
        assert world.player.heading < math.pi / 2


# ---------------------------------------------------------------------------
# 无输入 → 惯性衰减
# ---------------------------------------------------------------------------


class TestDragOnNoInput:
    def test_velocity_magnitude_monotonically_decays(self) -> None:
        cfg = LevelConfig.default()
        world = World(cfg, SeededRng(seed=cfg.seed))
        # 先加速到一个非零速度
        for _ in range(60):
            world.step(DT, InputFrame(desired_dir=Vec2(1.0, 0.0)))
        speed_before = math.hypot(world.player.vel.x, world.player.vel.y)
        assert speed_before > 1.0

        prev_speed = speed_before
        for _ in range(30):
            world.step(DT, InputFrame(desired_dir=None))
            cur = math.hypot(world.player.vel.x, world.player.vel.y)
            assert cur < prev_speed, f"speed must strictly decrease, {cur} >= {prev_speed}"
            prev_speed = cur

        # 30 * DT = 0.5s 的指数衰减后，速度显著小于初始
        expected = speed_before * math.exp(-PLAYER_DRAG * 30 * DT)
        assert prev_speed == pytest.approx(expected, rel=1e-4)

    def test_zero_vector_from_bypassed_input_validation_decays_without_nan(self) -> None:
        cfg = LevelConfig.default()
        world = World(cfg, SeededRng(seed=cfg.seed))
        world.player.vel = Vec2(100.0, 0.0)

        # InputFrame 本身会拒绝 Vec2(0,0)；这里模拟自定义测试桩绕过校验，
        # MovementSystem 应仍按 None 分支处理，避免角度/速度污染成 NaN。
        world.step(DT, SimpleNamespace(desired_dir=Vec2(0.0, 0.0)))

        decay = math.exp(-PLAYER_DRAG * DT)
        assert world.player.vel.x == pytest.approx(100.0 * decay)
        assert world.player.vel.y == pytest.approx(0.0)
        assert math.isfinite(world.player.pos.x)
        assert math.isfinite(world.player.pos.y)
        assert math.isfinite(world.player.heading)


# ---------------------------------------------------------------------------
# 边界反射
# ---------------------------------------------------------------------------


class TestBoundaryReflection:
    @pytest.mark.parametrize(
        ("start_pos", "start_vel", "component", "boundary_value", "sign_after"),
        [
            (Vec2(1.0, WORLD_H / 2.0), Vec2(-600.0, 0.0), "x", 0.0, 1.0),
            (Vec2(WORLD_W - 1.0, WORLD_H / 2.0), Vec2(600.0, 0.0), "x", float(WORLD_W), -1.0),
            (Vec2(WORLD_W / 2.0, 1.0), Vec2(0.0, -600.0), "y", 0.0, 1.0),
            (Vec2(WORLD_W / 2.0, WORLD_H - 1.0), Vec2(0.0, 600.0), "y", float(WORLD_H), -1.0),
        ],
    )
    def test_all_four_walls_reflect_velocity_with_damping(
        self,
        start_pos: Vec2,
        start_vel: Vec2,
        component: str,
        boundary_value: float,
        sign_after: float,
    ) -> None:
        cfg = LevelConfig.default()
        world = World(cfg, SeededRng(seed=cfg.seed))
        p = world.player
        p.pos = start_pos
        p.vel = start_vel

        # 用 desired_dir=None 保持惯性（避免 thrust 再次拉起 vx）
        world.step(DT, InputFrame(desired_dir=None))

        vel_component = p.vel.x if component == "x" else p.vel.y
        pos_component = p.pos.x if component == "x" else p.pos.y

        assert math.copysign(1.0, vel_component) == sign_after
        # 衰减因子（无输入时还会乘上 exp(-drag*dt)；先衰减再反射）
        decay = math.exp(-PLAYER_DRAG * DT)
        expected_speed = 600.0 * decay * WALL_BOUNCE_DAMPING
        assert abs(vel_component) == pytest.approx(expected_speed, rel=1e-6)
        assert pos_component == pytest.approx(boundary_value)
        assert 0.0 <= p.pos.x <= float(WORLD_W)
        assert 0.0 <= p.pos.y <= float(WORLD_H)

    def test_exact_wall_outward_velocity_reflects_immediately(self) -> None:
        cfg = LevelConfig.default()
        world = World(cfg, SeededRng(seed=cfg.seed))
        p = world.player
        p.pos = Vec2(0.0, WORLD_H / 2.0)
        p.vel = Vec2(-10.0, 0.0)

        MovementSystem._reflect_bounds(p)

        assert p.pos.x == 0.0
        assert p.vel.x == pytest.approx(10.0 * WALL_BOUNCE_DAMPING)


# ---------------------------------------------------------------------------
# snapshot 契约 #2
# ---------------------------------------------------------------------------


class TestSnapshotContract:
    def test_player_pos_in_snapshot_equals_player_pos(self) -> None:
        cfg = LevelConfig.default()
        world = World(cfg, SeededRng(seed=cfg.seed))
        for _ in range(20):
            world.step(DT, InputFrame(desired_dir=Vec2(1.0, 0.0)))
        snap = world.snapshot()
        assert snap["player_pos"] == (
            float(world.player.pos.x),
            float(world.player.pos.y),
        )
        assert isinstance(snap["player_pos"], tuple)

    def test_entities_snapshot_includes_player(self) -> None:
        cfg = LevelConfig.default()
        world = World(cfg, SeededRng(seed=cfg.seed))
        snap = world.snapshot()
        ents = snap["entities"]
        players = [e for e in ents if e["kind"] == "player"]
        assert len(players) == 1
        pe = players[0]
        for k in ("eid", "pos", "vel", "heading", "tier", "radius", "alive"):
            assert k in pe


# ---------------------------------------------------------------------------
# 决定性
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_two_worlds_same_seed_and_inputs_produce_same_hash_sequence(self) -> None:
        cfg = LevelConfig.default()
        inputs = [
            InputFrame(desired_dir=Vec2(1.0, 0.0)),
            InputFrame(desired_dir=Vec2(0.0, 1.0)),
            InputFrame(desired_dir=None),
            InputFrame(desired_dir=Vec2(-1.0, 0.0)),
            InputFrame(desired_dir=Vec2(0.0, -1.0)),
        ] * 6

        w1 = World(cfg, SeededRng(seed=cfg.seed))
        w2 = World(cfg, SeededRng(seed=cfg.seed))
        h1: list[str] = []
        h2: list[str] = []
        for ifr in inputs:
            w1.step(DT, ifr)
            w2.step(DT, ifr)
            h1.append(w1.snapshot_hash())
            h2.append(w2.snapshot_hash())

        assert len(h1) == 30
        assert h1 == h2


# ---------------------------------------------------------------------------
# MovementSystem 直接驱动其它实体
# ---------------------------------------------------------------------------


class TestOtherEntities:
    def test_non_player_entities_advance_and_reflect(self) -> None:
        from fish.entities.base import Entity

        cfg = LevelConfig.default()
        world = World(cfg, SeededRng(seed=cfg.seed))
        ent = Entity(
            eid=999,
            pos=Vec2(float(WORLD_W) - 0.5, 100.0),
            vel=Vec2(600.0, 0.0),
            radius=5.0,
            alive=True,
        )
        world.entities.append(ent)

        sys_ = MovementSystem()
        sys_.step(world, DT)
        assert ent.pos.x <= float(WORLD_W)
        assert ent.vel.x < 0.0
        assert abs(ent.vel.x) == pytest.approx(600.0 * WALL_BOUNCE_DAMPING, rel=1e-6)
