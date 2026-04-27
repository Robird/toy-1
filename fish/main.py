"""fish/main.py — 程序入口（M3-04 升级：headless 跑 300 帧驱动 Spawner+FishAI）。

M3-04 范围：装配 LevelConfig + SeededRng + World + GameLoop，headless 跑 300
逻辑帧（5s）后打印 snapshot 摘要 + 按 tier 分组的鱼数。**不**初始化
pygame.display；GUI 接入留 M3-08。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.loop import GameLoop
from toy_engine.rng import SeededRng

from fish.config.constants import DT
from fish.config.level_config import LevelConfig
from fish.world import World


_DEFAULT_HEADLESS_FRAMES: int = 300


class _StubInput:
    """占位输入源：每帧返回固定方向 ``Vec2(1, 0)``。

    仅供 M3-03 headless 演示 player 实际会移动；M3-10 接入 BotInput
    / KeyboardMouseInput 后下线。结构化兼容 ``InputSource`` 协议。
    """

    def poll(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        return InputFrame(desired_dir=Vec2(1.0, 0.0))


def main() -> None:
    """跑 300 帧 headless 骨架并打印 snapshot + fish counts by tier。"""

    print("fish MVP — skeleton ready")

    cfg = LevelConfig.default()
    rng = SeededRng(seed=cfg.seed)
    world = World(cfg, rng)

    loop = GameLoop(
        world=world,
        input_source=_StubInput(),
        dt=DT,
    )
    loop.step_once(_DEFAULT_HEADLESS_FRAMES)

    print(f"frames={world.frame_count} elapsed_s={world.elapsed_s:.4f}")
    print(
        f"player_pos=({world.player.pos.x:.2f}, {world.player.pos.y:.2f}) "
        f"heading={world.player.heading:.4f}"
    )

    counts = Counter(f.tier for f in world.fishes if f.alive)
    parts = ", ".join(f"tier{t}={counts.get(t, 0)}" for t in (1, 2, 3, 4))
    print(f"fish_count_by_tier: {parts} (total={sum(counts.values())})")
    print(f"snapshot_hash={world.snapshot_hash()}")


if __name__ == "__main__":
    main()
