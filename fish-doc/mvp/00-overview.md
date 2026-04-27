# Fish MVP — 总览（Overview）

> 本文是 MVP 阶段所有设计文档的入口。任何 subagent 接到 fish 项目相关任务时，**先读完本文**，再按需跳转到具体步骤文档。

---

## 1. 项目一句话定位

> **在一片会呼吸的深海里，被缓慢逼近的巨兽追猎；玩家必须在压力下贪婪进食、用每一次成长重新定义"谁吃谁"，最终从猎物逆转成猎手。**

类型：2D 大鱼吃小鱼（Feeding Frenzy 类）+ 简易 Boss 追击战
单局时长目标：60 ~ 120 秒
核心情感曲线：**逃命 → 贪食 → 临门一脚 → 逆转狂喜**

---

## 2. 技术栈与范围

| 项 | 选择 | 备注 |
|---|---|---|
| 语言 | Python 3.x | 与仓库现有 6 个游戏一致 |
| 渲染 | pygame（几何绘制） | 不引入位图素材；走"程序化矢量卡通风" |
| 字体 | 复用仓库 `font_utils.py` | 中文友好 |
| 音频 | 复用仓库 `audio_runtime.py`（可后置） | MVP 留 hook，可不出声 |
| 引擎依赖 | `toy-engine/`（本仓库子包，待建） | 见 §6 |
| 平台 | Windows 桌面（开发机）；理论上跨平台 | |

**MVP 不做**：位图素材、音乐、菜单/存档、多 Boss、多关卡选择、迷宫/机关、技能树、商店、剧情、网络对战。

---

## 3. MVP 必含的 5 大支柱

按优先级降序，每一项对应一篇步骤文档：

| # | 支柱 | 文档 |
|---|---|---|
| P0 | 工程化测试脚手架（seeded RNG / 录像 / headless bot / 5 指标） | [07-test-harness.md](07-test-harness.md) |
| P0 | 核心循环（玩家、成长、吃/被吃、死亡重开） | [01-core-loop.md](01-core-loop.md) |
| P0 | 鱼群生态（5 档体型、AI、外观、刷新） | [02-fish-ecosystem.md](02-fish-ecosystem.md) |
| P0 | Boss 战（状态机、追击、反杀） | [03-boss.md](03-boss.md) |
| P0 | 参数化关卡生成器（参数维度、三段式曲线、硬约束） | [04-level-generator.md](04-level-generator.md) |
| P1 | 视觉规范（调色板、几何鱼模板、背景视差、反馈粒子） | [05-visuals.md](05-visuals.md) |
| P1 | 操作与手感（鼠标跟随、惯性、拖尾、画面反馈） | [06-controls-feel.md](06-controls-feel.md) |
| — | MVP 验收标准（Definition of Done） | [08-mvp-scope.md](08-mvp-scope.md) |
| — | 进度追踪（活文档） | [progress.md](progress.md) |

**P0 = MVP 不可砍，P1 = 影响体验但可降级实现。**

---

## 4. 全局术语表（Glossary）

> Subagent 写代码/文档时**必须沿用**以下命名，不得自创同义词。

### 4.1 体型档位（Tier）

```
Tier 0  fry      幼鱼      玩家初始
Tier 1  small    小鱼
Tier 2  medium   中鱼
Tier 3  large    大鱼
Tier 4  giant    巨鱼      Boss 体型档位
```

判定规则：玩家与目标 `tier_self >= tier_other + 0` ⇒ 可吃；`tier_self < tier_other` ⇒ 被吃。
Boss 在被反杀阶段前对玩家始终视为 Tier 4，无视一般规则（详见 [03-boss.md](03-boss.md)）。

### 4.2 坐标系与单位

- 屏幕坐标：左上原点，X 向右、Y 向下，单位**像素 px**
- 世界坐标：与屏幕一致（MVP 不做卷轴），世界尺寸 `WORLD_W × WORLD_H`，建议 `1280 × 720`
- 时间：仿真步长固定 `DT = 1/60 s`（逻辑层定时步进，渲染层独立帧率）
- 速度：`px/s`；角度：弧度，0 = 正右，逆时针为正

### 4.3 颜色变量（在 [05-visuals.md](05-visuals.md) 中定义具体值）

```
PALETTE_DEEP, PALETTE_MID, PALETTE_SHALLOW, PALETTE_FOAM, PALETTE_HIGHLIGHT
ROLE_PLAYER, ROLE_PREY, ROLE_PEER, ROLE_THREAT, ROLE_BOSS
```

