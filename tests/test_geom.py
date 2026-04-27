"""Unit tests for ``toy_engine.geom`` (DoD of toy-engine/mvp/06-geom.md)."""

from __future__ import annotations

import math

import pytest

from toy_engine.geom import (
    AABB,
    Vec2,
    aabb_overlap,
    angle_delta,
    angle_in_arc,
    angle_lerp,
    circle_circle_overlap,
    circle_circle_penetration,
    clamp,
    lerp,
    lerp_vec,
    rotate_toward,
    smoothstep,
    wrap_angle,
)


# ---------------------------------------------------------------------------
# Vec2: add/sub/mul/div, normalize (zero edge), rotation, angle round-trip
# ---------------------------------------------------------------------------


class TestVec2:
    def test_add_sub(self) -> None:
        a = Vec2(1.0, 2.0)
        b = Vec2(3.0, -1.0)
        assert a + b == Vec2(4.0, 1.0)
        assert a - b == Vec2(-2.0, 3.0)

    def test_mul_div_neg(self) -> None:
        v = Vec2(2.0, -4.0)
        assert v * 3 == Vec2(6.0, -12.0)
        assert 3 * v == Vec2(6.0, -12.0)
        assert v / 2 == Vec2(1.0, -2.0)
        assert -v == Vec2(-2.0, 4.0)

    def test_length_and_dot_cross(self) -> None:
        v = Vec2(3.0, 4.0)
        assert v.length() == pytest.approx(5.0)
        assert v.length_sq() == pytest.approx(25.0)
        assert Vec2(1.0, 0.0).dot(Vec2(0.0, 1.0)) == 0.0
        assert Vec2(1.0, 0.0).cross(Vec2(0.0, 1.0)) == pytest.approx(1.0)

    def test_normalized_unit(self) -> None:
        v = Vec2(3.0, 4.0).normalized()
        assert v.length() == pytest.approx(1.0)
        assert v.x == pytest.approx(0.6)
        assert v.y == pytest.approx(0.8)

    def test_normalized_zero_returns_zero(self) -> None:
        assert Vec2(0.0, 0.0).normalized() == Vec2(0.0, 0.0)
        # 极小向量也应被视为零，避免 NaN/数值爆炸。
        assert Vec2(1e-12, 0.0).normalized() == Vec2(0.0, 0.0)

    def test_with_length_zero(self) -> None:
        assert Vec2(0.0, 0.0).with_length(5.0) == Vec2(0.0, 0.0)
        v = Vec2(3.0, 4.0).with_length(10.0)
        assert v.length() == pytest.approx(10.0)

    def test_rotated(self) -> None:
        v = Vec2(1.0, 0.0).rotated(math.pi / 2)
        assert v.x == pytest.approx(0.0, abs=1e-12)
        assert v.y == pytest.approx(1.0)
        # 旋转 2π 回到原点
        v2 = Vec2(1.0, 0.0).rotated(2 * math.pi)
        assert v2.x == pytest.approx(1.0)
        assert v2.y == pytest.approx(0.0, abs=1e-12)

    def test_angle_roundtrip(self) -> None:
        for theta in (-math.pi + 0.1, -1.0, 0.0, 0.7, math.pi - 0.1):
            v = Vec2.from_angle(theta, length=2.5)
            assert v.length() == pytest.approx(2.5)
            assert v.angle() == pytest.approx(theta)

    def test_frozen_and_hashable(self) -> None:
        v = Vec2(1.0, 2.0)
        with pytest.raises(Exception):
            v.x = 5.0  # type: ignore[misc]
        # 同值可作为 dict key
        assert {Vec2(1.0, 2.0): "a"}[Vec2(1.0, 2.0)] == "a"


# ---------------------------------------------------------------------------
# 圆碰撞
# ---------------------------------------------------------------------------


