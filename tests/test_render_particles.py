"""Tests for ``toy_engine.render.particles`` (M2-08 / 07-render.md §4.2)."""

from __future__ import annotations

import math

import pytest

from toy_engine.geom import Vec2
from toy_engine.render.particles import (
    ParticleEmitter,
    ParticleSpec,
    ParticleSystem,
)
from toy_engine.render.pyg import GeoCanvas
from toy_engine.rng import SeededRng


def _spec(**kw):
    base = dict(
        pos=Vec2(0, 0),
        vel=Vec2(0, 0),
        color=(255, 0, 0),
        radius=4.0,
        life_s=1.0,
    )
    base.update(kw)
    return ParticleSpec(**base)


def test_capacity_and_initial_state():
    ps = ParticleSystem(capacity=8)
    assert ps.capacity == 8
    assert len(ps) == 0
    assert ps.alive_count() == 0


def test_capacity_must_be_positive():
    with pytest.raises(ValueError):
        ParticleSystem(0)


def test_emit_increments_count():
    ps = ParticleSystem(capacity=4)
    ps.emit(_spec())
    assert len(ps) == 1
    ps.emit(_spec())
    assert len(ps) == 2


def test_zero_life_is_rejected():
    ps = ParticleSystem()
    ps.emit(_spec(life_s=0.0))
    assert len(ps) == 0


def test_capacity_overwrites_oldest():
    ps = ParticleSystem(capacity=3)
    for i in range(10):
        ps.emit(_spec(pos=Vec2(float(i), 0.0), life_s=10.0))
    # Capacity should never be exceeded.
    assert len(ps) == 3
    alive_x = sorted(p.x for p in ps._slots if p.alive)
    assert alive_x == [7.0, 8.0, 9.0]


def test_update_kills_expired_particles():
    ps = ParticleSystem(capacity=4)
    ps.emit(_spec(life_s=0.5))
    ps.emit(_spec(life_s=2.0))
    ps.update(1.0)
    assert len(ps) == 1


def test_update_integrates_velocity_and_gravity():
    ps = ParticleSystem(capacity=2)
    ps.emit(_spec(vel=Vec2(10, 0), gravity=Vec2(0, 100), life_s=10.0))
    ps.update(0.1)
    p = ps._slots[0]
    # vx unchanged (no x-gravity), vy increased by 10
    assert math.isclose(p.vx, 10.0)
    assert math.isclose(p.vy, 10.0)
    # x = 10 * 0.1, y = 10 * 0.1 (vy after kick is 10, integrate)
    assert math.isclose(p.x, 1.0)
    assert math.isclose(p.y, 1.0)


def test_emit_burst_requires_rng():
    ps = ParticleSystem()
    with pytest.raises(TypeError):
        ps.emit_burst(
            5,
            center=Vec2(0, 0),
            speed_range=(10, 20),
            color=(1, 2, 3),
            radius_range=(1, 2),
            life_range=(0.1, 0.2),
            rng=None,  # type: ignore[arg-type]
        )


def test_emit_burst_deterministic_with_same_seed():
    a = ParticleSystem(capacity=64)
    b = ParticleSystem(capacity=64)
    ra = SeededRng(7)
    rb = SeededRng(7)
    kw = dict(
        center=Vec2(50, 50),
        speed_range=(20, 80),
        color=(255, 200, 100),
        radius_range=(2, 5),
        life_range=(0.3, 0.6),
    )
    a.emit_burst(20, rng=ra, **kw)
    b.emit_burst(20, rng=rb, **kw)
    for pa, pb in zip(a._slots, b._slots):
        if not pa.alive:
            assert not pb.alive
            continue
        assert pa.x == pb.x and pa.y == pb.y
        assert pa.vx == pb.vx and pa.vy == pb.vy
        assert pa.life == pb.life


def test_emit_from_carry_handles_low_rate():
    """rate=2/s, dt=0.1 should accumulate over multiple ticks instead of
    silently dropping fractional emissions."""
    ps = ParticleSystem(capacity=64)
    rng = SeededRng(1)
    em = ParticleEmitter(
        center=Vec2(0, 0),
        rate_per_s=2.0,
        angle_range=(0.0, 6.28),
        speed_range=(1.0, 1.0),
        color=(10, 20, 30),
        radius_range=(1.0, 1.0),
        life_range=(5.0, 5.0),
    )
    for _ in range(10):
        ps.emit_from(em, 0.1, rng)
    # 10 * 0.1 * 2 = 2 emissions expected (modulo carry)
    assert len(ps) == 2


