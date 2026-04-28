"""fish/ai/boss_ai.py — Boss 五个核心状态 + ENRAGED 修饰位（M3-07）。

按 fish-doc/mvp/03-boss.md §3 实现：

    PATROL → CHASE → CHARGE_WINDUP → CHARGE → STUNNED → CHASE → ...

外加 ENRAGED 叠加：HP 比例 < ``BOSS_ENRAGE_HP_RATIO`` 后 ``boss.enraged``
持续为 True；它不是独立 FSM 状态，而是修饰 CHASE/CHARGE 行为的布尔位：
charge 冷却 × ``BOSS_ENRAGED_COOLDOWN_MUL``，windup 时长 ×
``BOSS_ENRAGED_WINDUP_MUL``，sense_radius × ``BOSS_ENRAGED_SENSE_MUL``。

运动学：
- BossAI 直接读写 ``boss.pos / boss.vel / boss.heading``。``MovementSystem``
  会跳过 boss（见 fish/systems/movement.py），避免 CHARGE 撞墙时被
  ``WALL_BOUNCE_DAMPING`` 反射掉而错过 STUNNED 触发。
- CHARGE 撞墙：本帧 boss.pos 越过 [0, W]×[0, H] 任意边 → 钳回边界 +
  state → STUNNED + vel = 0。
- 其它状态撞墙：钳到边界，沿法向反向（与 MovementSystem 同款 0.7 衰减）
  并继续在场内移动。

不在本步实现：进场视觉警示（M3-08）、蓄力箭头粒子（M3-09）、bot 联调
（M3-10）。Boss 与 player 的吃/被咬判定在 ``fish/systems/collision.py``。
"""

from __future__ import annotations

import enum
import math
from typing import TYPE_CHECKING

from toy_engine.geom import Vec2, rotate_toward

from fish.config.constants import (
    BOSS_CHARGE_DURATION_S,
    BOSS_CHARGE_SPEED_MUL,
    BOSS_CHARGE_TRIGGER_DIST,
    BOSS_CHARGE_WINDUP_S,
    BOSS_ENRAGE_HP_RATIO,
    BOSS_ENRAGED_COOLDOWN_MUL,
    BOSS_ENRAGED_SENSE_MUL,
    BOSS_ENRAGED_WINDUP_MUL,
    BOSS_PATROL_DURATION_S,
    BOSS_PATROL_SPEED_RATIO,
    BOSS_PATROL_TURN_INTERVAL_S,
    BOSS_STUNNED_DURATION_S,
    WALL_BOUNCE_DAMPING,
    WORLD_H,
    WORLD_W,
)

if TYPE_CHECKING:
    from fish.entities.boss import Boss
    from fish.world import World


__all__ = ["BossState", "BossAI"]


class BossState(enum.Enum):
    """Boss FSM 五个核心状态；``boss.enraged`` 是叠加修饰位。"""

    PATROL = "PATROL"
    CHASE = "CHASE"
    CHARGE_WINDUP = "CHARGE_WINDUP"
    CHARGE = "CHARGE"
    STUNNED = "STUNNED"


