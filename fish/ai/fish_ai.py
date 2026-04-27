"""fish/ai/fish_ai.py — 普通鱼 AI（M3-04）。

实现 fish-doc/mvp/02-fish-ecosystem.md §2 描述的 FSM（WANDER/FLEE/CHASE）的
**MVP 简化版**：

- FLEE：``player.tier > fish.tier`` 且玩家在 ``FISH_FLEE_RADIUS[tier]`` 内
- CHASE：``player.tier < fish.tier`` 且玩家在 ``FISH_CHASE_RADIUS[tier]`` 内
- WANDER：其它情况；每 ``WANDER_TURN_INTERVAL_S`` 秒重选一次随机偏航，
  巡航速度 = ``WANDER_SPEED_RATIO * fish.max_speed``

文档 §2 的完整版包含 ``aggression`` 标志与 ``flee_radius * 1.5`` 的滞回阈值；
MVP 用上述简化版本，足以让 bot 跑分有梯度区分；M4 调参时再补滞回。

群行为（§4）：MVP **只做 separation**——同 tier 鱼之间 ``circle_circle_overlap``
检出半径 1.5x 重叠时给一个推开速度。alignment / cohesion 留 M4。
"""

from __future__ import annotations

import enum
import math
from typing import TYPE_CHECKING

from toy_engine.geom import Vec2, circle_circle_overlap, rotate_toward

from fish.config.constants import (
    FISH_CHASE_RADIUS,
    FISH_FLEE_RADIUS,
    FISH_SEPARATION_OVERLAP_MUL,
    FISH_SEPARATION_PUSH_SPEED,
    WANDER_HEADING_JITTER_RAD,
    WANDER_SPEED_RATIO,
    WANDER_TURN_INTERVAL_S,
)

if TYPE_CHECKING:
    from fish.entities.fish import Fish
    from fish.world import World


__all__ = ["FishAIState", "FishAI"]


class FishAIState(enum.Enum):
    """FishAI 三态。名称用于 snapshot 序列化（``state.name``）。"""

    WANDER = "WANDER"
    FLEE = "FLEE"
    CHASE = "CHASE"


class FishAI:
    """无状态控制器：每帧对每条 fish 调用 ``step``。

    决策只读 ``world.player`` 与 ``world.fishes``；写 ``fish.heading``、
    ``fish.vel``、``fish.state``、``fish.state_timer``。所有随机决策都走
    ``fish.rng``，保证 snapshot_hash 决定性（契约 #3）。
    """

    def step(self, fish: "Fish", world: "World", dt: float) -> None:
        if not fish.alive or dt <= 0.0:
            return

        # 1) 状态机切换（基于 player tier 差 + 距离）
        new_state = self._decide_state(fish, world)
        if new_state is not fish.state:
            fish.state = new_state
            fish.state_timer = 0.0
        else:
            fish.state_timer += dt

        # 2) 由当前状态决定目标 heading 与目标速度
        target_heading, target_speed = self._target(fish, world)

        # 3) 限速旋转
        max_step = fish.turn_rate_rad_s * dt
        fish.heading = rotate_toward(fish.heading, target_heading, max_step)

        # 4) 设速度
        fish.vel = Vec2.from_angle(fish.heading, target_speed)

        # 5) Separation（仅同 tier）
        self._apply_separation(fish, world)

    # ------------------------------------------------------------------
    # FSM
    # ------------------------------------------------------------------
    @staticmethod
    def _decide_state(fish: "Fish", world: "World") -> FishAIState:
        player = world.player
        if not player.alive:
            return FishAIState.WANDER
        dx = player.pos.x - fish.pos.x
        dy = player.pos.y - fish.pos.y
        dist_sq = dx * dx + dy * dy
        if player.tier > fish.tier:
            r = FISH_FLEE_RADIUS[fish.tier]
            if dist_sq <= r * r:
                return FishAIState.FLEE
        elif player.tier < fish.tier:
            r = FISH_CHASE_RADIUS[fish.tier]
            if dist_sq <= r * r:
                return FishAIState.CHASE
        return FishAIState.WANDER

    @staticmethod
    def _target(fish: "Fish", world: "World") -> tuple[float, float]:
        """返回 (target_heading_rad, target_speed_px_s)。"""
        player = world.player
        dx = player.pos.x - fish.pos.x
        dy = player.pos.y - fish.pos.y
        if fish.state is FishAIState.FLEE:
            # 朝远离 player 的方向
            return (
                FishAI._safe_heading_from_delta(-dx, -dy, fish.heading),
                fish.max_speed,
            )
        if fish.state is FishAIState.CHASE:
            # 朝 player
            return (FishAI._safe_heading_from_delta(dx, dy, fish.heading), fish.max_speed)
        # WANDER：每 WANDER_TURN_INTERVAL_S 秒重选偏航
        rng = fish.rng
        if rng is not None and fish.state_timer >= WANDER_TURN_INTERVAL_S:
            jitter = rng.uniform(-WANDER_HEADING_JITTER_RAD, WANDER_HEADING_JITTER_RAD)
            target = fish.heading + jitter
            fish.state_timer = 0.0
            return (target, fish.max_speed * WANDER_SPEED_RATIO)
        return (fish.heading, fish.max_speed * WANDER_SPEED_RATIO)

    @staticmethod
    def _safe_heading_from_delta(dx: float, dy: float, fallback: float) -> float:
        """从 delta 取 heading；零向量/非有限输入沿用 fallback，避免 NaN。"""
        if not math.isfinite(dx) or not math.isfinite(dy):
            return fallback
        if dx * dx + dy * dy <= 1e-18:
            return fallback
        return math.atan2(dy, dx)

    # ------------------------------------------------------------------
    # 群行为：仅 separation
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_separation(fish: "Fish", world: "World") -> None:
        """仅对同 tier 的活跃 fish 做"半径 1.5x 重叠 → 推开"的简化分离。

        MVP 简化：alignment（对齐速度）/ cohesion（趋向群中心）暂不做，留 M4
        实施。fish-doc/mvp/02-fish-ecosystem.md §4 的完整 boid 三件套等到
        bot 跑分提示需要时再补。
        """
        mul = FISH_SEPARATION_OVERLAP_MUL
        push_dx = 0.0
        push_dy = 0.0
        for other in world.fishes:
            if other is fish or not other.alive or other.tier != fish.tier:
                continue
            if not circle_circle_overlap(
                fish.pos, fish.radius * mul, other.pos, other.radius * mul
            ):
                continue
            ddx = fish.pos.x - other.pos.x
            ddy = fish.pos.y - other.pos.y
            d = math.hypot(ddx, ddy)
            if d <= 1e-9:
                # 完全同位 → 沿 heading 取一个稳定方向，避免 NaN
                ddx = math.cos(fish.heading)
                ddy = math.sin(fish.heading)
                d = 1.0
            push_dx += ddx / d
            push_dy += ddy / d

        if push_dx == 0.0 and push_dy == 0.0:
            return
        n = math.hypot(push_dx, push_dy)
        if n <= 1e-9:
            return
        scale = FISH_SEPARATION_PUSH_SPEED / n
        vx = fish.vel.x + push_dx * scale
        vy = fish.vel.y + push_dy * scale
        speed = math.hypot(vx, vy)
        if speed > fish.max_speed and speed > 0.0:
            k = fish.max_speed / speed
            vx *= k
            vy *= k
        fish.vel = Vec2(vx, vy)
