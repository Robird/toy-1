# toy-engine MVP — 总览（Overview）

> 本文是 `toy-engine` MVP 阶段所有设计文档的入口。任何 subagent 接到引擎相关任务时，**先读完本文**，再按需跳转到具体步骤文档。
>
> 兄弟项目：[fish-doc/mvp/00-overview.md](../../fish-doc/mvp/00-overview.md)（引擎的首位也是 MVP 唯一消费方）

---

## 1. 引擎一句话定位

> **一个为"参数化、可回放、可批量跑分"的小型 2D pygame 游戏服务的轻量工具集。** 它不替你写游戏循环里的业务，但它保证：随机可控、输入可抽象、跑分可自动化、几何/绘图基础工具不必每个项目重写。

**风格关键词**：薄、可读、可被一个游戏一周内吃透；**不是** Unity / Godot 的 mini 复刻。

---

## 2. 范围与非范围

### 2.1 引擎**做**什么

| # | 能力 | 文档 |
|---|---|---|
| 1 | `SeededRng`：可派生命名空间的确定性随机源 | [01-rng.md](01-rng.md) |
| 2 | `GameLoop`：固定步长 + 输入/逻辑/渲染解耦的极简循环辅助 | [02-scene.md](02-scene.md) |
| 3 | `InputSource` 抽象 + 键鼠/回放实现 + Bot 基类 | [03-input.md](03-input.md) |
| 4 | `Recorder`：种子+输入序列录像与回放 | [04-recorder.md](04-recorder.md) |
| 5 | `MetricsCollector`：指标聚合与 JSON 输出 | [05-metrics.md](05-metrics.md) |
| 6 | `geom`：`Vec2`、圆碰撞、`clamp/lerp` 等数学小工具 | [06-geom.md](06-geom.md) |
| 7 | `GeoCanvas`：pygame 上的几何绘制高阶封装 + 调色板/粒子/屏震 | [07-render.md](07-render.md) |
| 8 | `tools/` 命令行框架：`run_headless` / `param_sweep` / `replay` | [08-tools.md](08-tools.md) |

### 2.2 引擎**不做**什么

- 不做 ECS / Scene / System 抽象（决议见 [02-scene.md §1](02-scene.md)，原因：**MVP 只服务 fish 一个游戏，过度抽象切碎业务难调试**）
- 不做资源管理器、动画系统、Tween 库、UI 框架
- 不做物理引擎（仅提供圆碰撞、AABB 等轻量几何原语；物理积分/碰撞系统由业务自己写）
- 不下沉 fish 的领域逻辑（鱼/Boss/关卡/AI 全留 fish）
- 不下沉**已有但未来未必通用**的代码（如 `audio_runtime.py`、`audio_utils.py`，详见 §6）
- 不做位图加载、不引入新的二进制依赖（除 pygame 本身）

---

## 3. 模块图

```
toy_engine/
├── __init__.py
├── rng.py               # SeededRng
├── loop.py              # GameLoop（极简，可选使用）
├── input.py             # InputSource, InputFrame, KeyboardMouseInput, ReplayInput, BotInputBase
├── recorder.py          # Recorder
├── metrics.py           # MetricsCollector
├── geom.py              # Vec2, circle_circle_overlap, clamp, lerp, AABB ...
├── font.py              # 薄 re-export（详见 §5）
├── tools_lib.py         # GameFactory 协议与命令行工具共用 helper（详见 08-tools.md）
└── render/
    ├── __init__.py
    ├── pyg.py           # GeoCanvas
    ├── palette.py       # Palette 加载/混色工具（不含颜色常量本身）
    └── particles.py     # 通用粒子系统

tools/                    # 命令行脚本（与 toy_engine 同级，不属于包）
├── run_headless.py
├── param_sweep.py
└── replay.py
```

依赖关系（左侧为更底层模块；右侧可依赖左侧）：

```
rng ───────────────► input
input ─────────────► recorder
input ─────────────► loop
geom, rng, font ───► render
metrics ───────────► tools_lib / tools/*
input, recorder, metrics, loop ──► tools_lib / tools/*
```

