# 07 — GeoCanvas（渲染封装）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[fish-doc 05](../../fish-doc/mvp/05-visuals.md)、[01-rng.md §4](01-rng.md)

## 1. 定位

> **`GeoCanvas` 是 pygame `Surface` 的高阶绘制包装。** 它下沉的是"几何绘图原语 + 通用视觉效果（粒子/屏震/调色板/渐变）"，**不**下沉"画一条鱼"这种业务函数。

**画一条鱼**留在 `fish/render/visuals.py`（[fish-doc 05 §3](../../fish-doc/mvp/05-visuals.md)），它**调用** `GeoCanvas` 的椭圆/三角/弧线原语来组装。

边界判别原则（subagent 写代码时遇到犹豫就回看）：

| 想下沉的能力 | 该不该下沉到 GeoCanvas？ |
|---|---|
| 渐变填充椭圆 | ✅ 任何下一个游戏都用得上 |
| 屏幕震动 | ✅ 通用 |
| 粒子系统 | ✅ 通用 |
| 调色板加载/查色/混色 | ✅ 通用，但**不**含 fish 的具体颜色常量 |
| 贝塞尔曲线 | ✅ 通用 |
| 三层视差背景 | ❌ 业务（具体 caustics/海草是鱼游戏的） |
| 画一条鱼 | ❌ 业务 |
| 画 Boss 双眼 | ❌ 业务 |
| Boss 状态对应颜色 | ❌ 业务 |

## 2. 构造与窗口管理

```python
class GeoCanvas:
    def __init__(self, surface: "pygame.Surface", *, palette: "Palette | None" = None,
                 rng: "SeededRng | None" = None) -> None: ...

    @classmethod
    def create_window(cls, w: int, h: int, *, title: str = "",
                      vsync: bool = True, palette: "Palette | None" = None) -> "GeoCanvas":
        """便捷工厂：内部 pygame.init + display.set_mode；headless 时不要调用此方法。"""

    @classmethod
    def offscreen(cls, w: int, h: int) -> "GeoCanvas":
        """离屏 surface，pygame 不需要 display；用于测试或截图。"""

    # 帧生命周期
    def clear(self, color: tuple[int,int,int] | None = None) -> None: ...
    def present(self) -> None: ...        # GUI: pygame.display.flip(); offscreen: no-op

    @property
    def size(self) -> tuple[int, int]: ...
    @property
    def surface(self) -> "pygame.Surface": ...   # 逃生舱：业务直接拿 raw surface
```

> **业务永远可以拿到底层 `surface`**——引擎不假装能预见所有需求。`GeoCanvas` 是"提速"，不是"管制"。

DPI / 高分屏约定：`GeoCanvas.size` 始终返回**逻辑像素**尺寸；`create_window` 不得在业务无感知的情况下把坐标乘以设备像素比。若后续使用 `pygame.SCALED` / 平台高 DPI flag，输入坐标换算必须在 `KeyboardMouseInput` 或窗口边界完成，`GeoCanvas` 的绘制 API 仍只接受逻辑坐标。

## 3. 绘图原语

### 3.1 基础

```python
def line(self, p0, p1, color, width: int = 1, alpha: int = 255): ...
def circle(self, center, r, color, width: int = 0, alpha: int = 255): ...     # width=0 = 填充
def ellipse(self, center, length, height, angle: float, color,
        stroke_width: int = 0, alpha: int = 255): ...                    # 旋转椭圆
def rect(self, aabb, color, width: int = 0, alpha: int = 255): ...
def polygon(self, points, color, width: int = 0, alpha: int = 255): ...
def rotated_polygon(self, center, local_points, angle: float, color,
                    width: int = 0, alpha: int = 255): ...
def arc(self, center, length, height, angle: float,
        start_angle: float, end_angle: float, color,
    stroke_width: int = 1, alpha: int = 255): ...
def blit(self, source: "pygame.Surface", dest, *, alpha: int = 255,
         special_flags: int = 0, apply_shake: bool = True): ...
```

