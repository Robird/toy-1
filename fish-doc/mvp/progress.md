# Fish MVP — 进度追踪（活文档）

> **每次开始/结束任务都必须更新本文。** 任何 subagent 接到 fish 项目相关任务时，先读 [00-overview.md](00-overview.md)，再读本文了解当前状态与未决问题。

---

## 总体里程碑

| 里程碑 | 状态 | 说明 |
|---|---|---|
| M0 设计文档（fish-doc/mvp/） | ✅ 完成 | 由主会话起草 |
| M1 引擎设计文档（toy-engine/mvp/） | ✅ 完成 | 由 Claude subagent 起草 |
| M2 toy-engine 实现 | ✅ 完成 | 372 passed，覆盖率 92%（rng/geom/recorder/metrics 100%）；详见 [toy-engine progress](../../toy-engine/mvp/progress.md) |
| M3 fish 业务实现 | 🟡 进行中 | 10 步任务表见下；Claude 编码 + GPT 审阅 + 主会话 commit |
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

## M3 任务表（fish 业务实现）

采用 **Claude 编码 → GPT 审阅 + 顺手修复 → 主会话独立 commit** 的迭代流程，同 M2。每步开工前 subagent 必读 [00-overview.md](00-overview.md) + 本文 + 该步关联文档。每步完成后必须更新本文「工作日志」与本表「状态/提交」列。

模块布局参见 [00-overview.md §5](00-overview.md)。