def test_emit_from_deterministic_with_same_seed():
    a = ParticleSystem(capacity=64)
    b = ParticleSystem(capacity=64)
    ea = ParticleEmitter(
        center=Vec2(10, 20),
        rate_per_s=50.0,
        angle_range=(-0.5, 0.5),
        speed_range=(10.0, 30.0),
        color=(10, 20, 30),
        radius_range=(1.0, 3.0),
        life_range=(0.5, 1.5),
        color_end=(30, 20, 10),
        gravity=Vec2(0, 9.8),
    )
    eb = ParticleEmitter(
        center=Vec2(10, 20),
        rate_per_s=50.0,
        angle_range=(-0.5, 0.5),
        speed_range=(10.0, 30.0),
        color=(10, 20, 30),
        radius_range=(1.0, 3.0),
        life_range=(0.5, 1.5),
        color_end=(30, 20, 10),
        gravity=Vec2(0, 9.8),
    )
    a.emit_from(ea, 0.2, SeededRng(9))
    b.emit_from(eb, 0.2, SeededRng(9))
    assert len(a) == len(b) == 10
    for pa, pb in zip(a._slots, b._slots):
        assert pa.alive == pb.alive
        if not pa.alive:
            continue
        assert (pa.x, pa.y, pa.vx, pa.vy, pa.gx, pa.gy) == (
            pb.x, pb.y, pb.vx, pb.vy, pb.gx, pb.gy
        )
        assert (pa.life, pa.r0, pa.c0r, pa.c0g, pa.c0b, pa.c1r, pa.c1g, pa.c1b) == (
            pb.life, pb.r0, pb.c0r, pb.c0g, pb.c0b, pb.c1r, pb.c1g, pb.c1b
        )


def test_emit_from_respects_duration():
    ps = ParticleSystem(capacity=64)
    rng = SeededRng(1)
    em = ParticleEmitter(
        center=Vec2(0, 0),
        rate_per_s=10.0,
        angle_range=(0.0, 1.0),
        speed_range=(1.0, 1.0),
        color=(0, 0, 0),
        radius_range=(1.0, 1.0),
        life_range=(5.0, 5.0),
        duration_s=0.5,
    )
    # Run for 2 seconds total — only 0.5s worth of emissions allowed.
    for _ in range(20):
        ps.emit_from(em, 0.1, rng)
    # 10/s * 0.5s = 5 expected, but float carry can lose 1 emission to
    # rounding when dt is clipped at the duration boundary.
    assert 4 <= len(ps) <= 5


def test_color_end_interpolation_at_midlife():
    ps = ParticleSystem(capacity=2)
    ps.emit(
        _spec(color=(0, 0, 0), color_end=(200, 100, 50), life_s=1.0, fade=False)
    )
    ps.update(0.5)
    # After 0.5s, t = 0.5; halfway between (0,0,0) and (200,100,50)
    canvas = GeoCanvas.offscreen(64, 64)
    canvas.clear((255, 255, 255))
    # We can't easily extract the post-interp color without poking internals,
    # so verify via direct draw: pixel at (32,32) should be ~ midway color.
    p = ps._slots[0]
    p.x = 32; p.y = 32
    p.r0 = 5.0; p.has_radius_end = False
    ps.draw(canvas)
    px = canvas.surface.get_at((32, 32))
    # expect roughly (100, 50, 25) +/- rounding; allow tolerance
    assert abs(px.r - 100) <= 3
    assert abs(px.g - 50) <= 3
    assert abs(px.b - 25) <= 3


def test_radius_end_shrinks():
    ps = ParticleSystem(capacity=2)
    ps.emit(_spec(radius=10.0, radius_end=0.0, life_s=1.0, fade=False))
    ps.update(1.0 - 1e-3)  # near end of life
    p = ps._slots[0]
    assert p.alive  # not yet expired
    # at t≈1, radius near 0
    canvas = GeoCanvas.offscreen(40, 40)
    canvas.clear((255, 255, 255))
    p.x = 20; p.y = 20
    ps.draw(canvas)
    # nearly invisible — pixel at center should remain white-ish (radius < 0.5 skipped)
    px = canvas.surface.get_at((20, 20))
    assert (px.r, px.g, px.b) == (255, 255, 255)


def test_update_negative_dt_raises():
    ps = ParticleSystem()
    with pytest.raises(ValueError):
        ps.update(-0.1)


def test_draw_does_not_explode_when_empty():
    ps = ParticleSystem()
    canvas = GeoCanvas.offscreen(20, 20)
    ps.draw(canvas)  # no error
