"""tests/fish/test_boss.py — M3-07 Boss 实体 + BossAI 五核心状态 + 复仇判定 + Tier-4 提示。

覆盖 (DoD)：
- Boss.spawn 在屏外朝内
- PATROL→CHASE：强制 8s PATROL 后，player 进入感知半径 → 切状态
- CHASE→CHARGE_WINDUP：距离够近 + 冷却就绪
- CHARGE_WINDUP→CHARGE：windup_s 后
- CHARGE→STUNNED：撞墙
- STUNNED：player 在尾部弧内咬 → hp--；不在弧内 → 不算咬
- HP=0 → boss.alive=False, world.boss=None；director 切 REVENGE；REVENGE 超时 → VICTORY
- ENRAGED：HP < 阈值 → boss.enraged=True；windup 缩短；charge 冷却缩短
- 决定性：相同 seed → 相同 hash 序列
- Tier-4 警示：fish.tier=4 与 player 同屏 + player.tier<4 时 world.tier4_warning=True
- player.tier < 4 + 任意接触 → DEAD
- player.tier == 4 + 正面接触 → DEAD（非 STUNNED）
- 玩家无敌窗口期内不再被 fish 吃掉
"""

from __future__ import annotations

import math

import pytest

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.rng import SeededRng

from fish.ai.boss_ai import BossAI, BossState
from fish.config.constants import (
    BOSS_BITE_DAMAGE,
    BOSS_CHARGE_COOLDOWN_S,
    BOSS_CHARGE_DURATION_S,
    BOSS_CHARGE_TRIGGER_DIST,
    BOSS_CHARGE_WINDUP_S,
    BOSS_ENRAGE_HP_RATIO,
    BOSS_ENRAGED_COOLDOWN_MUL,
    BOSS_ENRAGED_WINDUP_MUL,
    BOSS_HP,
    BOSS_PATROL_DURATION_S,
    BOSS_INTRO_DURATION_S,
    BOSS_RADIUS,
    BOSS_SENSE_RADIUS,
    BOSS_STUNNED_DURATION_S,
    BOSS_TIER,
    DT,
    PHASE_PRESSURE_DURATION_RANGE_S,
    PHASE_WARMUP_DURATION_RANGE_S,
    Phase,
    PLAYER_INVULN_AFTER_BITE_S,
    REVENGE_PHASE_TIMEOUT_S,
    TIER_GIANT,
    WORLD_H,
    WORLD_W,
)
from fish.config.level_config import LevelConfig
from fish.entities.boss import Boss
from fish.entities.fish import Fish
from fish.systems.collision import CollisionSystem
from fish.systems.level_director import LevelDirector
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


def _place_boss(
    world: World,
    x: float,
    y: float,
    *,
    state: BossState = BossState.CHASE,
    heading: float = 0.0,
    hp: int = BOSS_HP,
    intro_remaining: float = 0.0,
) -> Boss:
    """在 world 中插入一个可控的 Boss 实例。绕过 world.spawn_boss() 以便测试控制位置。"""
    eid = world.alloc_eid()
    rng = world.rng.spawn(f"test_boss_{eid}")
    boss = Boss.spawn(
        eid=eid,
        world_size=world.config.world_size,
        rng=rng,
        player_pos=world.player.pos,
        cfg_boss=world.config.boss,
    )
    boss.pos = Vec2(x, y)
    boss.vel = Vec2(0.0, 0.0)
    boss.heading = heading
    boss.hp = hp
    boss.max_hp = max(boss.max_hp, hp)
    boss.state = state
    boss.state_timer = 0.0
    boss.intro_remaining = intro_remaining
    boss.charge_cooldown_remaining = 0.0
    world.boss = boss
    world.entities.append(boss)
    return boss


# ---------------------------------------------------------------------------
# Boss.spawn 工厂
# ---------------------------------------------------------------------------


