"""fish/main.py — 程序入口（M3-06 升级：LevelGenerator + 阶段切换演示）。

M3-06 范围：用 ``LevelGenerator.generate(seed=0, difficulty=0.5, rng=...)`` 生
成关卡（替代 ``LevelConfig.default()`` 占位），headless 跑直至 ``is_finished()``
或上限 3600 帧（60s），打印阶段切换日志、最终 ``game_result`` 与统计。
**不**初始化 pygame.display；GUI 接入留 M3-08。

为了让 demo 有概率真的吃到鱼，本步沿用 ``_ChaseNearestInput`` 驱动玩家朝最近
一条 fish 直奔（M3-10 接入 BotInput 后下线）。
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.loop import GameLoop
from toy_engine.rng import SeededRng

from fish.config.constants import DT, Phase
from fish.systems.level_generator import LevelGenerator
from fish.world import World


_DEFAULT_HEADLESS_FRAMES: int = 3600  # 60s @ 60Hz；遇 is_finished 提前退出


class _ChaseNearestInput:
    """占位输入：朝最近的「可吃」鱼 (tier <= player.tier+1) 方向给定 desired_dir；
    若周围只有更大的鱼，则朝相反方向逃离最近的威胁，避免 demo 还没触发第二次
    阶段切换就 DEAD。M3-10 接入 BotInput 后下线。"""

    def __init__(self, world: World) -> None:
        self._world = world

    def poll(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        w = self._world
        if w.game_result is not None or not w.player.alive:
            return InputFrame()
        px, py = w.player.pos.x, w.player.pos.y
        ptier = int(w.player.tier)
        nearest_prey = None
        nearest_prey_d2 = float("inf")
        nearest_threat = None
        nearest_threat_d2 = float("inf")
        for f in w.fishes:
            if not f.alive:
                continue
            d2 = (f.pos.x - px) ** 2 + (f.pos.y - py) ** 2
            # 裁决 #13：can_eat = a.tier >= b.tier - 1 → 玩家可吃 tier <= ptier+1
            if int(f.tier) <= ptier + 1:
                if d2 < nearest_prey_d2:
                    nearest_prey_d2 = d2
                    nearest_prey = f
            else:
                if d2 < nearest_threat_d2:
                    nearest_threat_d2 = d2
                    nearest_threat = f
        # 仅当威胁非常近（< 200px）时才放下猎物逃命；否则贪心追猎物，
        # 力求在 WARMUP→PRESSURE 之前升到 tier=2 直接触发 PRESSURE→BOSS。
        if nearest_threat is not None and nearest_threat_d2 < 200.0 ** 2:
            # 径向逃离 + 朝中心偏置（避免被推进墙角）
            fx = px - nearest_threat.pos.x
            fy = py - nearest_threat.pos.y
            cx, cy = 1280.0 / 2.0, 720.0 / 2.0
            to_cx = cx - px
            to_cy = cy - py
            # 归一两者再线性加权（中心偏置 0.6，逃离 1.0）
            fn = math.hypot(fx, fy) + 1e-9
            cn = math.hypot(to_cx, to_cy) + 1e-9
            dx = fx / fn + 0.6 * to_cx / cn
            dy = fy / fn + 0.6 * to_cy / cn
        elif nearest_prey is not None:
            dx = nearest_prey.pos.x - px
            dy = nearest_prey.pos.y - py
        else:
            return InputFrame()
        if not (math.isfinite(dx) and math.isfinite(dy)):
            return InputFrame()
        n = math.hypot(dx, dy)
        if n <= 1e-9:
            return InputFrame()
        return InputFrame(desired_dir=Vec2(dx / n, dy / n))


def main() -> None:
    """跑 ≤3600 帧 headless 演示，展示 LevelGenerator + LevelDirector。"""

    print("fish MVP — skeleton ready")

    cfg_rng = SeededRng(seed=0)
    cfg = LevelGenerator.generate(seed=0, difficulty=0.5, rng=cfg_rng)
    world_rng = SeededRng(seed=cfg.seed)
    world = World(cfg, world_rng)

    print(
        f"level: seed={cfg.seed} difficulty={cfg.difficulty:.2f} "
        f"warmup={cfg.phases[Phase.WARMUP].duration_s:.2f}s "
        f"pressure={cfg.phases[Phase.PRESSURE].duration_s:.2f}s "
        f"boss_appear={cfg.boss.appear_time_s:.2f}s"
    )

    loop = GameLoop(
        world=world,
        input_source=_ChaseNearestInput(world),
        dt=DT,
        max_sim_seconds=_DEFAULT_HEADLESS_FRAMES * DT,
    )
    loop.run_headless()

    print(f"phase_transitions ({len(world.director.transition_log)}):")
    for at_s, old, new in world.director.transition_log:
        print(f"  t={at_s:6.2f}s  {old.name} -> {new.name}")

    print(f"frames={world.frame_count} elapsed_s={world.elapsed_s:.4f}")
    print(
        f"player_pos=({world.player.pos.x:.2f}, {world.player.pos.y:.2f}) "
        f"heading={world.player.heading:.4f} "
        f"tier={world.player.tier} exp={world.player.exp:.2f}"
    )
    print(
        f"phase={world.director.current_phase.name} "
        f"phase_elapsed_s={world.director.phase_elapsed_s:.2f}"
    )
    print(f"game_result={world.game_result.name if world.game_result else None}")
    print(f"stats={world.stats}")

    counts = Counter(f.tier for f in world.fishes if f.alive)
    parts = ", ".join(f"tier{t}={counts.get(t, 0)}" for t in (1, 2, 3, 4))
    print(f"fish_count_by_tier: {parts} (total={sum(counts.values())})")
    print(f"snapshot_hash={world.snapshot_hash()}")


if __name__ == "__main__":
    main()
