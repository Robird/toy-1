# toy-engine MVP — 进度追踪（活文档）

> **每次开始/结束任务都必须更新本文。** 任何 subagent 接到引擎相关任务时，先读 [00-overview.md](00-overview.md)，再读本文了解当前状态与未决问题。
>
> 兄弟项目进度：[fish-doc/mvp/progress.md](../../fish-doc/mvp/progress.md)

---

## 总体里程碑

| 里程碑 | 状态 | 说明 |
|---|---|---|
| M1 引擎设计文档（toy-engine/mvp/） | ✅ 完成 | 本轮由 Claude subagent 交付 |
| M2 引擎实现 + 单测 | ✅ 完成 | 10 步全部落地，全仓 372 passed，覆盖率 92%（rng/geom/recorder/metrics 100%） |
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

## M2 任务表

本轮采用 Claude 实现 → GPT 审阅修小问题 → 主会话独立 commit 的迭代流程。

| ID | 任务 | 状态 | 提交 | 备注 |
|---|---|---|---|---|
| M2-01 | 实现 `toy_engine/rng.py` + 单测 | ✅ | `901cdb2` | 28 测试；命名子流派生算法用 `_SPAWN_DOMAIN = b"toy_engine.SeededRng.v1\0"` 钉死字节级 |
| M2-02 | 实现 `toy_engine/geom.py` + 单测 | ✅ | `1709d76` | 42 测试；含同心兜底；纯标准库 |
| M2-03 | 实现 `toy_engine/input.py` + 单测 | ✅ | `0dbe088` | 37 测试；pygame IO 通过 monkeypatch helper 注入桩 |
| M2-04 | 实现 `toy_engine/recorder.py` + 单测 | ✅ | `f334e16` | 同步把 `ReplayInput.from_recording` 改为 `Recorder.load` 薄包装 |
| M2-05 | 实现 `toy_engine/metrics.py` + 单测 | ✅ | `3986274` | Kahan 求和；`debug=False` 默认 release（warn+drop） |
| M2-06 | 实现 `toy_engine/loop.py` + 单测 | ✅ | `d09bd0f` | 固定步长；GUI/headless 共用 `_tick_once`；零 pygame 引用 |
| M2-07 | 实现 `toy_engine/font.py` re-export | ✅ | `fe20224` | 方案 A（path hack + re-export `load_font` / `FONT_ALIASES`） |
| M2-08 | 实现 `toy_engine/render/` 全部 | ✅ | `cd231d7` | `GeoCanvas` / `Palette` / `ParticleSystem` / `ScreenShake`；像素级断言 |
| M2-09 | 实现 `toy_engine/tools_lib` + `tools/*.py` | ✅ | `c7a6838` | `GameFactory` Protocol + 三个 CLI；含 mock factory |
| M2-10 | 端到端 smoke + 覆盖率自检 | ✅ | `dbe5f71` | 6 个 subprocess e2e；总覆盖率 92%；4 个核心模块 100% |

---

## 未决问题（Open Questions）

| # | 问题 | 来源文档 | 状态 |
|---|---|---|---|
| EQ7 | audio_runtime/audio_utils 是否下沉 | [00-overview.md §6](00-overview.md) | 暂不下沉，待第二个游戏出现再评 |
| EQ12 | `GameFactory.bind_metrics` hook 已落地（可选、未列入 Protocol 本体）；fish 真接入后再确认 sink 形式（World 内部 API 是否要标准化、是否需要 detach 等）| M2-09 review 发现 | **降级**为"待 M3 fish 联调验证" |
| EQ13 | `tools/render_benchmark.py` 渲染 CPU 指标工具化缺口 | [09-mvp-scope.md §3](09-mvp-scope.md) | 延后到 M5 联合验收（手测说明或工具化） |

## 已关闭问题（Closed）