| ID | 任务 | 状态 | 提交 | 关联设计文档 | 关键产出 |
|---|---|---|---|---|---|
| M3-01 | 项目骨架：包结构 + `fish/config/constants.py` + `fish/config/level_config.py`（dataclass）+ `fish/main.py` 占位 + 单测脚手架 | ✅ 已审，待提交 | — | [00](00-overview.md), [04](04-level-generator.md), [08](08-mvp-scope.md) | `fish/{__init__,main}.py`, `fish/config/*`, `tests/fish/test_skeleton.py`（5 passed；GPT review PASS_WITH_FIXES） |
| M3-02 | `World` 骨架：`Steppable` 协议（`step/snapshot/snapshot_hash/is_finished`）+ `GameResult` 枚举 + 实体基类；空逻辑但 `GameLoop` 能跑通 | ✅ 已审，待提交 | — | [00 §5](00-overview.md), engine [02](../../toy-engine/mvp/02-scene.md), 契约 #1/#2/#3 | `fish/world.py`（World + GameResult + snapshot_hash 规范化）, `fish/entities/base.py`（Entity 基类）, `fish/main.py`（30 帧 headless）, `tests/fish/test_world_skeleton.py`（GPT 补强后 tests/fish 25 passed；GPT review PASS_WITH_FIXES） |
| M3-03 | Player + 移动系统（惯性/turn_rate/边界反射）+ `KeyboardMouseInput` 接入（消费 `InputFrame.desired_dir: Vec2\|None`） | ✅ 已审，待提交 | — | [01](01-core-loop.md), [06](06-controls-feel.md), 契约 #2/#6 | `fish/entities/player.py`, `fish/systems/movement.py`, `fish/world.py` 接入 player + MovementSystem；GPT 审阅后按设计文档修正玩家初始 `tier=0`；snapshot 落实契约 #2；`fish/main.py` 以 `_StubInput` 驱动 30 帧证明实际移动（player_pos.x=724.92 > WORLD_W/2）；补强零向量防御、四向边界反射、30 帧平行决定性测试；`pytest tests/fish -q` 40 passed，全仓 418 passed 无回归 |
| M3-04 | Fish 实体 + `FishAI`(WANDER/FLEE/CHASE 三态) + 简化群行为 + `Spawner`(基础版,4 个非 Boss 等阶) | ✅ 已审，待提交 | — | [02](02-fish-ecosystem.md) | `fish/entities/fish.py`, `fish/ai/fish_ai.py`, `fish/systems/spawner.py`，`fish/world.py` 接入 spawner+fish_ai+`alloc_eid`，snapshot 增 fish 项；GPT 审阅补强 FLEE 零向量防护、separation 限速、spawn 瞬间屏外测试，并修正 `fish/main.py` 精确跑 300 帧；`tests/fish/test_fish_ai.py` 共 20 用例；`pytest tests/fish -q` **60 passed**，全仓 `pytest -q` **438 passed**（+20 vs M3-03 基线 418）；`python -m fish.main` 输出 `frames=300 elapsed_s=5.0000`、`fish_count_by_tier: tier1=8, tier2=0, tier3=0, tier4=0`（达成 WARMUP target=8）；GPT review PASS_WITH_FIXES |
| M3-05 | 碰撞检测 + 吃/被吃判定 + 成长（TIER 阈值）+ `GameResult.DEAD` + 同阶弹性反弹 | ⬜ | — | [01](01-core-loop.md), [02 §3](02-fish-ecosystem.md) | `fish/systems/collision.py`, `fish/systems/growth.py` |
| M3-06 | `LevelGenerator`（参数+校验+重试）+ `LevelDirector`（WARMUP/PRESSURE/BOSS/REVENGE 阶段切换）；接入 spawner | ⬜ | — | [04](04-level-generator.md), [01 §4](01-core-loop.md) | `fish/systems/level_generator.py`, `fish/systems/level_director.py` |
| M3-07 | Boss 实体 + `BossAI` 五状态机（PATROL/CHASE/CHARGE_WINDUP/CHARGE/STUNNED/ENRAGED）+ 玩家复仇判定 + Tier4 提示 | ⬜ | — | [03](03-boss.md) | `fish/entities/boss.py`, `fish/ai/boss_ai.py` |
| M3-08 | 视觉：`Palette` 配色 + `draw_fish` / `draw_boss` + 视差背景 + UI + 字体（`toy_engine.font.load_font`） | ⬜ | — | [05](05-visuals.md), engine [07](../../toy-engine/mvp/07-render.md) | `fish/render/{palette,visuals,pyg_renderer}.py` |
| M3-09 | 手感：拖尾 + squash + 吃鱼三件套粒子 + 屏震 + 慢镜 + 渐隐；集成进 World/render | ⬜ | — | [06](06-controls-feel.md) | `fish/render/feel.py`, World 钩子 |
| M3-10 | `BotInput`（继承 `BotInputBase`）+ `MetricsCollector` 绑定（`bind_metrics` hook，闭合 EQ12）+ `GameFactory` 实现 + `tools/run_headless` `tools/param_sweep` 联调跑通 | ⬜ | — | [07](07-test-harness.md), engine [08](../../toy-engine/mvp/08-tools.md), 契约 #4/#8 | `fish/ai/bot_player.py`, `fish/io/metrics_adapter.py`, `fish/factory.py` |

> M3 全部完成后进入 M4：用 `tools/param_sweep.py` 跑 100 局 headless 验证 5 个 metric 落入 [08 §3](08-mvp-scope.md) 的目标区间，必要时回头微调参数。

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

## M3 实施期发现

> 由 M3 阶段 subagent 在实施过程中登记的、与设计文档不一致或文档存在歧义/缺失之处。**禁止 subagent 自行修改设计文档**，由主会话裁决后再回填。

