"""fish/main.py — 程序入口（M3-05 升级：headless 跑 600 帧驱动碰撞 + 成长）。

M3-05 范围：装配 LevelConfig + SeededRng + World + GameLoop，headless 跑 600
逻辑帧（10s）后打印 snapshot 摘要 + 吃鱼 / 成长 / DEAD 统计。**不**初始化
pygame.display；GUI 接入留 M3-08。

为了让 demo 有概率真的吃到鱼，本步用 ``_ChaseNearestInput`` 驱动玩家朝最近一条
fish 直奔（M3-10 接入 BotInput 后下线）。
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.loop import GameLoop
from toy_engine.rng import SeededRng

from fish.config.constants import DT
from fish.config.level_config import LevelConfig
from fish.world import World


_DEFAULT_HEADLESS_FRAMES: int = 600


class _ChaseNearestInput:
    """占位输入：朝最近的活鱼方向给定 desired_dir；无鱼则不动。

    仅供 M3-05 headless 演示「玩家会吃到鱼 / 偶尔被吃」；M3-10 接入
    `BotInput` 后下线。
    """

    def __init__(self, world: World) -> None:
        self._world = world

    def poll(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        w = self._world
        if w.game_result is not None or not w.player.alive:
            return InputFrame()
        px, py = w.player.pos.x, w.player.pos.y
        nearest = None
        nearest_d2 = float("inf")
        for f in w.fishes:
            if not f.alive:
                continue
            d2 = (f.pos.x - px) ** 2 + (f.pos.y - py) ** 2
            if d2 < nearest_d2:
                nearest_d2 = d2
                nearest = f
        if nearest is None:
            return InputFrame()
        dx = nearest.pos.x - px
        dy = nearest.pos.y - py
        if not (math.isfinite(dx) and math.isfinite(dy)):
            return InputFrame()
        n = math.hypot(dx, dy)
        if n <= 1e-9:
            return InputFrame()
        return InputFrame(desired_dir=Vec2(dx / n, dy / n))


def main() -> None:
    """跑 600 帧 headless 骨架，展示吃鱼 / 成长 / 可能 DEAD。"""

    print("fish MVP — skeleton ready")

    cfg = LevelConfig.default()
    rng = SeededRng(seed=cfg.seed)
    world = World(cfg, rng)

    loop = GameLoop(
        world=world,
        input_source=_ChaseNearestInput(world),
        dt=DT,
    )
    loop.step_once(_DEFAULT_HEADLESS_FRAMES)

    print(f"frames={world.frame_count} elapsed_s={world.elapsed_s:.4f}")
    print(
        f"player_pos=({world.player.pos.x:.2f}, {world.player.pos.y:.2f}) "
        f"heading={world.player.heading:.4f} "
        f"tier={world.player.tier} exp={world.player.exp:.2f}"
    )
    print(f"game_result={world.game_result.name if world.game_result else None}")
    print(f"stats={world.stats}")

    counts = Counter(f.tier for f in world.fishes if f.alive)
    parts = ", ".join(f"tier{t}={counts.get(t, 0)}" for t in (1, 2, 3, 4))
    print(f"fish_count_by_tier: {parts} (total={sum(counts.values())})")
    print(f"snapshot_hash={world.snapshot_hash()}")


if __name__ == "__main__":
    main()
