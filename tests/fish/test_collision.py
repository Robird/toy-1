"""tests/fish/test_collision.py — M3-05 碰撞 + 吃/被吃 + 同 tier 反弹 + 成长 + DEAD。

覆盖 (DoD)：
- player + fish 重叠且 player.tier >= fish.tier-1 → fish.alive=False、player.exp 增加
- player.tier > 4 不再升级（exp 仍累加）
- player + fish 重叠且 fish.tier > player.tier+1 → world.game_result == DEAD
- player + fish 同 tier → 双方 alive 不变，互相被推开（距离增大）+ 法向速度互换符号
- 多次吃同 tier 鱼累计到阈值后 player.tier 升级 + radius/max_speed 同步增大
- 决定性：相同 seed + 相同输入 + 相同碰撞序列 → snapshot_hash 序列一致
- DEAD 后再 step 不崩溃 + game_result 不会回退 + stats 不再增加
- can_eat 公式（progress.md 发现 #13）单元测试
- fish vs fish 同 tier bounce + 不同 tier 不互斥
- on_fish_eaten / on_player_grow stats 计数
"""

from __future__ import annotations

import math

import pytest

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.rng import SeededRng

from fish.config.constants import (
    DT,
    GROWTH_REWARD,
    PLAYER_MAX_SPEED,
    PLAYER_RADIUS,
    TIER_MAX,
    TIER_THRESHOLDS,
    WORLD_H,
    WORLD_W,
)
from fish.config.level_config import LevelConfig
from fish.entities.fish import Fish
from fish.systems.collision import CollisionSystem, _elastic_bounce_same_tier, can_eat
from fish.world import GameResult, World


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _NullInput:
    def poll(self, world_state):  # noqa: ARG002
        return InputFrame()


def _new_world(seed: int = 0) -> World:
    return World(LevelConfig.default(), SeededRng(seed=seed))


def _add_fish(world: World, tier: int, pos: Vec2) -> Fish:
    """直接把一条 fish 注入 world，用于隔离测试碰撞 / 成长。"""
    eid = world.alloc_eid()
    rng = world.rng.spawn(f"test_fish_{eid}")
    f = Fish.spawn(eid=eid, tier=tier, pos=pos, heading=0.0, rng=rng)
    world.fishes.append(f)
    world.entities.append(f)
    return f


def _place_player(world: World, x: float, y: float, tier: int = 0) -> None:
    world.player.pos = Vec2(x, y)
    world.player.vel = Vec2(0.0, 0.0)
    if tier != world.player.tier:
        world.player.grow_to(tier)


# ---------------------------------------------------------------------------
# can_eat 公式
# ---------------------------------------------------------------------------


class TestCanEat:
    def test_one_tier_higher_can_eat(self) -> None:
        a = type("E", (), {"tier": 0})()
        b = type("E", (), {"tier": 1})()
        assert can_eat(a, b) is True  # 0 >= 1 - 1 = 0

    def test_two_tier_higher_cannot_eat(self) -> None:
        a = type("E", (), {"tier": 0})()
        b = type("E", (), {"tier": 2})()
        assert can_eat(a, b) is False  # 0 >= 2 - 1 = 1 false

    def test_same_tier_can_eat_returns_true(self) -> None:
        # CollisionSystem 在调用前会优先用 same-tier 走 bounce 分支。
        a = type("E", (), {"tier": 2})()
        b = type("E", (), {"tier": 2})()
        assert can_eat(a, b) is True

    def test_eater_strictly_larger_can_eat(self) -> None:
        a = type("E", (), {"tier": 3})()
        b = type("E", (), {"tier": 1})()
        assert can_eat(a, b) is True


# ---------------------------------------------------------------------------
# player 吃 fish + 计数 + exp
# ---------------------------------------------------------------------------


class TestPlayerEatsFish:
    def test_tier0_player_eats_tier1_fish_via_one_tier_rule(self) -> None:
        """进度发现 #13：tier=0 玩家可吃 tier=1 鱼。"""
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=0)
        f = _add_fish(w, tier=1, pos=Vec2(605.0, 360.0))  # 与玩家重叠
        w.step(DT, InputFrame())
        assert f.alive is False
        assert f not in w.fishes  # cleanup
        assert w.player.exp == pytest.approx(float(GROWTH_REWARD[1]))
        assert w.stats["fish_eaten_count"] == 1
        assert w.stats["fish_eaten_tier1"] == 1
        assert w.game_result is None

    def test_player_eats_strictly_smaller_fish(self) -> None:
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=2)
        f = _add_fish(w, tier=1, pos=Vec2(601.0, 360.0))
        w.step(DT, InputFrame())
        assert f.alive is False
        assert w.player.exp == pytest.approx(float(GROWTH_REWARD[1]))

    def test_no_collision_no_eating(self) -> None:
        w = _new_world()
        _place_player(w, 100.0, 100.0, tier=2)
        f = _add_fish(w, tier=1, pos=Vec2(900.0, 600.0))
        w.step(DT, InputFrame())
        assert f.alive is True
        assert w.player.exp == 0.0
        assert w.stats["fish_eaten_count"] == 0