| # | 时间 | 步骤 | 发现 | 提出方 | 主会话裁决 |
|---|---|---|---|---|---|
| 1 | 2026-04-28 | M3-01 | fish-doc/04 §2 的 `LevelConfig.phases: dict[Phase, PhaseConfig]` 引用了 `Phase` 类型但全套 fish-doc 未给出其形式定义（00 §4.4 只以 `PHASE_WARMUP / PHASE_PRESSURE / PHASE_BOSS / PHASE_REVENGE` 列出四个阶段名）。M3-01 实现选择把 `Phase` 定义为 `enum.Enum`，成员名为 `WARMUP/PRESSURE/BOSS/REVENGE`（去掉 `PHASE_` 前缀以避免与枚举类名叠词），放在 `fish/config/constants.py`。 | Claude subagent (M3-01) | ✅ 通过（主会话, 2026-04-28）：成员名 `WARMUP/PRESSURE/BOSS/REVENGE` 是约定俗成的 enum 风格。M3-06 实现 LevelGenerator 时若涉及录像/JSON 序列化，使用 `Phase.<name>.name` 字符串落盘以保持稳定。fish-doc/00 §4.4 暂不回填（属业务约定，作为 M3 实现层细节合理）。 |
| 2 | 2026-04-28 | M3-01 | fish-doc/04 §2 的 `PhaseConfig` / `BossConfig` / `LevelConfig` 三者均写作 `@dataclass`（默认非 frozen），但 M3-01 任务书要求 `LevelConfig` 必须 `frozen=True`。当前实现：仅 `LevelConfig` 顶层 frozen，`PhaseConfig`/`BossConfig` 与文档一致保持非 frozen；后果是嵌套 `cfg.phases[Phase.WARMUP].duration_s = X` 仍可被改写。 | Claude subagent (M3-01) | ✅ 通过（主会话, 2026-04-28）：M3-01 不强制深度不可变。MVP 阶段 LevelGenerator 产出后约定为「只读使用」，靠纪律而非语言机制。如 M3-06 实现期发现误改导致 bug，再升级为全链 frozen。 |
| 3 | 2026-04-28 | M3-02 | fish-doc/01 §4 的 `GameResult` 列出 4 个枚举值（`RUNNING / DEAD / VICTORY / TIMEOUT`），但 M3-02 任务书举例时写「至少含 `WIN`、`DEAD`」。当前实现按 fish-doc/01 §4 取 4 态枚举（`RUNNING/DEAD/VICTORY/TIMEOUT`），且 `World.snapshot()['game_result']` 在「进行中」用 `None` 表达（不写 `RUNNING.name`），便于 JSON 友好与「终态写入即 finished」的判定一致。`RUNNING` 成员保留以兼容文档枚举完备性，但 M3-02 路径不会写入。 | Claude subagent (M3-02) | ⬜ 待裁决：建议 ① 接受 `None` ↔「进行中」的 snapshot 表达；② 保留 `RUNNING` 成员仅作枚举完备性；③ 后续 M3-05/07 写终态时必为 `DEAD/VICTORY/TIMEOUT` 之一。 |
| 4 | 2026-04-28 | M3-02 | fish-doc 未明示 `LevelConfig.total_duration` 计算公式。fish-doc/04 §2 中 `PhaseConfig.duration_s` 对 BOSS/REVENGE 两阶段为「事件驱动」(M3-01 默认实现填 `0.0`)；fish-doc/01 §4 给出独立的硬上限 `TIMEOUT_S=180`。当前 `World.is_finished()` 暂取 `Σ phase.duration_s`（默认 = WARMUP 15 + PRESSURE 20 + 0 + 0 = 35s），并在 docstring 注明「正式终态判定由 M3-05/07 接入 LevelDirector」。 | Claude subagent (M3-02) | ⬜ 待裁决：建议明确 ① `is_finished()` 的 fallback 是否应改为 `min(Σ phase.duration_s, TIMEOUT_S)`；② BOSS/REVENGE 阶段的 `duration_s` 字段语义（是「上限」还是「事件驱动占位 0」），并在 fish-doc/04 §2 回填。 |
| 5 | 2026-04-28 | M3-02 | fish-doc/00 §5 + 01 §1 未对 `Entity` 基类字段集合给出权威清单。当前实现取最小公共子集（`eid: int / pos: Vec2 / vel: Vec2 / radius: float / alive: bool`），把 `tier / hp / state / ai_state` 等留给具体子类按需追加。`eid` 字段是 fish 业务侧约定（`snapshot` 排序与 `snapshot_hash` 的稳定性所需），fish-doc 未明示但与 toy-engine/08 §5 「按 id 排序」隐含一致。 | Claude subagent (M3-02) | ⬜ 待裁决：建议在 fish-doc/00 §5 或 01 §1 回填 `Entity` 字段权威清单（含 `eid` 的来源说明），便于 M3-04/07 子类对齐。 |
| 6 | 2026-04-28 | M3-03 | M3-03 任务书明说 `Player.tier` 初始=1，但 fish-doc/00 §4.1 + 01 §2 「玩家初始 = Tier 0 fry」。Claude 初版按 tier=1；GPT 审阅后已修正当前实现为 `TIER_FRY`（tier=0，对应 `PLAYER_RADIUS[0]=10`、`PLAYER_MAX_SPEED[0]=220`），与设计文档和 `TIER_THRESHOLDS[0]=0` 对齐。 | Claude subagent (M3-03) + GPT review | ⬜ 待裁决：建议接受当前实现（tier=0）并视为任务书口误；若主会话确认 tier=1，需反向改代码并同步 fish-doc/00 §4.1、01 §2 与成长阈值语义。 |
| 7 | 2026-04-28 | M3-03 | fish-doc/06 §2 只给出单一标量的 `PLAYER_TURN_RATE=6.0` / `PLAYER_ACCEL=900` / `PLAYER_DRAG=3.5`（非 tier→table）；但 M3-03 任务书说「按 06 的 tier→数值表初始化」。当前实现：仅 `max_speed` 按 tier 查 `PLAYER_MAX_SPEED[tier]`；`accel` / `turn_rate_rad_s` 为全 tier 共享的文档标量。`PLAYER_DRAG` 作为 `desired_dir is None` 时的衰减依据（`vel *= exp(-drag*dt)`）。 | Claude subagent (M3-03) | ⬜ 待裁决：建议在 fish-doc/06 §2 明确 “MVP 阶段 turn_rate / accel / drag 为 tier 不分型”，或者在 M4 调参期补充 tier→table。 |
| 8 | 2026-04-28 | M3-03 | fish-doc/06 §2 仅提供玩家闪避 / 惯性参数，未说明「边界反射是否取玩家半径」。当前实现仍按 `[0, WORLD_W] x [0, WORLD_H]` 钉点反射（不减去 radius），与 M3-03 任务书「边界为 [0, WORLD_W]」一致；GPT 审阅补强了精确贴边且速度向外时立即反射的防粘墙保护。后续如需「鱼可见部分不出屏」，可在 M3-09 手感调优时改为留 radius 边距。 | Claude subagent (M3-03) + GPT review | ⬜ 待裁决（低优）：建议 MVP 暂保持点边界，半径边距留给 M3-09/M4 手感调参。 |
| 9 | 2026-04-28 | M3-04 | **任务书 vs 设计文档 tier 编号不一致**。M3-04 任务书写「fish.tier 范围 0..3（不含 Boss）」，但 fish-doc/02 §1 明确给出 4 类普通鱼为 **Tier 1..4**（Minnow=1 / Sardine=2 / Snapper=3 / Barracuda=4）；fish-doc/00 §4.1 同时写「Tier 0=fry 玩家初始」「Tier 4=giant Boss 体型档位」。MVP 实现选择以 fish-doc/02 §1（本步权威）为准：`Fish.tier ∈ {1,2,3,4}`，Tier 0 仅玩家初始，Boss 是独立实体（M3-07 接入），与 Barracuda 共享 Tier 4 的「体型档位」语义但不共享类。LevelConfig.default() 的 population_target 字典键 1..4 直接对齐。 | Claude subagent (M3-04) | ⬜ 待裁决：建议 ① 接受 fish.tier ∈ {1,2,3,4} 的实现；② 在 fish-doc/00 §4.1 注释一句「Tier 4 既是 Barracuda 的体型档位也是 Boss 的体型档位，两者按实体类型区分而非 tier」；③ 后续任务书统一引用「02 §1 的 1..4」。 |
| 10 | 2026-04-28 | M3-04 | fish-doc/02 §1~§4 给出了 FishParams 字段名（perception_radius / flee_radius / chase_radius / turn_rate / school_weight）但**未列具体数值**；fish-doc/02 §2 也未给出 WANDER 状态的 turn 间隔 / 巡航速度比例。MVP 实现自填 `FISH_TURN_RATE_RAD_S = (0, 5, 4, 3, 2.5)`、`FISH_PERCEPTION_RADIUS = FISH_FLEE_RADIUS = FISH_CHASE_RADIUS = (0, 100, 140, 180, 240)`、`WANDER_TURN_INTERVAL_S=1.0`、`WANDER_SPEED_RATIO=0.4`、`WANDER_HEADING_JITTER_RAD=1.0`、`FISH_SEPARATION_OVERLAP_MUL=1.5`、`FISH_SEPARATION_PUSH_SPEED=30.0`，全部在 `fish/config/constants.py` 加「MVP 占位 / M4 调参」来源注释。 | Claude subagent (M3-04) | ⬜ 待裁决：建议接受占位值进入 M4 bot 跑分，再根据 metrics 调整；若主会话希望此刻就在 fish-doc/02 §2 回填这些表，则需主会话给出权威值。 |
| 11 | 2026-04-28 | M3-04 | fish-doc/02 §2 的 FSM 含 `aggression` 标志与 `flee_radius * 1.5` 的滞回阈值；M3-04 任务书允许 MVP 简化为「player.tier > fish.tier → FLEE；player.tier < fish.tier → CHASE；相等 → WANDER」（无滞回 / 无 aggression）。当前实现采纳任务书简化版 + 距离门（`flee_radius` / `chase_radius` 内才切），其它行为差异通过 tier 数值与 perception_radius 隐式表达。完整 §2 滞回 / aggression 留 M4 调参。 | Claude subagent (M3-04) | ⬜ 待裁决：建议接受 MVP 简化 FSM；若 bot 跑分阶段出现「FLEE/WANDER 帧间反复抖动」（02 DoD 第 2 条），再补滞回阈值。 |
| 12 | 2026-04-28 | M3-04 | fish-doc/02 §4 末段写明硬约束「屏内 `count(tier <= player.tier) >= 1` 否则强制就近 spawn 一条 `tier == player.tier` 的猎物」与「Tier-4 在 PHASE_WARMUP 绝不出现」。M3-04 Spawner **未**实现这两条兜底：第 1 条属业务/director 层，留 M3-06 LevelDirector 接入；第 2 条目前依赖 `LevelConfig.default()` 中 WARMUP 的 `population_target[3]=population_target[4]=0` 自然满足，并未写显式 assert。 | Claude subagent (M3-04) | ⬜ 待裁决：建议两条兜底都留 M3-06；M3-06 实施期在 LevelDirector / Spawner 边界明确各自责任。 |

