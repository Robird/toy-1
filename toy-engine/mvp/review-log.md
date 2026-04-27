# toy-engine/mvp/ 设计文档审阅日志

> 由调度（主会话）维护。每位 reviewer subagent 在审阅完一篇文档后，**追加**自己的发现到本文。**不要**删除历史条目。

## 状态图例

- `Severity`: `trivial`（typo/坏链/明显笔误） | `minor`（措辞/小遗漏/可立即决定的小补充） | `major`（API/架构/跨文档影响/性能或确定性陷阱）
- `Status`: `fixed-by-reviewer` | `open-trivial` | `open-minor` | `open-major` | `resolved` | `wontfix`

## 审阅轮次

- **R1**：2026-04-27，9 个 GPT subagent 并行审阅 00–08
- **R2**：（待 R1 完成）主会话分诊 + 派活
- **R3**：（如必要）轻量复审

---

## Findings 表

| # | Doc | Reviewer | Severity | Status | 简述 | 提案 / 修复说明 |
|---|---|---|---|---|---|---|
| R1-1 | 00-overview | GPT | trivial-minor (6条) | resolved | reviewer 自行修复 contract 索引 / 模块图 / 字体 path / Recording 术语等 | 见 review-log R1 原始汇报 |
| R1-2 | 00-overview | GPT | minor x2 | resolved-by-r2 | progress.md 契约摘要漏第 5 项 / font.py 备注口径 | R2 任务 T5 |
| R1-3 | 01-rng | GPT | minor x6 + info | resolved | 删 shuffle / 明确 spawn 语义 / 固定 BLAKE2b 实现 / 边界行为 / 禁用全局 RNG 方式 | reviewer 全部自行修复 |
| R1-4 | 02-scene | GPT | minor x6 + trivial | resolved | Q6 反例条件 / Steppable 契约 / GameLoop 伪代码 / 时间源 / 渲染注入边界 | reviewer 全部自行修复 |
| R1-5 | 03-input | GPT | minor x5 | resolved | InputFrame 字段 / poll 幂等 / KeyboardMouse 细节 / Replay 边界 / BotInputBase 骨架 / DoD | reviewer 自行修复 |
| R1-6 | 03-input | GPT | major | resolved-by-r2 | desired_dir 类型 fish=Vec2 vs engine=tuple 不一致 | R2 任务 T1（裁决：保持 Vec2） |
| R1-7 | 03-input → 04-recorder | GPT | major | resolved-by-r1 | 04 中 extra 字段冲突 | reviewer 04 自己修了 04 |
| R1-8 | 04-recorder | GPT | minor x9 | resolved | JSON schema / 帧字段对齐 / gzip 魔数 / config_hash 算法 / 稀疏帧展开等 | reviewer 自行修复 |
| R1-9 | 04-recorder | GPT | major | resolved-by-r2 | fish-doc/07 §3 旧式 load()->tuple 与新 Recording 不符 | R2 任务 T2（更新 fish-doc/07 §3） |
| R1-10 | 05-metrics | GPT | minor x3 | resolved | 业务接入点 / 引擎与 fish 5 大指标边界 / Python 序列化与浮点陷阱 / DoD | reviewer 自行修复 |
| R1-11 | 05-metrics | GPT | major x3 | resolved | API 名 + JSON envelope + 字段归属与 fish-doc/07 §6 严重漂移 | 方案 A 实施完成（Claude, 2026-04-27）：05-metrics 重写、02/08 微调、契约 #8 登记 |
| R1-12 | 06-geom | GPT | minor x7 | resolved | 契约 #5 完整性 / 角度工具 / Vec2 设计 / 圆碰撞返回语义 / 数值稳健性 / 连续碰撞登记 | reviewer 自行修复 |
| R1-13 | 06-geom | GPT | major | resolved-by-r2 | 新增 4 个 API 未同步契约登记 | R2 任务 T4（追加契约 #7） |
| R1-14 | 07-render | GPT | minor x5 | resolved | GeoCanvas 原语完整性 / ScreenShake 签名 / ParticleSystem / 视差归属 / 慢动作与性能陷阱 / DoD | reviewer 自行修复 |
| R1-15 | 08-tools | GPT | minor x6 | resolved | CLI 一致性 / GameFactory 注册 / bot 名映射 / determinism-check 诊断 / metrics.json 路径 / replay --speed 不改 dt | reviewer 自行修复 |
| R1-16 | 09-mvp-scope | GPT | minor x5 + trivial | resolved | 与 fish 验收映射 / DoD 不过度承诺 / 工件清单 / 不做清单 / Checklist | reviewer 自行修复 |
| R1-17 | 09-mvp-scope | GPT | major | accepted | 渲染 CPU 指标无现成脚本 | 已接受为人工 benchmark + 联合验收记录方式 |

---

## 收尾结论

> **R1 总结（2026-04-27）**：9 篇文档由 9 位 GPT reviewer 并行审阅，共发现 60+ 条 findings，其中 ~85% 由 reviewer 自行修复（trivial / minor）；剩余 5 项 open major 中：4 项由 R2 简单修订包（本次）处理（A/C/D/F + bot 注释），1 项（metrics schema）由 Claude 出反方案 → 主会话裁决 → 另派 subagent 实施。1 项 major（渲染 CPU benchmark 工具化）已接受为可控缺口，转人工 benchmark + 联合验收记录方式。
>
> **后续 R3**：仅在 metrics 重写完成后做轻量复审（聚焦 metrics 与其消费方 02/08 的一致性）。