`render` 与 `loop` 均**可选**：headless 跑分根本不会 import `render` 与 `pygame.display`（仅 `tools/replay.py --render` 会走 GUI/渲染路径）。

---

## 4. 与 fish 项目的关系

引擎是 **被** fish 调用的库，**不**反向感知 fish。所有 import 走 `toy_engine.*` 命名空间。

fish-doc 中假定的 import（来自 [fish-doc progress.md "接口假设清单"](../../fish-doc/mvp/progress.md)）逐项回应如下：

| fish 假设 import | 引擎决议 | 说明 |
|---|---|---|
| `from toy_engine.rng import SeededRng` | ✅ 同意 | 见 [01-rng.md](01-rng.md) |
| `from toy_engine.input import InputSource, InputFrame, KeyboardMouseInput, ReplayInput` | ✅ 同意 | 见 [03-input.md](03-input.md) |
| `from toy_engine.recorder import Recorder` | ✅ 同意 | 见 [04-recorder.md](04-recorder.md) |
| `from toy_engine.metrics import MetricsCollector` | ✅ 同意 | 见 [05-metrics.md](05-metrics.md) |
| `from toy_engine.geom import Vec2, circle_circle_overlap, clamp, lerp` | ✅ 同意 | 见 [06-geom.md](06-geom.md) |
| `from toy_engine.render.pyg import GeoCanvas` | ✅ 同意 | 见 [07-render.md](07-render.md) |
| `from toy_engine.scene import Scene, System` | ❌ **不提供** | Q6 决议：见 [02-scene.md §1](02-scene.md)；改为可选的 `GameLoop`，fish 自己持有 `World` 即可，不必继承 `Scene` |

已裁决通过的增量/变更契约（来自 [fish-doc progress.md 变更登记区](../../fish-doc/mvp/progress.md)）索引如下：

| # | 契约 | 引擎归宿 |
|---|---|---|
| 1 | `Scene / System` 不下沉；改提供 `from toy_engine.loop import GameLoop` | [02-scene.md](02-scene.md) |
| 2 | `world.snapshot()` 必须暴露 `player_pos: tuple[float, float]`，供 `KeyboardMouseInput.poll` 使用 | [03-input.md §4.1](03-input.md) |
| 3 | `World.snapshot_hash() -> str` 由业务实现，供 `tools/run_headless.py --determinism-check` 使用 | [08-tools.md §5](08-tools.md) |
| 4 | `BotInput` 不在引擎下沉；引擎只提供 `BotInputBase`，具体启发式留 `fish/ai/bot_player.py` | [03-input.md §4.3](03-input.md) |
| 5 | 增量导出：`InputFrame`、`BotInputBase`、`Recording`、`GameLoop`、`Palette`、`ParticleSystem`、`ScreenShake`、`AABB`、`aabb_overlap`、`wrap_angle`、`angle_lerp`、`smoothstep`、`lerp_vec`、`circle_circle_penetration`、`toy_engine.font.load_font`、`toy_engine.tools_lib.GameFactory`（注：原列的 `RunInfo` 已被契约 #8 metrics 重写废弃，业务通过 `set_scalar(top_level=True)` 写入元数据） | [03-input.md](03-input.md)、[04-recorder.md](04-recorder.md)、[05-metrics.md](05-metrics.md)、[02-scene.md](02-scene.md)、[07-render.md](07-render.md)、[06-geom.md](06-geom.md)、本文 §5、[08-tools.md §2](08-tools.md) |

---

## 5. 字体处理决议

仓库根目录已有 `font_utils.py`，被 `snake.py`、`suika_game.py` 等旧游戏使用。处理方式：

**选项 A（采纳）**：保留根目录 `font_utils.py` 不动，引擎提供薄 re-export `toy_engine/font.py`：

```python
# toy_engine/font.py
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from font_utils import load_font  # noqa: F401, re-export
```

