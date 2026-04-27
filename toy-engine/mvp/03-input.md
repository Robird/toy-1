# 03 — InputSource / InputFrame

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[fish-doc 06 §4](../../fish-doc/mvp/06-controls-feel.md)、[04-recorder.md](04-recorder.md)、[fish-doc 07 §5](../../fish-doc/mvp/07-test-harness.md)

## 1. 设计目标

- 让 `World.step` **永远只接受 `InputFrame`**，不直接读 pygame 事件
- 三种来源——键鼠、录像回放、Bot——共享同一个抽象，可任意替换而不动 `World` 一行
- `InputFrame` 必须**可序列化为 JSON**（Recorder 要存）且**字段稳定**（多游戏时只追加不破坏）

## 2. `InputFrame` 数据结构

```python
from dataclasses import dataclass

from toy_engine.geom import Vec2, Vec2Like

@dataclass(frozen=True, slots=True)
class InputFrame:
    desired_dir: Vec2 | None = None
        # 归一化的 2D 方向向量；None = 本帧无方向输入 / 请求自然减速
    dash:        bool = False
        # MVP 始终 False；预留按键
```

> 核心字段只保留 `desired_dir` 与 `dash`，与 fish-doc 06 §4 的语义字段对齐；MVP 不提供 `extra` 逃生口，未来技能/暂停等输入位必须按版本追加显式字段，避免 Recorder 格式被任意 dict 污染。