class TestCircleCircle:
    def test_overlap_tangent_boundary_true(self) -> None:
        # (a-b).length == ra+rb 必须返回 True（相切视为相交）
        assert circle_circle_overlap((0.0, 0.0), 1.0, (3.0, 0.0), 2.0) is True

    def test_overlap_disjoint_false(self) -> None:
        assert circle_circle_overlap((0.0, 0.0), 1.0, (3.001, 0.0), 2.0) is False

    def test_overlap_accepts_vec2_and_tuple(self) -> None:
        assert circle_circle_overlap(Vec2(0.0, 0.0), 1.0, (1.0, 0.0), 1.0) is True

    def test_overlap_rejects_negative_radius(self) -> None:
        with pytest.raises(ValueError):
            circle_circle_overlap((0.0, 0.0), -1.0, (1.0, 0.0), 1.0)

    def test_penetration_disjoint_returns_none(self) -> None:
        assert (
            circle_circle_penetration((0.0, 0.0), 1.0, (10.0, 0.0), 1.0) is None
        )

    def test_penetration_overlap_direction_and_depth(self) -> None:
        # a 在 b 右侧 1 单位，半径各 1，穿插深度 = 2-1 = 1
        result = circle_circle_penetration((1.0, 0.0), 1.0, (0.0, 0.0), 1.0)
        assert result is not None
        push, depth = result
        assert push.x == pytest.approx(1.0)
        assert push.y == pytest.approx(0.0)
        assert depth == pytest.approx(1.0)
        # 业务用法：a += push * depth/2 后两圆相切
        # 即新中心距离 = 原距离 + depth = 1 + 1 = 2 = ra + rb ✓

    def test_penetration_concentric_no_nan(self) -> None:
        result = circle_circle_penetration((0.0, 0.0), 1.5, (0.0, 0.0), 2.5)
        assert result is not None
        push, depth = result
        assert math.isfinite(push.x) and math.isfinite(push.y)
        assert push == Vec2(1.0, 0.0)
        assert depth == pytest.approx(4.0)  # ra + rb 兜底

    def test_penetration_near_concentric_uses_theoretical_depth(self) -> None:
        result = circle_circle_penetration(
            (0.05, 0.0), 1.0, (0.0, 0.0), 1.0, eps=0.1
        )
        assert result is not None
        push, depth = result
        assert push == Vec2(1.0, 0.0)
        assert depth == pytest.approx(1.95)


# ---------------------------------------------------------------------------
# 标量工具
# ---------------------------------------------------------------------------


class TestScalarUtils:
    def test_clamp(self) -> None:
        assert clamp(5, 0, 10) == 5
        assert clamp(-1, 0, 10) == 0
        assert clamp(11, 0, 10) == 10

    def test_clamp_invalid_range(self) -> None:
        with pytest.raises(ValueError):
            clamp(0, 1, 0)

    def test_lerp(self) -> None:
        assert lerp(0.0, 10.0, 0.0) == 0.0
        assert lerp(0.0, 10.0, 1.0) == 10.0
        assert lerp(0.0, 10.0, 0.5) == 5.0
        # 允许外推
        assert lerp(0.0, 10.0, 2.0) == 20.0

    def test_lerp_vec_accepts_tuple(self) -> None:
        v = lerp_vec((0.0, 0.0), (10.0, 20.0), 0.25)
        assert v == Vec2(2.5, 5.0)
        v2 = lerp_vec(Vec2(0.0, 0.0), Vec2(10.0, 20.0), 0.5)
        assert v2 == Vec2(5.0, 10.0)

    def test_smoothstep_basic(self) -> None:
        assert smoothstep(0.0, 1.0, -1.0) == 0.0
        assert smoothstep(0.0, 1.0, 2.0) == 1.0
        assert smoothstep(0.0, 1.0, 0.5) == pytest.approx(0.5)
        # 单调
        assert smoothstep(0.0, 1.0, 0.25) < smoothstep(0.0, 1.0, 0.75)

    def test_smoothstep_degenerate_no_div_zero(self) -> None:
        # edge0 == edge1 退化为阶跃函数
        assert smoothstep(1.0, 1.0, 0.5) == 0.0
        assert smoothstep(1.0, 1.0, 1.5) == 1.0


