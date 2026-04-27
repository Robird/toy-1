"""fish/main.py — 程序入口（M3-02 升级：headless 跑 30 帧 World 骨架）。

M3-02 范围：装配 LevelConfig + SeededRng + World + GameLoop，headless 跑 30
逻辑帧后打印一份 snapshot。**不**初始化 pygame.display；GUI 接入留 M3-08。
"""

from __future__ import annotations

from math import nextafter
from typing import Any

from toy_engine.input import InputFrame
from toy_engine.loop import GameLoop
from toy_engine.rng import SeededRng

from fish.config.constants import DT
from fish.config.level_config import LevelConfig
from fish.world import World


_DEFAULT_HEADLESS_FRAMES: int = 30


class _NullInput:
    """占位输入源：每帧返回空 ``InputFrame``（无方向意图）。

    M3-03 接入 ``KeyboardMouseInput`` 后此类即可下线。结构化兼容
    ``toy_engine.input.InputSource`` 协议。
    """

    def poll(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        return InputFrame()


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
        input_source=_NullInput(),
        dt=DT,
        max_sim_seconds=max_sim_seconds,
    )
    loop.run_headless()

    print(f"frames={world.frame_count} elapsed_s={world.elapsed_s:.4f}")
    print(f"snapshot={world.snapshot()}")
    print(f"snapshot_hash={world.snapshot_hash()}")


if __name__ == "__main__":
    main()