---

## 工作日志

| 时间 | 角色 | 动作 | 备注 |
|---|---|---|---|
| 2026-04-27 | 主会话 | 完成 M0 全部 9 篇文档 | 等待安排 M1 |
| 2026-04-27 | Claude subagent | 完成 M1 全部 11 篇引擎文档 + 提交 5 项契约变更 | 见上方变更登记 |
| 2026-04-27 | 主会话 | 裁决 5 项契约变更全部通过 | M0/M1 设计阶段收尾，待用户开启 M2 实现轮次 |
| 2026-04-27 | Claude subagent | 完成 M1 全部 11 篇引擎文档；Q6 决议关闭（不做 ECS，做 `GameLoop`）；登记 5 项接口变更（变更区 #1~#5）；字体选方案 A（薄 re-export）；音频暂不下沉 | 等待主会话裁决变更区 #1~#5，然后启动 M2 |
| 2026-04-27 | Claude subagent | 完成 R2 metrics 文档重写（方案 A）+ 同步 02/08 + 契约 #8 登记 | review-log 待主会话关闭 |
| 2026-04-28 | 主会话 + Claude/GPT 团队 | 完成 toy-engine M2 全部 10 步实现（M2-01..M2-10）+ POST-M2 批次 A/B 修复（详见 toy-engine progress 工作日志），引擎进入「M3 可开工」状态 | 14 个本地 commit 未推 origin |
| 2026-04-28 | 主会话 | 评估 toy-engine M2 验收通过；登记 fish M3 任务表（10 步）；标记 M3 进入「进行中」 | 准备派遣 Claude 实施 M3-01 |
| 2026-04-28 | Claude subagent (M3-01) | 实施 M3-01 项目骨架：建立 `fish/{config,entities,systems,ai,render,io}/` 包；落地 `fish/config/constants.py`（集中所有文档已写死的数值，含 Tier 阈值/Boss 状态时长/Phase 区间等，每条带文档来源注释）；落地 `fish/config/level_config.py`（`LevelConfig` 用 `frozen=True` + `default()` 工厂；`PhaseConfig`/`BossConfig` 子配置严格按 fish-doc/04 §2）；占位 `fish/main.py`（`python -m fish.main` 可跑）；新增 `tests/fish/test_skeleton.py` 5 个轻量测试。`pytest tests/fish` 5 passed；`python -m fish.main` 输出 "fish MVP — skeleton ready"。**未**实现 World/实体/系统/AI/渲染。等待主会话 commit。新增「M3 实施期发现」小节登记 2 项待裁决问题。 |
| 2026-04-28 | GPT subagent (M3-01 review) | 独立审阅 M3-01，确认未越界实现 World/实体/系统/AI/render 逻辑；小修 `fish/main.py` 的 pygame 零副作用、`LevelConfig.default()` 来源说明、`TIER_MAX` 来源注释，并补强骨架测试的类型/硬约束与 `main()` 无 pygame import 断言。 | PASS_WITH_FIXES；`pytest tests/fish -q` 5 passed；指定 import smoke 可打印 `LevelConfig.default()`；建议 Phase 枚举命名与 nested dataclass frozen 范围均裁决通过。 |
| 2026-04-28 | Claude subagent (M3-02) | 实施 M3-02 World 骨架：新增 `fish/entities/base.py`（`Entity` 基类：`eid/pos:Vec2/vel:Vec2/radius/alive`，无业务行为）；新增 `fish/world.py`（`GameResult` 枚举对齐 fish-doc/01 §4 四态 RUNNING/DEAD/VICTORY/TIMEOUT；`World` 实现 `Steppable`：`step` 仅推进 `frame_count/elapsed_s` + 缓存 `last_input_frame`/`last_effective_dt`，`snapshot()` 返回含 `player_pos/frame_count/elapsed_s/entities/game_result` 的 dict，`snapshot_hash()` 用 `_normalize_for_hash`(浮点四舍五入到 6 位小数 + Enum→name + Vec2→[x,y]) + sorted-key JSON + sha1，`is_finished()` 基于 `game_result` 或 `elapsed_s ≥ Σ phase.duration_s` 占位）；升级 `fish/main.py` 为构造 `LevelConfig.default()+SeededRng+World+GameLoop` 跑 30 帧 headless 并打印 snapshot/hash；新增 `tests/fish/test_world_skeleton.py`（5 大类 16 用例覆盖 snapshot 形状/step 推进/snapshot_hash 稳定&变更/is_finished/Steppable&HashableSteppable&GameLoop 集成）；同步修订 `tests/fish/test_skeleton.py::test_main_runs` 移除「不得 import pygame」断言（M3-02 main 已合法依赖 toy_engine.input → pygame）。`pytest tests/fish -q` **21 passed**；全仓 `pytest -q` **399 passed** 无回归；`python -m fish.main` 输出 `frames=31 elapsed_s=0.5167 ... snapshot_hash=75d7dbc8...`。**未**实现 Player/Fish/Boss/AI/render/systems。新增「M3 实施期发现」3 项待裁决（见下表）。 |
| 2026-04-28 | GPT subagent (M3-02 review) | 独立审阅 M3-02，确认 `World.step(dt, input_frame)` 与 `GameLoop._tick_once` 实参一致，headless 集成测试确由 `GameLoop` 推进；顺手补强 `_normalize_for_hash` 的 NaN/±inf 与过深嵌套处理，补测 tuple/list/嵌套 dict/None/Vec2/Enum；修正 `fish.main` 30 帧 headless 演示因浮点 cap 多跑 1 帧的问题。 | PASS_WITH_FIXES；`pytest tests/fish -q` 25 passed；全仓 `pytest -q` 403 passed；`python -m fish.main` 输出 `frames=30 elapsed_s=0.5000 ... snapshot_hash=4e2920f5...`；建议实施期发现 #3 通过、#4 修改、#5 通过并回填说明。 |
| 2026-04-28 | Claude subagent (M3-03) | 实施 M3-03 Player + MovementSystem + 输入接入：新增 `fish/entities/player.py`（`Player(Entity)` + `from_config` 把玩家放在世界中央，tier=1，运动学参数按 `PLAYER_MAX_SPEED[tier]/PLAYER_ACCEL/PLAYER_TURN_RATE` 初始化）；新增 `fish/systems/movement.py`（`MovementSystem`：`rotate_toward` 按 `turn_rate*dt` 限转向、沿 heading 加速到 `max_speed`、`desired_dir is None` 时 `vel *= exp(-PLAYER_DRAG*dt)`、`[0,WORLD_W]x[0,WORLD_H]` 边界以 `WALL_BOUNCE_DAMPING` 反射且位置 clamp）；升级 `fish/world.py`（`__init__` 创建 `self.player` + `self._movement`；`step` 中调用 MovementSystem；`snapshot()['player_pos']` 改为玩家实际位置×契约 #2 落实；`entities` 含 player dict）；升级 `fish/main.py`（`_StubInput` 每帧返回 `Vec2(1,0)` 推进 30 帧）；新增 `tests/fish/test_movement.py` 10 用例；同步修订 `tests/fish/test_world_skeleton.py::test_initial_state` 与 `tests/fish/test_skeleton.py::test_main_runs` 以反映 entities/main 输出变更。`pytest tests/fish -q` **35 passed**；全仓 `pytest -q` **413 passed** 无回归；`python -m fish.main` 输出 `frames=30 elapsed_s=0.5000 player_pos=(728.75, 360.00) heading=0.0000 snapshot_hash=e433c420...`（player_pos.x=728.75 > WORLD_W/2=640 ×）。未实现 Fish/Boss/AI/spawner/collision/render。新增「M3 实施期发现」 3 项待裁决（#6 tier 初值·#7 turn_rate/accel/drag tier 表·#8 边界反射是否取 radius）。等主会话 commit。 |
| 2026-04-28 | GPT subagent (M3-03 review) | 独立审阅 M3-03，确认 `World.snapshot()['player_pos']` 已返回玩家实际位置、`MovementSystem` 使用引擎 `rotate_toward`、`desired_dir=None` 走指数衰减、加速度与 `max_speed` clamp 符合 06 §2、`_StubInput` 结构兼容 `InputSource` 且由 `GameLoop` 调用；顺手修正玩家初始 tier 到 0，补零向量/非有限输入防护，补精确贴边向外速度立即反射，更新过期 docstring，并补强四向反射与 30 帧平行决定性测试。 | PASS_WITH_FIXES；`pytest tests/fish -q` 40 passed；全仓 `pytest -q` 418 passed（较 Claude 413 多 5 个审阅补强用例）；`python -m fish.main` 输出 `frames=30 elapsed_s=0.5000 player_pos=(724.92, 360.00) heading=0.0000 snapshot_hash=ce098c931e0b592db1fd8a58e7ebcf20dccd2af6`；未 git commit。 |
| 2026-04-28 | Claude subagent (M3-04) | 实施 M3-04 Fish + FishAI + Spawner：① `fish/config/constants.py` 新增 fish-tier 表（FISH_RADIUS/FISH_MAX_SPEED 取 02 §1，FISH_TURN_RATE_RAD_S/perception/flee/chase/WANDER 各项/SEPARATION 各项为 MVP 占位且全部带来源注释 + 「M4 调参」标记）+ SPAWNER_EDGE_MARGIN；② 新增 `fish/entities/fish.py`（`Fish(Entity)` + `Fish.spawn(eid,tier,pos,heading,rng)`，tier ∈ [1,4] 校验，每条鱼携带独立 SeededRng 子流）；③ 新增 `fish/ai/fish_ai.py`（`FishAIState` + `FishAI`：MVP 简化 FSM「player.tier > self → FLEE / < self → CHASE / 相等 → WANDER」+ 距离门 + WANDER 周期重选偏航 + 仅同 tier 的 separation 推开力，alignment/cohesion docstring 标 M4）；④ 新增 `fish/systems/spawner.py`（每 0.5s 检查 + 屏外四边随机刷新 + 朝屏内 + 走 `world.rng.spawn("spawner")` 子流，每条 fish 拿 `spawner_rng.spawn(f"fish_{eid}")` 隔离子流，TODO M3-06 接入 director 已注释）；⑤ `fish/world.py` 升级：`alloc_eid()` 公有化、`self.fishes` + `self._fish_ai` + `self._spawner`，step 顺序 spawner→fish_ai(按 eid 升序)→movement，snapshot.entities 含 `kind="fish"` + heading/tier/state，entities 输出按 eid 排序保证 hash 决定性；⑥ `fish/main.py` 改 300 帧 + Counter 打印 by tier；⑦ `tests/fish/test_fish_ai.py` 新增 17 用例（4 tier 工厂 + 半径/速度单调 + invalid tier + FLEE/CHASE/WANDER 行为 + 500 帧 WANDER 无 NaN + 60 帧并行决定性 + 600 帧 population_target 不超 + 2000 帧达成 target=8 + 屏外缘 spawn + 朝屏内 + snapshot 含 fish 字段）。`pytest tests/fish -q` **57 passed**，全仓 `pytest -q` **435 passed** 无回归；`python -m fish.main` 输出 `frames=301 elapsed_s=5.0167 ... fish_count_by_tier: tier1=8, tier2=0, tier3=0, tier4=0 (total=8) snapshot_hash=fe9ff11a...`（WARMUP target[1]=8 已拉满，target[2..4]=0 故只有 Tier 1，证明 spawner 正常工作）。未实现 collision/eat/grow/Boss/director/render。新增「M3 实施期发现」 4 项待裁决（#9 tier 编号 0..3 vs 1..4 / #10 fish 参数表占位值 / #11 FSM 简化版无滞回 / #12 §4 硬约束兜底留 M3-06）。等主会话 commit。 |
| 2026-04-28 | GPT subagent (M3-04 review) | 独立审阅 M3-04，确认 `Fish.tier` 取 1..4 与 02 §1 一致、`alloc_eid()` 公有化对 Spawner 合理、`world.rng.spawn("spawner")` + `spawner_rng.spawn(f"fish_{eid}")` 在同 seed / 同输入下逐帧决定性；顺手补强 FLEE 同位/非有限方向兜底、separation 后速度不突破 `fish.max_speed`、Spawner 生成瞬间屏外且朝内测试，并修正 `fish.main` 由 `run_headless(max_sim_seconds)` 浮点累计导致多跑 1 帧的问题，改用 `GameLoop.step_once(300)`。 | PASS_WITH_FIXES；`pytest tests/fish -q` 60 passed；全仓 `pytest -q` 438 passed；`python -m fish.main` 输出 `frames=300 elapsed_s=5.0000 ... fish_count_by_tier: tier1=8, tier2=0, tier3=0, tier4=0 (total=8) snapshot_hash=23e45bb1bc27cb25e003bdf2857450765d89e0f5`；未 git commit。 |
