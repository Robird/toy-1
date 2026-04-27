"""fish/main.py — 程序入口（M3-02 升级：headless 跑 30 帧 World 骨架）。

M3-02 范围：装配 LevelConfig + SeededRng + World + GameLoop，headless 跑 30
逻辑帧后打印一份 snapshot。**不**初始化 pygame.display；GUI 接入留 M3-08。
"""

from __future__ import annotations

from math import nextafter
from typing import Any

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.loop import GameLoop
from toy_engine.rng import SeededRng

from fish.config.constants import DT
from fish.config.level_config import LevelConfig
from fish.world import World


_DEFAULT_HEADLESS_FRAMES: int = 30


class _StubInput:
    """占位输入源：每帧返回固定方向 ``Vec2(1, 0)``。

    仅供 M3-03 headless 演示 player 实际会移动；M3-10 接入 BotInput
    / KeyboardMouseInput 后下线。结构化兼容 ``InputSource`` 协议。
    """

    def poll(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        return InputFrame(desired_dir=Vec2(1.0, 0.0))


def main() -> None:
    """跑 30 帧 headless 骨架并打印 snapshot。"""

    print("fish MVP — skeleton ready")

    cfg = LevelConfig.default()
    rng = SeededRng(seed=cfg.seed)
    world = World(cfg, rng)

    # run_headless() 在每个 tick 后检查 max_sim_seconds；把上限设为目标时长
    # 的前一个浮点值，可避免 30 * DT 的累加末位误差导致多跑一帧。
    max_sim_seconds = nextafter(_DEFAULT_HEADLESS_FRAMES * DT, 0.0)

    loop = GameLoop(
        world=world,
        input_source=_StubInput(),
        dt=DT,
        max_sim_seconds=max_sim_seconds,
    )
    loop.run_headless()

    print(f"frames={world.frame_count} elapsed_s={world.elapsed_s:.4f}")
    print(
        f"player_pos=({world.player.pos.x:.2f}, {world.player.pos.y:.2f}) "
        f"heading={world.player.heading:.4f}"
    )
    print(f"snapshot_hash={world.snapshot_hash()}")


if __name__ == "__main__":
    main()
