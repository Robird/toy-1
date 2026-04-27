"""fish/systems/movement.py — 玩家 + 通用实体的移动 / 边界反射系统（M3-03）。

依据：
- fish-doc/mvp/06-controls-feel.md §2（turn_rate / accel / drag / dead_zone）
- fish-doc/mvp/01-core-loop.md §1（World.step 内移动子步）
- fish-doc/mvp/02-fish-ecosystem.md §3（边界反射与 WALL_BOUNCE_DAMPING）

M3-03 范围：仅处理 ``world.player`` 与 ``world.entities`` 中除 player 之外
的"占位实体"（M3-04 起 Fish/Boss 会真正出现）。不实现 AI、不处理碰撞。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from toy_engine.geom import Vec2, rotate_toward

from fish.config.constants import (
    PLAYER_DRAG,
    WALL_BOUNCE_DAMPING,
    WORLD_H,
    WORLD_W,
)
from fish.entities.player import Player

if TYPE_CHECKING:
    from fish.entities.base import Entity
    from fish.world import World


class MovementSystem:
    """推进所有实体的速度/位置；负责玩家朝向控制与边界反射。"""

    def step(self, world: "World", dt: float) -> None:
        if dt <= 0.0:
            return

        # 1) 玩家：转向 + 推进 + 速度上限/惯性
        self._step_player(world.player, world.last_input_frame, dt)
        self._reflect_bounds(world.player)

        # 2) 其它实体（M3-03 阶段没有；为 M3-04 留口）：纯运动学 + 反射
        for ent in world.entities:
            if ent is world.player:
                continue
            if not ent.alive:
                continue
            ent.pos = Vec2(ent.pos.x + ent.vel.x * dt, ent.pos.y + ent.vel.y * dt)
            self._reflect_bounds(ent)

    # ------------------------------------------------------------------
    # Player
    # ------------------------------------------------------------------
    @staticmethod
    def _step_player(p: Player, input_frame, dt: float) -> None:
        desired = None if input_frame is None else input_frame.desired_dir
        if desired is not None:
            # InputFrame 正常会拒绝零向量 / 非有限值；这里再防御一层，避免
            # 测试桩或未来自定义 InputSource 绕过校验后把角度/速度推进到 NaN。
            if (
                not math.isfinite(desired.x)
                or not math.isfinite(desired.y)
                or desired.x * desired.x + desired.y * desired.y <= 1e-18
            ):
                desired = None

        if desired is None:
            # 无输入：保持 heading；速度按 PLAYER_DRAG 指数衰减（fish-doc 06 §2）。
            decay = math.exp(-PLAYER_DRAG * dt)
            p.vel = Vec2(p.vel.x * decay, p.vel.y * decay)
        else:
            # 有方向意图：受 turn_rate 限制把 heading 朝目标方向旋转，沿
            # heading 施加恒定推力，并限制速度上限到 max_speed。
            target_heading = math.atan2(desired.y, desired.x)
            max_step = p.turn_rate_rad_s * dt
            p.heading = rotate_toward(p.heading, target_heading, max_step)

            thrust = Vec2.from_angle(p.heading, p.accel * dt)
            new_vel = Vec2(p.vel.x + thrust.x, p.vel.y + thrust.y)

            speed = math.hypot(new_vel.x, new_vel.y)
            if speed > p.max_speed and speed > 0.0:
                k = p.max_speed / speed
                new_vel = Vec2(new_vel.x * k, new_vel.y * k)
            p.vel = new_vel

        # 位移
        p.pos = Vec2(p.pos.x + p.vel.x * dt, p.pos.y + p.vel.y * dt)

    # ------------------------------------------------------------------
    # 边界反射
    # ------------------------------------------------------------------
    @staticmethod
    def _reflect_bounds(ent: "Entity") -> None:
        """把 ent 钳制到 ``[0, WORLD_W] x [0, WORLD_H]`` 内；越界分量速度
        翻转并按 ``WALL_BOUNCE_DAMPING`` 衰减。
        """
        x, y = ent.pos.x, ent.pos.y
        vx, vy = ent.vel.x, ent.vel.y

        if x <= 0.0:
            x = 0.0
            if vx < 0.0:
                vx = -vx * WALL_BOUNCE_DAMPING
        elif x >= WORLD_W:
            x = float(WORLD_W)
            if vx > 0.0:
                vx = -vx * WALL_BOUNCE_DAMPING

        if y <= 0.0:
            y = 0.0
            if vy < 0.0:
                vy = -vy * WALL_BOUNCE_DAMPING
        elif y >= WORLD_H:
            y = float(WORLD_H)
            if vy > 0.0:
                vy = -vy * WALL_BOUNCE_DAMPING

        ent.pos = Vec2(x, y)
        ent.vel = Vec2(vx, vy)