class BossAI:
    """无状态控制器；每帧对 ``world.boss`` 调用 ``step``。

    决策只读 ``world.player`` / ``boss.*`` 公有字段；写
    ``boss.state / state_timer / heading / vel / pos / charge_*``。
    所有随机决策（PATROL 转向）走 ``boss.rng`` 保证 snapshot_hash 决定性。
    """

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def step(self, boss: "Boss", world: "World", dt: float) -> None:
        if not boss.alive or dt <= 0.0:
            return

        # 第一帧：把 None → PATROL（Boss 工厂留给 AI 初始化以便测试观察）
        if boss.state is None:
            boss.state = BossState.PATROL
            boss.state_timer = 0.0

        # ENRAGED 叠加：一旦触发持续生效；不改变 BossState，只改变参数倍率。
        if (not boss.enraged) and boss.max_hp > 0 and boss.hp / boss.max_hp < BOSS_ENRAGE_HP_RATIO:
            boss.enraged = True

        # 进场无碰撞窗口递减（CollisionSystem 自行判读）
        if boss.intro_remaining > 0.0:
            boss.intro_remaining = max(0.0, boss.intro_remaining - dt)

        # CHARGE 冷却递减（即使在 PATROL/STUNNED 也算冷却进度）
        if boss.charge_cooldown_remaining > 0.0:
            boss.charge_cooldown_remaining = max(0.0, boss.charge_cooldown_remaining - dt)

        boss.state_timer += dt

        # 状态分派
        st = boss.state
        if st is BossState.PATROL:
            self._step_patrol(boss, world, dt)
        elif st is BossState.CHASE:
            self._step_chase(boss, world, dt)
        elif st is BossState.CHARGE_WINDUP:
            self._step_charge_windup(boss, world, dt)
        elif st is BossState.CHARGE:
            self._step_charge(boss, world, dt)
        elif st is BossState.STUNNED:
            self._step_stunned(boss, world, dt)

    # ------------------------------------------------------------------
    # 状态：PATROL
    # ------------------------------------------------------------------
    def _step_patrol(self, boss: "Boss", world: "World", dt: float) -> None:
        # 首次进场后强制 PATROL 8s；之后才按 sense_radius 进入 CHASE。
        if boss.state_timer >= BOSS_PATROL_DURATION_S and self._player_in_sense(boss, world):
            self._enter_chase(boss)
            return

        # 周期性重选随机偏航（rng 决定）
        rng = boss.rng
        if rng is not None and boss.state_timer % max(1e-6, BOSS_PATROL_TURN_INTERVAL_S) < dt:
            jitter = rng.uniform(-1.0, 1.0)
            target_heading = boss.heading + jitter
        else:
            target_heading = boss.heading

        max_step = boss.turn_rate * dt
        boss.heading = rotate_toward(boss.heading, target_heading, max_step)
        speed = boss.chase_speed * BOSS_PATROL_SPEED_RATIO
        boss.vel = Vec2.from_angle(boss.heading, speed)
        self._integrate_with_wall_reflect(boss, dt)

    # ------------------------------------------------------------------
    # 状态：CHASE（ENRAGED 通过 boss.enraged 修饰参数）
    # ------------------------------------------------------------------
    def _step_chase(self, boss: "Boss", world: "World", dt: float) -> None:
        player = world.player
        # 朝玩家
        dx = player.pos.x - boss.pos.x
        dy = player.pos.y - boss.pos.y
        dist = math.hypot(dx, dy)
        if dist > 1e-9 and math.isfinite(dx) and math.isfinite(dy):
            target_heading = math.atan2(dy, dx)
            max_step = boss.turn_rate * dt
            boss.heading = rotate_toward(boss.heading, target_heading, max_step)

        boss.vel = Vec2.from_angle(boss.heading, boss.chase_speed)
        self._integrate_with_wall_reflect(boss, dt)

        # 触发 CHARGE_WINDUP：距离够近 + 冷却就绪
        if dist < BOSS_CHARGE_TRIGGER_DIST and boss.charge_cooldown_remaining <= 0.0:
            boss.state = BossState.CHARGE_WINDUP
            boss.state_timer = 0.0
            boss.vel = Vec2(0.0, 0.0)

    # ------------------------------------------------------------------
    # 状态：CHARGE_WINDUP
    # ------------------------------------------------------------------
    def _step_charge_windup(self, boss: "Boss", world: "World", dt: float) -> None:
        # 蓄力期间锁速度=0；持续转向锁定玩家方向（蓄力快结束时拍下）
        boss.vel = Vec2(0.0, 0.0)
        player = world.player
        dx = player.pos.x - boss.pos.x
        dy = player.pos.y - boss.pos.y
        if dx * dx + dy * dy > 1e-18 and math.isfinite(dx) and math.isfinite(dy):
            target_heading = math.atan2(dy, dx)
            max_step = boss.turn_rate * dt
            boss.heading = rotate_toward(boss.heading, target_heading, max_step)

        windup_s = BOSS_CHARGE_WINDUP_S * (BOSS_ENRAGED_WINDUP_MUL if boss.enraged else 1.0)
        if boss.state_timer >= windup_s:
            # 拍下方向 → 进入 CHARGE
            boss.charge_dir = Vec2(math.cos(boss.heading), math.sin(boss.heading))
            boss.state = BossState.CHARGE
            boss.state_timer = 0.0

    # ------------------------------------------------------------------
    # 状态：CHARGE
    # ------------------------------------------------------------------
    def _step_charge(self, boss: "Boss", world: "World", dt: float) -> None:
        speed = boss.chase_speed * BOSS_CHARGE_SPEED_MUL
        boss.vel = Vec2(boss.charge_dir.x * speed, boss.charge_dir.y * speed)
        # 朝向跟随冲刺方向（视觉一致性）
        if boss.charge_dir.x != 0.0 or boss.charge_dir.y != 0.0:
            boss.heading = math.atan2(boss.charge_dir.y, boss.charge_dir.x)

        # 直接推进位置；越界即 STUNNED（不反射）
        new_x = boss.pos.x + boss.vel.x * dt
        new_y = boss.pos.y + boss.vel.y * dt
        hit_wall = (
            new_x <= 0.0 or new_x >= float(WORLD_W)
            or new_y <= 0.0 or new_y >= float(WORLD_H)
        )
        if hit_wall:
            new_x = max(0.0, min(float(WORLD_W), new_x))
            new_y = max(0.0, min(float(WORLD_H), new_y))
            boss.pos = Vec2(new_x, new_y)
            self._enter_stunned(boss)
            return
        boss.pos = Vec2(new_x, new_y)

        # 时间到 → 回 CHASE；冷却开始
        if boss.state_timer >= BOSS_CHARGE_DURATION_S:
            self._enter_chase(boss)
            cd = boss.charge_cooldown * (BOSS_ENRAGED_COOLDOWN_MUL if boss.enraged else 1.0)
            boss.charge_cooldown_remaining = max(boss.charge_cooldown_remaining, cd)

    # ------------------------------------------------------------------
    # 状态：STUNNED
    # ------------------------------------------------------------------
    def _step_stunned(self, boss: "Boss", world: "World", dt: float) -> None:
        boss.vel = Vec2(0.0, 0.0)
        if boss.state_timer >= BOSS_STUNNED_DURATION_S:
            self._enter_chase(boss)

    # ------------------------------------------------------------------
    # 切换辅助
    # ------------------------------------------------------------------
    def _enter_chase(self, boss: "Boss") -> None:
        boss.state = BossState.CHASE
        boss.state_timer = 0.0
        boss.vel = Vec2(0.0, 0.0)

    def _enter_stunned(self, boss: "Boss") -> None:
        boss.state = BossState.STUNNED
        boss.state_timer = 0.0
        boss.vel = Vec2(0.0, 0.0)
        # CHARGE 结束（无论时间到 / 撞墙）冷却开始
        cd = boss.charge_cooldown * (BOSS_ENRAGED_COOLDOWN_MUL if boss.enraged else 1.0)
        boss.charge_cooldown_remaining = max(boss.charge_cooldown_remaining, cd)

    # ------------------------------------------------------------------
    # 感知 + 运动学辅助
    # ------------------------------------------------------------------
    def _player_in_sense(self, boss: "Boss", world: "World") -> bool:
        player = world.player
        if not player.alive:
            return False
        dx = player.pos.x - boss.pos.x
        dy = player.pos.y - boss.pos.y
        r = boss.sense_radius * (BOSS_ENRAGED_SENSE_MUL if boss.enraged else 1.0)
        if not (math.isfinite(dx) and math.isfinite(dy) and math.isfinite(r)):
            return False
        return dx * dx + dy * dy <= r * r

    @staticmethod
    def _integrate_with_wall_reflect(boss: "Boss", dt: float) -> None:
        """非 CHARGE 状态下的 pos += vel*dt + 边界反射（同 MovementSystem 风格）。"""
        x = boss.pos.x + boss.vel.x * dt
        y = boss.pos.y + boss.vel.y * dt
        vx, vy = boss.vel.x, boss.vel.y
        if x <= 0.0:
            x = 0.0
            if vx < 0.0:
                vx = -vx * WALL_BOUNCE_DAMPING
        elif x >= float(WORLD_W):
            x = float(WORLD_W)
            if vx > 0.0:
                vx = -vx * WALL_BOUNCE_DAMPING
        if y <= 0.0:
            y = 0.0
            if vy < 0.0:
                vy = -vy * WALL_BOUNCE_DAMPING
        elif y >= float(WORLD_H):
            y = float(WORLD_H)
            if vy > 0.0:
                vy = -vy * WALL_BOUNCE_DAMPING
        boss.pos = Vec2(x, y)
        boss.vel = Vec2(vx, vy)
