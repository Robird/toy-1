# 06 — geom（几何工具）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[fish-doc 01 §3](../../fish-doc/mvp/01-core-loop.md)（圆碰撞用于吃/被吃判定）

## 1. 范围

只下沉**所有 2D 小游戏都会重写一遍**的极小集合。**不**做矩阵、四元数、旋转矩阵堆叠、SAT、GJK。

| API | 用途 |
|---|---|
| `Vec2` | 2D 向量运算 |
| `Vec2Like` | `Vec2 \| tuple[float, float]` 输入兼容别名 |
| `AABB` | 轴对齐矩形值对象 |
| `circle_circle_overlap(a, ra, b, rb, eps=1e-9) -> bool` | 圆-圆相交判定，只返回布尔值 |
| `circle_circle_penetration(a, ra, b, rb, eps=1e-9) -> tuple[Vec2, float] \| None` | 圆-圆穿插信息；与布尔判定分离，避免热路径多余分配 |
| `clamp(x, lo, hi) -> float` | 数值钳制 |
| `lerp(a, b, t) -> float` | 标量线性插值 |
| `lerp_vec(a, b, t) -> Vec2` | 向量线性插值 |
| `smoothstep(edge0, edge1, x) -> float` | 平滑阶跃插值 |
| `aabb_overlap(a, b) -> bool` | 轴对齐矩形相交（粒子裁剪用） |
| `wrap_angle(theta) -> float` | 把角度规范到 `[-π, π]` 边界约定 |
| `angle_delta(a, b) -> float` | 从角 `a` 转到角 `b` 的最短有符号差值 |
| `angle_lerp(a, b, t) -> float` | 角度插值（最短弧） |
| `rotate_toward(current, target, max_step) -> float` | 按最大角速度步进转向 |
| `angle_in_arc(angle, center, half_width, eps=1e-9) -> bool` | 扇形/尾部判定 |

## 2. `Vec2` 数据类

```python
from dataclasses import dataclass
from math import hypot, atan2, cos, sin
from typing import TypeAlias

@dataclass(frozen=True, slots=True)
class Vec2:
    x: float
    y: float

    # 算术
    def __add__(self, o: "Vec2") -> "Vec2": ...
    def __sub__(self, o: "Vec2") -> "Vec2": ...
    def __mul__(self, k: float) -> "Vec2": ...
    def __rmul__(self, k: float) -> "Vec2": ...
    def __truediv__(self, k: float) -> "Vec2": ...
    def __neg__(self) -> "Vec2": ...

    # 度量
    def length(self) -> float: ...
    def length_sq(self) -> float: ...           # 优先用 sq 比较，省 sqrt
    def normalized(self, eps: float = 1e-9) -> "Vec2": ...   # 零向量返回 (0,0)
    def dot(self, o: "Vec2") -> float: ...
    def cross(self, o: "Vec2") -> float: ...    # 标量
    def angle(self) -> float: ...               # atan2(y, x)
    def rotated(self, theta: float) -> "Vec2": ...
    def with_length(self, k: float) -> "Vec2": ...        # 零向量返回 (0,0)

    # 转换
    def as_tuple(self) -> tuple[float, float]: ...
    @classmethod
    def from_angle(cls, theta: float, length: float = 1.0) -> "Vec2": ...
    @classmethod
    def zero(cls) -> "Vec2": ...

Vec2Like: TypeAlias = Vec2 | tuple[float, float]

def _to_vec2(v: Vec2Like) -> Vec2: ...
```

> `frozen=True + slots=True`：哈希友好、内存紧凑、避免被业务意外修改导致 bug；新建开销对百级实体可接受。`dataclass(frozen=True)` 的 `__eq__` / `__hash__` 按浮点字段生成；实现与测试中应避免让 `NaN` 进入 `Vec2`，也不要把含非有限值的 `Vec2` 长期作为 dict key。

### 2.1 与 `tuple[float, float]` 的边界

- `InputFrame.desired_dir` 的 canonical 类型为 `Vec2 | None`（[03-input.md §2](03-input.md)），构造时接受 `Vec2Like`（含 tuple），Recorder JSON wire format 仍为 `[x, y]` 数组
- `geom` 的所有位置/方向入参统一标注为 `Vec2Like`，同时接受 `Vec2` 和二元 `tuple` 输入（内部 `_to_vec2` 转成 float）
- `Vec2` 自身的算术方法只接受 `Vec2`，避免 `tuple` 隐式参与运算导致类型错误位置不清晰

### 2.2 与 `pygame.Vector2` 的关系

- `geom` 不 import、不继承 `pygame.Vector2`：headless 跑分不应因为几何工具触发 pygame 依赖
- 渲染/输入边界需要 pygame 类型时再显式转换：`pygame.Vector2(*v.as_tuple())`
- 如果后续 profiling 证明纯 Python 向量分配成为瓶颈，可在 fish 热点循环局部改用 `x/y` float 或 `pygame.Vector2`；`geom` 公共 API 保持 `Vec2Like`，MVP 不提前换实现

## 3. 圆碰撞 API

