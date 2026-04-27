"""fish/entities/base.py — Entity 基类（M3-02 骨架）。

只承载所有实体共有的最小字段；移动 / 碰撞 / 边界反射等行为属于
``fish/systems/`` 的职责（M3-03 起逐步落地）。

字段来源：fish-doc/mvp/00-overview.md §5（"World 内的所有领域逻辑"）+
fish-doc/mvp/01-core-loop.md §3（"圆形碰撞 player.r vs entity.r"）。
"""

from __future__ import annotations

from dataclasses import dataclass

from toy_engine.geom import Vec2


@dataclass
class Entity:
    """所有具象实体（Player / Fish / Boss / Particle）的基类。

    - ``eid``：稳定整数 ID，由 World 在生成时分配；用于 ``snapshot`` 排序与
      ``snapshot_hash`` 的稳定输出。
    - ``pos`` / ``vel``：世界坐标 / 速度（px, px/s）；坐标系见 fish-doc 00 §4.2。
    - ``radius``：圆形碰撞半径（px）；fish-doc 01 §3 的 "self.r vs other.r"。
    - ``alive``：实体是否仍在世界中；False 后由 World 在帧末统一清理。

    本类**不**实现 step / draw / collide：那些是 systems / render 的事。
    具体子类（Player/Fish/Boss）按需追加业务字段（tier / hp / state 等）。
    """

    eid: int
    pos: Vec2
    vel: Vec2
    radius: float
    alive: bool = True
