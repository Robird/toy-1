"""fish/main.py — 程序入口（M3-08：增 GUI 入口；保留 M3-07 headless）。

入口：
- ``main()``                 → 默认跑 ``run_gui()`` （开窗 1280×720 60fps）
- ``python -m fish.main --headless`` → 走 ``run_headless()``（M3-04..07 demo）
- ``run_gui(seed, difficulty)`` 程序化调用
- ``run_headless(seed, difficulty, max_frames)`` 程序化调用（兼容已有测试）

GUI 模式：
- ``KeyboardMouseInput``（鼠标 → 玩家方向；ESC 退出）
- ``GameLoop`` 单步固定 dt + ``PygRenderer`` 渲染
- 终态后维持 3s 显示，再退出

Headless 模式与 M3-07 一致：``_ChaseNearestInput`` 占位 + 90s + 打印日志。
"""

from __future__ import annotations

import argparse
import math
from collections import Counter
from typing import Any

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.loop import GameLoop
from toy_engine.rng import SeededRng

from fish.config.constants import DT, Phase, TIER_GIANT, WORLD_H, WORLD_W
from fish.systems.level_generator import LevelGenerator
from fish.world import World


_DEFAULT_HEADLESS_FRAMES: int = 5400  # 90s @ 60Hz


# ---------------------------------------------------------------------------
# 占位输入：M3-04..07 用过的 ChaseNearest（仅 headless 使用）
# ---------------------------------------------------------------------------


