# toy-engine MVP — 进度追踪（活文档）

> **每次开始/结束任务都必须更新本文。** 任何 subagent 接到引擎相关任务时，先读 [00-overview.md](00-overview.md)，再读本文了解当前状态与未决问题。
>
> 兄弟项目进度：[fish-doc/mvp/progress.md](../../fish-doc/mvp/progress.md)

---

## 总体里程碑

| 里程碑 | 状态 | 说明 |
|---|---|---|
| M1 引擎设计文档（toy-engine/mvp/） | ✅ 完成 | 本轮由 Claude subagent 交付 |
| M2 引擎实现 + 单测 | ⬜ 未开始 | 按 11 篇文档逐模块落地 |
| M3 fish 业务实现 | ⬜ 未开始 | M2 后启动，fish-doc 自行追踪 |
| M4 联调 + bot 跑分调参 | ⬜ 未开始 | |
| M5 引擎+fish 联合验收 | ⬜ 未开始 | 按 [09-mvp-scope.md §7](09-mvp-scope.md) |

状态图例：✅ 完成 · 🟡 进行中 · 🔵 待审 · ⬜ 未开始 · ❌ 阻塞

---

## M1 任务表（本轮）

| ID | 任务 | 状态 | 责任 | 产出 |
|---|---|---|---|---|
| M1-01 | overview + 术语 + 字体/音频归属 | ✅ | Claude subagent | [00-overview.md](00-overview.md) |
| M1-02 | RNG 模块设计 | ✅ | Claude subagent | [01-rng.md](01-rng.md) |
| M1-03 | Scene/System Q6 决议 + GameLoop | ✅ | Claude subagent | [02-scene.md](02-scene.md) |
| M1-04 | InputSource 抽象 | ✅ | Claude subagent | [03-input.md](03-input.md) |
| M1-05 | Recorder 录像格式 | ✅ | Claude subagent | [04-recorder.md](04-recorder.md) |
| M1-06 | Metrics 收集器 | ✅ | Claude subagent | [05-metrics.md](05-metrics.md) |
| M1-07 | 几何工具 | ✅ | Claude subagent | [06-geom.md](06-geom.md) |
| M1-08 | GeoCanvas 渲染封装 | ✅ | Claude subagent | [07-render.md](07-render.md) |
| M1-09 | tools 脚本框架 | ✅ | Claude subagent | [08-tools.md](08-tools.md) |
| M1-10 | 引擎 MVP 验收标准 | ✅ | Claude subagent | [09-mvp-scope.md](09-mvp-scope.md) |
| M1-11 | 引擎 progress（本文） | ✅ | Claude subagent | progress.md |

---

## M2 任务表（待启动）

> M2 在主会话批准 M1 后再细化。下面是建议的拆分顺序（自底向上，每条 ≈ 1 个独立 subagent 任务）。

| ID | 任务 | 依赖 | 备注 |
|---|---|---|---|
| M2-01 | 实现 `toy_engine/rng.py` + 单测 | — | 优先级最高，其它都依赖 |
| M2-02 | 实现 `toy_engine/geom.py` + 单测 | — | 与 M2-01 可并行 |
| M2-03 | 实现 `toy_engine/input.py` + 单测 | M2-01 | |
| M2-04 | 实现 `toy_engine/recorder.py` + 单测 | M2-03 | |
| M2-05 | 实现 `toy_engine/metrics.py` + 单测 | — | |
| M2-06 | 实现 `toy_engine/loop.py` + 单测 | M2-03 | |
| M2-07 | 实现 `toy_engine/font.py` re-export | — | 薄 re-export + repo root path guard |
| M2-08 | 实现 `toy_engine/render/` 全部 | M2-01, M2-02 | 体积最大 |
| M2-09 | 实现 `toy_engine/tools_lib` + `tools/*.py` | M2-04, M2-05, M2-06 | |
| M2-10 | 端到端 smoke：mock GameFactory 跑通 tools | M2-01..09 | fish 实现前的自检 |

---

## 未决问题（Open Questions）

| # | 问题 | 来源文档 | 状态 |
|---|---|---|---|
| EQ1 | `GameLoop` 是否要内置暂停？ | [02-scene.md](02-scene.md) | 暂否决（业务自理） |
| EQ2 | 是否提供"输入插值"以适配渲染≠逻辑帧 | [03-input.md](03-input.md) | 暂否决（MVP 渲染==逻辑） |
| EQ3 | `Vec2` 是否提供 numpy 加速 | [06-geom.md](06-geom.md) | 暂否决（百级实体不需要） |
| EQ4 | `GeoCanvas` 是否做后处理 layer | [07-render.md](07-render.md) | 暂否决 |
| EQ5 | tools 是否做并行/dashboard | [08-tools.md](08-tools.md) | 暂否决 |
| EQ6 | font_utils.py 是否最终搬家到 `toy_engine/font.py` | [00-overview.md §5](00-overview.md) | 选 A（薄 re-export）；待 M2 复盘 |
| EQ7 | audio_runtime/audio_utils 是否下沉 | [00-overview.md §6](00-overview.md) | 暂不下沉，待第二个游戏出现再评 |

> fish-doc Q6（Scene/System 抽象）已**关闭**：决议见 [02-scene.md §1](02-scene.md)，并已同步到 [fish-doc progress.md](../../fish-doc/mvp/progress.md)。

---

## 与 fish 的接口契约状态

逐项回应 [fish-doc progress.md "接口假设清单"](../../fish-doc/mvp/progress.md)，详见 [00-overview.md §4](00-overview.md)。

变更摘要（已同步登记到 fish-doc）：

1. **`Scene` / `System` 不下沉** —— 改为可选的 `GameLoop`，fish 直接持有 `World`（满足 `Steppable` 协议）即可
2. **新增隐含约束**：`World.snapshot()` 必须暴露 `player_pos: tuple[float, float]`（供 `KeyboardMouseInput` 计算方向；详见 [03-input.md §4.1](03-input.md)）
3. **新增隐含约束**：`World.snapshot_hash() -> str` 用于 `--determinism-check`（详见 [08-tools.md §5](08-tools.md)）
4. **新增引擎对外类**：`InputFrame`、`BotInputBase`、`Recording`、`GameLoop`、`Palette`、`ParticleSystem`、`ScreenShake`、`AABB`（属于"在 fish-doc 假设之外但合理的扩展"，不破坏既有契约；原列的 `RunInfo` 已在契约 #8 中废弃）
5. **契约 #5 新增导出完整清单**：`InputFrame`, `BotInputBase`, `Recording`, `GameLoop`, `Palette`, `ParticleSystem`, `ScreenShake`, `AABB`, `aabb_overlap`, `wrap_angle`, `angle_lerp`, `smoothstep`, `lerp_vec`, `circle_circle_penetration`, `toy_engine.font.load_font`, `toy_engine.tools_lib.GameFactory`（原列的 `RunInfo` 已在契约 #8 metrics 重写中废弃）

---

## 工作日志

| 时间 | 角色 | 动作 | 备注 |
|---|---|---|---|
| 2026-04-27 | Claude subagent | 完成 M1 全部 11 篇文档；Q6 决议为"不做 ECS，做 GameLoop"；字体选方案 A；音频暂不下沉 | 等待主会话批准并安排 M2 |
