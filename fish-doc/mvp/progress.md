# Fish MVP — 进度追踪（活文档）

> **每次开始/结束任务都必须更新本文。** 任何 subagent 接到 fish 项目相关任务时，先读 [00-overview.md](00-overview.md)，再读本文了解当前状态与未决问题。

---

## 总体里程碑

| 里程碑 | 状态 | 说明 |
|---|---|---|
| M0 设计文档（fish-doc/mvp/） | ✅ 完成 | 由主会话起草 |
| M1 引擎设计文档（toy-engine/mvp/） | ✅ 完成 | 由 Claude subagent 起草，本轮交付 |
| M2 toy-engine 实现 | ⬜ 未开始 | 下一轮激活 |
| M3 fish 业务实现 | ⬜ 未开始 | M2 后启动 |
| M4 联调 + bot 跑分调参 | ⬜ 未开始 | |
| M5 MVP 验收 | ⬜ 未开始 | 按 [08 §6](08-mvp-scope.md) |

状态图例：✅ 完成 · 🟡 进行中 · 🔵 待审 · ⬜ 未开始 · ❌ 阻塞

---

## 任务表

| ID | 任务 | 状态 | 责任 | 关联文档 | 产出 / 验收结论 |
|---|---|---|---|---|---|
| M0-01 | overview + 术语表 | ✅ | 主会话 | [00](00-overview.md) | 已交付 |
| M0-02 | 核心循环 | ✅ | 主会话 | [01](01-core-loop.md) | 已交付 |
| M0-03 | 鱼群生态 | ✅ | 主会话 | [02](02-fish-ecosystem.md) | 已交付 |
| M0-04 | Boss 战 | ✅ | 主会话 | [03](03-boss.md) | 已交付 |
| M0-05 | 关卡生成器 | ✅ | 主会话 | [04](04-level-generator.md) | 已交付 |
| M0-06 | 视觉规范 | ✅ | 主会话 | [05](05-visuals.md) | 已交付 |
| M0-07 | 操作与手感 | ✅ | 主会话 | [06](06-controls-feel.md) | 已交付 |
| M0-08 | 测试脚手架 | ✅ | 主会话 | [07](07-test-harness.md) | 已交付 |
| M0-09 | MVP 验收标准 | ✅ | 主会话 | [08](08-mvp-scope.md) | 已交付 |
| M1-01 | toy-engine overview + 术语 | ✅ | Claude subagent | [`toy-engine/mvp/00-overview.md`](../../toy-engine/mvp/00-overview.md) | 字体选方案 A；音频暂不下沉 |
| M1-02 | RNG 模块设计 | ✅ | Claude subagent | [`01-rng.md`](../../toy-engine/mvp/01-rng.md) | 与 [07 §1](07-test-harness.md) 一致；`spawn` 用 BLAKE2b 派生 |
| M1-03 | Scene/World 抽象 | ✅ | Claude subagent | [`02-scene.md`](../../toy-engine/mvp/02-scene.md) | **Q6 决议**：不做 ECS，改极简 `GameLoop` |
| M1-04 | InputSource 抽象 | ✅ | Claude subagent | [`03-input.md`](../../toy-engine/mvp/03-input.md) | 引擎只提供 `BotInputBase`；具体 bot 启发式留 fish |
| M1-05 | Recorder 录像格式 | ✅ | Claude subagent | [`04-recorder.md`](../../toy-engine/mvp/04-recorder.md) | JSON +可选 gzip；含 config_hash |
| M1-06 | Metrics 收集器 | ✅ | Claude subagent | [`05-metrics.md`](../../toy-engine/mvp/05-metrics.md) | 引擎只提供框架，5 大指标语义留 fish |
| M1-07 | 几何工具 | ✅ | Claude subagent | [`06-geom.md`](../../toy-engine/mvp/06-geom.md) | 含 `Vec2 / circle / AABB / 角度`，无 numpy |
| M1-08 | 渲染封装 GeoCanvas | ✅ | Claude subagent | [`07-render.md`](../../toy-engine/mvp/07-render.md) | 含粒子/屏震/调色板；零内置颜色常量 |
| M1-09 | tools 脚本框架 | ✅ | Claude subagent | [`08-tools.md`](../../toy-engine/mvp/08-tools.md) | 业务通过 `GameFactory` 协议注入 |
| M1-10 | 引擎 MVP 验收标准 | ✅ | Claude subagent | [`09-mvp-scope.md`](../../toy-engine/mvp/09-mvp-scope.md) | |
| M1-11 | 引擎 progress | ✅ | Claude subagent | [`progress.md`](../../toy-engine/mvp/progress.md) | |

