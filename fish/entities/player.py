"""fish/entities/player.py — 玩家实体（M3-03）。

只承载数据/工厂；移动逻辑放 ``fish/systems/movement.py``。
字段来源：
- 继承 ``Entity`` 基类（fish/entities/base.py）
- ``tier`` / ``heading`` 与运动学参数：fish-doc/mvp/01-core-loop.md §2 +
  fish-doc/mvp/06-controls-feel.md §2
"""

from __future__ import annotations

from dataclasses import dataclass

from toy_engine.geom import Vec2

from fish.config.constants import (
    PLAYER_ACCEL,
    PLAYER_MAX_SPEED,
    PLAYER_RADIUS,
    PLAYER_TURN_RATE,
    TIER_FRY,
)
from fish.config.level_config import LevelConfig
from fish.entities.base import Entity


@dataclass
class Player(Entity):
    """玩家鱼。

    Notes
    -----
    - ``tier``：体型档位（0..4）。玩家初始为 Tier 0 fry，见
      fish-doc/mvp/00-overview.md §4.1 与 fish-doc/mvp/01-core-loop.md §2。
    - ``heading``：朝向（弧度，0 = +x 正右）。MovementSystem 会按
      ``turn_rate_rad_s`` 限制每帧旋转量。
    - ``max_speed`` / ``accel`` / ``turn_rate_rad_s`` 由 ``from_config`` 按
      tier 初始化：MVP 仅 ``max_speed`` 是 tier→table（PLAYER_MAX_SPEED），
      ``accel`` / ``turn_rate`` 文档为单一标量、所有 tier 共享。M3-05 成长
      系统在 tier 变化时应同步更新这三项。
    """

    tier: int = TIER_FRY
    heading: float = 0.0
    max_speed: float = 0.0
    accel: float = 0.0
    turn_rate_rad_s: float = 0.0

    @classmethod
    def from_config(cls, cfg: LevelConfig, eid: int) -> "Player":
        """工厂：把玩家放在世界中央，按初始 tier 初始化运动参数。"""
        ww, wh = cfg.world_size
        tier = TIER_FRY
        return cls(
            eid=eid,
            pos=Vec2(float(ww) / 2.0, float(wh) / 2.0),
            vel=Vec2(0.0, 0.0),
            radius=float(PLAYER_RADIUS[tier]),
            alive=True,
            tier=tier,
            heading=0.0,
            max_speed=float(PLAYER_MAX_SPEED[tier]),
            accel=PLAYER_ACCEL,
            turn_rate_rad_s=PLAYER_TURN_RATE,
        )
