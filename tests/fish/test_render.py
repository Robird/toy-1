"""tests/fish/test_render.py — M3-08 视觉层 smoke / 像素抽样测试。

约束（任务书）：
- 必须 headless（``SDL_VIDEODRIVER=dummy``，由 tests/conftest.py 设置）
- 用 ``pygame.Surface((1280, 720))`` 离屏 surface 作 canvas target
- 不做大像素差快照断言（脆且对 MVP 过早）
- 各 draw_* 函数对边界状态都不崩（boss=None / fishes=[] / 终态等）
"""

from __future__ import annotations

import pygame
import pytest

from toy_engine.geom import Vec2
from toy_engine.render import GeoCanvas

from fish.config.constants import DT, Phase
from fish.config.level_config import LevelConfig
from fish.render import FISH_PALETTE, PygRenderer, build_fish_palette, tier_to_role_name
from fish.render import visuals
from fish.world import GameResult, World


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _new_canvas() -> GeoCanvas:
    """构造一个 1280x720 的离屏 GeoCanvas。"""
    return GeoCanvas.offscreen(1280, 720)


def _new_world(*, with_director_step: bool = False) -> World:
    """构造一个最小可用的 World。"""
    from toy_engine.rng import SeededRng

    cfg = LevelConfig.default()
    world = World(cfg, SeededRng(seed=1234))
    return world


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


class TestPalette:
    def test_named_colors_present(self) -> None:
        # fish-doc/05 §1 列出的所有颜色必须可读
        for key in (
            "bg_deep", "bg_mid", "bg_shallow", "bg_foam", "bg_highlight",
            "role_player", "role_prey", "role_peer", "role_threat", "role_boss",
            "ui_text", "ui_warning", "ui_bar_bg", "ui_bar_fill",
        ):
            r, g, b = FISH_PALETTE[key]
            assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255

    def test_locked_constants_match_doc(self) -> None:
        # fish-doc/05 §1 锁死的几个值
        assert FISH_PALETTE["bg_deep"] == (11, 29, 58)
        assert FISH_PALETTE["bg_shallow"] == (43, 140, 190)
        assert FISH_PALETTE["role_player"] == (255, 215, 0)
        assert FISH_PALETTE["role_threat"] == (220, 80, 60)
        assert FISH_PALETTE["role_boss"] == (60, 20, 80)

    def test_tier_to_role_name(self) -> None:
        # 裁决 #13 + 同 tier 优先 bounce：玩家 tier=2 时，1/3 可吃，2 同级弹开，4 威胁。
        assert tier_to_role_name(1, 2) == "role_prey"
        assert tier_to_role_name(2, 2) == "role_peer"
        assert tier_to_role_name(3, 2) == "role_prey"
        assert tier_to_role_name(4, 2) == "role_threat"
        roles = {tier_to_role_name(tier, 4) for tier in (1, 2, 3, 4)}
        assert roles == {"role_prey", "role_peer"}
        assert tier_to_role_name(4, 4) == "role_peer"

    def test_build_returns_independent_palette(self) -> None:
        p1 = build_fish_palette()
        p2 = build_fish_palette()
        assert p1 is not p2
        assert p1["role_player"] == p2["role_player"]


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------


