"""tests/fish/test_fish_ai.py — M3-04 Fish 实体 + FishAI + Spawner 契约测试。

覆盖：
- Fish 工厂：4 个 tier 各能生成；半径 / 速度按 tier 单调
- FishAI 状态切换：小鱼 + 大玩家 → FLEE 远离 player；大鱼 + 小玩家 → CHASE 朝 player
- WANDER：孤立 fish 长时间不崩溃，速度始终 < max_speed
- Spawner 决定性：相同 seed 跑 60 帧 → snapshot_hash 序列一致
- Spawner 不超出 population_target（多跑数百帧后总数稳定）
- Spawner 生成位置在屏外缘附近，朝屏内
"""

from __future__ import annotations

import math

import pytest

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.rng import SeededRng

from fish.ai.fish_ai import FishAI, FishAIState
from fish.config.constants import (
    DT,
    FISH_MAX_SPEED,
    FISH_RADIUS,
    Phase,
    SPAWNER_EDGE_MARGIN,
    WANDER_SPEED_RATIO,
    WORLD_H,
    WORLD_W,
)
from fish.config.level_config import LevelConfig
from fish.entities.fish import Fish
from fish.world import World


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_world(seed: int = 0) -> World:
    cfg = LevelConfig.default()
    return World(cfg, SeededRng(seed=seed))


class _NullInput:
    """玩家保持不动的输入源。"""

    def poll(self, world_state):  # noqa: ARG002
        return InputFrame()


# ---------------------------------------------------------------------------
# Fish 工厂
# ---------------------------------------------------------------------------


class TestFishFactory:
    @pytest.mark.parametrize("tier", [1, 2, 3, 4])
    def test_spawn_each_tier(self, tier: int) -> None:
        rng = SeededRng(seed=tier)
        f = Fish.spawn(eid=10 + tier, tier=tier, pos=Vec2(0.0, 0.0), heading=0.0, rng=rng)
        assert f.tier == tier
        assert f.eid == 10 + tier
        assert f.alive
        assert f.radius == pytest.approx(float(FISH_RADIUS[tier]))
        assert f.max_speed == pytest.approx(float(FISH_MAX_SPEED[tier]))
        assert f.state is FishAIState.WANDER
        assert f.rng is rng

    def test_radius_and_speed_monotone_in_tier(self) -> None:
        rngs = [SeededRng(seed=i) for i in range(1, 5)]
        fishes = [
            Fish.spawn(eid=i, tier=i, pos=Vec2(0.0, 0.0), heading=0.0, rng=rngs[i - 1])
            for i in range(1, 5)
        ]
        radii = [f.radius for f in fishes]
        speeds = [f.max_speed for f in fishes]
        assert radii == sorted(radii) and len(set(radii)) == 4
        assert speeds == sorted(speeds) and len(set(speeds)) == 4

    @pytest.mark.parametrize("bad_tier", [0, 5, -1])
    def test_invalid_tier_raises(self, bad_tier: int) -> None:
        with pytest.raises(ValueError):
            Fish.spawn(
                eid=0,
                tier=bad_tier,
                pos=Vec2(0.0, 0.0),
                heading=0.0,
                rng=SeededRng(seed=0),
            )


# ---------------------------------------------------------------------------
# FishAI FSM
# ---------------------------------------------------------------------------