- 所有点参数接受 `Vec2` 或 `(x, y)`；内部只在绘制边界做 tuple 转换。
- `polygon` / `triangle` 接收**世界坐标**；鱼尾、鳍等本地三角形优先用 `rotated_polygon(center, local_points, angle, ...)`。
- 填充 + 描边的约定是先用 `width=0` / `stroke_width=0` 画填充，再用正描边宽度画描边；不额外引入 `draw_fish` 级别的业务 helper。
- `blit` 只负责绘制已生成的 `Surface`（如缓存渐变、caustics 贴图、文本缓存），不负责位图资源加载。

### 3.2 渐变椭圆（fish 鱼身/Boss 主体用）

```python
def gradient_ellipse(
    self,
    center, length, width,                 # 几何
    angle: float,                          # 旋转
    color_a, color_b,
    *,
    mode: "Literal['linear', 'radial']" = "linear",
    alpha: int = 255,
    steps: int = 16,                       # 渐变分段数
) -> None: ...
```

- `mode="linear"`：`color_a -> color_b` 沿椭圆本地短轴渐变，用于鱼身纵向受光。
- `mode="radial"`：`color_a` 为中心色，`color_b` 为边缘色，用于背景径向渐变、Boss 外发光等。

pygame 没有原生渐变椭圆 API。实现要求：先在未旋转的临时 `SRCALPHA` surface 上生成椭圆 alpha mask；线性渐变用按行/条带填色后套 mask，径向渐变用由外向内的同心椭圆或距离场近似；最后 `pygame.transform.rotate` 后 `blit` 到目标 surface。临时 surface 必须走 LRU 缓存（key 至少含 `mode/length/width/color_a/color_b/alpha/steps`；角度可按 2°~5° bucket 另建旋转缓存），避免每帧重算。

### 3.3 三角形与扇形

```python
def triangle(self, p0, p1, p2, color, width: int = 0, alpha: int = 255): ...
def fan(self, center, r, angle_start, angle_end, color, alpha: int = 255): ...
```

`triangle` 是已经变换后的三点快捷入口；需要随鱼身旋转的尾巴/鳍不要在业务里手写三角函数，使用 §3.1 的 `rotated_polygon`。

### 3.4 贝塞尔曲线与闭合轮廓

```python
def sample_bezier_quad(self, p0, p1, p2, samples: int = 16) -> list["Vec2"]: ...
def sample_bezier_cubic(self, p0, p1, p2, p3, samples: int = 24) -> list["Vec2"]: ...
def bezier_quad(self, p0, p1, p2, color, width: int = 1,
                samples: int = 16, alpha: int = 255): ...
def bezier_cubic(self, p0, p1, p2, p3, color, width: int = 1,
                 samples: int = 24, alpha: int = 255): ...
def bezier_path(self, segments, *, closed: bool = False,
                fill_color = None, stroke_color = None,
                stroke_width: int = 1, samples_per_segment: int = 16,
                alpha: int = 255): ...
```

`segments` 是若干二次段 `(p0, p1, p2)` 或三次段 `(p0, p1, p2, p3)`。实现上全部采样为折线：海草用 `stroke_color` 画线；Boss 的 3~4 段贝塞尔轮廓（[fish-doc 05 §4](../../fish-doc/mvp/05-visuals.md)）用 `closed=True + fill_color + stroke_color` 采样成 polygon 后填充/描边。MVP 不做真正矢量路径布尔运算。

### 3.5 文本（薄包装）

```python
def text(self, s: str, pos, color, font: "pygame.font.Font", *,
         anchor: str = "topleft", alpha: int = 255): ...
```

`anchor` 取 `pygame.Rect` 的属性名（`"topleft" / "center" / ...`）。字体由业务从 `toy_engine.font.load_font` 取得后传入；引擎不内置字体常量。

## 4. 通用视觉效果

### 4.1 屏震（Screen Shake）

```python
class ScreenShake:
    def __init__(self, max_magnitude_px: float = 20.0) -> None: ...
    def shake(self, magnitude_px: float, duration_s: float) -> None: ...
    def update(self, dt: float) -> None: ...
    def offset(self) -> tuple[float, float]: ...    # 当前帧应用到所有渲染的偏移

# GeoCanvas 集成
canvas.shake.shake(6, 0.4)          # fish 反杀 Boss
canvas.shake.update(dt)             # 业务每帧调用
# canvas.clear / 绘图自动叠加 offset
```