**理由**：

1. 不破坏现有 6 个旧游戏的 import
2. 引擎对外只暴露 `from toy_engine.font import load_font` 一个公共入口，下游游戏不需要知道老文件
3. 后续若要"搬家到 `toy_engine/font.py`"也只是一次性把实现移过来，外部 API 不变，迁移成本接近 0

> 如果未来发现 path hack 太脏，可改为 B（彻底搬家 + 在根目录留 `from toy_engine.font import *` 反向兼容 shim）。**MVP 选 A**。

---

## 6. 音频归属决议

仓库已有 `audio_runtime.py` / `audio_utils.py`，但：

- fish MVP 阶段仅留 `sfx.play(name)` hook，**可不出声**（[fish-doc 06 §3.7](../../fish-doc/mvp/06-controls-feel.md)）
- 这两个模块当前与具体业务（"语音播报"等）耦合度未知，未必通用
- 引擎**不**下沉它们；fish 若需要直接 `import audio_runtime`，引擎不阻拦

> 未来某个游戏明确复用音频时再考虑下沉。MVP 不做猜想性抽象。

---

## 7. 全局术语表

仅引入引擎自身需要的新术语；游戏层术语（Tier/Phase/...）见 [fish-doc/mvp/00-overview.md §4](../../fish-doc/mvp/00-overview.md)。

| 术语 | 含义 |
|---|---|
| `InputFrame` | 一帧的玩家输入快照（方向 + 动作位）；详见 [03-input.md](03-input.md) |
| `Recording` | 一局录像 = 业务配置哈希（fish 中为 `LevelConfig` 哈希）+ 种子 + `InputFrame` 序列 |
| `state hash` | `World` 在某一帧的逻辑状态散列，用于确定性自检 |
| `命名子流（named sub-stream）` | `SeededRng.spawn(name)` 派生出的子 RNG，用于隔离不同子系统的随机消耗 |
| `GeoCanvas` | 包装 `pygame.Surface` 的高阶绘制对象 |
| `headless` | 无 `pygame.display`、不创建窗口的运行模式 |

> Subagent 不得自创同义词。如确需新增引擎术语，先在 [progress.md 未决问题](progress.md) 登记；若影响 fish 契约，再同步登记到 [fish-doc progress.md 未决问题](../../fish-doc/mvp/progress.md)。

---

## 8. 文档协作规范

- **修改前**先看 [progress.md](progress.md) 当前状态
- **完成后**更新 [progress.md](progress.md)：状态、产出、遗留问题
- **不复述其他文档内容**——一律用相对链接
- **每篇步骤文档末尾**固定两节：`## DoD 验收清单` 与 `## 未决问题`
- 接口若与 fish 假设不一致，**必须**同步登记到 [fish-doc progress.md 变更登记区](../../fish-doc/mvp/progress.md)

---

## 9. 当前阶段

> **现在处于：M1 — 引擎设计文档撰写阶段**

下一阶段：M2 — 引擎实现（按文档逐模块落地）

## DoD 验收清单

- [ ] 11 篇 M1 文档齐备且互相链接闭合
- [ ] [fish-doc progress.md](../../fish-doc/mvp/progress.md) 的"接口假设清单"逐项被本文 §4 回应
- [ ] [fish-doc progress.md](../../fish-doc/mvp/progress.md) 的 5 项已裁决契约变更均在本文 §4 有索引
- [ ] Q6 在 [02-scene.md](02-scene.md) 中给出明确决议
- [ ] 模块图列出 `toy_engine.tools_lib`，且与 [08-tools.md §2](08-tools.md) 的 `GameFactory` 入口一致
- [ ] 字体与音频归属在本文 §5、§6 中明确

## 未决问题

- 引擎自身未来是否要支持窗口缩放/DPI 缩放？MVP 锁固定窗口大小，留 hook。
- `GeoCanvas` 是否要支持离屏 RT 用于后处理（vignette、bloom）？MVP **不做**，反馈用粒子+屏震就够。
