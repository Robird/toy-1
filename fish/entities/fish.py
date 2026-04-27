"""fish/entities/fish.py — 普通鱼实体（M3-04）。

只承载数据 + 工厂；行为放 ``fish/ai/fish_ai.py``，运动学（pos += vel*dt + 边界
反射）走 ``fish/systems/movement.py`` 的非 player 分支。

字段来源：
- 继承 ``Entity`` 基类（fish/entities/base.py）
- ``tier`` / ``heading`` / ``state`` / 速度参数：fish-doc/mvp/02-fish-ecosystem.md §1~§3
- ``state``：FishAI 状态机的当前态（FishAIState；初始 WANDER）
"""

from __future__ import annotations

from dataclasses import dataclass

from toy_engine.geom import Vec2
from toy_engine.rng import SeededRng

from fish.ai.fish_ai import FishAIState
from fish.config.constants import (
    FISH_MAX_SPEED,
    FISH_RADIUS,
    FISH_TURN_RATE_RAD_S,
)
from fish.entities.base import Entity


@dataclass
class Fish(Entity):
    """普通鱼（非 Boss）。

    - ``tier``：1..4。Tier 0 是玩家初始档位、不存在 NPC fish；Boss 单列实体。
      （fish-doc/mvp/02-fish-ecosystem.md §1）
    - ``heading``：朝向（弧度，0 = +x 正右）。FishAI 用 ``rotate_toward`` 限速旋转。
    - ``max_speed``/``turn_rate_rad_s``：按 tier 查 ``FISH_MAX_SPEED`` /
      ``FISH_TURN_RATE_RAD_S``。
    - ``state``：FishAI 三态机当前态；``state_timer`` 由 AI 维护（如 WANDER 重选偏航）。
    - ``rng``：每条鱼独立的 ``SeededRng`` 子流，FishAI 的所有随机决策都走它，保证
      契约 #3（snapshot_hash 决定性）。**不**进入 snapshot；不参与 hash。
    """

    tier: int = 0
    heading: float = 0.0
    max_speed: float = 0.0
    turn_rate_rad_s: float = 0.0
    state: FishAIState = FishAIState.WANDER
    state_timer: float = 0.0
    rng: SeededRng | None = None

    @classmethod
    def spawn(
        cls,
        eid: int,
        tier: int,
        pos: Vec2,
        heading: float,
        rng: SeededRng,
    ) -> "Fish":
        """工厂：按 tier 设置 radius/max_speed/turn_rate，初始 vel 沿 heading 0 速。

        ``tier`` 必须在 ``[1, 4]`` 内，否则 ``ValueError``。
        ``rng`` 必须是已 spawn 出的子流（调用方负责命名一致性）。
        """
        if tier < 1 or tier > 4:
            raise ValueError(
                f"Fish.tier must be in [1, 4] (Tier 0 is player; Boss is separate); got {tier}"
            )
        return cls(
            eid=eid,
            pos=pos,
            vel=Vec2(0.0, 0.0),
            radius=float(FISH_RADIUS[tier]),
            alive=True,
            tier=int(tier),
            heading=float(heading),
            max_speed=float(FISH_MAX_SPEED[tier]),
            turn_rate_rad_s=float(FISH_TURN_RATE_RAD_S[tier]),
            state=FishAIState.WANDER,
            state_timer=0.0,
            rng=rng,
        )