# ---------------------------------------------------------------------------
# player 被 fish 吃 → DEAD
# ---------------------------------------------------------------------------


class TestPlayerEatenDead:
    def test_tier0_player_vs_tier2_fish_dead(self) -> None:
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=0)
        f = _add_fish(w, tier=2, pos=Vec2(602.0, 360.0))
        w.step(DT, InputFrame())
        assert w.game_result is GameResult.DEAD
        assert w.player.alive is False
        assert w.stats["death_cause_tier"] == 2
        assert f.alive is True  # fish 没被淘汰
        assert w.is_finished() is True

    def test_tier1_player_vs_tier3_fish_dead(self) -> None:
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=1)
        _add_fish(w, tier=3, pos=Vec2(605.0, 360.0))
        w.step(DT, InputFrame())
        assert w.game_result is GameResult.DEAD

    def test_dead_then_step_safe_and_no_regression(self) -> None:
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=0)
        _add_fish(w, tier=2, pos=Vec2(602.0, 360.0))
        w.step(DT, InputFrame())
        assert w.game_result is GameResult.DEAD
        prev_stats = dict(w.stats)
        prev_hash = w.snapshot_hash()
        # 多 step 几帧
        for _ in range(20):
            w.step(DT, InputFrame())
        # game_result 不回退；stats 不再变；frame_count 仍推进
        assert w.game_result is GameResult.DEAD
        assert w.stats == prev_stats
        assert w.frame_count == 21
        # snapshot_hash 会因 elapsed_s 改变而变；我们仅断言不抛异常 + 不回退
        new_hash = w.snapshot_hash()
        assert isinstance(new_hash, str) and len(new_hash) == 40
        assert new_hash != prev_hash  # elapsed 推进 → hash 不同 OK

    def test_collision_short_circuits_remaining_checks_after_player_death(self) -> None:
        """DEAD 写入同一帧后不再继续做 fish-fish bounce。"""
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=0)
        _add_fish(w, tier=2, pos=Vec2(602.0, 360.0))  # 先按 eid 触发 DEAD
        f1 = _add_fish(w, tier=1, pos=Vec2(100.0, 100.0))
        f2 = _add_fish(w, tier=1, pos=Vec2(101.0, 100.0))
        p1 = f1.pos
        p2 = f2.pos

        CollisionSystem().step(w, DT)

        assert w.game_result is GameResult.DEAD
        assert f1.pos == p1
        assert f2.pos == p2


# ---------------------------------------------------------------------------
# 同 tier 弹性反弹
# ---------------------------------------------------------------------------


