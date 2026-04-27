"""几何工具集（toy-engine MVP / 06-geom.md）。

只下沉所有 2D 小游戏会重写的极小集合：``Vec2``、``AABB``、圆碰撞、
``clamp``/``lerp``/``smoothstep``、角度工具。

设计要点：
- 纯标准库 + ``math``，不引入 ``numpy``（EQ3 已否决）。
- 不 import ``pygame``：headless 跑分不应被几何工具拖入 pygame。
- ``Vec2`` 为 ``frozen=True, slots=True`` dataclass；公共函数的位置/方向
  入参统一为 ``Vec2Like = Vec2 | tuple[float, float]``，内部 ``_to_vec2``
  转成 ``Vec2``。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, hypot, pi, sin, tau
from typing import TypeAlias

__all__ = [
    "Vec2",
    "Vec2Like",
    "AABB",
    "circle_circle_overlap",
    "circle_circle_penetration",
    "clamp",
    "lerp",
    "lerp_vec",
    "smoothstep",
    "aabb_overlap",
    "wrap_angle",
    "angle_delta",
    "angle_lerp",
    "rotate_toward",
    "angle_in_arc",
]


# ---------------------------------------------------------------------------
# Vec2
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Vec2:
    """不可变 2D 向量（float, float）。

    ``frozen=True + slots=True``：哈希友好、内存紧凑，避免业务无意修改导致 bug。
    实现与测试中应避免让 ``NaN`` 进入 ``Vec2``。
    """

    x: float
    y: float

    # ---- 算术 ----
    def __add__(self, o: "Vec2") -> "Vec2":
        if not isinstance(o, Vec2):
            return NotImplemented
        return Vec2(self.x + o.x, self.y + o.y)

    def __sub__(self, o: "Vec2") -> "Vec2":
        if not isinstance(o, Vec2):
            return NotImplemented
        return Vec2(self.x - o.x, self.y - o.y)

    def __mul__(self, k: float) -> "Vec2":
        if not isinstance(k, (int, float)):
            return NotImplemented
        return Vec2(self.x * k, self.y * k)

    def __rmul__(self, k: float) -> "Vec2":
        return self.__mul__(k)

    def __truediv__(self, k: float) -> "Vec2":
        if not isinstance(k, (int, float)):
            return NotImplemented
        return Vec2(self.x / k, self.y / k)

    def __neg__(self) -> "Vec2":
        return Vec2(-self.x, -self.y)

    # ---- 度量 ----
    def length(self) -> float:
        return hypot(self.x, self.y)

    def length_sq(self) -> float:
        return self.x * self.x + self.y * self.y

    def normalized(self, eps: float = 1e-9) -> "Vec2":
        """返回单位向量；零向量（长度 <= eps）返回 ``(0, 0)``。"""
        n = hypot(self.x, self.y)
        if n <= eps:
            return Vec2(0.0, 0.0)
        return Vec2(self.x / n, self.y / n)

    def dot(self, o: "Vec2") -> float:
        return self.x * o.x + self.y * o.y

    def cross(self, o: "Vec2") -> float:
        """2D 标量叉积 ``x1*y2 - y1*x2``。"""
        return self.x * o.y - self.y * o.x

    def angle(self) -> float:
        """``atan2(y, x)``，范围 ``(-π, π]``。"""
        return atan2(self.y, self.x)

    def rotated(self, theta: float) -> "Vec2":
        c, s = cos(theta), sin(theta)
        return Vec2(self.x * c - self.y * s, self.x * s + self.y * c)

    def with_length(self, k: float) -> "Vec2":
        """返回长度为 ``k`` 的同方向向量；零向量返回 ``(0, 0)``。"""
        n = hypot(self.x, self.y)
        if n <= 1e-9:
            return Vec2(0.0, 0.0)
        s = k / n
        return Vec2(self.x * s, self.y * s)

    # ---- 转换 ----
    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)

    @classmethod
    def from_angle(cls, theta: float, length: float = 1.0) -> "Vec2":
        return cls(cos(theta) * length, sin(theta) * length)

    @classmethod
    def zero(cls) -> "Vec2":
        return cls(0.0, 0.0)


Vec2Like: TypeAlias = Vec2 | tuple[float, float]


def _to_vec2(v: Vec2Like) -> Vec2:
    """把 ``Vec2`` 或二元 ``tuple`` 统一转成 ``Vec2``。"""
    if isinstance(v, Vec2):
        return v
    # 允许任意二元序列，但严格走 (x, y) 解包，避免静默接受异常输入。
    x, y = v  # type: ignore[misc]
    return Vec2(float(x), float(y))


# ---------------------------------------------------------------------------
# 圆碰撞
# ---------------------------------------------------------------------------


def circle_circle_overlap(
    a: Vec2Like,
    ra: float,
    b: Vec2Like,
    rb: float,
    eps: float = 1e-9,
) -> bool:
    """是否相交（含相切）。

    等价于 ``(a-b).length_sq() <= (ra+rb+eps)**2``。
    """
    if ra < 0 or rb < 0:
        raise ValueError("circle radii must be non-negative")
    av = _to_vec2(a)
    bv = _to_vec2(b)
    dx = av.x - bv.x
    dy = av.y - bv.y
    r = ra + rb + eps
    return dx * dx + dy * dy <= r * r


def circle_circle_penetration(
    a: Vec2Like,
    ra: float,
    b: Vec2Like,
    rb: float,
    eps: float = 1e-9,
) -> tuple[Vec2, float] | None:
    """返回 ``(push_dir_from_b_to_a, penetration_depth)`` 或 ``None``。

    ``push_dir`` 已归一化；同心时返回 ``((1, 0), ra+rb)`` 兜底，避免 NaN。
    """
    if ra < 0 or rb < 0:
        raise ValueError("circle radii must be non-negative")
    av = _to_vec2(a)
    bv = _to_vec2(b)
    dx = av.x - bv.x
    dy = av.y - bv.y
    rsum = ra + rb
    dist_sq = dx * dx + dy * dy
    # 与 overlap 一致：用 (rsum+eps)^2 作为相交边界。
    if dist_sq > (rsum + eps) * (rsum + eps):
        return None
    dist = hypot(dx, dy)
    if dist == 0.0:
        # 同心：方向无定义，给一个稳定兜底。
        return Vec2(1.0, 0.0), rsum
    inv = 1.0 / dist
    return Vec2(dx * inv, dy * inv), rsum - dist


# ---------------------------------------------------------------------------
# 标量工具
# ---------------------------------------------------------------------------


def clamp(x: float, lo: float, hi: float) -> float:
    if lo > hi:
        raise ValueError("clamp requires lo <= hi")
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_vec(a: Vec2Like, b: Vec2Like, t: float) -> Vec2:
    av = _to_vec2(a)
    bv = _to_vec2(b)
    return Vec2(av.x + (bv.x - av.x) * t, av.y + (bv.y - av.y) * t)


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Hermite 平滑插值；``edge0 == edge1`` 时按阶跃处理避免除零。"""
    if edge0 == edge1:
        return 0.0 if x < edge0 else 1.0
    t = (x - edge0) / (edge1 - edge0)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------
