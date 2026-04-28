"""fish/main.py — 程序入口（M3-07 升级：Boss 实体 + 状态机演示）。

M3-07 范围：Boss 实体真正落地，BossAI 五状态机 + 玩家复仇判定。Headless
跑直至 ``is_finished()`` 或上限 5400 帧（90s），打印阶段切换日志、Boss 状态
切换日志、最终 ``game_result`` 与统计。**不**初始化 pygame.display；GUI 接入
留 M3-08。

为了让 demo 的 boss 战有可观察事件，本步沿用 ``_ChaseNearestInput`` 思路并加
"boss 出现后优先咬尾部"的简单启发式（M3-10 接入正式 BotInput 后下线）。
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.loop import GameLoop
from toy_engine.rng import SeededRng

from fish.config.constants import DT, Phase, TIER_GIANT
from fish.systems.level_generator import LevelGenerator
from fish.world import World


_DEFAULT_HEADLESS_FRAMES: int = 5400  # 90s @ 60Hz；遇 is_finished 提前退出


class _ChaseNearestInput:
    """占位输入：
    - 若 boss 已出现且玩家 tier == TIER_GIANT → 朝 boss "尾部位点" 方向冲；
      尾部位点 = boss.pos + radius * (-cos(heading), -sin(heading))。
    - 否则朝最近的「可吃」鱼追；附近威胁 < 200px 时优先逃命。
    M3-10 接入 BotInput 后下线。
    """

    def __init__(self, world: World) -> None:
        self._world = world

    def poll(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        w = self._world
        if w.game_result is not None or not w.player.alive:
            return InputFrame()
        px, py = w.player.pos.x, w.player.pos.y
        ptier = int(w.player.tier)

        boss = w.boss
        # boss 优先策略：玩家 tier=4 且 boss 已可碰撞 → 直奔尾部
        if (
            boss is not None
            and boss.alive
            and ptier >= TIER_GIANT
            and boss.intro_remaining <= 0.0
        ):
            tail_x = boss.pos.x - math.cos(boss.heading) * boss.radius * 1.2
            tail_y = boss.pos.y - math.sin(boss.heading) * boss.radius * 1.2
            dx = tail_x - px
            dy = tail_y - py
            n = math.hypot(dx, dy)
            if n > 1e-9:
                return InputFrame(desired_dir=Vec2(dx / n, dy / n))

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
        # boss 也是巨大威胁（玩家 tier < 4 时）
        if boss is not None and boss.alive and ptier < TIER_GIANT and boss.intro_remaining <= 0.0:
            d2 = (boss.pos.x - px) ** 2 + (boss.pos.y - py) ** 2
            if d2 < nearest_threat_d2:
                nearest_threat_d2 = d2
                nearest_threat = boss
        # 仅当威胁非常近（< 250px）时才放下猎物逃命；否则贪心追猎物
        if nearest_threat is not None and nearest_threat_d2 < 250.0 ** 2:
            fx = px - nearest_threat.pos.x
            fy = py - nearest_threat.pos.y
            cx, cy = 1280.0 / 2.0, 720.0 / 2.0
            to_cx = cx - px
            to_cy = cy - py
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
    """跑 ≤5400 帧 headless 演示，展示 LevelGenerator + LevelDirector + Boss。"""

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

    # 监听 boss 状态切换（直接 hook step 不太干净，这里逐帧轮询比对）
    boss_state_log: list[tuple[float, str, str]] = []
    last_boss_state: str | None = None

    loop = GameLoop(
        world=world,
        input_source=_ChaseNearestInput(world),
        dt=DT,
        max_sim_seconds=_DEFAULT_HEADLESS_FRAMES * DT,
    )
    # GameLoop.run_headless 没有 per-frame hook，自己手动跑：
    while not world.is_finished() and world.frame_count < _DEFAULT_HEADLESS_FRAMES:
        loop.step_once(1)
        b = world.boss
        cur_state = b.state.name if (b is not None and b.alive and b.state is not None) else None
        if cur_state != last_boss_state:
            boss_state_log.append((world.elapsed_s, last_boss_state or "<none>", cur_state or "<none>"))
            last_boss_state = cur_state

    print(f"phase_transitions ({len(world.director.transition_log)}):")
    for at_s, old, new in world.director.transition_log:
        print(f"  t={at_s:6.2f}s  {old.name} -> {new.name}")

    print(f"boss_state_transitions ({len(boss_state_log)}):")
    for at_s, old, new in boss_state_log:
        print(f"  t={at_s:6.2f}s  {old} -> {new}")

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
    print(f"tier4_warning={world.tier4_warning}")
    print(f"stats={world.stats}")
    if world.boss is not None:
        b = world.boss
        print(f"boss: state={b.state.name if b.state else None} hp={b.hp}/{b.max_hp} bites={b.bite_count} enraged={b.enraged}")
    else:
        print("boss: None (killed or not yet spawned)")

    counts = Counter(f.tier for f in world.fishes if f.alive)
    parts = ", ".join(f"tier{t}={counts.get(t, 0)}" for t in (1, 2, 3, 4))
    print(f"fish_count_by_tier: {parts} (total={sum(counts.values())})")
    print(f"snapshot_hash={world.snapshot_hash()}")


if __name__ == "__main__":
    main()