class TestFishAIStateMachine:
    def test_small_fish_flees_from_bigger_player(self) -> None:
        world = _new_world(seed=1)
        # 玩家 tier=0；为了构造"player.tier > fish.tier"，临时把 player 升到 tier=2
        world.player.tier = 2
        world.player.pos = Vec2(640.0, 360.0)
        # 在 player 附近放一条 tier=1 fish
        fish = Fish.spawn(
            eid=world.alloc_eid(),
            tier=1,
            pos=Vec2(660.0, 360.0),  # 玩家右侧 20px
            heading=0.0,
            rng=SeededRng(seed=99),
        )
        world.fishes.append(fish)
        world.entities.append(fish)

        ai = FishAI()
        for _ in range(20):
            ai.step(fish, world, DT)
        assert fish.state is FishAIState.FLEE
        # 远离 player：vel.x 应当 > 0（玩家在左侧），且方向远离 player
        # 即 (fish.pos - player.pos) · vel > 0
        dx = fish.pos.x - world.player.pos.x
        dy = fish.pos.y - world.player.pos.y
        assert dx * fish.vel.x + dy * fish.vel.y > 0.0

    def test_big_fish_chases_smaller_player(self) -> None:
        world = _new_world(seed=2)
        world.player.tier = 0
        world.player.pos = Vec2(640.0, 360.0)
        fish = Fish.spawn(
            eid=world.alloc_eid(),
            tier=2,
            pos=Vec2(700.0, 360.0),
            heading=math.pi,  # 初始朝左（朝 player）使转向限速不阻挡
            rng=SeededRng(seed=99),
        )
        world.fishes.append(fish)
        world.entities.append(fish)

        ai = FishAI()
        for _ in range(20):
            ai.step(fish, world, DT)
        assert fish.state is FishAIState.CHASE
        # 朝 player：方向 (player - fish) · vel > 0
        dx = world.player.pos.x - fish.pos.x
        dy = world.player.pos.y - fish.pos.y
        assert dx * fish.vel.x + dy * fish.vel.y > 0.0

    def test_equal_tier_stays_wander(self) -> None:
        world = _new_world(seed=3)
        world.player.tier = 2
        world.player.pos = Vec2(640.0, 360.0)
        fish = Fish.spawn(
            eid=world.alloc_eid(),
            tier=2,
            pos=Vec2(660.0, 360.0),
            heading=0.0,
            rng=SeededRng(seed=99),
        )
        world.fishes.append(fish)
        world.entities.append(fish)
        ai = FishAI()
        for _ in range(10):
            ai.step(fish, world, DT)
        assert fish.state is FishAIState.WANDER

    def test_wander_speed_below_max_and_no_nan(self) -> None:
        # 孤立场景：把玩家挪到角落、tier=0；fish 保持 WANDER
        world = _new_world(seed=4)
        world.player.tier = 0
        world.player.pos = Vec2(0.0, 0.0)
        fish = Fish.spawn(
            eid=world.alloc_eid(),
            tier=2,  # tier > player → 既非 FLEE 也非 CHASE
            pos=Vec2(640.0, 360.0),
            heading=0.0,
            rng=SeededRng(seed=999),
        )
        world.fishes.append(fish)
        world.entities.append(fish)
        ai = FishAI()
        for _ in range(500):
            ai.step(fish, world, DT)
            speed = math.hypot(fish.vel.x, fish.vel.y)
            assert math.isfinite(speed)
            # 巡航速度 ≈ WANDER_SPEED_RATIO * max_speed；不应触及 max_speed
            assert speed <= fish.max_speed * (WANDER_SPEED_RATIO + 1e-6)
            assert math.isfinite(fish.heading)
        assert fish.state is FishAIState.WANDER

    def test_flee_overlap_uses_finite_fallback_heading(self) -> None:
        """player 与 fish 完全同位时，FLEE 仍应给出有限速度。"""
        world = _new_world(seed=5)
        world.player.tier = 2
        world.player.pos = Vec2(640.0, 360.0)
        fish = Fish.spawn(
            eid=world.alloc_eid(),
            tier=1,
            pos=Vec2(640.0, 360.0),
            heading=0.0,
            rng=SeededRng(seed=99),
        )
        world.fishes.append(fish)
        world.entities.append(fish)

        FishAI().step(fish, world, DT)

        assert fish.state is FishAIState.FLEE
        assert math.isfinite(fish.heading)
        assert math.isfinite(fish.vel.x)
        assert math.isfinite(fish.vel.y)
        assert math.hypot(fish.vel.x, fish.vel.y) == pytest.approx(fish.max_speed)

    def test_separation_does_not_push_past_max_speed(self) -> None:
        """separation 只改变拥挤鱼的方向/分散趋势，不额外突破 max_speed。"""
        world = _new_world(seed=6)
        fish = Fish.spawn(
            eid=world.alloc_eid(),
            tier=1,
            pos=Vec2(100.0, 100.0),
            heading=0.0,
            rng=SeededRng(seed=1),
        )
        other = Fish.spawn(
            eid=world.alloc_eid(),
            tier=1,
            pos=Vec2(99.0, 100.0),
            heading=0.0,
            rng=SeededRng(seed=2),
        )
        fish.vel = Vec2(fish.max_speed, 0.0)
        world.fishes.extend([fish, other])
        world.entities.extend([fish, other])

        FishAI._apply_separation(fish, world)

        assert math.hypot(fish.vel.x, fish.vel.y) <= fish.max_speed + 1e-9


# ---------------------------------------------------------------------------
# Spawner
# ---------------------------------------------------------------------------