> M2 起的实现任务在 toy-engine 文档落地后再细化登记。

---

## 未决问题（Open Questions）

| # | 问题 | 来源文档 | 状态 |
|---|---|---|---|
| Q1 | 是否引入"饥饿衰减"？ | [01 未决](01-core-loop.md) | 暂否决（MVP 不做） |
| Q2 | 是否引入"营养鱼" | [02 未决](02-fish-ecosystem.md) | 暂否决 |
| Q3 | 玩家咬 Boss 是否要付出"缩水"代价 | [03 未决](03-boss.md) | 暂否决 |
| Q4 | LevelGenerator 是否引入洋流方向场 | [04 未决](04-level-generator.md) | 暂否决，留接口 |
| Q5 | Bot 多档聪明度（low/mid/stress） | [07 未决](07-test-harness.md) | MVP 只做一档 |
| Q6 | toy-engine 是否提供 Scene/System 抽象，还是只做底层工具集？ | M1 起草时决定 | ✅ **已决议（2026-04-27, Claude subagent）：不提供 ECS / Scene / System，改提供可选的极简 `GameLoop` helper（固定步长 + 输入/逻辑/渲染解耦）。** fish 的 `World` 直接以 `Steppable` 协议（`step / snapshot / is_finished`）接入。理由与反例条件见 [`toy-engine/mvp/02-scene.md §1`](../../toy-engine/mvp/02-scene.md)。|

---

## 与 toy-engine 的接口假设清单

> fish-doc 在写作时**假设**以下 import 可用。toy-engine subagent 在 M1 起草时如需变更命名或参数，**必须**在本表追加并通知主会话裁决。

```python
from toy_engine.rng     import SeededRng
from toy_engine.input   import InputSource, InputFrame, KeyboardMouseInput, ReplayInput
from toy_engine.recorder import Recorder
from toy_engine.metrics import MetricsCollector
from toy_engine.geom    import Vec2, circle_circle_overlap, clamp, lerp
from toy_engine.render.pyg import GeoCanvas   # 几何绘制高阶封装（可选）
# Scene/System 抽象是否提供 → Q6 已决议：不提供，改用 GameLoop（见下方变更登记 #1）
```

变更登记区（subagent 修改时追加，不要删除历史）：