| # | 问题 | 关闭理由 |
|---|---|---|
| EQ1 | `GameLoop` 是否要内置暂停 | 共识：业务自理；MVP 不内置 |
| EQ2 | 是否提供"输入插值"以适配渲染≠逻辑帧 | 共识：MVP 渲染==逻辑，不做 |
| EQ3 | `Vec2` 是否提供 numpy 加速 | 共识：百级实体不需要，纯标准库已达性能预算 |
| EQ4 | `GeoCanvas` 是否做后处理 layer | 共识：MVP 不做 |
| EQ5 | tools 是否做并行/dashboard | 共识：MVP 单进程 100 局 < 60s 已满足 |
| EQ6 | font_utils.py 是否最终搬家到 `toy_engine/font.py` | 选定方案 A（薄 re-export）；M2-08 render 落地未触发清理需求 |
| EQ8 | 03-input.md / 04-recorder.md 关于 `meta.duration_frames` 的文档冲突 | 批次 B 已修 03-input.md §4.2：`from_recording` 是 `Recorder.load` 的薄包装，缺失 `duration_frames` 由 `Recorder.load` 抛 `ValueError`；与实现一致 |
| EQ9 | `MetricsCollector(debug=...)` 与 sample schema (`{t,v}`) 未文档化 | 批次 B 已修 05-metrics.md §1.1/§1.2/§3：`__init__` 含 `debug` 关键字、sample wire 固定 `{"t","v"}` 严格白名单、`record_event` 不带 value 不写 samples |
| EQ10 | tools 在业务 `result` 缺失时兜底 `DONE`/`TIMEOUT` 未声明 | 批次 B 已修 08-tools.md §3.1/§3.2：明确兜底规则与 `DONE` 不进 *_rate 桶 |
| EQ11 | `--force` 之前走私有 `_canonical_hash` + 临时文件 | 批次 A 落地 `Recorder.load(..., strict_hash=False)` + `ConfigDriftWarning` + `Recording.file_config_hash`；批次 B 已修 04-recorder.md §1.1 + 08-tools.md §6 |
| EQ14 | `test_perf_budget_100_runs_under_2s` 在 `coverage.py` 行级追踪下超时 | 批次 A 已加 `@pytest.mark.perf` + `sys.gettrace()` skip；新增 `pytest.ini` 注册 `perf` marker；CI 跑覆盖率任务可 `-m "not perf"` deselect |

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
| 2026-04-27 | 主会话 + Claude/GPT subagent 团队 | 完成 M2 全部 10 步实现；每步 Claude 编码 + GPT 审阅 + 主会话独立 commit；全仓 372 passed，覆盖率 92%（rng/geom/recorder/metrics 4 个核心模块 100%）；新增 EQ8–EQ14 七项文档/集成遗留 | 等待 M3 fish 业务接入；提示 fish 团队优先关注 EQ12（metrics 入口）与 EQ8（duration_frames 文档对齐） |
| 2026-04-28 | 主会话 + Claude/GPT/Gemini 三方 + Claude subagent | POST-M2 共识：批次 A 落地代码（`Recorder.load(strict_hash=...)` + `ConfigDriftWarning` + `Recording.file_config_hash` 诊断字段；`tools/replay.py --force` 改走 `strict_hash=False` 并删私有 `_canonical_hash` hack；可选 `GameFactory.bind_metrics(world, metrics)` hook + `run_single_headless` 单 tick 移交业务；perf 用例加 `@pytest.mark.perf` + `sys.gettrace()` skip + 新建 `pytest.ini`；`.coverage` 入 `.gitignore`），批次 B 文档对齐（03/04/05/08 四篇）。EQ1–EQ6/EQ8/EQ9/EQ10/EQ11/EQ14 全部关闭；EQ7 / EQ13 保持 Pending；EQ12 降级为"待 M3 fish 联调验证 sink 形式"，hook 已落地 | 等待 M3 fish 接入验证 `bind_metrics` 调用形式 |