# ---------------------------------------------------------------------------
# 角度工具
# ---------------------------------------------------------------------------


class TestAngleUtils:
    def test_wrap_angle_boundaries(self) -> None:
        assert wrap_angle(3 * math.pi) == pytest.approx(math.pi)
        assert wrap_angle(-3 * math.pi) == pytest.approx(-math.pi)
        assert wrap_angle(math.pi) == pytest.approx(math.pi)
        assert wrap_angle(-math.pi) == pytest.approx(-math.pi)
        assert wrap_angle(0.0) == 0.0
        assert wrap_angle(0.5) == pytest.approx(0.5)

    def test_wrap_angle_range(self) -> None:
        for theta in (-10.0, -3.7, -1.0, 0.0, 1.0, 3.7, 10.0, 100.0):
            w = wrap_angle(theta)
            assert -math.pi <= w <= math.pi

    def test_angle_delta_shortest(self) -> None:
        assert angle_delta(0.1, 0.2) == pytest.approx(0.1)
        # 0.1 -> 6.18 走负向
        assert angle_delta(0.1, 6.18) < 0

    def test_angle_lerp_takes_short_arc(self) -> None:
        # DoD: angle_lerp(0.1, 6.18, 0.5) 应走 -0.05 方向（最短弧）
        result = angle_lerp(0.1, 6.18, 0.5)
        # 中点应在 0.1 与 wrap_angle(6.18)≈-0.103 之间偏负侧
        assert result < 0.1
        # 严格落在最短弧中点附近：(0.1 + (-0.103))/2 ≈ -0.0017
        assert result == pytest.approx(-0.00159, abs=1e-3)

    def test_angle_lerp_endpoints(self) -> None:
        assert angle_lerp(0.5, 1.5, 0.0) == pytest.approx(0.5)
        assert angle_lerp(0.5, 1.5, 1.0) == pytest.approx(1.5)

    def test_rotate_toward_step_capped(self) -> None:
        # 目标在 +1.0 处，步长 0.2 → 一次只走 0.2
        out = rotate_toward(0.0, 1.0, 0.2)
        assert out == pytest.approx(0.2)

    def test_rotate_toward_negative_direction(self) -> None:
        # 目标在 0.1 处，从 6.18 出发应走正方向（最短弧）
        out = rotate_toward(0.1, 6.18, 0.05)
        # delta < 0，应该走 -0.05
        assert out == pytest.approx(0.05)

    def test_rotate_toward_snap_when_close(self) -> None:
        out = rotate_toward(0.0, 0.05, 0.2)
        assert out == pytest.approx(0.05)

    def test_rotate_toward_rejects_negative_step(self) -> None:
        with pytest.raises(ValueError):
            rotate_toward(0.0, 1.0, -0.1)

    def test_rotate_toward_never_overshoots(self) -> None:
        # 反复迭代必单调收敛到 target，且不超过 max_step
        cur = 0.0
        target = 1.234
        prev_err = abs(angle_delta(cur, target))
        for _ in range(1000):
            nxt = rotate_toward(cur, target, 0.05)
            assert abs(angle_delta(cur, nxt)) <= 0.05 + 1e-9
            cur = nxt
            err = abs(angle_delta(cur, target))
            assert err <= prev_err + 1e-12
            prev_err = err
        assert cur == pytest.approx(target)

    def test_angle_in_arc_boss_120_front_and_240_tail(self) -> None:
        # Boss 朝向 heading=0；正面 120° 即 half_width = pi/3
        heading = 0.0
        half = math.pi / 3
        # 正前方
        assert angle_in_arc(0.0, heading, half) is True
        # 正面边界 ±60°
        assert angle_in_arc(math.pi / 3, heading, half) is True
        assert angle_in_arc(-math.pi / 3, heading, half) is True
        # 略外侧（尾部 240°）
        assert angle_in_arc(math.pi / 3 + 0.01, heading, half) is False
        assert angle_in_arc(math.pi, heading, half) is False
        # 尾部 = not(in front arc)
        assert (not angle_in_arc(math.pi, heading, half)) is True

    def test_angle_in_arc_handles_wrap(self) -> None:
        # heading 在 -π 附近，目标在 +π 附近 — 应被认为是同方向
        assert angle_in_arc(math.pi - 0.05, -math.pi + 0.05, 0.2) is True