```python
def circle_circle_overlap(
    a: Vec2Like, ra: float,
    b: Vec2Like, rb: float,
    eps: float = 1e-9,
) -> bool:
    """是否相交（含相切）。等价于 (a-b).length_sq() <= (ra+rb+eps)**2。"""

def circle_circle_penetration(
    a: Vec2Like, ra: float,
    b: Vec2Like, rb: float,
    eps: float = 1e-9,
) -> tuple[Vec2, float] | None:
    """
    返回 (push_dir_from_b_to_a, penetration_depth) 或 None（不相交）。
    push_dir 已归一化；同心时返回 ((1,0), ra+rb) 兜底，避免 NaN。
    业务用法：a.pos += push_dir * (depth/2)，b.pos -= push_dir * (depth/2)
    """
```

> fish 的"同 Tier 互相弹开"（[fish-doc 01 §3](../../fish-doc/mvp/01-core-loop.md)）直接用此函数。
> 半径必须非负；实现中发现 `ra < 0` 或 `rb < 0` 应抛 `ValueError`，不要静默取绝对值。

## 4. 标量工具

```python
def clamp(x: float, lo: float, hi: float) -> float: ...
def lerp(a: float, b: float, t: float) -> float: ...
def lerp_vec(a: Vec2Like, b: Vec2Like, t: float) -> Vec2: ...
def smoothstep(edge0: float, edge1: float, x: float) -> float: ...
def wrap_angle(theta: float) -> float: ...
def angle_delta(a: float, b: float) -> float: ...       # wrap_angle(b - a)
def angle_lerp(a: float, b: float, t: float) -> float: ...   # 走最短弧
def rotate_toward(current: float, target: float, max_step: float) -> float: ...
def angle_in_arc(angle: float, center: float, half_width: float, eps: float = 1e-9) -> bool: ...
```

- `wrap_angle` 使用 Python `%`，不要用 `math.fmod`；负数边界必须稳定。约定：`wrap_angle(3π) == π`，`wrap_angle(-3π) == -π`
- `angle_lerp(a, b, t)` 等价于 `wrap_angle(a + angle_delta(a, b) * t)`，其中 `angle_delta(a, b)` 是最短有符号弧
- `rotate_toward(current, target, max_step)` 要求 `max_step >= 0`；若 `abs(delta) <= max_step` 直接返回 `wrap_angle(target)`，否则沿 `delta` 符号步进
- Boss 正面 120° 判定可写成：`angle_in_arc(angle_to_player, boss_heading, pi/3)`；尾部 240° 判定写成其取反，避免边界同时属于正面与尾部
- `smoothstep` 内部先把 `x` 规范到 `[0, 1]`；`edge0 == edge1` 时按阶跃处理，避免除零

## 5. AABB

```python
@dataclass(frozen=True, slots=True)
class AABB:
    x: float; y: float; w: float; h: float
    def contains_point(self, p: Vec2Like) -> bool: ...
    def overlaps(self, o: "AABB") -> bool: ...
    def expanded(self, dx: float, dy: float | None = None) -> "AABB": ...

def aabb_overlap(a: AABB, b: AABB) -> bool: ...
```

> 坐标约定：`x/y` 为左上角，`w/h` 非负；边界接触视为 overlap。用途：粒子是否在屏幕内（裁剪），鱼群是否进入"屏外保留区"等。fish 暂用不到广相碰撞，故无 quadtree。

## 6. **不**做

- 不做 3D 向量
- 不做矩阵/变换栈（pygame 自身的 `pygame.transform` 已够）
- 不做物理积分（业务自己写 `pos += vel * dt`，几行代码不值得抽）
- 不做连续碰撞/扫掠体积（MVP 固定步长 + 圆重叠足够；若后续出现高速穿透再补新 API）
- 不做绳索/弹簧/约束求解

## DoD 验收清单

- [ ] `Vec2` 在 `pytest -k vec2` 下覆盖加减乘除、归一化（含零向量边界）、旋转、角度往返
- [ ] `circle_circle_overlap` 在 `(a-b).length == ra+rb` 边界返回 `True`（含相切）
- [ ] `circle_circle_penetration` 同心情况不抛 NaN
- [ ] `wrap_angle(3π) == π`、`wrap_angle(-3π) == -π`，`angle_lerp(0.1, 6.18, 0.5)` 走的是 -0.05 方向（最短弧）
- [ ] `rotate_toward(current, target, max_step)` 不超过 `max_step`，且接近目标时直接吸附到 `target`
- [ ] `angle_in_arc(angle_to_player, boss_heading, pi/3)` 能覆盖 Boss 正面 120° 判定，取反后覆盖尾部 240° 判定
- [ ] 所有公开函数的位置/方向入参同时接受 `Vec2` 与 `tuple` 输入（fish 集成时无适配代码）

## 未决问题

- 是否要 SIMD/numpy 加速？MVP **不做**——百级实体性能完全够。
- 是否提供 `Vec2.lerp_to(other, t)` 方法形式？倾向 **不做**，统一走顶层 `lerp_vec` 减少 API 表面。
- 是否提供 `swept_circle_circle` / 连续碰撞？MVP **不做**；若 Boss 冲刺或后续"子弹时间"调参导致 tunneling，再以独立 API 增补，不能把扫掠语义塞进 `circle_circle_overlap`。