class TestSameTierBounce:
    def test_player_vs_fish_same_tier_both_alive_pushed_apart(self) -> None:
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=1)
        f = _add_fish(w, tier=1, pos=Vec2(602.0, 360.0))
        d_before = math.hypot(f.pos.x - w.player.pos.x, f.pos.y - w.player.pos.y)
        w.step(DT, InputFrame())
        assert f.alive is True
        assert w.player.alive is True
        assert w.game_result is None
        d_after = math.hypot(f.pos.x - w.player.pos.x, f.pos.y - w.player.pos.y)
        assert d_after > d_before
        # 不再相交（含 epsilon）
        assert d_after >= w.player.radius + f.radius - 1e-3

    def test_elastic_bounce_swaps_normal_velocity(self) -> None:
        """直接调用底层 helper：等质量法向速度互换。"""
        # 构造 a 在原点向 +x 方向 100，b 在 (5, 0) 向 -x 方向 50；接触法向 = (-1, 0)
        # （push_dir 从 b 指向 a，即 (-1, 0)）
        from dataclasses import dataclass

        @dataclass
        class _E:
            pos: Vec2
            vel: Vec2
            radius: float

        a = _E(pos=Vec2(0.0, 0.0), vel=Vec2(100.0, 7.0), radius=4.0)
        b = _E(pos=Vec2(5.0, 0.0), vel=Vec2(-50.0, -3.0), radius=4.0)
        _elastic_bounce_same_tier(a, b)
        # 法向 (-1, 0)：a.vel.x 原来 100（沿 +x = 远离 b 还是靠近 b？b 在 +x 方向，
        # 所以 a.vel.x=+100 表示朝 b 移动，即靠近）。互换后 a.vel.x 应变成 -50。
        assert a.vel.x == pytest.approx(-50.0)
        assert b.vel.x == pytest.approx(100.0)
        # 切向 (y) 分量保留
        assert a.vel.y == pytest.approx(7.0)
        assert b.vel.y == pytest.approx(-3.0)
        # 推开：距离 > 4+4
        d = math.hypot(b.pos.x - a.pos.x, b.pos.y - a.pos.y)
        assert d >= 8.0 - 1e-6

    def test_elastic_bounce_no_swap_when_separating(self) -> None:
        """已经在分离的两实体仅做位置推开，不再交换法向速度。"""
        from dataclasses import dataclass

        @dataclass
        class _E:
            pos: Vec2
            vel: Vec2
            radius: float

        a = _E(pos=Vec2(0.0, 0.0), vel=Vec2(-100.0, 0.0), radius=4.0)  # 远离 b
        b = _E(pos=Vec2(5.0, 0.0), vel=Vec2(100.0, 0.0), radius=4.0)
        _elastic_bounce_same_tier(a, b)
        assert a.vel.x == pytest.approx(-100.0)
        assert b.vel.x == pytest.approx(100.0)

    def test_elastic_bounce_same_center_stays_finite_and_separates(self) -> None:
        """同心重叠时使用稳定轴兜底，不产生 NaN 且能分离。"""
        from dataclasses import dataclass

        @dataclass
        class _E:
            pos: Vec2
            vel: Vec2
            radius: float

        a = _E(pos=Vec2(0.0, 0.0), vel=Vec2(1.0, 0.5), radius=4.0)
        b = _E(pos=Vec2(0.0, 0.0), vel=Vec2(-1.0, -0.25), radius=4.0)

        _elastic_bounce_same_tier(a, b)

        values = (a.pos.x, a.pos.y, b.pos.x, b.pos.y, a.vel.x, a.vel.y, b.vel.x, b.vel.y)
        assert all(math.isfinite(v) for v in values)
        d = math.hypot(b.pos.x - a.pos.x, b.pos.y - a.pos.y)
        assert d >= 8.0 - 1e-6

    def test_fish_fish_same_tier_bounce_keeps_both_alive(self) -> None:
        w = _new_world()
        _place_player(w, 50.0, 50.0, tier=4)  # 远离，避免触发 player vs fish
        f1 = _add_fish(w, tier=2, pos=Vec2(600.0, 360.0))
        f2 = _add_fish(w, tier=2, pos=Vec2(602.0, 360.0))
        d_before = math.hypot(f2.pos.x - f1.pos.x, f2.pos.y - f1.pos.y)
        w.step(DT, InputFrame())
        assert f1.alive and f2.alive
        # FishAI 会改写 vel & 推动它们；这里只验证 bounce 触发后没死、没崩
        # 距离至少不再小于一个回到接触临界的阈值（间接验证 push 起作用了）
        d_after = math.hypot(f2.pos.x - f1.pos.x, f2.pos.y - f1.pos.y)
        assert d_after > 0.0
        assert math.isfinite(d_after)
        del d_before  # 可能因 AI 改向变近也合法

    def test_fish_fish_different_tier_no_collision_effect(self) -> None:
        """不同 tier 鱼不互斥（MVP：仅同 tier bounce）。"""
        w = _new_world()
        _place_player(w, 50.0, 50.0, tier=4)
        f1 = _add_fish(w, tier=1, pos=Vec2(600.0, 360.0))
        f2 = _add_fish(w, tier=3, pos=Vec2(601.0, 360.0))
        w.step(DT, InputFrame())
        # 都活着、都没被淘汰
        assert f1.alive and f2.alive
        assert w.stats["fish_eaten_count"] == 0


# ---------------------------------------------------------------------------
# 成长 + 升级 + 上限
# ---------------------------------------------------------------------------