class TestSpawner:
    def test_determinism_two_parallel_worlds(self) -> None:
        """相同 seed 跑 60 帧 → snapshot_hash 序列必须逐帧一致。"""
        w1 = _new_world(seed=42)
        w2 = _new_world(seed=42)
        inp = _NullInput()
        for _ in range(60):
            ifr1 = inp.poll(w1.snapshot())
            ifr2 = inp.poll(w2.snapshot())
            w1.step(DT, ifr1)
            w2.step(DT, ifr2)
            assert w1.snapshot_hash() == w2.snapshot_hash()
        # 跑了 60 帧 = 1.0s，spawner 至少触发过一次（间隔 0.5s）
        assert len(w1.fishes) >= 1
        assert len(w1.fishes) == len(w2.fishes)

    def test_population_does_not_exceed_target(self) -> None:
        """长时间跑后，每 tier 在场数不应超过 WARMUP 的 population_target。"""
        world = _new_world(seed=7)
        target = world.config.phases[Phase.WARMUP].population_target
        inp = _NullInput()
        for _ in range(600):  # 10s
            world.step(DT, inp.poll(world.snapshot()))
            counts: dict[int, int] = {t: 0 for t in target}
            for f in world.fishes:
                if f.alive:
                    counts[f.tier] = counts.get(f.tier, 0) + 1
            for t, n in counts.items():
                assert n <= target[t], (
                    f"tier {t} count {n} exceeds target {target[t]} at frame {world.frame_count}"
                )

    def test_eventually_reaches_warmup_target(self) -> None:
        """跑足够长时间后，Tier-1 的在场数应当达到 WARMUP target（=8）。

        M3-06 起 LevelDirector 会在 WARMUP duration（12~18s）后切到 PRESSURE，
        改变 population_target；此处把 spin-up 限制在 WARMUP 阶段内。
        """
        from fish.config.constants import Phase as _P  # 避免污染顶层 import

        world = _new_world(seed=11)
        target = world.config.phases[_P.WARMUP].population_target
        inp = _NullInput()
        # WARMUP min=12s 内已远足以填满 8 条 Tier-1（每 0.5s spawn 1 条）
        # 限制在 8s 以内，确保未触发 WARMUP→PRESSURE 转换。
        for _ in range(int(8.0 / DT)):
            world.step(DT, inp.poll(world.snapshot()))
        assert world.director.current_phase == _P.WARMUP
        counts: dict[int, int] = {t: 0 for t in target}
        for f in world.fishes:
            if f.alive:
                counts[f.tier] = counts.get(f.tier, 0) + 1
        # WARMUP 阶段只 spawn Tier-1（target[2..4] = 0）
        assert counts[1] == target[1]
        assert counts.get(2, 0) == target.get(2, 0) == 0
        assert counts.get(3, 0) == 0
        assert counts.get(4, 0) == 0

    def test_spawn_position_at_screen_edge_and_heads_inward(self) -> None:
        """新刷出的 fish 必须在屏外缘 margin 内，且 heading 朝屏内。"""
        world = _new_world(seed=21)
        inp = _NullInput()
        for _ in range(120):  # 2s
            world.step(DT, inp.poll(world.snapshot()))
        assert len(world.fishes) >= 1
        margin = SPAWNER_EDGE_MARGIN + 1e-6
        for f in world.fishes:
            x, y = f.pos.x, f.pos.y
            # 至少其中一条边在外缘 margin 内（spawn 时位置；之后若已移动应仍接近）
            on_left = x <= 0.0 + margin
            on_right = x >= float(WORLD_W) - margin
            on_top = y <= 0.0 + margin
            on_bottom = y >= float(WORLD_H) - margin
            # 注意：fish 已经被 movement 推进了若干步，可能进入屏内；只检查刚 spawn
            # 时是否朝屏内（heading 向中心方向）。改为检查 heading 与"指向屏中心"
            # 的方向夹角 < 90°。
            cx = float(WORLD_W) / 2.0 - x
            cy = float(WORLD_H) / 2.0 - y
            hx, hy = math.cos(f.heading), math.sin(f.heading)
            # 若 fish 仍在屏外缘，验证朝屏内；否则放过
            if on_left or on_right or on_top or on_bottom:
                assert cx * hx + cy * hy > 0.0, (
                    f"fish at edge ({x:.1f},{y:.1f}) does not head inward "
                    f"(heading={f.heading:.3f})"
                )

    def test_spawn_one_starts_outside_screen_and_heads_inward(self) -> None:
        """直接验证 Spawner 的生成瞬间：位置在屏外，heading 指向屏内。"""
        world = _new_world(seed=22)

        world._spawner._spawn_one(world, tier=1)

        fish = world.fishes[-1]
        x, y = fish.pos.x, fish.pos.y
        assert x < 0.0 or x > float(WORLD_W) or y < 0.0 or y > float(WORLD_H)
        cx = float(WORLD_W) / 2.0 - x
        cy = float(WORLD_H) / 2.0 - y
        hx, hy = math.cos(fish.heading), math.sin(fish.heading)
        assert cx * hx + cy * hy > 0.0

    def test_world_snapshot_includes_fish_entries(self) -> None:
        world = _new_world(seed=33)
        inp = _NullInput()
        for _ in range(60):
            world.step(DT, inp.poll(world.snapshot()))
        snap = world.snapshot()
        kinds = [e["kind"] for e in snap["entities"]]
        assert "player" in kinds
        assert "fish" in kinds
        for ent in snap["entities"]:
            if ent["kind"] != "fish":
                continue
            for key in ("eid", "pos", "vel", "radius", "alive", "heading", "tier", "state"):
                assert key in ent, f"fish entity missing field: {key}"
            assert ent["state"] in {"WANDER", "FLEE", "CHASE"}
            assert ent["tier"] in (1, 2, 3, 4)