class TestBossSpawn:
    def test_boss_spawned_outside_world(self) -> None:
        rng = SeededRng(seed=1)
        boss = Boss.spawn(eid=0, world_size=(WORLD_W, WORLD_H), rng=rng)
        # 至少有一个轴在 [0, W] / [0, H] 之外
        outside_x = boss.pos.x < 0.0 or boss.pos.x > WORLD_W
        outside_y = boss.pos.y < 0.0 or boss.pos.y > WORLD_H
        assert outside_x or outside_y

    def test_boss_initial_fields(self) -> None:
        rng = SeededRng(seed=2)
        boss = Boss.spawn(eid=7, world_size=(WORLD_W, WORLD_H), rng=rng)
        assert boss.eid == 7
        assert boss.tier == BOSS_TIER
        assert boss.hp == BOSS_HP and boss.max_hp == BOSS_HP
        assert boss.alive is True
        assert boss.intro_remaining == pytest.approx(BOSS_INTRO_DURATION_S)
        assert boss.charge_cooldown_remaining == 0.0
        assert boss.bite_count == 0
        assert boss.enraged is False
        assert boss.state is None  # AI 第一帧把 None → PATROL
        assert boss.radius == pytest.approx(BOSS_RADIUS)

    def test_boss_picks_farthest_edge_from_player(self) -> None:
        # player 在屏幕左上角 → boss 应从右或下进入（距离 player 远的那一侧）
        rng = SeededRng(seed=3)
        boss = Boss.spawn(
            eid=0,
            world_size=(WORLD_W, WORLD_H),
            rng=rng,
            player_pos=Vec2(20.0, 20.0),
        )
        assert boss.pos.x > WORLD_W * 0.4 or boss.pos.y > WORLD_H * 0.4


# ---------------------------------------------------------------------------
# BossAI 状态机
# ---------------------------------------------------------------------------


class TestBossAI:
    def test_first_step_initializes_to_patrol(self) -> None:
        w = _new_world(seed=10)
        boss = _place_boss(w, 100.0, 100.0, state=None)  # type: ignore[arg-type]
        BossAI().step(boss, w, DT)
        assert boss.state is BossState.PATROL

    def test_patrol_to_chase_on_player_in_sense(self) -> None:
        w = _new_world(seed=11)
        _place_player(w, 200.0, 200.0)
        boss = _place_boss(w, 250.0, 200.0, state=BossState.PATROL)
        boss.state_timer = BOSS_PATROL_DURATION_S
        # 强制巡逻期结束后，player 距 boss 50px < BOSS_SENSE_RADIUS 380
        BossAI().step(boss, w, DT)
        assert boss.state is BossState.CHASE

    def test_patrol_stays_when_player_far(self) -> None:
        w = _new_world(seed=12)
        _place_player(w, 50.0, 50.0)
        boss = _place_boss(w, 1200.0, 600.0, state=BossState.PATROL)
        boss.state_timer = BOSS_PATROL_DURATION_S
        # 距离 ~ sqrt(1150^2 + 550^2) ≈ 1275 > sense_radius 380
        BossAI().step(boss, w, DT)
        assert boss.state is BossState.PATROL

    def test_chase_to_charge_windup_when_close(self) -> None:
        w = _new_world(seed=13)
        _place_player(w, 200.0, 200.0)
        # 距离 100 < BOSS_CHARGE_TRIGGER_DIST=220，冷却=0
        boss = _place_boss(w, 300.0, 200.0, state=BossState.CHASE)
        BossAI().step(boss, w, DT)
        assert boss.state is BossState.CHARGE_WINDUP

    def test_chase_does_not_charge_during_cooldown(self) -> None:
        w = _new_world(seed=14)
        _place_player(w, 200.0, 200.0)
        boss = _place_boss(w, 300.0, 200.0, state=BossState.CHASE)
        boss.charge_cooldown_remaining = 5.0
        BossAI().step(boss, w, DT)
        assert boss.state is BossState.CHASE

    def test_charge_windup_transitions_to_charge_after_windup_s(self) -> None:
        w = _new_world(seed=15)
        _place_player(w, 200.0, 200.0)
        boss = _place_boss(w, 350.0, 200.0, state=BossState.CHARGE_WINDUP)
        ai = BossAI()
        # 推进 windup_s + 一帧 余量
        steps = int(math.ceil(BOSS_CHARGE_WINDUP_S / DT)) + 2
        for _ in range(steps):
            ai.step(boss, w, DT)
            if boss.state is BossState.CHARGE:
                break
        assert boss.state is BossState.CHARGE
        # charge_dir 应被设置为非零单位向量（boss turn_rate=0.9 rad/s 限速，0.8s 内
        # 无法从 heading=0 转到 π，仅能转 0.72 rad；故只断言已锁定方向）
        assert boss.charge_dir.x ** 2 + boss.charge_dir.y ** 2 == pytest.approx(1.0, abs=1e-6)

    def test_charge_to_stunned_on_wall_hit(self) -> None:
        w = _new_world(seed=16)
        _place_player(w, 50.0, 200.0)  # player 在左侧 → boss 朝左冲
        boss = _place_boss(w, 100.0, 200.0, state=BossState.CHARGE)
        boss.charge_dir = Vec2(-1.0, 0.0)
        boss.heading = math.pi
        ai = BossAI()
        # 以最坏 chase_speed*1.6 推进，10s 内必撞左墙
        for _ in range(int(2.0 / DT)):
            ai.step(boss, w, DT)
            if boss.state is BossState.STUNNED:
                break
        assert boss.state is BossState.STUNNED
        # 撞墙后 pos 钳到边界
        assert boss.pos.x == 0.0

    def test_stunned_returns_to_chase_after_stun_s(self) -> None:
        w = _new_world(seed=17)
        _place_player(w, 200.0, 200.0)
        boss = _place_boss(w, 800.0, 400.0, state=BossState.STUNNED)
        ai = BossAI()
        steps = int(math.ceil(BOSS_STUNNED_DURATION_S / DT)) + 2
        for _ in range(steps):
            ai.step(boss, w, DT)
            if boss.state is not BossState.STUNNED:
                break
        assert boss.state is BossState.CHASE

    def test_enraged_when_hp_below_threshold(self) -> None:
        w = _new_world(seed=18)
        _place_player(w, 200.0, 200.0)
        # 放远，避免本帧立即被 CHASE→CHARGE_WINDUP 切换覆盖 CHASE 标识
        # max_hp=10, hp=2 → 0.2 < 0.3
        boss = _place_boss(w, 700.0, 200.0, state=BossState.CHASE)
        boss.max_hp = 10
        boss.hp = 2
        BossAI().step(boss, w, DT)
        assert boss.enraged is True
        assert boss.state is BossState.CHASE

    def test_enraged_remains_modifier_not_state(self) -> None:
        assert "ENRAGED" not in BossState.__members__

    def test_enraged_reduces_windup_duration(self) -> None:
        # windup 在 enraged 下缩短到 BOSS_ENRAGED_WINDUP_MUL 倍
        w = _new_world(seed=19)
        _place_player(w, 200.0, 200.0)
        boss = _place_boss(w, 350.0, 200.0, state=BossState.CHARGE_WINDUP)
        boss.enraged = True
        ai = BossAI()
        target_s = BOSS_CHARGE_WINDUP_S * BOSS_ENRAGED_WINDUP_MUL
        # 推进 target_s + 一帧 余量后必入 CHARGE
        steps = int(math.ceil(target_s / DT)) + 2
        # 但推进 target_s 之前不应入 CHARGE
        early_steps = max(1, int((target_s / DT) * 0.5))
        for _ in range(early_steps):
            ai.step(boss, w, DT)
        assert boss.state is BossState.CHARGE_WINDUP
        for _ in range(steps):
            ai.step(boss, w, DT)
            if boss.state is BossState.CHARGE:
                break
        assert boss.state is BossState.CHARGE