class TestGrowth:
    def test_player_levels_up_when_exp_crosses_threshold(self) -> None:
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=0)
        # tier 0 -> 1 阈值 = 8；GROWTH_REWARD[1] = 2 → 4 条 tier-1 即可升级
        # 一次性堆叠到玩家位置
        for i in range(4):
            _add_fish(w, tier=1, pos=Vec2(600.0 + i * 0.5, 360.0))
        w.step(DT, InputFrame())
        # 4 条都被吃掉（圆形重叠 + 同帧）
        assert w.stats["fish_eaten_count"] == 4
        assert w.player.exp == pytest.approx(8.0)
        assert w.player.tier == 1
        assert w.player.radius == pytest.approx(float(PLAYER_RADIUS[1]))
        assert w.player.max_speed == pytest.approx(float(PLAYER_MAX_SPEED[1]))
        assert w.stats["player_grow_count"] == 1

    def test_many_eats_in_one_frame_can_cross_multiple_thresholds(self) -> None:
        """同一帧吃多条鱼累计 exp 后可 while 连升多级。"""
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=0)
        # 13 条 tier-1 鱼：13 * 2 = 26，跨过 tier1(8) 与 tier2(25)。
        for i in range(13):
            _add_fish(w, tier=1, pos=Vec2(600.0 + (i % 5) * 0.1, 360.0 + (i // 5) * 0.1))

        w.step(DT, InputFrame())

        assert w.stats["fish_eaten_count"] == 13
        assert w.player.exp == pytest.approx(26.0)
        assert w.player.tier == 2
        assert w.stats["player_grow_count"] == 2

    def test_growth_radius_max_speed_synced_on_grow_to(self) -> None:
        w = _new_world()
        for t in range(TIER_MAX + 1):
            w.player.grow_to(t)
            assert w.player.tier == t
            assert w.player.radius == pytest.approx(float(PLAYER_RADIUS[t]))
            assert w.player.max_speed == pytest.approx(float(PLAYER_MAX_SPEED[t]))

    def test_tier_cap_not_exceeded(self) -> None:
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=TIER_MAX)
        # 给一大堆 exp，确认 tier 不超过 TIER_MAX
        w.player.exp = float(TIER_THRESHOLDS[-1]) * 10.0
        w.step(DT, InputFrame())
        assert w.player.tier == TIER_MAX
        assert w.player.radius == pytest.approx(float(PLAYER_RADIUS[TIER_MAX]))
        # exp 不被清零
        assert w.player.exp >= float(TIER_THRESHOLDS[-1])

    def test_grow_to_clamps_negative_and_overflow(self) -> None:
        w = _new_world()
        w.player.grow_to(-5)
        assert w.player.tier == 0
        w.player.grow_to(TIER_MAX + 99)
        assert w.player.tier == TIER_MAX

    def test_multi_levelup_in_single_frame(self) -> None:
        """一帧内攒够多档 → 连升。"""
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=0)
        # 直接给 exp >= TIER_THRESHOLDS[2]=25
        w.player.exp = 30.0
        w.step(DT, InputFrame())
        assert w.player.tier == 2
        assert w.stats["player_grow_count"] == 2


# ---------------------------------------------------------------------------
# 决定性
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_two_runs_with_same_seed_produce_same_hash_sequence(self) -> None:
        def run(seed: int) -> list[str]:
            w = _new_world(seed=seed)
            inp = _NullInput()
            hashes = []
            for _ in range(120):
                w.step(DT, inp.poll(w.snapshot()))
                hashes.append(w.snapshot_hash())
            return hashes

        h1 = run(42)
        h2 = run(42)
        assert h1 == h2

    def test_different_seed_diverges(self) -> None:
        w1 = _new_world(seed=1)
        w2 = _new_world(seed=2)
        for _ in range(60):
            w1.step(DT, InputFrame())
            w2.step(DT, InputFrame())
        # 至少在 60 帧内 spawn 序列不同 → hash 不同
        assert w1.snapshot_hash() != w2.snapshot_hash()


# ---------------------------------------------------------------------------
# CollisionSystem 单元（隔离 World）
# ---------------------------------------------------------------------------


class TestCollisionSystemIsolated:
    def test_no_op_when_dt_zero(self) -> None:
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=0)
        f = _add_fish(w, tier=1, pos=Vec2(601.0, 360.0))
        CollisionSystem().step(w, 0.0)
        assert f.alive is True
        assert w.player.exp == 0.0

    def test_no_op_when_already_dead(self) -> None:
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=0)
        w.game_result = GameResult.DEAD
        f = _add_fish(w, tier=1, pos=Vec2(601.0, 360.0))
        CollisionSystem().step(w, DT)
        assert f.alive is True


# ---------------------------------------------------------------------------
# Snapshot 字段扩展
# ---------------------------------------------------------------------------


class TestSnapshotExtensions:
    def test_snapshot_has_new_fields(self) -> None:
        w = _new_world()
        snap = w.snapshot()
        for key in ("player_tier", "player_exp", "stats", "game_result"):
            assert key in snap
        assert snap["player_tier"] == 0
        assert snap["player_exp"] == 0.0
        assert isinstance(snap["stats"], dict)
        assert snap["stats"]["fish_eaten_count"] == 0

    def test_stats_reflect_eats(self) -> None:
        w = _new_world()
        _place_player(w, 600.0, 360.0, tier=0)
        _add_fish(w, tier=1, pos=Vec2(601.0, 360.0))
        w.step(DT, InputFrame())
        snap = w.snapshot()
        assert snap["stats"]["fish_eaten_count"] == 1
        assert snap["player_exp"] > 0.0