| # | 时间 | 变更 | 提出方 | 主会话裁决 |
|---|---|---|---|---|
| 0 | — | （初始） | — | — |
| 1 | 2026-04-27 | **`Scene / System` 不下沉**。改提供可选的 `from toy_engine.loop import GameLoop`。fish 的 `World` 不必继承任何引擎基类，仅按 `Steppable` 协议实现 `step / snapshot / is_finished` 三个方法。详见 [`toy-engine/mvp/02-scene.md`](../../toy-engine/mvp/02-scene.md)。 | Claude subagent | ✅ 通过（主会话, 2026-04-27）：YAGNI 优先，避免为 N=1 样本过度抽象。fish 实现 subagent 须按此约定。 |
| 2 | 2026-04-27 | **新增隐含契约**：`world.snapshot()` 需暴露 `player_pos: tuple[float, float]` 字段，供 `KeyboardMouseInput.poll` 计算鼠标→玩家方向。详见 [`toy-engine/mvp/03-input.md §4.1`](../../toy-engine/mvp/03-input.md)。 | Claude subagent | ✅ 通过：fish 实现 subagent 必须在 `World.snapshot()` 中包含 `player_pos`。 |
| 3 | 2026-04-27 | **新增隐含契约**：`World.snapshot_hash() -> str` 由业务实现，供 `tools/run_headless.py --determinism-check` 比对帧序列。详见 [`toy-engine/mvp/08-tools.md §5`](../../toy-engine/mvp/08-tools.md)。 | Claude subagent | ✅ 通过：fish 实现时把所有可观察状态做稳定哈希（建议 sorted-key JSON + sha1）。 |
| 4 | 2026-04-27 | **`BotInput` 不在引擎下沉**。引擎只提供 `BotInputBase`（接 `SeededRng` 的构造基类），具体启发式留 `fish/ai/bot_player.py`（启发式属业务知识）。fish-doc 07 §5 的 BotInput 不再 import 自 `toy_engine.input`。 | Claude subagent | ✅ 通过：启发式确属业务。M3 实现 subagent 在 fish-doc/mvp/07 §5 顶部补一句"实现位于 fish/ai/bot_player.py，继承 toy_engine.input.BotInputBase"。 |
| 5 | 2026-04-27 | **新增引擎导出**（fish-doc 假设之外但合理的扩展，不破坏既有 import）：`InputFrame`, `BotInputBase`, `Recording`, `GameLoop`, `Palette`, `ParticleSystem`, `ScreenShake`, `AABB`, `aabb_overlap`, `wrap_angle`, `angle_lerp`, `smoothstep`, `lerp_vec`, `circle_circle_penetration`, `toy_engine.font.load_font`, `toy_engine.tools_lib.GameFactory`。 | Claude subagent | ✅ 通过：纯增量扩展，不破坏现有契约。**注**：原列的 `RunInfo` 已在契约 #8 metrics 重写中废弃。 |
| 6 | 2026-04-27 | **澄清/重申**：`InputFrame.desired_dir` canonical 类型为 `Vec2 | None`（fish-doc/mvp/06 §4 为权威）。引擎 03-input、04-recorder 已对齐。`Vec2` 接受 `Vec2Like` 入参便于传 tuple；录像 JSON wire format 为 `[x, y]` 数组。 | 主会话（R2 修订） | ✅ 通过：是澄清非变更。 |
| 7 | 2026-04-27 | **新增 geom 导出**：`Vec2Like`（输入类型联合）、`angle_delta(a, b)`、`rotate_toward(current, target, max_step)`、`angle_in_arc(angle, center, half_width)`。这些是 fish 的 Boss "尾部 240° 判定"与鱼群 turn_rate 转向所必需的便捷工具，不是新机制。详见 [`toy-engine/mvp/06-geom.md`](../../toy-engine/mvp/06-geom.md)。 | GPT subagent (R2) | ✅ 通过：纯增量便捷函数，不破坏现有契约。 |
| 8 | 2026-04-27 | **MetricsCollector envelope 与 API 改名**：单局 JSON 严格遵循 fish-doc/07 §6 envelope（顶层 `seed/difficulty/result/duration_s/player_max_tier/death_cause` + `metrics` 段 + 引擎附加 `engine_version/duration_frames/events/extra`）。新核心 API：`set_scalar(name, value, *, top_level=False)`、`record_event(name, value=None)`、`final_report() -> dict`、`finish(result, **extra)`。旧名 `event`/`to_dict` 作为兼容别名保留至 M3。详见 [`toy-engine/mvp/05-metrics.md`](../../toy-engine/mvp/05-metrics.md)。 | 主会话裁决 + Claude subagent 实施 (R2) | ✅ 通过：与 fish-doc/07 §6 完全对齐，保持 Q6 推/拉模型不变。 |

---

## 工作日志

| 时间 | 角色 | 动作 | 备注 |
|---|---|---|---|
| 2026-04-27 | 主会话 | 完成 M0 全部 9 篇文档 | 等待安排 M1 |
| 2026-04-27 | Claude subagent | 完成 M1 全部 11 篇引擎文档 + 提交 5 项契约变更 | 见上方变更登记 |
| 2026-04-27 | 主会话 | 裁决 5 项契约变更全部通过 | M0/M1 设计阶段收尾，待用户开启 M2 实现轮次 |
| 2026-04-27 | Claude subagent | 完成 M1 全部 11 篇引擎文档；Q6 决议关闭（不做 ECS，做 `GameLoop`）；登记 5 项接口变更（变更区 #1~#5）；字体选方案 A（薄 re-export）；音频暂不下沉 | 等待主会话裁决变更区 #1~#5，然后启动 M2 |
| 2026-04-27 | Claude subagent | 完成 R2 metrics 文档重写（方案 A）+ 同步 02/08 + 契约 #8 登记 | review-log 待主会话关闭 |