# ---------------------------------------------------------------------------
# 玩家 vs Boss 碰撞 / 复仇判定
# ---------------------------------------------------------------------------


class TestPlayerBossCollision:
    def test_player_below_tier4_dies_on_any_contact(self) -> None:
        w = _new_world(seed=20)
        _place_player(w, 400.0, 400.0, tier=2)
        boss = _place_boss(w, 400.0 + BOSS_RADIUS - 5.0, 400.0)
        CollisionSystem().step(w, DT)
        assert w.game_result is GameResult.DEAD
        assert w.player.alive is False
        assert w.stats["death_cause_tier"] == BOSS_TIER

    def test_intro_window_skips_collision(self) -> None:
        w = _new_world(seed=21)
        _place_player(w, 400.0, 400.0, tier=2)
        boss = _place_boss(w, 400.0, 400.0, intro_remaining=1.0)
        CollisionSystem().step(w, DT)
        assert w.game_result is None
        assert w.player.alive is True

    def test_tier4_player_bites_boss_from_tail(self) -> None:
        w = _new_world(seed=22)
        # boss 朝右 (heading=0) → 尾部在左
        _place_player(w, 400.0 - BOSS_RADIUS + 5.0, 400.0, tier=TIER_GIANT)
        boss = _place_boss(w, 400.0, 400.0, state=BossState.CHASE, heading=0.0)
        hp0 = boss.hp
        CollisionSystem().step(w, DT)
        assert boss.hp == hp0 - BOSS_BITE_DAMAGE
        assert boss.bite_count == 1
        assert boss.state is BossState.STUNNED
        assert w.player.alive is True
        assert w.player.invuln_remaining == pytest.approx(PLAYER_INVULN_AFTER_BITE_S)

    def test_tier4_player_dies_from_front_contact(self) -> None:
        w = _new_world(seed=23)
        # boss 朝右 (heading=0) → 正面在右
        _place_player(w, 400.0 + BOSS_RADIUS - 5.0, 400.0, tier=TIER_GIANT)
        boss = _place_boss(w, 400.0, 400.0, state=BossState.CHASE, heading=0.0)
        CollisionSystem().step(w, DT)
        assert w.game_result is GameResult.DEAD

    def test_tier4_player_bites_during_stunned_any_angle(self) -> None:
        w = _new_world(seed=24)
        # boss 朝右；玩家从正面接触，但 boss STUNNED → 也算咬
        _place_player(w, 400.0 + BOSS_RADIUS - 5.0, 400.0, tier=TIER_GIANT)
        boss = _place_boss(w, 400.0, 400.0, state=BossState.STUNNED, heading=0.0)
        hp0 = boss.hp
        CollisionSystem().step(w, DT)
        assert boss.hp == hp0 - BOSS_BITE_DAMAGE
        assert w.player.alive is True

    def test_boss_killed_when_hp_zero(self) -> None:
        w = _new_world(seed=25)
        _place_player(w, 400.0 - BOSS_RADIUS + 5.0, 400.0, tier=TIER_GIANT)
        boss = _place_boss(w, 400.0, 400.0, state=BossState.STUNNED, heading=0.0, hp=1)
        CollisionSystem().step(w, DT)
        # hp 归零 → boss.alive=False；on_boss_killed 把 world.boss 置 None
        assert boss.alive is False
        assert w.boss is None
        assert w.stats["boss_killed"] == 1
        # 终态 game_result 由 director 在 REVENGE 段写入（这里仅 collision）
        assert w.game_result is None

    def test_invuln_throttles_repeated_boss_bites(self) -> None:
        w = _new_world(seed=250)
        _place_player(w, 400.0 + BOSS_RADIUS - 5.0, 400.0, tier=TIER_GIANT)
        boss = _place_boss(w, 400.0, 400.0, state=BossState.STUNNED, heading=0.0)
        CollisionSystem().step(w, DT)
        hp_after_first_bite = boss.hp
        CollisionSystem().step(w, DT)
        assert boss.hp == hp_after_first_bite
        assert boss.bite_count == 1

    def test_tier4_same_center_with_boss_is_dead_not_tail_bite(self) -> None:
        w = _new_world(seed=251)
        _place_player(w, 400.0, 400.0, tier=TIER_GIANT)
        boss = _place_boss(w, 400.0, 400.0, state=BossState.CHASE, heading=0.0)
        CollisionSystem().step(w, DT)
        assert w.game_result is GameResult.DEAD
        assert boss.bite_count == 0

    def test_invuln_protects_from_lethal_contact(self) -> None:
        w = _new_world(seed=26)
        _place_player(w, 400.0, 400.0, tier=2)
        w.player.invuln_remaining = 1.0
        boss = _place_boss(w, 400.0 + BOSS_RADIUS - 5.0, 400.0)
        CollisionSystem().step(w, DT)
        # invuln 期间应忽略致死接触
        assert w.game_result is None
        assert w.player.alive is True