# 角度工具
# ---------------------------------------------------------------------------


def wrap_angle(theta: float) -> float:
    """把角度规范到 ``[-π, π]``。

    约定：``wrap_angle(3π) == π``、``wrap_angle(-3π) == -π``（边界稳定）。
    """
    # 先处理边界对齐到 +π 的情形：theta 是 π 的奇数倍时，按符号决定 ±π。
    # 通用公式 ((theta + π) % (2π)) - π 会把 -π 变成 -π、+π 变成 -π，
    # 故对正侧的 +π 单独保留。
    t = (theta + pi) % tau - pi
    if t == -pi and theta > 0:
        return pi
    return t


def angle_delta(a: float, b: float) -> float:
    """从 ``a`` 转到 ``b`` 的最短有符号弧。"""
    return wrap_angle(b - a)


def angle_lerp(a: float, b: float, t: float) -> float:
    """角度插值，沿最短弧。"""
    return wrap_angle(a + angle_delta(a, b) * t)


def rotate_toward(current: float, target: float, max_step: float) -> float:
    """按最大角速度步进转向；``abs(delta) <= max_step`` 时直接吸附到 target。"""
    if max_step < 0:
        raise ValueError("max_step must be non-negative")
    delta = angle_delta(current, target)
    if abs(delta) <= max_step:
        return wrap_angle(target)
    step = max_step if delta >= 0 else -max_step
    return wrap_angle(current + step)


def angle_in_arc(
    angle: float,
    center: float,
    half_width: float,
    eps: float = 1e-9,
) -> bool:
    """``angle`` 是否落在以 ``center`` 为中心、半宽 ``half_width`` 的弧内。"""
    if half_width < 0:
        raise ValueError("half_width must be non-negative")
    return abs(angle_delta(center, angle)) <= half_width + eps


# ---------------------------------------------------------------------------
# AABB
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AABB:
    """轴对齐矩形：``x/y`` 为左上角，``w/h`` 非负，边界接触视为 overlap。"""

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        if self.w < 0 or self.h < 0:
            raise ValueError("AABB w/h must be non-negative")

    def contains_point(self, p: Vec2Like) -> bool:
        pv = _to_vec2(p)
        return (
            self.x <= pv.x <= self.x + self.w
            and self.y <= pv.y <= self.y + self.h
        )

    def overlaps(self, o: "AABB") -> bool:
        return aabb_overlap(self, o)

    def expanded(self, dx: float, dy: float | None = None) -> "AABB":
        """向四周外扩 ``dx`` / ``dy``（``dy`` 缺省同 ``dx``）。允许负值收缩。"""
        if dy is None:
            dy = dx
        nw = self.w + 2.0 * dx
        nh = self.h + 2.0 * dy
        if nw < 0 or nh < 0:
            raise ValueError("expanded AABB w/h must remain non-negative")
        return AABB(self.x - dx, self.y - dy, nw, nh)


def aabb_overlap(a: AABB, b: AABB) -> bool:
    """轴对齐矩形相交（边界接触视为相交）。"""
    return (
        a.x <= b.x + b.w
        and b.x <= a.x + a.w
        and a.y <= b.y + b.h
        and b.y <= a.y + a.h
    )
