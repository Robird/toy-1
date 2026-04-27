# 09 — 引擎 MVP 验收（Definition of Done）

> 父文档：[00-overview.md](00-overview.md) ｜ 对应 fish 的 [fish-doc 08](../../fish-doc/mvp/08-mvp-scope.md)

## 1. 引擎 MVP 完成的定义

> **fish 项目能仅依赖 `toy_engine` + pygame + 标准库，跑通游戏全链路（GUI 玩 + headless 跑分 + 录像回放 + 确定性自检）。**

引擎自身不能"独立游玩"；其 MVP = "引擎提供足够支撑，让 fish 能完成 [fish-doc 08 §6 验收 Checklist](../../fish-doc/mvp/08-mvp-scope.md)"。fish 的数值平衡、Boss 规则与视觉内容仍由 fish 负责，不作为 engine-only DoD。

## 2. 模块级 DoD 总表

每个 ☑ 都来自对应文档的 `## DoD 验收清单` 末尾，本表只做索引。

| 模块 | 文档 | 关键验收 |
|---|---|---|
| RNG | [01-rng.md](01-rng.md) | 同 seed 跨进程一致；`spawn` 子流独立 |
| GameLoop | [02-scene.md](02-scene.md) | GUI/headless 同一份代码；不绑定 `Scene` 基类 |
| Input | [03-input.md](03-input.md) | 三种 source 可互换；`InputFrame` JSON 友好 |
| Recorder | [04-recorder.md](04-recorder.md) | 录像跨进程逐帧重放一致；ConfigDrift 可检测 |
| Metrics | [05-metrics.md](05-metrics.md) | tick/event/finish 完备；时间加权聚合精确 |
| geom | [06-geom.md](06-geom.md) | Vec2/circle 边界条件覆盖 |
| GeoCanvas | [07-render.md](07-render.md) | offscreen 可用；零内置颜色常量；性能达标 |
| tools | [08-tools.md](08-tools.md) | run_headless / param_sweep / replay / determinism-check 全跑通 |

## 3. 与 fish-doc 08 验收门槛的对应

引擎需配合 fish 达成 [fish-doc 08 §2](../../fish-doc/mvp/08-mvp-scope.md) 的全部客观门槛；下表同时标明工具入口与责任边界：

| fish 验收门槛 | 可执行入口 | 引擎支撑 / 责任边界 |
|---|---|---|
| `--determinism-check` 必须通过 | `tools/run_headless.py --determinism-check 10` | `SeededRng`、固定步长 `GameLoop`、`World.snapshot_hash()` hook；hash 内容由 fish 实现 |
| Bot fail_rate 30% ~ 70% | `tools/run_headless.py --seeds 100 --difficulty 0.5 --bot heuristic` | `InputSource` / bot 注入、批量聚合；目标区间靠 fish bot 与关卡调参达成 |
| 进入 PHASE_BOSS 的局数占比 ≥ 90% | 同上 | `MetricsCollector` event/gauge 与 tools 聚合；PHASE_BOSS 语义由 fish 事件定义 |
| 反杀成功率（仅含进入 BOSS 的局）20% ~ 70% | 同上 | tools 只聚合 `result` / 事件；Boss 尾部判定、连击规则与调参由 fish 负责 |
| 平均 `starvation_ratio` < 0.20 | 同上 | `MetricsCollector.tick()` 时间加权均值；"视野内无可吃"判定由 fish 负责 |
| 单局 headless 平均耗时 < 0.5s | 同上输出的 `wall_time_s.mean_per_run` | `run_headless` / `GameLoop` / metrics 不做 IO 和 display；fish World 热路径仍需自测 |
| 60 FPS 渲染 100 鱼 + Boss + 粒子，CPU < 40% | **当前无 tools 脚本直接产出** | `GeoCanvas` 缓存、`ParticleSystem` 容量上限提供支撑；这是本轮登记的验收工具化缺口，建议后续补 `tools/render_benchmark.py` 或在 fish 联合验收中写明手测机器与方法 |

除渲染 CPU 指标外，fish-doc 08 §2 的客观指标都应能由 `tools/run_headless.py` 的批量 JSON / `tools/param_sweep.py` 的 CSV 直接读出。引擎**不**对数值目标本身负责，只负责让指标可稳定采集、聚合和复现。

## 4. 工件清单

```
toy_engine/                  # 实现包
toy-engine/mvp/              # 本套 11 篇文档（活文档：progress.md）
tools/run_headless.py
tools/param_sweep.py
tools/replay.py
tests/                       # pytest 单测，覆盖 RNG/geom/recorder/metrics/loop
                             # render 走可选离屏测试（CI 装 SDL dummy 即可）
requirements.txt 已含 pygame；引擎不新增依赖
```

## 5. 明确**不做**

本节只列 engine 不做项；fish-doc 08 §4 的多 Boss、存档、排行榜、移动端等业务/产品范围由 fish 自己约束，引擎不重复承诺，也不提供对应专用框架。

- 不做 Scene/System/ECS（[02-scene.md](02-scene.md)）
- 不做物理引擎（仅圆碰撞原语）
- 不下沉音频
- 不下沉位图加载
- 不下沉 fish 的具体颜色常量、视觉绘制（鱼/Boss）
- 不做 dashboard / GUI 调参工具
- 不做并行 / 多进程 / 网络

## 6. 阶段路线图

```
M1  引擎设计文档（toy-engine/mvp/）        ← 当前（本轮交付）
M2  引擎实现（按 11 篇文档逐模块落地 + 单测）
M3  fish 业务实现（依赖已实现的引擎）
M4  联调 + bot 跑分调参 + 视觉打磨
M5  fish + engine 联合验收（按 fish-doc 08 §6）
```

## 7. 引擎自身验收 Checklist（最终一票否决）

- [ ] 11 篇 M1 文档齐备且互相链接闭合
- [ ] 与 fish-doc 接口契约偏离的项已全部登记到 [fish-doc progress.md 变更登记区](../../fish-doc/mvp/progress.md)
- [ ] 各模块 DoD 全部勾选
- [ ] `tests/` 单测覆盖率 > 80%（geom/rng/recorder/metrics 必须 100%）
- [ ] `tools/run_headless.py --determinism-check 10` 退出码 0（前提：fish 已实现）
- [ ] `tools/run_headless.py --seeds 100 --difficulty 0.5 --bot heuristic` 能产出 §3 除渲染 CPU 外的客观指标字段
- [ ] 渲染 CPU 指标若仍无脚本，联合验收记录中必须写明手测机器、方法与结果；若补脚本，则回填 §3 的可执行入口
- [ ] 引擎包**零**新增第三方依赖（除 pygame 与标准库）

> 全部勾选 ⇒ 引擎 MVP 完成。

## DoD 验收清单

- [ ] §2 表中每个模块的 DoD 链接均有效
- [ ] §3 的 fish 门槛逐条都能找到引擎支撑点
- [ ] §5 的"不做清单"与 [00-overview.md §2.2](00-overview.md) 一致

## 未决问题

- 是否需要 benchmark 套件（pytest-benchmark）？MVP **不做**——性能门槛靠 fish 联调时手测。
- 是否做"engine 0.1.0 → 0.2.0 升级指南"？现在没有用户，**不做**。
