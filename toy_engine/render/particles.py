"""ParticleSystem — generic, pygame-agnostic particle simulation.

See ``toy-engine/mvp/07-render.md`` §4.2.

Performance notes: the per-particle update loop deliberately avoids method
calls on ``Vec2`` (which would allocate), instead operating on flat
``_x/_y/_vx/_vy`` arrays-of-floats inside the active list. The MVP target is
512 active particles at 60 FPS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..geom import Vec2

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..rng import SeededRng
    from .pyg import GeoCanvas

__all__ = ["ParticleSpec", "ParticleEmitter", "ParticleSystem"]

Color3 = tuple[int, int, int]


@dataclass
class ParticleSpec:
    pos: Vec2
    vel: Vec2
    color: Color3
    radius: float
    life_s: float
    gravity: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    drag: float = 0.0
    color_end: Color3 | None = None
    radius_end: float | None = None
    fade: bool = True


@dataclass
class ParticleEmitter:
    center: Vec2
    rate_per_s: float
    angle_range: tuple[float, float]
    speed_range: tuple[float, float]
    color: Color3
    radius_range: tuple[float, float]
    life_range: tuple[float, float]
    color_end: Color3 | None = None
    gravity: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))
    duration_s: float | None = None
    carry: float = 0.0
    _elapsed_s: float = field(default=0.0, init=False, repr=False, compare=False)


class _Particle:
    """Mutable per-particle struct kept inside a ring buffer."""

    __slots__ = (
        "alive",
        "x", "y",
        "vx", "vy",
        "gx", "gy",
        "drag",
        "age", "life",
        "r0", "r1",
        "c0r", "c0g", "c0b",
        "c1r", "c1g", "c1b",
        "has_color_end", "has_radius_end",
        "fade",
    )

    def __init__(self) -> None:
        self.alive = False
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.gx = 0.0
        self.gy = 0.0
        self.drag = 0.0
        self.age = 0.0
        self.life = 0.0
        self.r0 = 1.0
        self.r1 = 1.0
        self.c0r = self.c0g = self.c0b = 0
        self.c1r = self.c1g = self.c1b = 0
        self.has_color_end = False
        self.has_radius_end = False
        self.fade = True


class ParticleSystem:
    """Ring-buffered particle pool.

    On overflow we overwrite the *oldest* slot to avoid GC churn — this
    means very-long-lived particles in a saturated system can be evicted
    early; that is documented behavior of MVP.
    """

    def __init__(self, capacity: int = 512) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = int(capacity)
        self._slots: list[_Particle] = [_Particle() for _ in range(self._capacity)]
        # ring write pointer
        self._head = 0
        # number of alive particles (for tests / metrics)
        self._alive_count = 0

    # ----- inspection -----
    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return self._alive_count

    def alive_count(self) -> int:
        return self._alive_count

    # ----- emission -----
    def _next_slot(self) -> _Particle:
        # Prefer a dead slot near the head; fall back to overwriting head.
        cap = self._capacity
        for _ in range(cap):
            slot = self._slots[self._head]
            self._head = (self._head + 1) % cap
            if not slot.alive:
                return slot
        # Fully saturated — overwrite oldest (current head).
        slot = self._slots[self._head]
        self._head = (self._head + 1) % cap
        # was alive, gets overwritten — alive_count stays the same.
        slot.alive = False
        self._alive_count -= 1
        return slot

    def _populate(self, p: _Particle, spec: ParticleSpec) -> None:
        if spec.life_s <= 0:
            # zero-life particles are rejected (would div-by-zero in interp).
            return
        p.alive = True
        p.x = spec.pos.x
        p.y = spec.pos.y
        p.vx = spec.vel.x
        p.vy = spec.vel.y
        p.gx = spec.gravity.x
        p.gy = spec.gravity.y
        p.drag = spec.drag
        p.age = 0.0
        p.life = spec.life_s
        p.r0 = spec.radius
        p.r1 = spec.radius_end if spec.radius_end is not None else spec.radius
        p.has_radius_end = spec.radius_end is not None
        p.c0r, p.c0g, p.c0b = spec.color
        if spec.color_end is not None:
            p.c1r, p.c1g, p.c1b = spec.color_end
            p.has_color_end = True
        else:
            p.c1r, p.c1g, p.c1b = spec.color
            p.has_color_end = False
        p.fade = spec.fade
        self._alive_count += 1

    def emit(self, spec: ParticleSpec) -> None:
        if spec.life_s <= 0:
            return
        slot = self._next_slot()
        self._populate(slot, spec)

    def emit_burst(
        self,
        n: int,
        *,
        center: Vec2,
        speed_range: tuple[float, float],
        color: Color3,
        radius_range: tuple[float, float],
        life_range: tuple[float, float],
        rng: "SeededRng",
    ) -> None:
        if rng is None:
            raise TypeError("emit_burst requires an explicit SeededRng instance")
        if n <= 0:
            return
        from math import cos, pi, sin, tau

        s_lo, s_hi = speed_range
        r_lo, r_hi = radius_range
        l_lo, l_hi = life_range
        for _ in range(n):
            theta = rng.uniform(0.0, tau)
            speed = rng.uniform(s_lo, s_hi)
            radius = rng.uniform(r_lo, r_hi)
            life = rng.uniform(l_lo, l_hi)
            spec = ParticleSpec(
                pos=center,
                vel=Vec2(cos(theta) * speed, sin(theta) * speed),
                color=color,
                radius=radius,
                life_s=life,
            )
            self.emit(spec)

    def emit_from(self, emitter: ParticleEmitter, dt: float, rng: "SeededRng") -> None:
        if rng is None:
            raise TypeError("emit_from requires an explicit SeededRng instance")
        if dt <= 0:
            return
        if emitter.duration_s is not None:
            if emitter._elapsed_s >= emitter.duration_s:
                return
            # clip dt so we don't over-emit past duration
            remain = emitter.duration_s - emitter._elapsed_s
            if dt > remain:
                dt = remain
        emitter._elapsed_s += dt
        from math import cos, sin

        emitter.carry += emitter.rate_per_s * dt
        n = int(emitter.carry)
        emitter.carry -= n
        a_lo, a_hi = emitter.angle_range
        s_lo, s_hi = emitter.speed_range
        r_lo, r_hi = emitter.radius_range
        l_lo, l_hi = emitter.life_range
        for _ in range(n):
            theta = rng.uniform(a_lo, a_hi)
            speed = rng.uniform(s_lo, s_hi)
            radius = rng.uniform(r_lo, r_hi)
            life = rng.uniform(l_lo, l_hi)
            spec = ParticleSpec(
                pos=emitter.center,
                vel=Vec2(cos(theta) * speed, sin(theta) * speed),
                color=emitter.color,
                radius=radius,
                life_s=life,
                color_end=emitter.color_end,
                gravity=emitter.gravity,
            )
            self.emit(spec)

    # ----- simulation -----
    def update(self, dt: float) -> None:
        if dt < 0:
            raise ValueError("dt must be non-negative")
        if dt == 0:
            return
        for p in self._slots:
            if not p.alive:
                continue
            p.age += dt
            if p.age >= p.life:
                p.alive = False
                self._alive_count -= 1
                continue
            # integrate
            p.vx += p.gx * dt
            p.vy += p.gy * dt
            if p.drag:
                # exponential drag, cheap approximation
                k = 1.0 - p.drag * dt
                if k < 0.0:
                    k = 0.0
                p.vx *= k
                p.vy *= k
            p.x += p.vx * dt
            p.y += p.vy * dt

    # ----- rendering -----
    def draw(self, canvas: "GeoCanvas") -> None:
        for p in self._slots:
            if not p.alive:
                continue
            t = p.age / p.life if p.life > 0 else 0.0
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            if p.has_radius_end:
                radius = p.r0 + (p.r1 - p.r0) * t
            else:
                radius = p.r0
            if radius < 0.5:
                continue
            if p.has_color_end:
                cr = int(p.c0r + (p.c1r - p.c0r) * t)
                cg = int(p.c0g + (p.c1g - p.c0g) * t)
                cb = int(p.c0b + (p.c1b - p.c0b) * t)
            else:
                cr, cg, cb = p.c0r, p.c0g, p.c0b
            alpha = 255
            if p.fade:
                alpha = int(round(255 * (1.0 - t)))
                if alpha < 0:
                    alpha = 0
                elif alpha > 255:
                    alpha = 255
            canvas.circle((p.x, p.y), radius, (cr, cg, cb), width=0, alpha=alpha)
