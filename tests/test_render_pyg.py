"""Tests for ``toy_engine.render.pyg`` — GeoCanvas + ScreenShake.

(M2-08 / 07-render.md §2, §3, §4.1)

All tests run headless via ``GeoCanvas.offscreen(...)``; pixel assertions
use ``surface.get_at()``.
"""

from __future__ import annotations

import math

import pytest

import pygame

from toy_engine.geom import Vec2
from toy_engine.render.palette import Palette
from toy_engine.render.pyg import GeoCanvas, ScreenShake
from toy_engine.rng import SeededRng


# ---------------------------------------------------------------------------
# Construction / lifecycle
# ---------------------------------------------------------------------------


def test_offscreen_creates_without_display():
    canvas = GeoCanvas.offscreen(64, 48)
    assert canvas.size == (64, 48)
    assert isinstance(canvas.surface, pygame.Surface)


def test_constructor_rejects_non_surface():
    with pytest.raises(TypeError):
        GeoCanvas("not a surface")  # type: ignore[arg-type]


def test_clear_default_black():
    canvas = GeoCanvas.offscreen(10, 10)
    canvas.clear((255, 255, 255))
    canvas.clear()
    px = canvas.surface.get_at((5, 5))
    assert (px.r, px.g, px.b) == (0, 0, 0)


def test_clear_color():
    canvas = GeoCanvas.offscreen(10, 10)
    canvas.clear((10, 20, 30))
    px = canvas.surface.get_at((5, 5))
    assert (px.r, px.g, px.b) == (10, 20, 30)


def test_present_offscreen_is_noop():
    canvas = GeoCanvas.offscreen(4, 4)
    canvas.present()  # must not raise


# ---------------------------------------------------------------------------
# Basic primitives — pixel assertions
# ---------------------------------------------------------------------------


def test_circle_draws_filled():
    canvas = GeoCanvas.offscreen(64, 64)
    canvas.clear((0, 0, 0))
    canvas.circle((32, 32), 10, (255, 0, 0))
    px = canvas.surface.get_at((32, 32))
    assert (px.r, px.g, px.b) == (255, 0, 0)
    far = canvas.surface.get_at((0, 0))
    assert (far.r, far.g, far.b) == (0, 0, 0)


def test_rect_draws():
    canvas = GeoCanvas.offscreen(40, 40)
    canvas.clear((0, 0, 0))
    canvas.rect((10, 10, 20, 20), (0, 255, 0))
    px = canvas.surface.get_at((20, 20))
    assert (px.r, px.g, px.b) == (0, 255, 0)


def test_line_draws():
    canvas = GeoCanvas.offscreen(20, 20)
    canvas.clear((0, 0, 0))
    canvas.line((0, 10), (19, 10), (255, 255, 255), width=1)
    px = canvas.surface.get_at((10, 10))
    assert (px.r, px.g, px.b) == (255, 255, 255)


def test_triangle_and_polygon():
    canvas = GeoCanvas.offscreen(60, 60)
    canvas.clear((0, 0, 0))
    canvas.triangle((10, 50), (30, 10), (50, 50), (0, 0, 255))
    # interior of triangle near centroid should be blue
    px = canvas.surface.get_at((30, 35))
    assert (px.r, px.g, px.b) == (0, 0, 255)


def test_rotated_polygon_matches_manual_rotation():
    canvas = GeoCanvas.offscreen(80, 80)
    canvas.clear((0, 0, 0))
    # Equilateral-ish triangle local pts; rotate 90 deg around (40,40).
    canvas.rotated_polygon(
        (40, 40),
        [(0, -10), (10, 10), (-10, 10)],
        math.pi / 2,
        (255, 255, 0),
    )
    # After +90deg rotation, top vertex (0,-10) goes to (10,0) → world (50,40).
    px = canvas.surface.get_at((48, 40))
    assert (px.r, px.g, px.b) == (255, 255, 0)


def test_arc_draws_within_bounding_box():
    canvas = GeoCanvas.offscreen(80, 80)
    canvas.clear((0, 0, 0))
    canvas.arc(
        (40, 40), length=60, height=60, angle=0.0,
        start_angle=0.0, end_angle=math.pi,
        color=(255, 0, 255), stroke_width=3,
    )
    # at least one magenta pixel must exist inside the bounding box
    found = False
    for y in range(10, 50):
        for x in range(10, 70):
            p = canvas.surface.get_at((x, y))
            if (p.r, p.g, p.b) == (255, 0, 255):
                found = True
                break
        if found:
            break
    assert found, "arc should produce visible magenta stroke"