class _ChaseNearestInput:
    """占位输入（headless demo 用）；M3-10 接入 BotInput 后下线。"""

    def __init__(self, world: World) -> None:
        self._world = world

    def poll(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        w = self._world
        if w.game_result is not None or not w.player.alive:
            return InputFrame()
        px, py = w.player.pos.x, w.player.pos.y
        ptier = int(w.player.tier)
        boss = w.boss
        if (
            boss is not None and boss.alive
            and ptier >= TIER_GIANT and boss.intro_remaining <= 0.0
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
            if int(f.tier) <= ptier + 1:
                if d2 < nearest_prey_d2:
                    nearest_prey_d2 = d2
                    nearest_prey = f
            else:
                if d2 < nearest_threat_d2:
                    nearest_threat_d2 = d2
                    nearest_threat = f
        if boss is not None and boss.alive and ptier < TIER_GIANT and boss.intro_remaining <= 0.0:
            d2 = (boss.pos.x - px) ** 2 + (boss.pos.y - py) ** 2
            if d2 < nearest_threat_d2:
                nearest_threat_d2 = d2
                nearest_threat = boss
        if nearest_threat is not None and nearest_threat_d2 < 250.0 ** 2:
            fx = px - nearest_threat.pos.x
            fy = py - nearest_threat.pos.y
            cx, cy = WORLD_W / 2.0, WORLD_H / 2.0
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


# ---------------------------------------------------------------------------
# Headless（M3-04..07 兼容入口）
# ---------------------------------------------------------------------------


def run_headless(
    *,
    seed: int = 0,
    difficulty: float = 0.5,
    max_frames: int = _DEFAULT_HEADLESS_FRAMES,
    verbose: bool = True,
) -> World:
    """无 GUI 跑一局；返回最终 World 供测试 / 调试断言。"""

    cfg_rng = SeededRng(seed=seed)
    cfg = LevelGenerator.generate(seed=seed, difficulty=difficulty, rng=cfg_rng)
    world_rng = SeededRng(seed=cfg.seed)
    world = World(cfg, world_rng)

    if verbose:
        print(
            f"level: seed={cfg.seed} difficulty={cfg.difficulty:.2f} "
            f"warmup={cfg.phases[Phase.WARMUP].duration_s:.2f}s "
            f"pressure={cfg.phases[Phase.PRESSURE].duration_s:.2f}s "
            f"boss_appear={cfg.boss.appear_time_s:.2f}s"
        )

    boss_state_log: list[tuple[float, str, str]] = []
    last_boss_state: str | None = None

    loop = GameLoop(
        world=world,
        input_source=_ChaseNearestInput(world),
        dt=DT,
        max_sim_seconds=max_frames * DT,
    )
    while not world.is_finished() and world.frame_count < max_frames:
        loop.step_once(1)
        b = world.boss
        cur_state = b.state.name if (b is not None and b.alive and b.state is not None) else None
        if cur_state != last_boss_state:
            boss_state_log.append(
                (world.elapsed_s, last_boss_state or "<none>", cur_state or "<none>")
            )
            last_boss_state = cur_state

    if verbose:
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
            print(
                f"boss: state={b.state.name if b.state else None} "
                f"hp={b.hp}/{b.max_hp} bites={b.bite_count} enraged={b.enraged}"
            )
        else:
            print("boss: None (killed or not yet spawned)")
        counts = Counter(f.tier for f in world.fishes if f.alive)
        parts = ", ".join(f"tier{t}={counts.get(t, 0)}" for t in (1, 2, 3, 4))
        print(f"fish_count_by_tier: {parts} (total={sum(counts.values())})")
        print(f"snapshot_hash={world.snapshot_hash()}")

    return world


# ---------------------------------------------------------------------------
# GUI 入口（M3-08）
# ---------------------------------------------------------------------------


def run_gui(
    *,
    seed: int = 0,
    difficulty: float = 0.5,
    title: str = "fish — MVP",
    end_screen_seconds: float = 3.0,
) -> None:
    """开 1280×720 窗口跑实时游戏；ESC 退出。

    实现注意：
    - 自管事件循环 + ``loop.step_once(1)``：方便在每帧抓 ESC / QUIT 事件。
    - 终态后保留 ``end_screen_seconds`` 秒展示遮罩，再退出。

    本函数不被任何自动化测试调用（测试走 PygRenderer 离屏路径）。
    """
    # 延迟 import，避免 headless 路径被动触发窗口副作用
    import pygame

    from toy_engine.font import load_font
    from toy_engine.input import KeyboardMouseInput
    from toy_engine.render import GeoCanvas

    from fish.render import FISH_PALETTE, PygRenderer

    if not pygame.get_init():
        pygame.init()
    canvas = GeoCanvas.create_window(WORLD_W, WORLD_H, title=title, palette=FISH_PALETTE)
    font = load_font(20, "consolas", "microsoftyahei", fallback_size=20)

    cfg_rng = SeededRng(seed=seed)
    cfg = LevelGenerator.generate(seed=seed, difficulty=difficulty, rng=cfg_rng)
    world_rng = SeededRng(seed=cfg.seed)
    world = World(cfg, world_rng)

    keyboard = KeyboardMouseInput(viewport=(WORLD_W, WORLD_H))
    renderer = PygRenderer(canvas, FISH_PALETTE, font)

    loop = GameLoop(
        world=world,
        input_source=keyboard,
        dt=DT,
    )

    clock = pygame.time.Clock()
    finished_at_ms: int | None = None
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
                break
        if not running:
            break

        if not world.is_finished():
            loop.step_once(1)
        else:
            if finished_at_ms is None:
                finished_at_ms = pygame.time.get_ticks()
            elif pygame.time.get_ticks() - finished_at_ms >= end_screen_seconds * 1000:
                running = False

        renderer.render(world)
        canvas.present()
        clock.tick(60)

    pygame.quit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="fish MVP entry point")
    parser.add_argument("--headless", action="store_true", help="run without GUI")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--difficulty", type=float, default=0.5)
    parser.add_argument("--max-frames", type=int, default=_DEFAULT_HEADLESS_FRAMES)
    args = parser.parse_args()

    print("fish MVP — skeleton ready")

    if args.headless:
        run_headless(
            seed=args.seed,
            difficulty=args.difficulty,
            max_frames=args.max_frames,
        )
    else:
        run_gui(seed=args.seed, difficulty=args.difficulty)


if __name__ == "__main__":
    main()