class TestBackground:
    def test_clears_to_non_black(self) -> None:
        canvas = _new_canvas()
        # 强制起始为奇怪颜色，确保 draw_parallax_background 真的覆盖
        canvas.surface.fill((255, 255, 255))
        visuals.draw_parallax_background(
            canvas, FISH_PALETTE, frame_count=0, player_offset=(0.0, 0.0)
        )
        # 抽样几个像素：必须非纯白且包含蓝色调
        c = canvas.surface.get_at((640, 360))
        assert (c.r, c.g, c.b) != (0, 0, 0)
        assert (c.r, c.g, c.b) != (255, 255, 255)
        # 预期偏蓝（B > R）
        assert c.b > c.r

    def test_handles_extreme_player_offset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        canvas = _new_canvas()
        centers: list[tuple[float, float]] = []
        original_gradient_ellipse = canvas.gradient_ellipse

        def _record_gradient_ellipse(*args, **kwargs):
            center = kwargs.get("center")
            if center is not None:
                centers.append(center)
            return original_gradient_ellipse(*args, **kwargs)

        monkeypatch.setattr(canvas, "gradient_ellipse", _record_gradient_ellipse)
        # 任意夸张偏移都不应抛
        visuals.draw_parallax_background(
            canvas, FISH_PALETTE, frame_count=120, player_offset=(99999.0, -99999.0),
        )
        assert centers[0] == pytest.approx((640.0 - 30.0, 360.0 + 30.0))

    def test_animates_with_frame_count(self) -> None:
        c1 = _new_canvas()
        c2 = _new_canvas()
        visuals.draw_parallax_background(c1, FISH_PALETTE, frame_count=0)
        visuals.draw_parallax_background(c2, FISH_PALETTE, frame_count=200)
        # 两帧任一像素应不同（气泡 / 海草摆动）。气泡分布是稀疏的，所以
        # 大网格扫描而非定点对比。
        differ = False
        for x in range(0, 1280, 20):
            for y in range(0, 720, 20):
                if c1.surface.get_at((x, y)) != c2.surface.get_at((x, y)):
                    differ = True
                    break
            if differ:
                break
        assert differ


# ---------------------------------------------------------------------------
# draw_player / draw_fish / draw_boss 边界
# ---------------------------------------------------------------------------