# ---------------------------------------------------------------------------
# Bezier
# ---------------------------------------------------------------------------


def test_sample_bezier_quad_endpoints():
    canvas = GeoCanvas.offscreen(2, 2)
    pts = canvas.sample_bezier_quad((0, 0), (5, 10), (10, 0), samples=8)
    assert pts[0] == Vec2(0, 0)
    assert pts[-1] == Vec2(10, 0)
    assert len(pts) == 9


def test_sample_bezier_cubic_endpoints():
    canvas = GeoCanvas.offscreen(2, 2)
    pts = canvas.sample_bezier_cubic((0, 0), (1, 5), (9, 5), (10, 0), samples=12)
    assert pts[0] == Vec2(0, 0)
    assert pts[-1] == Vec2(10, 0)


def test_bezier_path_closed_fill():
    canvas = GeoCanvas.offscreen(80, 80)
    canvas.clear((0, 0, 0))
    # Two cubic segments that form a closed loop encircling (40,40).
    seg1 = ((10, 40), (10, 10), (70, 10), (70, 40))
    seg2 = ((70, 40), (70, 70), (10, 70), (10, 40))
    canvas.bezier_path(
        [seg1, seg2],
        closed=True,
        fill_color=(0, 200, 50),
        stroke_color=(255, 255, 255),
        stroke_width=1,
        samples_per_segment=12,
    )
    px = canvas.surface.get_at((40, 40))
    assert (px.r, px.g, px.b) == (0, 200, 50)


def test_bezier_path_invalid_segment_raises():
    canvas = GeoCanvas.offscreen(8, 8)
    with pytest.raises(ValueError):
        canvas.bezier_path([((0, 0), (1, 1))])  # only 2 control points


# ---------------------------------------------------------------------------
# Gradient ellipse + cache
# ---------------------------------------------------------------------------


def test_gradient_ellipse_linear_runs():
    GeoCanvas._clear_gradient_cache()
    canvas = GeoCanvas.offscreen(80, 80)
    canvas.clear((0, 0, 0))
    canvas.gradient_ellipse(
        center=(40, 40),
        length=60, width=30, angle=0.0,
        color_a=(255, 0, 0), color_b=(0, 0, 255),
        mode="linear", steps=8,
    )
    # at top of ellipse it should look red-ish (color_a side)
    p_top = canvas.surface.get_at((40, 27))
    p_bot = canvas.surface.get_at((40, 53))
    assert p_top.r > p_top.b
    assert p_bot.b > p_bot.r


def test_gradient_ellipse_radial_runs():
    GeoCanvas._clear_gradient_cache()
    canvas = GeoCanvas.offscreen(80, 80)
    canvas.clear((0, 0, 0))
    canvas.gradient_ellipse(
        center=(40, 40),
        length=60, width=60, angle=0.0,
        color_a=(255, 255, 255), color_b=(0, 0, 0),
        mode="radial", steps=12,
    )
    center_px = canvas.surface.get_at((40, 40))
    edge_px = canvas.surface.get_at((40, 25))
    # center brighter than near-edge
    assert sum((center_px.r, center_px.g, center_px.b)) > sum(
        (edge_px.r, edge_px.g, edge_px.b)
    )


def test_gradient_ellipse_caches_by_params():
    GeoCanvas._clear_gradient_cache()
    canvas = GeoCanvas.offscreen(80, 80)
    canvas.gradient_ellipse(
        center=(40, 40), length=60, width=30, angle=0.0,
        color_a=(10, 10, 10), color_b=(20, 20, 20), mode="linear", steps=8,
    )
    assert GeoCanvas._gradient_cache_size() == 1
    # Same params → cache hit, size still 1.
    canvas.gradient_ellipse(
        center=(10, 10), length=60, width=30, angle=0.5,
        color_a=(10, 10, 10), color_b=(20, 20, 20), mode="linear", steps=8,
    )
    assert GeoCanvas._gradient_cache_size() == 1
    # Different params → new entry.
    canvas.gradient_ellipse(
        center=(40, 40), length=80, width=30, angle=0.0,
        color_a=(10, 10, 10), color_b=(20, 20, 20), mode="linear", steps=8,
    )
    assert GeoCanvas._gradient_cache_size() == 2


def test_gradient_invalid_mode_raises():
    canvas = GeoCanvas.offscreen(20, 20)
    with pytest.raises(ValueError):
        canvas.gradient_ellipse(
            (10, 10), 10, 10, 0.0,
            (0, 0, 0), (255, 255, 255),
            mode="bogus",  # type: ignore[arg-type]
        )