- 振幅按时间衰减（`linear` 或 `exp`，可选）
- 多次 `shake(...)` 采用有上限的能量叠加：`magnitude = min(max_magnitude_px, hypot(current, new))`，`remaining_duration = max(current_remaining, new_duration)`；避免 Boss 连续事件把画面抖到不可读
- **UI 层不应受屏震影响**：`canvas.with_no_shake() -> ContextManager` 返回一个 with 块，块内绘制忽略震动
- 震动伪随机走 `rng.spawn("screen_shake")`，保证可复现

### 4.2 粒子系统

```python
@dataclass
class ParticleSpec:
    pos: Vec2
    vel: Vec2
    color: tuple[int, int, int]
    radius: float
    life_s: float
    gravity: Vec2 = Vec2(0, 0)
    drag: float = 0.0
    color_end: tuple[int, int, int] | None = None
    radius_end: float | None = None
    fade: bool = True       # alpha 随剩余寿命线性衰减

@dataclass
class ParticleEmitter:
    center: Vec2
    rate_per_s: float
    angle_range: tuple[float, float]       # radians
    speed_range: tuple[float, float]
    color: tuple[int, int, int]
    radius_range: tuple[float, float]
    life_range: tuple[float, float]
    color_end: tuple[int, int, int] | None = None
    gravity: Vec2 = Vec2(0, 0)
    duration_s: float | None = None
    carry: float = 0.0                     # 小数发射量累积，避免低 rate 抖动

class ParticleSystem:
    def __init__(self, capacity: int = 512): ...
    def emit(self, spec: ParticleSpec) -> None: ...
    def emit_burst(self, n: int, *, center: Vec2, speed_range: tuple[float, float],
                   color: tuple, radius_range: tuple[float, float],
                   life_range: tuple[float, float], rng: "SeededRng") -> None: ...
    def emit_from(self, emitter: ParticleEmitter, dt: float, rng: "SeededRng") -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, canvas: "GeoCanvas") -> None: ...
```

> "吃鱼三件套"中的"粒子四散"（[fish-doc 05 §6](../../fish-doc/mvp/05-visuals.md)）一行 `particles.emit_burst(...)` 即可。fish 的"气泡尾迹"也用同一个 ParticleSystem，只是参数不同。

容量上限 + 环形缓冲：到达 `capacity` 时覆盖最老的，避免 GC 抖动。

- `color_end` / `radius_end` 为可选终值；绘制时按 `age / life_s` 插值，`fade=True` 再额外乘 alpha 衰减。
- `ParticleSystem` 是纯渲染/表现层对象：不 import、不持有 `World`；fish 可以把它放在 renderer 或临时 visual-state 中，headless 跑分可完全不创建。
- 所有随机发射必须显式接收 `SeededRng`，禁止内部调用 `random.*`。

### 4.3 调色板

```python
class Palette:
    def __init__(self, named: dict[str, tuple[int,int,int]]): ...

    @classmethod
    def from_json(cls, path: str) -> "Palette": ...

    def __getitem__(self, name: str) -> tuple[int,int,int]: ...
    def lighten(self, name: str, k: float) -> tuple[int,int,int]: ...   # 朝白色 lerp
    def darken(self, name: str, k: float) -> tuple[int,int,int]: ...    # 朝黑色 lerp
    def jitter_hue(self, color, deg: float, rng: "SeededRng") -> tuple[int,int,int]: ...
```

- **不内置任何颜色常量**——`PALETTE_DEEP` 等是 fish 的（[fish-doc 05 §2](../../fish-doc/mvp/05-visuals.md)）
- fish 在 `fish/render/palette.py` 里 `palette = Palette({...})` 一次构造、全局复用
- `jitter_hue` 必须接受外部 `SeededRng`（**禁止**内部用 `random.*`，否则破坏确定性）

### 4.4 背景视差 / caustics 边界

引擎**不**提供 `ParallaxBackground`、`SeaweedLayer`、`CausticsLayer` 这类业务组件。fish 的三层视差由 `fish/render/background.py` 自己组合：