class TestDrawEntities:
    def test_draw_player_each_tier(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        for tier in (0, 1, 2, 3, 4):
            world.player.grow_to(tier)
            visuals.draw_player(canvas, world.player, FISH_PALETTE, t_seconds=tier * 0.1)

    def test_draw_fish_states(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        # 触发 spawner 一次，造出至少几条 fish
        # 直接手动构造 1 条 fish 各 tier 各 state
        from toy_engine.rng import SeededRng

        from fish.ai.fish_ai import FishAIState
        from fish.entities.fish import Fish

        for tier in (1, 2, 3, 4):
            f = Fish.spawn(
                eid=100 + tier,
                tier=tier,
                pos=Vec2(640.0, 360.0),
                heading=0.5,
                rng=SeededRng(seed=tier),
            )
            for state in (FishAIState.WANDER, FishAIState.FLEE, FishAIState.CHASE):
                f.state = state
                visuals.draw_fish(canvas, f, FISH_PALETTE, player_tier=2, t_seconds=0.5)

    def test_draw_boss_all_states(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        boss = world.spawn_boss()
        from fish.ai.boss_ai import BossState

        for state in (
            BossState.PATROL, BossState.CHASE, BossState.CHARGE_WINDUP,
            BossState.CHARGE, BossState.STUNNED,
        ):
            boss.state = state
            for enraged in (False, True):
                boss.enraged = enraged
                visuals.draw_boss(canvas, boss, FISH_PALETTE, t_seconds=1.5)

    def test_draw_boss_during_intro(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        boss = world.spawn_boss()
        boss.intro_remaining = 2.0
        visuals.draw_boss(canvas, boss, FISH_PALETTE, t_seconds=0.0)

    def test_draw_boss_none_safe(self) -> None:
        canvas = _new_canvas()
        visuals.draw_boss(canvas, None, FISH_PALETTE, t_seconds=0.0)

    def test_draw_player_none_safe(self) -> None:
        canvas = _new_canvas()
        visuals.draw_player(canvas, None, FISH_PALETTE, t_seconds=0.0)

    def test_draw_fish_none_safe(self) -> None:
        canvas = _new_canvas()
        visuals.draw_fish(canvas, None, FISH_PALETTE, player_tier=0)


# ---------------------------------------------------------------------------
# UI / GameOver
# ---------------------------------------------------------------------------


class TestUI:
    def test_draw_ui_no_font_no_crash(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        snapshot = world.snapshot()
        # font=None 时应 silently 跳过
        visuals.draw_ui(canvas, snapshot, FISH_PALETTE, font=None)

    def test_draw_ui_with_font(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        if not pygame.font.get_init():
            pygame.font.init()
        font = pygame.font.Font(None, 20)
        snapshot = world.snapshot()
        visuals.draw_ui(canvas, snapshot, FISH_PALETTE, font=font)

    def test_draw_ui_with_boss_and_warning(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        world.spawn_boss()
        world.tier4_warning = True
        if not pygame.font.get_init():
            pygame.font.init()
        font = pygame.font.Font(None, 20)
        snapshot = world.snapshot()
        visuals.draw_ui(canvas, snapshot, FISH_PALETTE, font=font)

    def test_draw_ui_with_enraged_boss(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        boss = world.spawn_boss()
        boss.enraged = True
        boss.hp = 1
        if not pygame.font.get_init():
            pygame.font.init()
        font = pygame.font.Font(None, 20)
        visuals.draw_ui(canvas, world.snapshot(), FISH_PALETTE, font=font)

    def test_draw_game_over_each_result(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        if not pygame.font.get_init():
            pygame.font.init()
        font = pygame.font.Font(None, 32)
        for result in (GameResult.DEAD, GameResult.VICTORY, GameResult.TIMEOUT):
            world.game_result = result
            visuals.draw_game_over(canvas, world.snapshot(), FISH_PALETTE, font=font)

    def test_draw_game_over_skipped_when_running(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        # game_result is None → 不应做任何绘制（即不抛）
        before = canvas.surface.get_at((10, 10))
        visuals.draw_game_over(canvas, world.snapshot(), FISH_PALETTE, font=None)
        after = canvas.surface.get_at((10, 10))
        assert before == after


# ---------------------------------------------------------------------------
# PygRenderer 集成
# ---------------------------------------------------------------------------


class TestPygRenderer:
    def test_render_empty_world(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        renderer = PygRenderer(canvas, FISH_PALETTE, font=None)
        renderer.render(world)
        # 至少背景色被刷成非黑
        c = canvas.surface.get_at((50, 50))
        assert (c.r, c.g, c.b) != (0, 0, 0)

    def test_render_with_player_in_world(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        renderer = PygRenderer(canvas, FISH_PALETTE, font=None)
        renderer.render(world)

    def test_render_after_some_frames(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        # 跑 60 帧让 spawner 至少刷一波
        from toy_engine.input import InputFrame

        for _ in range(60):
            world.step(DT, InputFrame())
        renderer = PygRenderer(canvas, FISH_PALETTE, font=None)
        renderer.render(world)

    def test_render_with_boss(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        world.spawn_boss()
        renderer = PygRenderer(canvas, FISH_PALETTE, font=None)
        renderer.render(world)

    def test_render_terminal_states(self) -> None:
        canvas = _new_canvas()
        world = _new_world()
        if not pygame.font.get_init():
            pygame.font.init()
        font = pygame.font.Font(None, 32)
        renderer = PygRenderer(canvas, FISH_PALETTE, font=font)
        for result in (GameResult.DEAD, GameResult.VICTORY, GameResult.TIMEOUT):
            world.game_result = result
            renderer.render(world)

    def test_render_does_not_open_window(self) -> None:
        canvas = _new_canvas()
        # 离屏 canvas → present 必须 no-op
        canvas.present()
        # 上面没抛即可（headless 下 pygame.display 未初始化）

    def test_render_two_worlds_independent(self) -> None:
        # 不同 seed 的世界应可独立渲染（PygRenderer 无内部状态）
        canvas = _new_canvas()
        world_a = _new_world()
        world_b = _new_world()
        renderer = PygRenderer(canvas, FISH_PALETTE, font=None)
        renderer.render(world_a)
        renderer.render(world_b)


# ---------------------------------------------------------------------------
# imports + side effects
# ---------------------------------------------------------------------------


class TestModuleImports:
    def test_visuals_module_no_pygame_top_import(self) -> None:
        # visuals.py 不应直接 import pygame；只能间接通过 toy_engine.render
        import fish.render.visuals as v
        assert "pygame" not in v.__dict__

    def test_pyg_renderer_module_no_pygame_top_import(self) -> None:
        import fish.render.pyg_renderer as r
        assert "pygame" not in r.__dict__