> `Vec2` 来自 `toy_engine.geom`，构造时接受 `Vec2Like`（含 tuple），便于业务方便传值；序列化到录像 JSON 时表现为 `[x, y]` 数组（见 [04-recorder.md §3](04-recorder.md#3-文件格式)）。`InputFrame.desired_dir` 的 canonical 内存类型是 `Vec2 | None`；实现应在 `__post_init__` 或构造 helper 中把传入的 `Vec2Like` 规范化为 `Vec2`。`None` 与零向量必须区分。

`desired_dir` 约定：

- `None` = 本帧没有方向意图；`World.step` 应按自身阻尼/拖拽让玩家自然减速，可同时表达“待命”和“请求停下”的 MVP 语义。
- `Vec2(0.0, 0.0)`（以及等价 tuple 入参）**禁止作为有效输入**；生产者遇到死区、松开键盘或无法取得焦点时必须返回 `None`。
- 非 `None` 时必须是有限值、长度约为 1 的归一化 `Vec2`。实现可在 `InputFrame.__post_init__` 或构造 helper 中校验，避免 NaN/零向量进入物理层。

序列化约定（详见 [04-recorder.md §3](04-recorder.md)）：

```json
{ "i": 1234, "dir": [0.707, -0.707], "dash": false }
```

## 3. `InputSource` 抽象基类

```python
from typing import Protocol, Any

class InputSource(Protocol):
    def poll(self, world_state: Any) -> InputFrame:
        """读取本帧输入。world_state 是 world.snapshot() 的返回值，便于 Bot 做反应。"""
```

> 用 `Protocol`（结构化子类型）而非 ABC，让 fish 的 BotInput 不必显式继承也能塞进 GameLoop。

**契约**：

- `GameLoop` 必须保证每个逻辑帧只调用一次 `poll`；`ReplayInput` 会推进内部游标，`KeyboardMouseInput` 会维护键鼠模式状态，因此 `poll` **不是幂等 API**
- `poll` 不得修改 `world_state`；在相同 InputSource 内部状态、相同 `world_state` 与相同外部 IO 状态下，返回值必须确定
- `poll` 必须**在 1 帧内返回**（< 1ms 量级）；任何重计算放到 Bot 的别处缓存
- 不允许在 `poll` 内调用 `world.step` 或修改 `world_state`

## 4. 内置实现

### 4.1 `KeyboardMouseInput`

```python
class KeyboardMouseInput:
    def __init__(self, dead_zone_px: float = 15.0, screen_to_world=None): ...
    def poll(self, world_state) -> InputFrame: ...
```

行为（与 [fish-doc 06 §1](../../fish-doc/mvp/06-controls-feel.md) 对齐）：

1. 每帧先调用 `pygame.event.pump()` 更新 pygame 输入状态；不要在这里 `pygame.event.get()` 清空事件队列，窗口关闭、暂停等事件仍由游戏主循环/外层处理。
2. 读取 `world_state.player_pos`。若 snapshot 不含该字段，立刻抛 `InputContractError`（或实现期等价的清晰异常），不要 fallback 到 `(0, 0)`，否则鼠标方向会静默错误。
3. 读取 `pygame.mouse.get_pos()` 的**屏幕坐标**，经 `screen_to_world` 转换为世界坐标；`screen_to_world=None` 时视为 identity。fish MVP 暂无卷轴/缩放，因此屏幕坐标与世界坐标一致，但 API 保留 transform hook。
4. 若窗口未聚焦（如 `pygame.key.get_focused()` 为 false），返回 `InputFrame(desired_dir=None)`，避免使用过期键鼠状态。鼠标越界时实现应先按窗口/viewport clamp，再走 `screen_to_world`。
5. 状态机维护 `mode in {"mouse", "keyboard"}` 与 `last_mouse_pos`：
   - 任一逻辑帧用 `pygame.key.get_pressed()` 检测到 WASD/方向键非零输入 → `mode="keyboard"`，输出 8 向归一化方向。
   - `mode="keyboard"` 且本帧无方向键时 → 输出 `None`，但仍保持 keyboard 模式。
   - 之后检测到鼠标位置相对 `last_mouse_pos` 发生变化 → `mode="mouse"`，重新按鼠标指向输出。
6. 鼠标模式下，世界鼠标位置与 `player_pos` 的距离 `< dead_zone_px` → `desired_dir=None`；否则归一化 → `desired_dir=Vec2(dx, dy)`（或等价 `Vec2Like` 入参）。
7. `dash` MVP 留默认值 `False`。

> 引擎层只要求 `world_state` 提供 `player_pos: tuple[float, float]` 这一个属性。这是引擎对 fish snapshot 的**唯一硬约束**，已在 fish-doc progress 契约 #2 中裁决通过；本文给出实现期失败模式。

### 4.2 `ReplayInput`

```python
class ReplayInput:
    def __init__(self, frames_by_index: list[InputFrame], *, strict_end: bool = False): ...
    @classmethod
    def from_recording(cls, path: str, *, strict_end: bool = False) -> tuple["LevelConfig 等价物", "ReplayInput"]: ...
    def poll(self, world_state) -> InputFrame: ...
```

- 回放按**逻辑帧序号 `frame_index`** 驱动，不按 `sim_time` 查表；`GameLoop` 每执行一次固定步长 `world.step(dt, input_frame)`，就会先调用一次 `ReplayInput.poll()` 并推进一个索引
- `from_recording` 负责读取 Recorder 的稀疏变更帧 `{ "i": frame_index, "dir": ..., "dash": ... }`，按 [04-recorder.md §3.1](04-recorder.md) 的规则把间隙重复上一帧，展开为 `frames_by_index`
- 录像总长度优先取 `meta.duration_frames`；缺失时退化为最后一个记录帧的 `i + 1`，但实现应 warning，因为无法知道最后一次输入是否本应持续到更晚
- 内部维护 `frame_idx`，每次 `poll` 返回 `frames_by_index[frame_idx]` 然后递增
- 越界后默认返回静止帧 `InputFrame(desired_dir=None, dash=False)`，让 `max_sim_seconds` / metrics 触发 TIMEOUT；若 `strict_end=True`，则抛 `EndOfReplay` 供 `tools/replay.py` 精确结束回放
- **不**读取 `world_state`（回放靠确定性，不靠"看世界做决定"）

### 4.3 `BotInputBase`

引擎只提供**基类**，不下沉具体启发式（启发式属业务知识，住在 `fish/ai/bot_player.py`）：

```python
class BotInputBase:
    def __init__(self, rng: SeededRng):
        self.rng = rng

    def poll(self, world_state) -> InputFrame:
        return self.decide(world_state)

    def decide(self, world_state) -> InputFrame:
        raise NotImplementedError

    def reset(self) -> None:
        pass
```

提供基类的目的：

- 统一构造接受 `rng` 参数，避免子类各自接全局随机
- 固定 `poll -> decide` 骨架，便于未来在基类里统一加输入校验、trace、录制 mixin，而不改业务 bot
- 提供 `reset` hook，便于同一个 bot 实例在批量跑分前清空内部缓存；默认无状态

> `danger_radius`、`flee_weight`、Boss 特判等启发式参数属于 fish 业务层。具体实现位于 `fish/ai/bot_player.py`，继承或结构兼容 `BotInputBase`；本引擎不提供任何具体启发式 bot。

## 5. 三者的可替换性证明（DoD 关键）

GameLoop 的循环只调一处：

```python
input_frame = input_source.poll(world.snapshot())
world.step(dt, input_frame)
```

**同一个 World + 同一个 seed**：

- `KeyboardMouseInput` 驱动 → 真实游戏
- `Recorder.record` 同时保存 input_frame 序列
- 之后 `ReplayInput.from_recording(...)`（或等价的 `frames_by_index`）重跑 → 与原始一帧不差（state hash 一致）
- 同 seed 用 `BotInput` 跑 → 得到一个新的（确定性）跑分

这是 [fish-doc 07 §8 确定性自检](../../fish-doc/mvp/07-test-harness.md) 的基础。

## DoD 验收清单

- [ ] `InputFrame` 可经 Recorder 序列化 helper（`Vec2` → `[x, y]`）→ `json.dumps` 往返
- [ ] `KeyboardMouseInput.poll` 在 dead_zone 内返回 `desired_dir=None`
- [ ] `KeyboardMouseInput` 在 monkeypatch 的 pygame key/mouse/focus 状态下覆盖：键盘优先切换、鼠标移动切回、失焦返回静止、缺失 `player_pos` 抛清晰异常
- [ ] `ReplayInput` 覆盖 Recorder 稀疏帧间隙重复、按 frame_index 推进、越界静止与 `strict_end=True` 抛异常
- [ ] `ReplayInput` 用 Recorder 录制的序列回放后，与原游戏 state hash 完全一致
- [ ] `BotInputBase` 子类能被 GameLoop 直接驱动（Protocol 兼容），且同 seed + 同 snapshot 序列输出完全一致
- [ ] 三种 InputSource 在同一 `World(seed=42)` 上跑出的 metrics 在各自语义下确定可重复

## 已关闭问题

- 2026-04-27 R2：`InputFrame.desired_dir` 类型问题已关闭；canonical 内存类型为 `Vec2 | None`，录像 JSON wire format 仍为 `[x, y]` 数组。

## 未决问题

- 是否需要"输入插值"以适配渲染帧 ≠ 逻辑帧的高刷场景？MVP **不做**，渲染==逻辑（[02-scene.md §2.3](02-scene.md)）。
- 手柄/触控：MVP **不做**（与 [fish-doc 06 未决](../../fish-doc/mvp/06-controls-feel.md) 一致）。