# ---------------------------------------------------------------------------
# AABB
# ---------------------------------------------------------------------------


class TestAABB:
    def test_contains_point(self) -> None:
        box = AABB(0.0, 0.0, 10.0, 5.0)
        assert box.contains_point((5.0, 2.0)) is True
        assert box.contains_point(Vec2(0.0, 0.0)) is True  # 边界
        assert box.contains_point((10.0, 5.0)) is True  # 对角边界
        assert box.contains_point((10.1, 2.0)) is False

    def test_overlap_basic(self) -> None:
        a = AABB(0.0, 0.0, 10.0, 10.0)
        b = AABB(5.0, 5.0, 10.0, 10.0)
        assert aabb_overlap(a, b) is True
        assert a.overlaps(b) is True

    def test_overlap_edge_touch_true(self) -> None:
        a = AABB(0.0, 0.0, 10.0, 10.0)
        b = AABB(10.0, 0.0, 5.0, 5.0)  # 左边贴 a 的右边
        assert aabb_overlap(a, b) is True

    def test_overlap_disjoint_false(self) -> None:
        a = AABB(0.0, 0.0, 10.0, 10.0)
        b = AABB(10.001, 0.0, 5.0, 5.0)
        assert aabb_overlap(a, b) is False

    def test_expanded(self) -> None:
        a = AABB(10.0, 20.0, 30.0, 40.0)
        b = a.expanded(1.0, 2.0)
        assert b == AABB(9.0, 18.0, 32.0, 44.0)
        c = a.expanded(5.0)  # dy 缺省同 dx
        assert c == AABB(5.0, 15.0, 40.0, 50.0)

    def test_negative_size_rejected(self) -> None:
        with pytest.raises(ValueError):
            AABB(0.0, 0.0, -1.0, 1.0)
        with pytest.raises(ValueError):
            AABB(0.0, 0.0, 1.0, -1.0)


# ---------------------------------------------------------------------------
# 统一接受 Vec2 与 tuple 的契约（DoD 最后一条）
# ---------------------------------------------------------------------------


class TestVec2LikeAcceptance:
    def test_all_position_apis_accept_both_forms(self) -> None:
        # tuple 形式
        assert circle_circle_overlap((0.0, 0.0), 1.0, (1.5, 0.0), 1.0) is True
        assert (
            circle_circle_penetration((0.0, 0.0), 1.0, (1.5, 0.0), 1.0)
            is not None
        )
        assert lerp_vec((0.0, 0.0), (2.0, 4.0), 0.5) == Vec2(1.0, 2.0)
        assert AABB(0.0, 0.0, 1.0, 1.0).contains_point((0.5, 0.5)) is True

        # Vec2 形式
        a = Vec2(0.0, 0.0)
        b = Vec2(1.5, 0.0)
        assert circle_circle_overlap(a, 1.0, b, 1.0) is True
        assert circle_circle_penetration(a, 1.0, b, 1.0) is not None
        assert lerp_vec(a, Vec2(2.0, 4.0), 0.5) == Vec2(1.0, 2.0)
        assert AABB(0.0, 0.0, 1.0, 1.0).contains_point(Vec2(0.5, 0.5)) is True