# ---------------------------------------------------------------------------
# Tier-4 警示
# ---------------------------------------------------------------------------


class TestTier4Warning:
    def test_warning_set_when_tier4_fish_present_and_player_below(self) -> None:
        w = _new_world(seed=30)
        _place_player(w, 400.0, 400.0, tier=2)
        _add_fish(w, tier=4, pos=Vec2(800.0, 400.0))
        CollisionSystem().step(w, DT)
        assert w.tier4_warning is True

    def test_warning_off_when_player_already_tier4(self) -> None:
        w = _new_world(seed=31)
        _place_player(w, 400.0, 400.0, tier=4)
        _add_fish(w, tier=4, pos=Vec2(800.0, 400.0))
        CollisionSystem().step(w, DT)
        assert w.tier4_warning is False

    def test_warning_off_when_no_tier4_fish(self) -> None:
        w = _new_world(seed=32)
        _place_player(w, 400.0, 400.0, tier=2)
        _add_fish(w, tier=2, pos=Vec2(800.0, 400.0))
        CollisionSystem().step(w, DT)
        assert w.tier4_warning is False

    def test_warning_off_for_offscreen_tier4_fish(self) -> None:
        w = _new_world(seed=33)
        _place_player(w, 400.0, 400.0, tier=2)
        _add_fish(w, tier=4, pos=Vec2(-10.0, 400.0))
        CollisionSystem().step(w, DT)
        assert w.tier4_warning is False

    def test_warning_exposed_in_snapshot(self) -> None:
        w = _new_world(seed=34)
        _place_player(w, 400.0, 400.0, tier=2)
        _add_fish(w, tier=4, pos=Vec2(800.0, 400.0))
        CollisionSystem().step(w, DT)
        assert w.snapshot()["tier4_warning"] is True


