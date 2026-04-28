"""fish/entities/boss.py — Boss "Leviathan" 实体（M3-07）。

只承载数据 + 工厂；状态机行为放 ``fish/ai/boss_ai.py``，运动学（沿 vel
推进 + CHARGE 撞墙判定 + 反射）也在 BossAI 内统一处理（避免与
``MovementSystem`` 的边界反射规则在 CHARGE 状态下打架）。

字段来源：
- 继承 ``Entity`` 基类（fish/entities/base.py）
- 状态 / 时长 / HP / 感知半径 / 巡航参数：fish-doc/mvp/03-boss.md §3
- 进场无碰撞窗口：fish-doc/mvp/03-boss.md §2 ("前 3s 不参与碰撞")
- ``tier`` = ``BOSS_TIER`` 标识符（与 Fish.tier∈{1..4} 区分；可吃判定不依赖
  此值，由 fish/systems/collision.py 直接走 boss-special 分支）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from toy_engine.geom import Vec2
from toy_engine.rng import SeededRng

from fish.config.constants import (
    BOSS_CHARGE_COOLDOWN_S,
    BOSS_CHASE_SPEED,
    BOSS_HP,
    BOSS_INTRO_DURATION_S,
    BOSS_RADIUS,
    BOSS_SENSE_RADIUS,
    BOSS_TIER,
    BOSS_TURN_RATE,
    SPAWNER_EDGE_MARGIN,
)
from fish.entities.base import Entity

if TYPE_CHECKING:
    from fish.ai.boss_ai import BossState


__all__ = ["Boss"]


@dataclass
class Boss(Entity):
    """Boss"Leviathan"实体。

    Attributes
    ----------
    tier:
        体型档位标识；BOSS_TIER=5（超 Tier，仅作 snapshot 标识）。
    heading:
        朝向（弧度）。BossAI 用 ``rotate_toward`` 限速旋转；CHARGE 期间
        heading 锁定（在 ENTER_CHARGE 时刻拍下）。
    hp / max_hp:
        当前 / 满血。玩家咬一口扣 ``BOSS_BITE_DAMAGE``。
    state:
        当前 BossAI 状态。声明为 object 类型避免与 ``boss_ai`` 形成 import 环。
    state_timer:
        进入当前 state 后累计的秒数。
    bite_count:
        被玩家咬到的次数（统计用；DoD 验证「STUNNED 期间能稳定咬到」）。
    intro_remaining:
        进场无碰撞剩余秒数；> 0 时 ``CollisionSystem`` 跳过 player↔boss。
    charge_cooldown_remaining:
        距下一次 CHARGE_WINDUP 触发可用的冷却秒数；进入 CHASE 后递减。
    charge_dir:
        CHARGE 状态下锁定的冲刺单位方向；其它状态为 ``Vec2(0, 0)``。
    enraged:
        是否进入"狂暴叠加"（HP 比例 < ``BOSS_ENRAGE_HP_RATIO``）。一旦
        触发不会撤销；CHASE/CHARGE 行为跟随放大（感知半径↑、冷却↓、windup↓）。
    sense_radius / chase_speed / turn_rate / charge_cooldown:
        从 LevelConfig.boss 读入；MVP 与 fish-doc/03 §3 数值表一致，
        生成器允许后续按 difficulty 偏置。
    rng:
        boss 私有 RNG 子流；BossAI 的随机决策（PATROL 转向）走它。
    """

    tier: int = BOSS_TIER
    heading: float = 0.0
    hp: int = BOSS_HP
    max_hp: int = BOSS_HP
    # state 实际为 fish.ai.boss_ai.BossState；用 object 标注避免循环 import。
    state: object = None
    state_timer: float = 0.0
    bite_count: int = 0
    intro_remaining: float = BOSS_INTRO_DURATION_S
    charge_cooldown_remaining: float = 0.0
    charge_dir: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    enraged: bool = False
    sense_radius: float = BOSS_SENSE_RADIUS
    chase_speed: float = BOSS_CHASE_SPEED
    turn_rate: float = BOSS_TURN_RATE
    charge_cooldown: float = BOSS_CHARGE_COOLDOWN_S
    rng: SeededRng | None = None

    @classmethod
    def spawn(
        cls,
        eid: int,
        world_size: tuple[int, int],
        rng: SeededRng,
        *,
        player_pos: Vec2 | None = None,
        cfg_boss=None,
    ) -> "Boss":
        """工厂：放在屏幕外/边缘，朝屏内中心。

        Parameters
        ----------
        eid:
            稳定整数 ID（由 World.alloc_eid() 分配）。
        world_size:
            ``(W, H)``；进场点位于世界矩形外 ``SPAWNER_EDGE_MARGIN`` px。
        rng:
            boss 私有 RNG 子流（``world.rng.spawn("boss")``）；本工厂仅用
            其 ``choice`` 在「最远边缘」并列时打破平局，及为 PATROL 行为预留。
        player_pos:
            玩家当前位置；fish-doc/03 §2 "Boss 从距离玩家最远的世界边缘游入"。
            None 时退化为 rng.choice 随机选边。
        cfg_boss:
            可选 ``BossConfig``；若提供则用其 ``sense_radius/chase_speed/
            turn_rate/charge_cooldown/hp`` 覆盖 fish-doc/03 §3 默认值。
        """
        ww, wh = world_size
        margin = SPAWNER_EDGE_MARGIN

        # 选边：取距 player 最远的那条边（左/右/上/下）。距离并列时按 rng 抽。
        if player_pos is None:
            edge = rng.choice(("left", "right", "top", "bottom"))
        else:
            dists = {
                "left": float(player_pos.x),
                "right": float(ww) - float(player_pos.x),
                "top": float(player_pos.y),
                "bottom": float(wh) - float(player_pos.y),
            }
            best = max(dists.values())
            candidates = [k for k, v in dists.items() if v >= best - 1e-9]
            edge = rng.choice(tuple(candidates)) if len(candidates) > 1 else candidates[0]

        if edge == "left":
            x = -margin
            y = float(wh) * 0.5
            heading = 0.0
        elif edge == "right":
            x = float(ww) + margin
            y = float(wh) * 0.5
            heading = math.pi
        elif edge == "top":
            x = float(ww) * 0.5
            y = -margin
            heading = math.pi * 0.5
        else:  # bottom
            x = float(ww) * 0.5
            y = float(wh) + margin
            heading = -math.pi * 0.5

        sense_radius = float(cfg_boss.sense_radius) if cfg_boss is not None else BOSS_SENSE_RADIUS
        chase_speed = float(cfg_boss.chase_speed) if cfg_boss is not None else BOSS_CHASE_SPEED
        turn_rate = float(cfg_boss.turn_rate) if cfg_boss is not None else BOSS_TURN_RATE
        charge_cooldown = float(cfg_boss.charge_cooldown) if cfg_boss is not None else BOSS_CHARGE_COOLDOWN_S
        hp = int(cfg_boss.hp) if cfg_boss is not None else BOSS_HP

        return cls(
            eid=eid,
            pos=Vec2(x, y),
            vel=Vec2(0.0, 0.0),
            radius=BOSS_RADIUS,
            alive=True,
            tier=BOSS_TIER,
            heading=heading,
            hp=hp,
            max_hp=hp,
            state=None,  # BossAI.step 在第一帧把 None → BossState.PATROL
            state_timer=0.0,
            bite_count=0,
            intro_remaining=BOSS_INTRO_DURATION_S,
            charge_cooldown_remaining=0.0,
            charge_dir=Vec2(0.0, 0.0),
            enraged=False,
            sense_radius=sense_radius,
            chase_speed=chase_speed,
            turn_rate=turn_rate,
            charge_cooldown=charge_cooldown,
            rng=rng,
        )