- Far：可用 `gradient_ellipse(..., mode="radial")` 或预渲染 surface 做深海径向背景
- caustics：Perlin/noise 生成、蓝化叠加、UV 偏移都在 fish 侧；引擎只提供 `blit(..., alpha=60, special_flags=...)` 和 offscreen surface
- Mid：海草用 `bezier_path(stroke_color=..., alpha=140)`，摆动控制点由 fish 计算
- Near：气泡用 `ParticleSystem` 或 fish 自己维护的粒子参数

原因：三层内容、颜色、移动速度都直接来自 fish 视觉规范；下沉会把 fish 风格硬编码进引擎。

### 4.5 时间缩放 / 慢动作协作

渲染层不读取真实时间，也不拥有全局 `time_scale`。所有动画推进只通过调用方传入的 `dt`：`ScreenShake.update(dt)`、`ParticleSystem.update(dt)`、尾迹/背景摆动也由 fish 传入时间。

fish 触发死亡慢动作时，应在业务层计算 `scaled_dt = base_dt * time_scale`，并把同一个 `scaled_dt` 用于逻辑步进与世界内视觉状态推进；GameLoop 的固定步长、录像帧号、metrics 采样仍保持基准 `base_dt`。UI 淡入淡出若需要不受慢动作影响，显式使用未缩放 dt，并通过 `with_no_shake()` 保持在屏震图层之上。

## 5. headless 兼容

- `GeoCanvas.offscreen(w, h)` 创建离屏 canvas，**不需要** `pygame.display`
- `tools/run_headless.py` 默认完全不 import `toy_engine.render`
- 业务代码路径上必须有"GUI / headless"开关，避免 headless 误调 `present()`

## 6. 性能预算

按 [fish-doc 05 DoD](../../fish-doc/mvp/05-visuals.md)：60 FPS、100 鱼 + Boss + 30 气泡，CPU < 30%。

引擎层关键优化点：

- 渐变/旋转椭圆用 LRU 缓存避免每帧重算；缓存 surface 在 display 初始化后尽量 `convert_alpha()`
- 预渲染静态或低频变化 surface：背景径向渐变、caustics 噪声贴图、Boss 固定轮廓 mask、常用 UI 文本
- 避免在每个原语调用里新建 `pygame.SRCALPHA` 大 surface；确需 alpha 合成时优先复用小临时 surface 或缓存结果
- 粒子 update 内联 `for p in particles: p.x += p.vx*dt` 风格，**不**用对象方法调用
- 文本渲染缓存（`(s, font_id, color)` → `Surface`），LRU 128
- Dirty rect：MVP 默认整帧 `flip()`，因为视差背景、粒子、屏震通常会让大面积失效；仅在 `--no-bg` / UI-only 调试模式可实验 `pygame.display.update(rects)`
- 渐变填充禁止逐像素 Python 循环跑在每帧热路径；按行画线、同心椭圆或 numpy 都必须发生在预生成/缓存阶段
- 高 DPI / 缩放窗口下以逻辑分辨率 profile；不要把物理像素翻倍后的 fill-rate 误算成游戏复杂度问题

## DoD 验收清单

- [ ] `GeoCanvas.offscreen` 在无 display 的 CI 环境可创建并调用所有原语不报错
- [ ] `gradient_ellipse(length=80, width=40, mode="linear"/"radial")` 缓存命中时单次 < 0.05ms
- [ ] `rotated_polygon`、`arc`、`bezier_path(closed=True, fill_color=...)` 可覆盖鱼尾/鳍、高光弧线、Boss 填充轮廓
- [ ] `ParticleSystem(512)` 在满载时 60 FPS 单帧 < 2ms
- [ ] `ParticleEmitter` 连续发射、`color_end` 渐变、`gravity` 与 `life_s` 在固定 RNG 下可复现
- [ ] `ScreenShake.shake` 多次叠加有上限，且在 `with canvas.with_no_shake():` 块内偏移为 0
- [ ] `Palette.jitter_hue` 在固定 RNG 下输出可复现
- [ ] **零内置颜色常量**——`grep -E "= \(\d+, \d+, \d+\)" toy_engine/render/` 仅命中默认参数（如 `clear` 的 black）

## 未决问题

- 是否提供"后处理"layer（vignette/bloom）？MVP **不做**，反馈靠粒子+屏震+慢动作即可。
- 文本布局是否要支持自动换行？MVP **不做**，业务自己 split。
