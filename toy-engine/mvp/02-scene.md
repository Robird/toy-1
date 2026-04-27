# 02 — Scene / System / GameLoop（Q6 决议）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[fish-doc 01](../../fish-doc/mvp/01-core-loop.md)、[fish-doc progress Q6](../../fish-doc/mvp/progress.md)、[03-input.md](03-input.md)、[04-recorder.md](04-recorder.md)、[05-metrics.md](05-metrics.md)、[07-render.md](07-render.md)、[08-tools.md](08-tools.md)

## 1. Q6 决议：**不做** ECS / Scene / System，改做极简 `GameLoop`

### 1.1 结论

> 引擎**不**提供 `Scene` / `System` / `Entity` 风格的抽象基类。fish 自行持有 `World`、自己组织子系统模块即可。引擎只下沉一个**可选**的 `GameLoop` helper，封装"固定步长 + 累加器 + 输入/逻辑/渲染解耦 + headless 切换"这一段所有 pygame 游戏都会重写一遍的样板代码。

### 1.2 论证

**反对完整 Scene/System 抽象的理由（按重要性排序）**：

1. **MVP 只服务一个游戏（fish）**。在 N=1 的样本上做抽象，几乎必然 over-fit 这一个游戏的形状，等下一个游戏（如打砖块）出现时仍要重写。**YAGNI**。
2. fish 的 `World` 已经是一个自然聚合（玩家+鱼群+Boss+粒子+计时器都在一处）。强行把它拆成 `MovementSystem` / `CollisionSystem` / `SpawnerSystem` 会让"为什么这条鱼没被吃"这种调试问题需要跨 4 个文件追踪，**调试链路被拉长**而不是缩短。
3. fish-doc 已经规定 `World.step(dt, input_frame)` 是**纯函数**（[fish-doc 07 §2](../../fish-doc/mvp/07-test-harness.md)）。这个契约本身就是最简的"系统"抽象——再额外套一层 Scene/System 是冗余。
4. ECS 的真正收益（数据局部性、可并行、批量更新）在百级别实体的小游戏上**根本不显著**，反而带来调度复杂度。
5. 抽象一旦下沉，文档/测试/迁移成本都跟着下沉——**抽象有税**。

**那么 fish 没有任何好处吗？** 有，但都能由"约定 + 几行 helper"达成，不需要继承体系：

- "固定步长循环"由 `GameLoop` 提供（见 §2）
- "渲染只读 World 快照"由 fish 自己写一行 `state = world.snapshot()` 实现，不需要基类强制
- "可插拔的 InputSource" 已由 [03-input.md](03-input.md) 解决，与 Scene 无关

### 1.3 反例：什么情况下我会改主意

推翻本决议需要**真实反例**，而不是"看起来更像引擎"：

1. 至少两个已落地游戏都出现了 `GameLoop` 覆盖不了的重复生命周期代码，例如 `enter/update/render/exit`、场景栈、过场切换、暂停层叠、统一资源卸载。
2. 至少两个已落地游戏都需要同一套跨对象批处理能力，例如按组件查询、稳定系统排序、批量碰撞宽阶段；并且这些能力不能用业务侧普通列表/函数拆分清楚表达。
3. 性能或确定性问题明确来自"业务自己组织对象"而不是来自算法实现，例如实体规模上升到数千级、需要数据局部性或可并行更新。

满足上述任一类反例、且能给出**至少两个真实游戏的代码**时，再重新评估是否引入 `Scene` / `System` / ECS。在那之前，YAGNI。

---

## 2. `GameLoop` 极简 helper

### 2.1 目标

封装以下三件事，**仅此而已**：

1. 固定逻辑步长（`DT = 1/60`）+ 累加器（保证慢机器逻辑不抽搐，快机器渲染流畅）
2. 输入采集 → `world.step(dt, input_frame)` → 渲染 / metrics 钩子的调度
3. headless 与 GUI 两套出口走同一份循环代码

**不**封装：场景切换、暂停菜单、状态栈、协程……（这些 fish 要么不需要，要么自己写一两行就够）

### 2.2 API（伪代码）