def test_ellipse_long_axis_aligns_with_heading_at_45deg():
    """试玩反馈 #26：椭圆长轴必须沿 heading 方向。

    在 heading=π/4（screen-Y-down 时指向"右下"）下绘制 length>>width 的椭圆，
    长轴方向上、距中心 ~length/2 的点必须落在椭圆内（命中染色），而短轴方向
    上、距中心 ~length/2 的点必须在椭圆外（未染色）。
    在 bug 修复前（pygame.transform.rotate 角度未取负），45° 时长短轴互换 →
    长轴方向像素不命中、短轴方向像素命中，本测试将失败。
    """
    canvas = GeoCanvas.offscreen(160, 160)
    canvas.clear((0, 0, 0))
    cx, cy = 80, 80
    L, W = 80.0, 16.0  # 极扁椭圆放大长短轴差异
    heading = math.pi / 4.0
    canvas.ellipse(
        center=(cx, cy), length=L, height=W, angle=heading,
        color=(0, 255, 0), stroke_width=0,
    )
    # 长轴方向单位向量（screen-Y-down 与 heading 同号）
    dx, dy = math.cos(heading), math.sin(heading)
    # 取沿长轴 ~L*0.4 处（在椭圆内）
    px = int(round(cx + dx * L * 0.4))
    py = int(round(cy + dy * L * 0.4))
    along = canvas.surface.get_at((px, py))
    # 取垂直方向（短轴）~L*0.4 处（应在椭圆外）
    perp_dx, perp_dy = -dy, dx
    qx = int(round(cx + perp_dx * L * 0.4))
    qy = int(round(cy + perp_dy * L * 0.4))
    perp = canvas.surface.get_at((qx, qy))
    assert (along.r, along.g, along.b) == (0, 255, 0), (
        f"long-axis sample at heading {heading} rad should be inside ellipse, "
        f"got pixel={along}"
    )
    assert (perp.r, perp.g, perp.b) == (0, 0, 0), (
        f"perpendicular sample should be outside ellipse, got pixel={perp}"
    )


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


def test_text_renders_without_error():
    pygame.font.init()
    font = pygame.font.Font(None, 14)
    canvas = GeoCanvas.offscreen(120, 40)
    canvas.clear((0, 0, 0))
    canvas.text("hi", (10, 10), (255, 255, 255), font, anchor="topleft")
    # at least one pixel should now be brighter than 0
    found = False
    for y in range(40):
        for x in range(120):
            p = canvas.surface.get_at((x, y))
            if (p.r, p.g, p.b) != (0, 0, 0):
                found = True
                break
        if found:
            break
    assert found


def test_text_unknown_anchor_raises():
    pygame.font.init()
    font = pygame.font.Font(None, 14)
    canvas = GeoCanvas.offscreen(40, 20)
    with pytest.raises(ValueError):
        canvas.text("x", (5, 5), (255, 255, 255), font, anchor="bogus")


# ---------------------------------------------------------------------------
# Optional palette + rng wiring
# ---------------------------------------------------------------------------


def test_canvas_holds_palette_and_rng():
    pal = Palette({"a": (1, 2, 3)})
    rng = SeededRng(123)
    canvas = GeoCanvas(pygame.Surface((4, 4), 0, 32), palette=pal, rng=rng)
    assert canvas.palette is pal
    assert canvas.rng is rng


# ---------------------------------------------------------------------------
# ScreenShake
# ---------------------------------------------------------------------------


def test_screen_shake_offset_zero_when_idle():
    s = ScreenShake(max_magnitude_px=10.0)
    s.update(0.016)
    assert s.offset() == (0.0, 0.0)


def test_screen_shake_decays_to_zero():
    s = ScreenShake(max_magnitude_px=10.0)
    s.shake(8.0, 0.2)
    s.update(0.05)
    assert s.is_active
    s.update(0.5)  # past the duration
    assert not s.is_active
    assert s.offset() == (0.0, 0.0)


def test_screen_shake_combination_capped():
    s = ScreenShake(max_magnitude_px=10.0)
    s.shake(8.0, 0.5)
    s.shake(8.0, 0.5)  # hypot(8, 8) ≈ 11.3 → capped to 10
    # internal magnitude isn't public; assert via offset bound.
    s.update(0.001)
    ox, oy = s.offset()
    assert max(abs(ox), abs(oy)) <= 10.0 + 1e-6


