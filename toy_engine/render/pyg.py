"""GeoCanvas + ScreenShake — pygame drawing wrapper.

See ``toy-engine/mvp/07-render.md``.

This module is the **only** place ``pygame`` is imported in the engine
(besides ``toy_engine.font`` re-export of ``font_utils``).  Tests run
headless with ``SDL_VIDEODRIVER=dummy`` set in ``tests/conftest.py``.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterable, Iterator, Literal

import pygame

from ..geom import Vec2

if TYPE_CHECKING:  # pragma: no cover
    from ..rng import SeededRng
    from .palette import Palette

__all__ = ["GeoCanvas", "ScreenShake"]

Color3 = tuple[int, int, int]


# ---------------------------------------------------------------------------
# ScreenShake
# ---------------------------------------------------------------------------


class ScreenShake:
    """Time-decaying screen shake.

    See 07-render.md §4.1.  Multiple ``shake(...)`` calls combine via
    ``hypot`` capped to ``max_magnitude_px``; remaining duration becomes
    ``max(current_remaining, new_duration)``.

    Random offsets are drawn from a sub-stream named ``"screen_shake"``
    (per spec).  If no ``rng`` is supplied a degenerate seeded one is
    created so deterministic tests still work without surprise.
    """

    def __init__(self, max_magnitude_px: float = 20.0, *, rng: "SeededRng | None" = None) -> None:
        if max_magnitude_px < 0:
            raise ValueError("max_magnitude_px must be non-negative")
        self._max = float(max_magnitude_px)
        self._magnitude = 0.0
        self._remaining = 0.0
        self._duration = 0.0
        if rng is None:
            from ..rng import SeededRng

            rng = SeededRng(0).spawn("screen_shake")
        else:
            rng = rng.spawn("screen_shake")
        self._rng = rng
        self._cur_offset: tuple[float, float] = (0.0, 0.0)

    def shake(self, magnitude_px: float, duration_s: float) -> None:
        if magnitude_px < 0 or duration_s < 0:
            raise ValueError("shake magnitude and duration must be non-negative")
        if duration_s == 0 or magnitude_px == 0:
            return
        combined = math.hypot(self._magnitude, magnitude_px)
        if combined > self._max:
            combined = self._max
        self._magnitude = combined
        if duration_s > self._remaining:
            self._remaining = duration_s
        self._duration = max(self._duration, duration_s)

    def update(self, dt: float) -> None:
        if dt < 0:
            raise ValueError("dt must be non-negative")
        if self._remaining <= 0:
            self._magnitude = 0.0
            self._remaining = 0.0
            self._duration = 0.0
            self._cur_offset = (0.0, 0.0)
            return
        self._remaining -= dt
        if self._remaining <= 0:
            self._remaining = 0.0
            self._magnitude = 0.0
            self._duration = 0.0
            self._cur_offset = (0.0, 0.0)
            return
        # linear decay over remaining/duration
        scale = self._remaining / self._duration if self._duration > 0 else 0.0
        amp = self._magnitude * scale
        if amp <= 0:
            self._cur_offset = (0.0, 0.0)
            return
        ox = self._rng.uniform(-amp, amp)
        oy = self._rng.uniform(-amp, amp)
        self._cur_offset = (ox, oy)

    def offset(self) -> tuple[float, float]:
        return self._cur_offset

    @property
    def is_active(self) -> bool:
        return self._remaining > 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_xy(p) -> tuple[float, float]:
    if isinstance(p, Vec2):
        return (p.x, p.y)
    x, y = p
    return (float(x), float(y))


def _ipair(p: tuple[float, float]) -> tuple[int, int]:
    return (int(round(p[0])), int(round(p[1])))


def _alpha_color(color: Color3, alpha: int) -> tuple[int, int, int, int]:
    if alpha < 0:
        alpha = 0
    elif alpha > 255:
        alpha = 255
    r, g, b = color
    return (int(r), int(g), int(b), int(alpha))


# ---------------------------------------------------------------------------
# GeoCanvas
# ---------------------------------------------------------------------------


class GeoCanvas:
    """Pygame Surface wrapper with geometry primitives + effects.

    Construction:
    - ``GeoCanvas(surface)`` for an already-existing surface
    - ``GeoCanvas.create_window(w, h, ...)`` for a real window
    - ``GeoCanvas.offscreen(w, h)`` for headless testing/screenshots
    """

    # Cache shared across all canvases (keyed by full param tuple).
    _GRADIENT_CACHE: "OrderedDict[tuple, pygame.Surface]" = OrderedDict()
    _GRADIENT_CACHE_LIMIT = 128

    def __init__(
        self,
        surface: "pygame.Surface",
        *,
        palette: "Palette | None" = None,
        rng: "SeededRng | None" = None,
    ) -> None:
        if not isinstance(surface, pygame.Surface):
            raise TypeError("GeoCanvas requires a pygame.Surface")
        self._surface = surface
        self._is_window = False
        self.palette = palette
        self.rng = rng
        self.shake = ScreenShake(rng=rng)
        self._shake_enabled = True

    # ---- factories ----
    @classmethod
    def create_window(
        cls,
        w: int,
        h: int,
        *,
        title: str = "",
        vsync: bool = True,
        palette: "Palette | None" = None,
    ) -> "GeoCanvas":
        if not pygame.get_init():
            pygame.init()
        if not pygame.display.get_init():
            pygame.display.init()
        flags = 0
        try:
            surface = pygame.display.set_mode((int(w), int(h)), flags, vsync=1 if vsync else 0)
        except TypeError:  # pragma: no cover - very old pygame
            surface = pygame.display.set_mode((int(w), int(h)), flags)
        if title:
            pygame.display.set_caption(title)
        c = cls(surface, palette=palette)
        c._is_window = True
        return c

    @classmethod
    def offscreen(cls, w: int, h: int) -> "GeoCanvas":
        """Create an offscreen canvas — never opens a window."""
        # 32-bit RGB so get_at() returns predictable Color objects without
        # needing a display to be initialized.
        surface = pygame.Surface((int(w), int(h)), 0, 32)
        return cls(surface)

    # ---- frame lifecycle ----
    def clear(self, color: Color3 | None = None) -> None:
        c = (0, 0, 0) if color is None else tuple(color)
        self._surface.fill(c)

    def present(self) -> None:
        if self._is_window:
            pygame.display.flip()

    @property
    def size(self) -> tuple[int, int]:
        return self._surface.get_size()

    @property
    def surface(self) -> "pygame.Surface":
        return self._surface

    @contextmanager
    def with_no_shake(self) -> Iterator["GeoCanvas"]:
        prev = self._shake_enabled
        self._shake_enabled = False
        try:
            yield self
        finally:
            self._shake_enabled = prev

    # ---- internal: shake offset ----
    def _ox(self) -> tuple[int, int]:
        if not self._shake_enabled:
            return (0, 0)
        ox, oy = self.shake.offset()
        return (int(round(ox)), int(round(oy)))

    def _apply(self, p: tuple[float, float]) -> tuple[int, int]:
        ox, oy = self._ox()
        return (int(round(p[0])) + ox, int(round(p[1])) + oy)

    # ---------------------- 3.1 basic primitives ----------------------
    def line(self, p0, p1, color: Color3, width: int = 1, alpha: int = 255) -> None:
        a = self._apply(_to_xy(p0))
        b = self._apply(_to_xy(p1))
        if alpha >= 255:
            pygame.draw.line(self._surface, color, a, b, max(1, int(width)))
        else:
            xs = [a[0], b[0]]
            ys = [a[1], b[1]]
            pad = max(1, int(width)) + 2
            x0, y0 = min(xs) - pad, min(ys) - pad
            x1, y1 = max(xs) + pad, max(ys) + pad
            w, h = x1 - x0, y1 - y0
            tmp = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.line(
                tmp, _alpha_color(color, alpha),
                (a[0] - x0, a[1] - y0),
                (b[0] - x0, b[1] - y0),
                max(1, int(width)),
            )
            self._surface.blit(tmp, (x0, y0))

    def circle(self, center, r, color: Color3, width: int = 0, alpha: int = 255) -> None:
        c = self._apply(_to_xy(center))
        ri = max(0, int(round(r)))
        if ri <= 0:
            return
        if alpha >= 255:
            pygame.draw.circle(self._surface, color, c, ri, max(0, int(width)))
        else:
            pad = ri + max(0, int(width)) + 2
            tmp = pygame.Surface((pad * 2, pad * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                tmp, _alpha_color(color, alpha),
                (pad, pad), ri, max(0, int(width)),
            )
            self._surface.blit(tmp, (c[0] - pad, c[1] - pad))

    def rect(self, aabb, color: Color3, width: int = 0, alpha: int = 255) -> None:
        # aabb may be AABB | pygame.Rect | (x,y,w,h)
        if hasattr(aabb, "x") and hasattr(aabb, "y") and hasattr(aabb, "w") and hasattr(aabb, "h"):
            x, y, w, h = aabb.x, aabb.y, aabb.w, aabb.h
        else:
            x, y, w, h = aabb
        ox, oy = self._ox()
        rx, ry = int(round(x)) + ox, int(round(y)) + oy
        rw, rh = int(round(w)), int(round(h))
        if alpha >= 255:
            pygame.draw.rect(self._surface, color, (rx, ry, rw, rh), max(0, int(width)))
        else:
            tmp = pygame.Surface((max(1, rw), max(1, rh)), pygame.SRCALPHA)
            pygame.draw.rect(
                tmp, _alpha_color(color, alpha),
                (0, 0, rw, rh), max(0, int(width)),
            )
            self._surface.blit(tmp, (rx, ry))

    def polygon(self, points: Iterable, color: Color3, width: int = 0, alpha: int = 255) -> None:
        pts = [self._apply(_to_xy(p)) for p in points]
        if len(pts) < 3:
            return
        if alpha >= 255:
            pygame.draw.polygon(self._surface, color, pts, max(0, int(width)))
        else:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            pad = max(0, int(width)) + 2
            x0, y0 = min(xs) - pad, min(ys) - pad
            x1, y1 = max(xs) + pad, max(ys) + pad
            w, h = max(1, x1 - x0), max(1, y1 - y0)
            tmp = pygame.Surface((w, h), pygame.SRCALPHA)
            local = [(p[0] - x0, p[1] - y0) for p in pts]
            pygame.draw.polygon(
                tmp, _alpha_color(color, alpha), local, max(0, int(width)),
            )
            self._surface.blit(tmp, (x0, y0))

    def rotated_polygon(
        self, center, local_points: Iterable, angle: float, color: Color3,
        width: int = 0, alpha: int = 255,
    ) -> None:
        cx, cy = _to_xy(center)
        ca, sa = math.cos(angle), math.sin(angle)
        world = [
            (cx + p[0] * ca - p[1] * sa, cy + p[0] * sa + p[1] * ca)
            for p in (_to_xy(pt) for pt in local_points)
        ]
        self.polygon(world, color, width=width, alpha=alpha)

    def triangle(self, p0, p1, p2, color: Color3, width: int = 0, alpha: int = 255) -> None:
        self.polygon([p0, p1, p2], color, width=width, alpha=alpha)

    def ellipse(
        self, center, length, height, angle: float, color: Color3,
        stroke_width: int = 0, alpha: int = 255,
    ) -> None:
        L = max(1, int(round(length)))
        H = max(1, int(round(height)))
        # build axis-aligned ellipse on small SRCALPHA surface, rotate, blit.
        tmp = pygame.Surface((L, H), pygame.SRCALPHA)
        pygame.draw.ellipse(
            tmp, _alpha_color(color, alpha),
            (0, 0, L, H), max(0, int(stroke_width)),
        )
        if angle != 0:
            # pygame.transform.rotate is CCW in standard math coords; our
            # `angle` is a heading in screen-Y-down (CW positive), so negate.
            # Without this, ellipses appeared correct only at 0°/90°/180°/270°
            # (where AABB is symmetric) and rotated 90° off at 45°/135°/...
            # See fish-doc/mvp/progress.md 发现 #26.
            rotated = pygame.transform.rotate(tmp, -math.degrees(angle))
        else:
            rotated = tmp
        rect = rotated.get_rect()
        cx, cy = self._apply(_to_xy(center))
        rect.center = (cx, cy)
        self._surface.blit(rotated, rect.topleft)

    def arc(
        self, center, length, height, angle: float,
        start_angle: float, end_angle: float, color: Color3,
        stroke_width: int = 1, alpha: int = 255,
    ) -> None:
        L = max(1, int(round(length)))
        H = max(1, int(round(height)))
        tmp = pygame.Surface((L, H), pygame.SRCALPHA)
        # pygame.draw.arc takes angles in radians, CCW from +x.
        sw = max(1, int(stroke_width))
        pygame.draw.arc(
            tmp, _alpha_color(color, alpha),
            (0, 0, L, H), float(start_angle), float(end_angle), sw,
        )
        if angle != 0:
            # See ellipse() above: negate to match screen-Y-down heading.
            rotated = pygame.transform.rotate(tmp, -math.degrees(angle))
        else:
            rotated = tmp
        rect = rotated.get_rect()
        cx, cy = self._apply(_to_xy(center))
        rect.center = (cx, cy)
        self._surface.blit(rotated, rect.topleft)

    def fan(
        self, center, r: float, angle_start: float, angle_end: float,
        color: Color3, alpha: int = 255,
    ) -> None:
        if r <= 0:
            return
        steps = max(8, int(abs(angle_end - angle_start) * 8))
        cx, cy = _to_xy(center)
        pts = [(cx, cy)]
        for i in range(steps + 1):
            t = i / steps
            a = angle_start + (angle_end - angle_start) * t
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        self.polygon(pts, color, width=0, alpha=alpha)

    def blit(
        self, source: "pygame.Surface", dest, *, alpha: int = 255,
        special_flags: int = 0, apply_shake: bool = True,
    ) -> None:
        if apply_shake:
            d = self._apply(_to_xy(dest))
        else:
            xy = _to_xy(dest)
            d = (int(round(xy[0])), int(round(xy[1])))
        if alpha >= 255:
            self._surface.blit(source, d, special_flags=special_flags)
            return
        # Apply alpha by copying to a fresh SRCALPHA surface; this is only
        # for rare per-frame cases — caller should prefer per-Surface alpha
        # via ``set_alpha`` for hot paths.
        tmp = source.copy()
        tmp.set_alpha(int(alpha))
        self._surface.blit(tmp, d, special_flags=special_flags)

    # ---------------------- 3.4 bezier ----------------------
    def sample_bezier_quad(self, p0, p1, p2, samples: int = 16) -> list[Vec2]:
        if samples < 2:
            samples = 2
        a = _to_xy(p0); b = _to_xy(p1); c = _to_xy(p2)
        out: list[Vec2] = []
        for i in range(samples + 1):
            t = i / samples
            mt = 1.0 - t
            x = mt * mt * a[0] + 2 * mt * t * b[0] + t * t * c[0]
            y = mt * mt * a[1] + 2 * mt * t * b[1] + t * t * c[1]
            out.append(Vec2(x, y))
        return out

    def sample_bezier_cubic(self, p0, p1, p2, p3, samples: int = 24) -> list[Vec2]:
        if samples < 2:
            samples = 2
        a = _to_xy(p0); b = _to_xy(p1); c = _to_xy(p2); d = _to_xy(p3)
        out: list[Vec2] = []
        for i in range(samples + 1):
            t = i / samples
            mt = 1.0 - t
            x = mt**3 * a[0] + 3 * mt**2 * t * b[0] + 3 * mt * t * t * c[0] + t**3 * d[0]
            y = mt**3 * a[1] + 3 * mt**2 * t * b[1] + 3 * mt * t * t * c[1] + t**3 * d[1]
            out.append(Vec2(x, y))
        return out

    def bezier_quad(
        self, p0, p1, p2, color: Color3, width: int = 1,
        samples: int = 16, alpha: int = 255,
    ) -> None:
        pts = self.sample_bezier_quad(p0, p1, p2, samples)
        self._stroke_polyline(pts, color, width, alpha)

    def bezier_cubic(
        self, p0, p1, p2, p3, color: Color3, width: int = 1,
        samples: int = 24, alpha: int = 255,
    ) -> None:
        pts = self.sample_bezier_cubic(p0, p1, p2, p3, samples)
        self._stroke_polyline(pts, color, width, alpha)

    def bezier_path(
        self,
        segments: Iterable,
        *,
        closed: bool = False,
        fill_color: Color3 | None = None,
        stroke_color: Color3 | None = None,
        stroke_width: int = 1,
        samples_per_segment: int = 16,
        alpha: int = 255,
    ) -> None:
        sampled: list[Vec2] = []
        for seg in segments:
            if len(seg) == 3:
                pts = self.sample_bezier_quad(seg[0], seg[1], seg[2], samples_per_segment)
            elif len(seg) == 4:
                pts = self.sample_bezier_cubic(seg[0], seg[1], seg[2], seg[3], samples_per_segment)
            else:
                raise ValueError(f"bezier segment must have 3 (quad) or 4 (cubic) control points, got {len(seg)}")
            # Avoid duplicating the join point between segments.
            if sampled and pts:
                sampled.extend(pts[1:])
            else:
                sampled.extend(pts)
        if not sampled:
            return
        if closed and fill_color is not None:
            self.polygon(sampled, fill_color, width=0, alpha=alpha)
        if stroke_color is not None:
            if closed:
                pts = list(sampled) + [sampled[0]]
            else:
                pts = sampled
            self._stroke_polyline(pts, stroke_color, stroke_width, alpha)

    def _stroke_polyline(self, pts: list[Vec2], color: Color3, width: int, alpha: int) -> None:
        if len(pts) < 2:
            return
        if alpha >= 255:
            xy = [self._apply(_to_xy(p)) for p in pts]
            pygame.draw.lines(self._surface, color, False, xy, max(1, int(width)))
        else:
            xy = [self._apply(_to_xy(p)) for p in pts]
            xs = [p[0] for p in xy]
            ys = [p[1] for p in xy]
            pad = max(1, int(width)) + 2
            x0, y0 = min(xs) - pad, min(ys) - pad
            x1, y1 = max(xs) + pad, max(ys) + pad
            w, h = max(1, x1 - x0), max(1, y1 - y0)
            tmp = pygame.Surface((w, h), pygame.SRCALPHA)
            local = [(p[0] - x0, p[1] - y0) for p in xy]
            pygame.draw.lines(
                tmp, _alpha_color(color, alpha), False, local, max(1, int(width)),
            )
            self._surface.blit(tmp, (x0, y0))

    # ---------------------- 3.5 text ----------------------
    def text(
        self, s: str, pos, color: Color3, font, *,
        anchor: str = "topleft", alpha: int = 255,
    ) -> None:
        if not pygame.font.get_init():
            pygame.font.init()
        rendered = font.render(s, True, color)
        if alpha < 255:
            rendered = rendered.copy()
            rendered.set_alpha(int(alpha))
        rect = rendered.get_rect()
        target = self._apply(_to_xy(pos))
        if not hasattr(rect, anchor):
            raise ValueError(f"unknown rect anchor: {anchor!r}")
        setattr(rect, anchor, target)
        self._surface.blit(rendered, rect.topleft)

    # ---------------------- 3.2 gradient ellipse ----------------------
    def gradient_ellipse(
        self,
        center,
        length,
        width,
        angle: float,
        color_a: Color3,
        color_b: Color3,
        *,
        mode: Literal["linear", "radial"] = "linear",
        alpha: int = 255,
        steps: int = 16,
    ) -> None:
        L = max(1, int(round(length)))
        W = max(1, int(round(width)))
        ca = (int(color_a[0]), int(color_a[1]), int(color_a[2]))
        cb = (int(color_b[0]), int(color_b[1]), int(color_b[2]))
        a8 = max(0, min(255, int(alpha)))
        st = max(2, int(steps))
        key = (mode, L, W, ca, cb, a8, st)
        cache = type(self)._GRADIENT_CACHE
        base = cache.get(key)
        if base is None:
            base = self._build_gradient_surface(L, W, ca, cb, mode, a8, st)
            cache[key] = base
            if len(cache) > type(self)._GRADIENT_CACHE_LIMIT:
                cache.popitem(last=False)
        else:
            cache.move_to_end(key)
        if angle != 0:
            # See ellipse() above: negate to match screen-Y-down heading.
            rotated = pygame.transform.rotate(base, -math.degrees(angle))
        else:
            rotated = base
        rect = rotated.get_rect()
        cx, cy = self._apply(_to_xy(center))
        rect.center = (cx, cy)
        self._surface.blit(rotated, rect.topleft)

    @staticmethod
    def _build_gradient_surface(
        L: int, W: int,
        color_a: Color3, color_b: Color3,
        mode: str, alpha: int, steps: int,
    ) -> "pygame.Surface":
        surf = pygame.Surface((L, W), pygame.SRCALPHA)
        # alpha mask for the ellipse
        mask = pygame.Surface((L, W), pygame.SRCALPHA)
        pygame.draw.ellipse(mask, (255, 255, 255, alpha), (0, 0, L, W))
        if mode == "linear":
            # Linear gradient along the short axis (Y, height=W), split
            # into ``steps`` bands as exposed by the public API.
            bands = min(max(2, steps), W)
            for i in range(bands):
                y0 = int(round(i * W / bands))
                y1 = int(round((i + 1) * W / bands))
                t = i / max(1, bands - 1)
                r = int(color_a[0] + (color_b[0] - color_a[0]) * t)
                g = int(color_a[1] + (color_b[1] - color_a[1]) * t)
                b = int(color_a[2] + (color_b[2] - color_a[2]) * t)
                pygame.draw.rect(surf, (r, g, b, 255), (0, y0, L, max(1, y1 - y0)))
        elif mode == "radial":
            # color_a center, color_b edge — paint progressively smaller
            # concentric ellipses inward, ``steps`` of them.
            for i in range(steps):
                t = i / max(1, steps - 1)
                # outer (i=0) = edge color_b; inner (i=steps-1) = center color_a
                r = int(color_b[0] + (color_a[0] - color_b[0]) * t)
                g = int(color_b[1] + (color_a[1] - color_b[1]) * t)
                b = int(color_b[2] + (color_a[2] - color_b[2]) * t)
                shrink = 1.0 - t
                lw = max(1, int(round(L * shrink)))
                hh = max(1, int(round(W * shrink)))
                rect = pygame.Rect(0, 0, lw, hh)
                rect.center = (L // 2, W // 2)
                pygame.draw.ellipse(surf, (r, g, b, 255), rect)
        else:
            raise ValueError(f"gradient mode must be 'linear' or 'radial', got {mode!r}")
        # apply ellipse alpha mask via BLEND_RGBA_MULT — keep RGB, multiply
        # by mask alpha so outside-of-ellipse becomes alpha 0.
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return surf

    @classmethod
    def _clear_gradient_cache(cls) -> None:
        """Test hook."""
        cls._GRADIENT_CACHE.clear()

    @classmethod
    def _gradient_cache_size(cls) -> int:
        return len(cls._GRADIENT_CACHE)