### 4.4 关卡阶段（Phase）

```
PHASE_WARMUP    教学期：仅 Tier-1 小鱼，无威胁
PHASE_PRESSURE  压力期：引入 Tier-2/3 同级与威胁鱼
PHASE_BOSS      Boss 期：Boss 进场，节奏陡升
PHASE_REVENGE   反杀期：玩家达阈值，Boss 转为逃跑
```

---

## 5. 模块架构（高层）

```
fish/                          # 游戏代码（本项目主体）
  main.py                      # 入口：装配 World + Renderer + InputSource，跑主循环
  world.py                     # World：纯逻辑层，World.step(dt, inputs) -> state
  entities/
    player.py
    fish.py                    # 普通鱼：行为 AI + 体型 + 渲染描述
    boss.py
    particle.py
  systems/
    movement.py                # 速度/惯性/边界
    collision.py               # 圆形碰撞 + 吃/被吃判定
    spawner.py                 # 鱼群刷新（受 LevelConfig 驱动）
    level_director.py          # 三段式阶段切换
    level_generator.py         # 参数化关卡生成器（输入种子+难度）
  ai/
    fish_ai.py                 # boid + 逃逸/追击启发式
    boss_ai.py                 # Patrol/Chase/Charge/Stunned/Enraged 状态机
    bot_player.py              # headless 自动测试用的玩家 bot
  render/
    pyg_renderer.py            # pygame 渲染层（只读 World 状态）
    visuals.py                 # 几何绘制原语（鱼/泡泡/Boss 剪影）
    palette.py
  io/
    input_source.py            # 抽象：键鼠输入 / 录像回放 / Bot 输入
    recorder.py                # 录像 = 种子+输入序列
    metrics.py                 # 5 大指标统计
  config/
    level_config.py            # LevelConfig 数据类
    constants.py               # WORLD_W、DT、TIER_THRESHOLDS 等
tools/
  run_headless.py              # 无窗口跑 N 局，输出 JSON 报告
  param_sweep.py               # 参数扫描脚本
  replay.py                    # 回放录像
```

> 上面**斜体的目录结构是建议而非强制**，实现 subagent 可在不破坏关注点分离的前提下微调。

---

## 6. 与 toy-engine 的关系

为避免重复造轮子并便于后续游戏复用，**部分基础设施会下沉到** `toy-engine/`（本仓库子包，与 `fish/` 平级）。引擎部分另有独立设计文档系列 `toy-engine/mvp/`（由后续 subagent 起草）。

**预计下沉到引擎的能力**（fish-doc 在写作时假设这些 import 可用）：

```python
from toy_engine.rng import SeededRng
from toy_engine.scene import Scene, System            # 可选；若引擎太重可不下沉
from toy_engine.input import InputSource, KeyboardMouseInput, ReplayInput
from toy_engine.recorder import Recorder
from toy_engine.metrics import MetricsCollector
from toy_engine.geom import circle_circle, vec2
from toy_engine.render.pyg import GeoCanvas           # 几何绘制的高阶封装
```

**fish 项目中保留为业务代码的部分**：World 内的所有领域逻辑（鱼群、Boss、关卡生成、AI、视觉风格）。

> 协调原则：**fish-doc 先按假设接口写**，engine-doc 后续按这些假设回填具体 API。如果 engine subagent 觉得某个假设不合理，必须在 [progress.md](progress.md) 的"未决问题"区提出，由本会话仲裁。

---

## 7. 文档协作规范（给 subagent）

- **修改文档前**先读 [progress.md](progress.md)，看任务是否已被认领或已完成。
- **完成任务后**必须更新 [progress.md](progress.md)：状态、产出、验收结论、遗留问题。
- **不要跨文档复述设计**——需要引用的请用相对链接，例如：体型判定见 [`02-fish-ecosystem.md` §3](02-fish-ecosystem.md)。
- **遇到术语冲突或缺失**：不要自己发明，先在 [progress.md](progress.md) 的"未决问题"区登记，由本会话裁决。
- **每篇步骤文档末尾**固定两节：`## DoD 验收清单` 与 `## 未决问题`。

---

## 8. 当前阶段

> **现在处于：M0 — 设计文档撰写阶段**

下一阶段：M1 — toy-engine 设计文档（subagent 起草）
之后：M2 — engine 实现 → M3 — fish 实现 → M4 — 联调 + bot 跑分调参 → MVP 完成
