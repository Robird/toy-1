"""fish/systems/collision.py — 碰撞检测 + 吃/被吃判定 + 同 tier 弹性反弹（M3-05/M3-07）。

依据：
- fish-doc/mvp/01-core-loop.md §3（吃 / 被吃判定 + 同 Tier 弹开 + DEAD）
- fish-doc/mvp/02-fish-ecosystem.md §3（同 tier 弹开 + 鱼之间不做硬碰撞，仅同
  tier 例外作为 MVP 简化避免群体卡死）
- fish-doc/mvp/03-boss.md §4（player ↔ boss 表：Tier-4 + 尾部 240° → 咬 boss；
  Tier-4 + 正面 120° → 玩家死；Tier<4 任意接触 → 玩家死；STUNNED 期任意角咬）
- 主会话裁决（progress.md「M3 实施期发现」#13）：``can_eat(eater, victim) =
  eater.tier >= victim.tier - 1``，即「以小搏大一档」。

判定优先级（同时满足时按顺序取首个匹配，使同 tier 永远走 bounce 而非互吃）：
  1. ``player.tier == fish.tier`` → 弹性反弹
  2. ``can_eat(player, fish)`` → player 吃 fish（含 player.tier == fish.tier-1
     的「以小搏大一档」边）
  3. ``can_eat(fish, player)`` → DEAD（在前两条之后只剩
     ``fish.tier >= player.tier + 2`` 的情况）

NPC 鱼之间：MVP 不互吃（避免群体灭绝），仅同 tier 弹开；不同 tier 互不影响。

Boss 与 player（M3-07）：见 ``_resolve_player_boss``；Boss 与普通鱼 / Boss 与
墙的逻辑由 ``BossAI`` 自行处理。

副作用：每帧维护 ``world.tier4_warning`` 标志（任一 Tier-4 fish 在场且玩家
tier < 4 时为 True，渲染层 M3-08 据此显示告警）。

遍历顺序：fish 列表始终按 ``eid`` 升序遍历；fish-fish 配对按 ``(i, j)``
``i < j`` 走，保证 snapshot_hash 决定性（契约 #3）。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from toy_engine.geom import Vec2, angle_in_arc, circle_circle_overlap, circle_circle_penetration

from fish.config.constants import (
    BOSS_TAIL_ARC_HALF_DEG,
    TIER_GIANT,
    WORLD_H,
    WORLD_W,
)

if TYPE_CHECKING:
    from fish.entities.base import Entity
    from fish.entities.boss import Boss
    from fish.entities.player import Player
    from fish.world import World


__all__ = ["CollisionSystem", "can_eat"]


# 推开后再额外抬一点点，避免下一帧仍贴在 (rsum + eps) 边界上反复触发判定。
_BOUNCE_PUSH_EPSILON: float = 1e-6

_TAIL_HALF_RAD: float = math.radians(BOSS_TAIL_ARC_HALF_DEG)


def can_eat(eater: "Entity", victim: "Entity") -> bool:
    """是否可以吃：``eater.tier >= victim.tier - 1``（progress.md 发现 #13）。

    与 fish-doc/01 §3 原文「self > other」相比放宽一档：让 Tier-0 玩家也
    能吃 Tier-1 小鱼，开局不至于卡死。注意此函数对同 tier 也返回 True，
    需在调用方先优先处理同 tier bounce 才能得到符合 fish-doc 语义的结果。
    """
    return int(eater.tier) >= int(victim.tier) - 1


class CollisionSystem:
    """player ↔ fish + fish ↔ fish（仅同 tier）+ player ↔ boss 碰撞 / 吃 / 弹开判定。

    本类不直接修改 World 的统计 / 终态字段；通过 ``world.on_fish_eaten``
    / ``world.on_player_eaten`` / ``world.on_boss_bitten`` /
    ``world.on_boss_killed`` hook 让 World 自行落实。这样 GrowthSystem
    / metrics / 手感粒子（M3-09）都能复用同一组 hook。
    """

    def step(self, world: "World", dt: float) -> None:
        if dt <= 0.0:
            return

        # 玩家无敌剩余时间递减（每帧推进一次，含 game_result 已写入的帧；让
        # snapshot 显示的剩余时间稳定衰减）
        if world.player.invuln_remaining > 0.0:
            world.player.invuln_remaining = max(
                0.0, world.player.invuln_remaining - dt
            )

        # Tier-4 警示：任一 Tier-4 fish 在场 + player.tier < 4
        world.tier4_warning = bool(
            int(world.player.tier) < TIER_GIANT
            and any(
                f.alive
                and int(f.tier) == TIER_GIANT
                and 0.0 <= f.pos.x <= float(WORLD_W)
                and 0.0 <= f.pos.y <= float(WORLD_H)
                for f in world.fishes
            )
        )

        if world.game_result is not None:
            # 终态后不再产生新的吃/被吃事件；但同 tier 鱼群仍可能黏在一起，
            # 留待下一步 (M3-08/09) 再决定是否继续 bounce。MVP：直接 return。
            return

        player = world.player
        fishes_sorted = sorted(world.fishes, key=lambda f: f.eid)

        # 1) player vs each fish
        if player.alive:
            for fish in fishes_sorted:
                if not fish.alive:
                    continue
                if not circle_circle_overlap(
                    player.pos, player.radius, fish.pos, fish.radius
                ):
                    continue

                if player.tier == fish.tier:
                    _elastic_bounce_same_tier(player, fish)
                elif can_eat(player, fish):
                    fish.alive = False
                    world.on_fish_eaten(player, fish)
                elif can_eat(fish, player):
                    # 等价于 fish.tier >= player.tier + 2
                    if player.invuln_remaining > 0.0:
                        # 无敌期间被「应当致命」的接触触发：忽略而非死亡
                        continue
                    world.on_player_eaten(fish)
                    # 玩家已死，本帧后续碰撞也不再判定；避免 DEAD 帧继续改变
                    # fish-fish 位置 / 速度，让「死亡瞬间」snapshot 更稳定。
                    return

        # 2) fish vs fish（仅同 tier，仅 bounce）
        # 重新过滤一次活鱼（player 那一遍可能淘汰过几条）
        live = [f for f in fishes_sorted if f.alive]
        n = len(live)
        for i in range(n):
            a = live[i]
            for j in range(i + 1, n):
                b = live[j]
                if a.tier != b.tier:
                    continue
                if not circle_circle_overlap(a.pos, a.radius, b.pos, b.radius):
                    continue
                _elastic_bounce_same_tier(a, b)

        # 3) player vs boss（M3-07）
        boss = getattr(world, "boss", None)
        if boss is not None and boss.alive and player.alive:
            self._resolve_player_boss(world, player, boss)

    # ------------------------------------------------------------------
    # player ↔ boss 判定（fish-doc/03 §4）
    # ------------------------------------------------------------------
    def _resolve_player_boss(self, world: "World", player: "Player", boss: "Boss") -> None:
        # 进场无碰撞窗口
        if boss.intro_remaining > 0.0:
            return
        if not circle_circle_overlap(player.pos, player.radius, boss.pos, boss.radius):
            return

        from fish.ai.boss_ai import BossState

        pt = int(player.tier)
        bs = boss.state

        # Tier < 4：任意接触均死亡（除非无敌窗口）
        if pt < TIER_GIANT:
            if player.invuln_remaining > 0.0:
                return
            world.on_player_eaten_by_boss(boss)
            return

        # Tier == 4：分尾部弧 / 正面弧 / STUNNED
        # 无敌窗口既保护玩家不被连撞致死，也节流连续重叠时的多次咬击。
        if player.invuln_remaining > 0.0:
            return

        if bs is BossState.STUNNED:
            self._bite_boss(world, player, boss)
            return

        # 计算玩家相对 boss 的方位角（boss → player）；尾部中心 = heading + π。
        # 二者同心或角度非有限时，方位无定义，按危险接触处理而不是误判为尾咬。
        dx = player.pos.x - boss.pos.x
        dy = player.pos.y - boss.pos.y
        if not (
            math.isfinite(dx)
            and math.isfinite(dy)
            and math.isfinite(boss.heading)
            and dx * dx + dy * dy > 1e-18
        ):
            world.on_player_eaten_by_boss(boss)
            return

        rel = math.atan2(dy, dx)
        tail_center = boss.heading + math.pi
        if angle_in_arc(rel, tail_center, _TAIL_HALF_RAD):
            self._bite_boss(world, player, boss)
            return

        # 否则视为正面（含侧面）接触：玩家死
        # （fish-doc/03 §4 「正面 120°」严格说是 heading±60°，但 240° 尾部
        # 已覆盖剩余范围，所以这里非尾部即"正面/侧面"危险区）
        world.on_player_eaten_by_boss(boss)

    def _bite_boss(self, world: "World", player: "Player", boss: "Boss") -> None:
        from fish.ai.boss_ai import BossState
        from fish.config.constants import BOSS_BITE_DAMAGE, PLAYER_INVULN_AFTER_BITE_S

        boss.hp = max(0, boss.hp - BOSS_BITE_DAMAGE)
        boss.bite_count += 1
        # 进入 STUNNED（无论之前在哪个状态）；为玩家提供下一次稳定咬合窗口
        boss.state = BossState.STUNNED
        boss.state_timer = 0.0
        boss.vel = Vec2(0.0, 0.0)

        player.invuln_remaining = max(
            player.invuln_remaining, float(PLAYER_INVULN_AFTER_BITE_S)
        )

        world.on_boss_bitten(player, boss)
        if boss.hp <= 0:
            boss.alive = False
            world.on_boss_killed(boss)


# ---------------------------------------------------------------------------
# 同 tier 等质量弹性反弹
# ---------------------------------------------------------------------------


def _elastic_bounce_same_tier(a: "Entity", b: "Entity") -> None:
    """把 ``a`` / ``b`` 按穿透深度沿法向各推一半，再交换法向速度分量。

    采用「同 tier ≈ 等质量」假设；切向速度保留，正常情况下弹开后下一帧
    AI / Movement 才会接管。仅当二者在法向上仍在「靠近」（相对法向速度
    指向接触面）时才交换速度，避免分离瞬间又反向粘住的振荡。

    fish-doc/02 §3 仅给出「不互伤、互相弹开」与「速度衰减 0.7」的边界反射
    系数；同 tier 之间的弹开力度细则未指定，MVP 取最朴素的等质量等效弹性
    碰撞模型，后续 M4 调参可在此处加入耗散系数。
    """
    pen = circle_circle_penetration(a.pos, a.radius, b.pos, b.radius)
    if pen is None:
        return
    push_dir, depth = pen  # push_dir from b to a
    if not (
        math.isfinite(push_dir.x)
        and math.isfinite(push_dir.y)
        and math.isfinite(depth)
    ):
        return
    half = max(0.0, depth * 0.5) + _BOUNCE_PUSH_EPSILON
    a.pos = Vec2(a.pos.x + push_dir.x * half, a.pos.y + push_dir.y * half)
    b.pos = Vec2(b.pos.x - push_dir.x * half, b.pos.y - push_dir.y * half)

    nx, ny = push_dir.x, push_dir.y
    if not (
        math.isfinite(a.vel.x)
        and math.isfinite(a.vel.y)
        and math.isfinite(b.vel.x)
        and math.isfinite(b.vel.y)
    ):
        return
    va_n = a.vel.x * nx + a.vel.y * ny
    vb_n = b.vel.x * nx + b.vel.y * ny
    # 法向上 a 的速度 < b 的速度 = 二者还在沿法向靠近（注意 n 指向 b→a）。
    if va_n - vb_n < 0.0:
        delta = vb_n - va_n  # > 0
        a.vel = Vec2(a.vel.x + nx * delta, a.vel.y + ny * delta)
        b.vel = Vec2(b.vel.x - nx * delta, b.vel.y - ny * delta)