def test_screen_shake_extends_duration():
    s = ScreenShake(max_magnitude_px=20.0)
    s.shake(5.0, 0.1)
    s.shake(5.0, 1.0)  # longer duration takes precedence
    # After 0.2s we should still be shaking because new duration was 1.0.
    s.update(0.2)
    assert s.is_active


def test_screen_shake_negative_args_raise():
    s = ScreenShake()
    with pytest.raises(ValueError):
        s.shake(-1, 0.1)
    with pytest.raises(ValueError):
        s.shake(1, -0.1)
    with pytest.raises(ValueError):
        s.update(-0.01)


def test_screen_shake_deterministic_with_seeded_rng():
    rng_a = SeededRng(99)
    rng_b = SeededRng(99)
    a = ScreenShake(max_magnitude_px=10.0, rng=rng_a)
    b = ScreenShake(max_magnitude_px=10.0, rng=rng_b)
    a.shake(6.0, 0.4)
    b.shake(6.0, 0.4)
    for _ in range(5):
        a.update(0.05)
        b.update(0.05)
        assert a.offset() == b.offset()


def test_with_no_shake_blocks_offset():
    canvas = GeoCanvas.offscreen(40, 40)
    canvas.shake.shake(20.0, 1.0)
    canvas.shake.update(0.1)
    # Force a measurable offset by direct injection (avoid test flakiness on
    # very small RNG samples).
    canvas.shake._cur_offset = (5.0, -5.0)
    assert canvas.shake.offset() == (5.0, -5.0)
    with canvas.with_no_shake():
        assert canvas._ox() == (0, 0)
        # draw a pixel at exact (10,10) — must land at (10,10), not offset.
        canvas.clear((0, 0, 0))
        canvas.rect((10, 10, 1, 1), (255, 255, 255))
        px = canvas.surface.get_at((10, 10))
        assert (px.r, px.g, px.b) == (255, 255, 255)
    # outside the with-block, offset comes back
    assert canvas._ox() == (5, -5)


def test_canvas_drawing_applies_shake_offset():
    canvas = GeoCanvas.offscreen(40, 40)
    canvas.shake._cur_offset = (3.0, 0.0)
    canvas.clear((0, 0, 0))
    canvas.rect((10, 10, 1, 1), (255, 255, 255))
    # The white pixel should be at x=13 (10 + 3), not x=10
    px_shifted = canvas.surface.get_at((13, 10))
    px_orig = canvas.surface.get_at((10, 10))
    assert (px_shifted.r, px_shifted.g, px_shifted.b) == (255, 255, 255)
    assert (px_orig.r, px_orig.g, px_orig.b) == (0, 0, 0)


def test_blit_apply_shake_false_ignores_offset():
    canvas = GeoCanvas.offscreen(40, 40)
    canvas.shake._cur_offset = (5.0, 0.0)
    canvas.clear((0, 0, 0))
    src = pygame.Surface((4, 4), 0, 32)
    src.fill((200, 50, 25))
    canvas.blit(src, (10, 10), apply_shake=False)
    px = canvas.surface.get_at((11, 11))
    assert (px.r, px.g, px.b) == (200, 50, 25)
    # Without apply_shake=True, no offset means (10,10) is the topleft.
    px_off = canvas.surface.get_at((16, 11))
    assert (px_off.r, px_off.g, px_off.b) == (0, 0, 0)


def test_blit_alpha_is_headless_safe_without_display():
    pygame.display.quit()
    assert not pygame.display.get_init()
    canvas = GeoCanvas.offscreen(8, 8)
    canvas.clear((0, 0, 0))
    src = pygame.Surface((4, 4), 0, 32)
    src.fill((255, 0, 0))
    canvas.blit(src, (2, 2), alpha=128)
    px = canvas.surface.get_at((3, 3))
    assert 120 <= px.r <= 135
    assert px.g == 0
    assert px.b == 0


def test_text_alpha_is_headless_safe_without_display():
    pygame.display.quit()
    assert not pygame.display.get_init()
    pygame.font.init()
    font = pygame.font.Font(None, 18)
    canvas = GeoCanvas.offscreen(80, 30)
    canvas.clear((0, 0, 0))
    canvas.text("hi", (5, 5), (255, 255, 255), font, alpha=128)
    assert not pygame.display.get_init()
    assert any(
        canvas.surface.get_at((x, y)).r > 0
        for y in range(30)
        for x in range(80)
    )


def test_max_magnitude_negative_rejected():
    with pytest.raises(ValueError):
        ScreenShake(-1.0)