```python
from typing import Callable, Protocol, runtime_checkable
from toy_engine.input import InputSource, InputFrame

class SnapshotLike(Protocol):
    """world.snapshot() 的最小只读形状；推荐业务用 frozen dataclass 实现，而不是裸 dict。"""
    @property
    def player_pos(self) -> tuple[float, float]: ...

@runtime_checkable
class Steppable(Protocol):
    """任何拥有 step / snapshot / is_finished 的对象都可被 GameLoop 驱动。fish.World 直接满足。"""
    def step(self, dt: float, input_frame: InputFrame) -> None: ...
    def snapshot(self) -> SnapshotLike: ...
    def is_finished(self) -> bool: ...      # True 时循环退出

@runtime_checkable
class HashableSteppable(Steppable, Protocol):
    """tools/run_headless.py --determinism-check 额外要求；普通 GameLoop 不调用。"""
    def snapshot_hash(self) -> str: ...

class GameLoop:
    def __init__(
        self,
        world: Steppable,
        input_source: InputSource,
        dt: float = 1.0 / 60.0,
        on_frame: Callable[[SnapshotLike], None] | None = None,  # 每个逻辑帧后回调（renderer / recorder / metrics）
        max_sim_seconds: float | None = None,                    # 库默认不限；tools/fish 可传 180.0
        max_steps_per_frame: int = 8,                             # spiral-of-death 防护；100ms 卡顿仍可追 6 步
        time_source: Callable[[], float] | None = None,           # 默认 time.perf_counter
        speed: float = 1.0,                                       # 真实时间倍率；0 = 暂停，2 = 快进
        logic_dt_scale: float | Callable[[SnapshotLike], float] = 1.0,
            # 传给 world.step 的 dt 缩放；fish 死亡慢动作可返回 0.3
    ) -> None: ...

    def set_speed(self, speed: float) -> None: ...                # speed >= 0
    def step_once(self, n: int = 1) -> None: ...                  # 调试/暂停单步，走同一套 _tick_once

    def run_realtime(self) -> None:
        """GUI 模式：用 time_source 驱动，固定步长 + 累加器。"""

    def run_headless(self) -> None:
        """Headless 模式：不睡眠、不读真实时钟，每次循环固定推进 dt。"""
```

> `@runtime_checkable` 只用于粗粒度 `isinstance(world, Steppable)` 防呆；Python 运行时不会校验完整签名。签名一致性靠类型检查、单测与 DoD 保证。

### 2.2.1 `Steppable` 契约细节

- 调用顺序固定为：`pre_state = world.snapshot()` → `input_source.poll(pre_state)` → `world.step(effective_dt, input_frame)` → `post_state = world.snapshot()` → `on_frame(post_state)`。
- `step` 只允许做确定性的逻辑状态推进；不得读系统时间、不得读 pygame、不得写文件、不得直接渲染。`effective_dt = dt * logic_dt_scale`，用于满足 fish 慢动作"逻辑步进同步缩放"要求。
- `snapshot` 必须无副作用，返回**只读视图**。MVP 选择属性访问风格（如 `state.player_pos`），不要求返回 `dict`；推荐业务定义 `@dataclass(frozen=True, slots=True)`，嵌套列表也应转成 tuple，避免输入/渲染层误改 World。
- `snapshot` 至少暴露 `player_pos: tuple[float, float]`，供 `KeyboardMouseInput.poll` 计算鼠标方向；fish 若要在 `on_frame` 中录像 / 渲染时间效果 / 指标采样，建议同时暴露 `frame_idx`、`last_input_frame` 与 `last_effective_dt`。
- `is_finished` 必须无副作用，只读取终局状态；`True` 后 `GameLoop` 不再调用 `step`。
- `snapshot_hash() -> str` 不属于普通运行所需的 3 方法，但 `tools/run_headless.py --determinism-check` 必须要求 `HashableSteppable`，并在发现缺失时直接报错。

### 2.3 共享 tick 与 `run_realtime` 累加器算法

GUI 与 headless 必须共用同一个 `_tick_once()`，差别只在"时间从哪里来"：

```
def _tick_once():
    pre = world.snapshot()
    input_frame = input_source.poll(pre)
    scale = logic_dt_scale(pre) if callable(logic_dt_scale) else logic_dt_scale
    effective_dt = dt * max(0.0, scale)
    world.step(effective_dt, input_frame)
    post = world.snapshot()
    if on_frame:
        on_frame(post)
    return effective_dt
```

`run_realtime()` 只负责把真实时间切成若干次 `_tick_once()`：

```
acc = 0.0
sim_time = 0.0
last = now()                              # 默认 time.perf_counter()
while not world.is_finished():
    cur = now()
    elapsed = max(0.0, cur - last)
    last = cur

    if speed == 0.0:
        acc = 0.0
        yield_to_host()                    # 伪函数：GUI 模式让出 CPU / 处理宿主事件
        continue                          # 暂停逻辑推进；调试时可用 step_once 单步

    acc += min(elapsed * speed, 0.25)      # 防止断点恢复时一次推几百帧

    steps = 0
    while acc >= dt and steps < max_steps_per_frame and not world.is_finished():
        sim_time += _tick_once()
        acc -= dt
        steps += 1
        if max_sim_seconds is not None and sim_time >= max_sim_seconds:
            return

    if steps == max_steps_per_frame and acc >= dt:
        acc = 0.0                          # 丢弃积压，优先保证交互不被 spiral-of-death 拖死
    elif acc < dt:
        yield_to_host()                    # 避免无渲染或无 vsync 时 busy spin
```

