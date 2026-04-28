"""fish/render/pyg_renderer.py — PygRenderer（M3-08）。

把 ``World`` 的当前状态画到一个 :class:`toy_engine.render.GeoCanvas` 上。
**纯函数式**：自身不保存逻辑状态（只持有 canvas / palette / font）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import math

from toy_engine.render import GeoCanvas

from fish.config.constants import WORLD_H, WORLD_W
from fish.render import visuals

if TYPE_CHECKING:
    from toy_engine.render import Palette
    from fish.world import World
    from fish.render.feel import FeelEffects


__all__ = ["PygRenderer"]


class PygRenderer:
    """组合 visuals.* 的渲染器。

    Parameters
    ----------
    canvas:
        已构造的 GeoCanvas（窗口或离屏 surface 都可）。
    palette:
        fish 业务调色板。
    font:
        UI / game-over 文字字体。``None`` 时跳过文字（适合纯像素抽样测试）。
    """

    __slots__ = ("canvas", "palette", "font")

    def __init__(
        self,
        canvas: GeoCanvas,
        palette: "Palette",
        font: Any | None,
    ) -> None:
        self.canvas = canvas
        self.palette = palette
        self.font = font

    def render(self, world: "World", *, feel: "FeelEffects | None" = None) -> None:
        """画一帧。

        顺序：背景 → 鱼群 → 玩家（带 squash）→ boss → feel 拖尾/粒子→
        UI → game_over → flash overlay。

        拖尾/粒子/飘字放在 UI 之前，这样 UI 文本不会被掩盖；
        flash overlay 在终态遮罩之后，合事件错错感。
        """
        snapshot = world.snapshot()
        # 视差偏移：玩家相对屏幕中心
        try:
            px = float(world.player.pos.x) - WORLD_W / 2.0
            py = float(world.player.pos.y) - WORLD_H / 2.0
        except Exception:  # noqa: BLE001
            px, py = 0.0, 0.0

        # 1. 背景
        visuals.draw_parallax_background(
            self.canvas, self.palette,
            frame_count=int(world.frame_count),
            player_offset=(px, py),
        )

        # 2. 普通鱼（按 eid 升序，与 snapshot 决定性一致）
        t_seconds = float(world.elapsed_s)
        player_tier = int(world.player.tier) if world.player is not None else 0
        for fish in sorted(world.fishes, key=lambda f: f.eid):
            if not fish.alive:
                continue
            visuals.draw_fish(
                self.canvas, fish, self.palette,
                player_tier=player_tier, t_seconds=t_seconds,
            )

        # 3. 玩家（squash 由 feel 提供）
        if world.player is not None:
            squash = (1.0, 1.0)
            if feel is not None:
                vx = float(world.player.vel.x)
                vy = float(world.player.vel.y)
                speed = math.hypot(vx, vy)
                squash = feel.squash.compute(
                    speed, float(getattr(world.player, "max_speed", 1.0))
                )
            visuals.draw_player(
                self.canvas, world.player, self.palette,
                t_seconds=t_seconds, squash=squash,
            )

        # 4. Boss
        if world.boss is not None and world.boss.alive:
            visuals.draw_boss(self.canvas, world.boss, self.palette, t_seconds=t_seconds)

        # 5. feel 拖尾 + 粒子 + 飘字（UI 之前）
        if feel is not None:
            feel.render(self.canvas, self.palette, font=self.font)

        # 6. UI
        visuals.draw_ui(self.canvas, snapshot, self.palette, self.font)

        # 7. 终态遮罩
        if world.game_result is not None:
            visuals.draw_game_over(self.canvas, snapshot, self.palette, self.font)

        # 8. flash overlay（最外层）
        if feel is not None:
            feel.render_flash_overlay(self.canvas)