# ---------------------------------------------------------------------------
# LevelDirector：BOSS / REVENGE
# ---------------------------------------------------------------------------


class TestDirectorBossPhase:
    def test_director_spawns_boss_on_entering_boss_phase(self) -> None:
        w = _new_world(seed=40)
        # 直接强制 PRESSURE → BOSS：把 player.tier 推到 2
        _place_player(w, 600.0, 400.0, tier=2)
        # 跑到 PRESSURE 需要先经过 WARMUP duration；快进 director 状态
        d = w.director
        d.current_phase = Phase.PRESSURE
        d.phase_elapsed_s = 0.0
        # PRESSURE → BOSS：player.tier>=2 触发
        d.step(w, DT)
        # 此时应已切到 BOSS 且 spawn 了 boss
        assert d.current_phase is Phase.BOSS
        assert w.boss is not None
        assert w.boss.alive is True

    def test_director_revenge_after_boss_dies(self) -> None:
        w = _new_world(seed=41)
        _place_player(w, 600.0, 400.0, tier=2)
        d = w.director
        d.current_phase = Phase.PRESSURE
        d.step(w, DT)
        assert d.current_phase is Phase.BOSS
        assert w.boss is not None
        # 模拟 boss 被杀
        w.boss.alive = False
        w.boss = None
        d.step(w, DT)
        assert d.current_phase is Phase.REVENGE

    def test_revenge_timeout_yields_victory(self) -> None:
        w = _new_world(seed=42)
        w.config.phases[Phase.REVENGE].duration_s = REVENGE_PHASE_TIMEOUT_S
        _place_player(w, 600.0, 400.0, tier=2)
        d = w.director
        d.current_phase = Phase.PRESSURE
        d.step(w, DT)
        assert d.current_phase is Phase.BOSS
        # 杀死 boss
        w.boss.alive = False
        w.boss = None
        d.step(w, DT)
        assert d.current_phase is Phase.REVENGE
        d.step(w, DT)
        assert w.game_result is None
        # 推进 REVENGE_PHASE_TIMEOUT_S
        d.phase_elapsed_s = REVENGE_PHASE_TIMEOUT_S + 1.0
        d.step(w, DT)
        assert w.game_result is GameResult.VICTORY

    def test_boss_hp_zero_world_step_reaches_victory_after_revenge_window(self) -> None:
        w = _new_world(seed=43)
        w.config.phases[Phase.REVENGE].duration_s = REVENGE_PHASE_TIMEOUT_S
        _place_player(w, 400.0 - BOSS_RADIUS + 5.0, 400.0, tier=TIER_GIANT)
        boss = _place_boss(w, 400.0, 400.0, state=BossState.STUNNED, heading=0.0, hp=1)
        w.director.current_phase = Phase.BOSS
        w.director._boss_was_present = True

        w.step(DT, InputFrame())
        assert boss.alive is False
        assert w.boss is None
        assert w.director.current_phase is Phase.REVENGE
        assert w.game_result is None

        w.director.phase_elapsed_s = REVENGE_PHASE_TIMEOUT_S
        w.step(DT, InputFrame())
        assert w.game_result is GameResult.VICTORY


# ---------------------------------------------------------------------------
# 决定性
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_hash_sequence(self) -> None:
        def run(seed: int) -> list[str]:
            w = World(LevelConfig.default(), SeededRng(seed=seed))
            # 注入 boss 远离 player，避免一帧内被吃；保留 intro 让 boss 不参与碰撞
            _place_boss(
                w,
                100.0,
                100.0,
                state=BossState.PATROL,
                intro_remaining=10.0,
            )
            inp = _NullInput()
            hashes = []
            for _ in range(120):
                fr = inp.poll(w.snapshot())
                w.step(DT, fr)
                hashes.append(w.snapshot_hash())
            return hashes

        a = run(seed=99)
        b = run(seed=99)
        assert a == b
        c = run(seed=100)
        assert a != c