`now()` 默认取 `time.perf_counter()`：它是跨平台单调高精度时钟，适合测帧间隔；不得用会受系统时间校准影响的 `time.time()`。
`yield_to_host()` 只存在于 realtime 实现（可用短 `time.sleep` 或宿主 GUI tick），不进入 headless 路径，也不参与确定性状态。
实现时要区分两个时间量：`frame_dt = dt` 用于帧号、Recorder 与回放节奏；`effective_dt = dt * logic_dt_scale` 只传给 `World.step` 和需要随慢动作缩放的世界内视觉状态。若 metrics 需要报告未缩放时长，可用 `frame_idx * dt`；若需要报告逻辑仿真时长，则读取 World 自己累积的 `effective_dt`。

> 渲染层通过 `on_frame(snapshot)` 注入：闭包里持有 `GeoCanvas`，调用 `canvas.clear()` / `fish.render.draw_world(canvas, snapshot)` / `canvas.present()`。`GameLoop` 本身不 import `pygame`、不持有 `GeoCanvas`，因此 headless 传 `on_frame=None` 或只传 recorder/metrics hook 即可。

### 2.4 `run_headless` 的循环

```
sim_time = 0.0
while not world.is_finished():
    sim_time += _tick_once()
    if max_sim_seconds is not None and sim_time >= max_sim_seconds:
        break
```

无 sleep、无 pygame、无 display；`tools/run_headless.py` 直接调用此入口。

---

## 3. 与 fish 的对接

fish 的 `main.py` 大致这样（**仅示意**，由 fish 实现 subagent 写）：

```python
world  = World(level_config, seed)
inputs = KeyboardMouseInput()
canvas = GeoCanvas.create_window(WORLD_W, WORLD_H, title="Fish")
recorder = Recorder(level_config, seed)

metrics = MetricsCollector()
metrics.set_scalar("seed", seed, top_level=True)
metrics.set_scalar("difficulty", difficulty, top_level=True)

def on_frame(state):
    recorder.record(state.frame_idx, state.last_input_frame)
    # metrics 可在 World.step 内部驱动；也可由 fish 从只读 snapshot 中取 gauges/events 后在这里
    # 调用 metrics.tick / metrics.record_event / metrics.set_scalar。
    canvas.clear()
    fish.render.draw_world(canvas, state)
    canvas.present()

GameLoop(
    world,
    inputs,
    on_frame=on_frame,
    logic_dt_scale=lambda state: 0.3 if state.death_slowmo_active else 1.0,
).run_realtime()

metrics.finish(result="VICTORY")   # 内部走 set_scalar("result", ..., top_level=True)
metrics.dump("metrics.json")
```

`tools/run_headless.py` 把 `inputs = BotInput(...)`、去掉 `canvas`、改用 `run_headless()` 即可。

## DoD 验收清单

- [ ] Q6 在本文 §1 给出明确决议（**不做** ECS）并已回写 [fish-doc progress.md](../../fish-doc/mvp/progress.md)
- [ ] `GameLoop` 在 GUI 模式下慢机器（强制 sleep 100ms/帧）逻辑步进数仍准确
- [ ] GUI / headless 共用 `_tick_once()`，两者的输入 → step → snapshot → hook 顺序完全一致
- [ ] `GameLoop.run_headless` 不依赖 `pygame.display`、可在 CI 容器中运行
- [ ] fish 的 `World` 不需继承任何引擎基类，仅按 `Steppable` 协议实现 3 个运行方法；确定性检查另实现 `snapshot_hash()`
- [ ] `world.snapshot()` 返回只读属性对象，且至少包含 `player_pos`
- [ ] `max_steps_per_frame` 默认值为 8，能防止 spiral-of-death 且覆盖 100ms 卡顿追帧
- [ ] `on_frame` 回调能同时驱动 renderer / recorder / metrics 三者

## 未决问题

- 暂停（`P` 键）UI 不由 GameLoop 内置；GameLoop 只提供 `set_speed(0)` / `step_once` 这些循环级控制点，fish 自己决定哪个输入触发。
- `on_frame` 是否需要未来拆成 `on_step` / `on_render` 两个 hook？MVP **不拆**，保持渲染==逻辑帧；高刷插值留到第二个游戏出现后再评估。
