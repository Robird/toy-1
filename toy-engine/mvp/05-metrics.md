# 05 — MetricsCollector

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[fish-doc 07 §6](../../fish-doc/mvp/07-test-harness.md#6-metricscollector5-大核心指标)、[02-scene.md](02-scene.md)、[08-tools.md](08-tools.md)

## 1. 设计原则

- **引擎只提供采集与序列化框架**，**不**内置具体指标定义（5 大指标的语义属于 fish 业务，写在 [fish-doc 07 §6](../../fish-doc/mvp/07-test-harness.md#6-metricscollector5-大核心指标)）
- 单局输出**单一 JSON**，**结构严格对齐 fish-doc 07 §6 envelope**：顶层 6 个固定字段（`seed / difficulty / result / duration_s / player_max_tier / death_cause`）+ `metrics` 段（fish 5 大指标）+ 引擎附加段（`engine_version / duration_frames / events / extra`）
- 三种采集语义：
  - **scalar**：业务在任意时刻 `set_scalar(name, value)` 写入一个标量，最终原样进入 JSON（`top_level=True` 写入 envelope 顶层；否则写入 `metrics`）
  - **event**：`record_event(name, value=None)` 记录离散事件；引擎只保留 `count / first_t / last_t` 与有界 `samples`
  - **tick**：`tick(dt, gauges=None)` 推进逻辑帧；`gauges` 中的每个键做时间加权累计，最终产出 `mean / max / min / ratio_above_zero`，**这些 gauge 派生量需要业务自己 `set_scalar` 落到 fish 指标位**（引擎不替业务命名）
- 必须 **headless 友好**（无 stdout 噪声，全部走文件）
- 业务**不允许**为了新增 fish 指标而修改 `toy_engine.metrics` 源码

## 1.1 公开 API

```python
from typing import Any

class MetricsCollector:
    def __init__(self, *, sample_limit: int = 20, sample_policy: str = "first") -> None: ...

    # ---- scalar ----
    # 把一个标量写入报告。
    # top_level=True  → 写入 envelope 顶层（仅允许 fish-doc 07 §6 列出的 6 个键之一，否则 ValueError）
    # top_level=False → 写入 metrics.<name>（fish 5 大指标走这里；其余业务自定义键也走这里）
    # 同名键再次写入：后写覆盖前写，并 emit warning（warnings.warn / collector 内部 log，不打 stdout）
    # value 必须是 JSON 可序列化的标量或 None
    def set_scalar(self, name: str, value: Any, *, top_level: bool = False) -> None: ...

    # ---- event ----
    # 自动记录 sim_time / frame_idx；value 可以是 None / 标量 / dict（仅当带 value 时占用 samples 配额）
    # 同名事件聚合为 {count, first_t, last_t, samples?}
    def record_event(self, name: str, value: Any = None) -> None: ...

    # ---- tick ----
    # 每个逻辑帧调用一次（由 GameLoop.on_frame 或 World 内部触发，引擎不强制）
    # gauges 中的每个键做时间加权累计，最终产出 {mean, max, min, ratio_above_zero}
    # 实现需用 math.fsum / Kahan 累加，避免长局浮点漂移
    def tick(self, dt: float, gauges: dict[str, float] | None = None) -> None: ...

    # ---- 终局 + 输出 ----
    # finish 是 set_scalar 的便捷封装：set_scalar("result", result, top_level=True)
    # 并把 **extra 中的键按 fish-doc 07 §6 顶层白名单分流（命中 → top_level；其余 → metrics 段；未知则进 extra）
    def finish(self, result: str, **extra: Any) -> None: ...

    # 产出最终 envelope（dict）。内部会做一次 json.dumps 干跑，
    # 不可序列化字段在此处早暴露（debug 模式抛 MetricsPayloadError；release 模式丢字段并 warning）
    def final_report(self) -> dict: ...

    # 写 JSON 文件；等价于 json.dump(self.final_report(), open(path, "w"))
    def dump(self, path: str) -> None: ...

    # ---- 兼容别名（M2 实现期保留，M3 后视使用情况弃用）----
    event = record_event
    to_dict = final_report
```

> 设计要点：
> - **不再有** `RunInfo` / `__init__(run=...)`。`seed / difficulty` 由业务通过 `set_scalar(..., top_level=True)` 在开局时写入；这样引擎不需要理解"什么是一局的元数据"。
> - `set_scalar(top_level=True)` 的合法键集 = fish-doc 07 §6 envelope 顶层的 6 个字段：`{"seed", "difficulty", "result", "duration_s", "player_max_tier", "death_cause"}`。其中 `duration_s` 引擎可在 `final_report()` 内部根据 `tick` 累积自动填充（业务未显式 `set_scalar` 时）；其余 5 个由业务负责。
> - `metrics` 段的键空间**不**限制——fish 5 大指标进 `metrics`，业务自定义指标也进 `metrics`。

## 1.2 输出 JSON Schema（与 fish-doc 07 §6 对齐）

引擎默认产出（业务可在 `extra` / `record_event` value 里追加任意字段）：

```json
{
  "seed": 12345,
  "difficulty": 0.5,
  "result": "VICTORY",
  "duration_s": 87.3,
  "player_max_tier": 4,
  "death_cause": null,

  "metrics": {
    "fail_rate":          null,
    "first_growth_time":  6.4,
    "starvation_ratio":   0.08,
    "near_miss_count":    11,
    "boss_ttk":           14.2
  },

  "engine_version": "0.1.0",
  "duration_frames": 5238,
  "events": {
    "ate_fish":      { "count": 47, "first_t": 1.2, "last_t": 80.1 },
    "near_miss":     { "count": 11, "first_t": 8.4, "last_t": 79.0 },
    "phase_changed": { "count": 3,  "first_t": 0.0, "last_t": 60.5,
                       "samples": [{"t": 0.0, "v": "WARMUP"}, {"t": 30.0, "v": "BOSS"}] }
  },
  "extra": {}
}
```

### 1.2.1 字段归属表（**契约**）

| JSON 路径 | 写入入口 | 谁负责写 | 备注 |
|---|---|---|---|
| `seed` (top) | `set_scalar("seed", v, top_level=True)` | 业务（开局） | fish-doc 07 §6 顶层契约字段 |
| `difficulty` (top) | `set_scalar("difficulty", v, top_level=True)` | 业务（开局） | 同上 |
| `result` (top) | `finish(result=...)` 内部 → `set_scalar(..., top_level=True)` | 业务（终局） | 取值 fish 决定（如 `VICTORY/DEAD/TIMEOUT`），引擎不校验 |
| `duration_s` (top) | `set_scalar("duration_s", v, top_level=True)`，未显式则引擎在 `final_report()` 内用 `sum(dt)` 自动填充 | 业务可覆盖；否则引擎兜底 | 浮点秒，`tick` dt 累计 |
| `player_max_tier` (top) | `set_scalar("player_max_tier", v, top_level=True)` | 业务（终局或终局前最大值更新） | 整数，fish 业务概念 |
| `death_cause` (top) | `set_scalar("death_cause", v, top_level=True)` | 业务（终局；未死可不写或写 `None`） | fish 业务字符串 |
| `metrics.<name>` | `set_scalar(name, v, top_level=False)` | 业务 | fish 5 大指标 + 任意业务自定义标量 |
| `engine_version` | 引擎自动填 | 引擎 | 取自 `toy_engine.__version__` |
| `duration_frames` | 引擎自动填 | 引擎 | `tick` 调用次数累计 |
| `events.<name>` | `record_event(name, value=None)` | 业务 | `{count, first_t, last_t, samples?}` |
| `extra` | `finish(..., **extra)` 中未命中顶层白名单也未在 metrics 自定义键的剩余项 | 业务 | 兜底容器，不参与 fish 强约束 |

> **不在表中的顶层键**一律拒绝（`set_scalar(top_level=True)` 时 raise `ValueError`），防止业务误把 fish 指标写到顶层污染 envelope。

### 1.2.2 关于 `gauges` 的最终去向

`tick(dt, gauges={...})` 在引擎内部维护 `(weighted_sum, total_dt, min, max)`；它**不直接出现在最终 envelope**。业务有两种使用路径：

1. 派生为 fish 指标：业务在 `finish` 之前调用 `metrics.set_scalar("starvation_ratio", collector.gauge_mean("starvation"))`（或自行根据 World 状态计算）→ 进 `metrics.starvation_ratio`
2. 仅作为业务自定义统计：业务自行决定是否落库（MVP 引擎**不**在 envelope 里默认导出 `gauges` 段，避免与 `metrics` 段产生双写歧义）

> 实现可暴露 `gauge_mean / gauge_max / gauge_min / gauge_ratio_above_zero` 只读方法供业务读取；这些方法不写 envelope。

## 1.3 与 GameLoop 集成

- `GameLoop` **不**内置、**不**创建、**不**理解 `MetricsCollector`；它只负责调度 `on_frame(snapshot)`
- 业务在自己的 main 中持有 `metrics`，在 `on_frame` 闭包或 `World.step` 内部调用 `tick / record_event / set_scalar`
- 终局由业务判定（`world.is_finished()` 或业务侧状态机），随后 `metrics.finish(result=...)` + `metrics.dump(path)`
- 引擎不在 `GameLoop` 析构 / 异常路径上做"自动 dump"——异常退出时是否要写部分报告由业务决定

最小集成示例见 [02-scene.md §3](02-scene.md#3-与-fish-的对接)。

## 1.4 跨多局聚合责任

- `MetricsCollector` **只负责单局**。`fail_rate` 等"跨局指标"在单局 JSON 中**固定为 `null`**（由业务在开局时 `set_scalar("fail_rate", None)` 占位，或省略）
- 跨局聚合由 `tools/run_headless.py --seeds N` / `tools/param_sweep.py` 收齐 N 个单局 JSON 后计算，规则见 [08-tools.md §3.2 / §4](08-tools.md)
- 引擎不提供"多局合并"的 API，避免与 tools 的聚合规则双向耦合

---

## 2. 业务接入流程（fish 适配示例，非规范）

```python
from toy_engine.metrics import MetricsCollector

metrics = MetricsCollector()

# 开局：写入顶层固定字段
metrics.set_scalar("seed", seed, top_level=True)
metrics.set_scalar("difficulty", difficulty, top_level=True)
metrics.set_scalar("fail_rate", None)             # 跨局聚合位，单局占位为 None

# 帧循环（由 GameLoop.on_frame 触发）
def on_frame(state):
    metrics.tick(state.last_effective_dt, gauges={
        "starvation": 1.0 if state.no_prey_in_view else 0.0,
    })
    if state.just_grew:
        metrics.record_event("growth_tier_up", {"tier": state.player.tier})
    if state.just_near_missed:
        metrics.record_event("near_miss")

# 终局
metrics.set_scalar("starvation_ratio",
                   metrics.gauge_mean("starvation"))           # → metrics.starvation_ratio
metrics.set_scalar("near_miss_count",
                   metrics.event_count("near_miss"))           # → metrics.near_miss_count
metrics.set_scalar("first_growth_time",
                   metrics.event_first_t("growth_tier_up"))    # → metrics.first_growth_time
metrics.set_scalar("boss_ttk", boss_ttk_business_value)
metrics.set_scalar("player_max_tier", world.player.max_tier_seen, top_level=True)
metrics.set_scalar("death_cause", world.death_cause, top_level=True)
metrics.finish(result="VICTORY")                                # → 顶层 result
metrics.dump("metrics.json")
```

### 2.1 与 fish 5 大指标的对应（业务侧职责，引擎不感知）

| fish 指标 | 业务这样产生 |
|---|---|
| `first_growth_time` | `record_event("growth_tier_up", {"tier": ...})` → 终局 `set_scalar("first_growth_time", event_first_t("growth_tier_up"))` |
| `starvation_ratio` | `tick(dt, gauges={"starvation": 0/1})` → 终局 `set_scalar("starvation_ratio", gauge_mean("starvation"))` |
| `near_miss_count` | `record_event("near_miss")` → 终局 `set_scalar("near_miss_count", event_count("near_miss"))` |
| `boss_ttk` | 业务侧记录 PHASE_BOSS 进入与终局时间差 → `set_scalar("boss_ttk", ttk)` |
| `fail_rate` | 单局占位 `None`；由 [08-tools.md §3.2](08-tools.md) 跨局聚合 |

---

## 3. 关于事件 / 标量 payload 限制

- 所有写入值必须 JSON 可序列化（`int / float / str / bool / None / dict / list`）
- 不允许塞 `numpy.ndarray`、`pygame.Surface` 等非原生对象
- `Enum` 必须转为 `.name` 或 `.value`，`Path` 必须转为 `str`，dataclass 必须先转为 plain dict；collector 不隐式猜测业务对象如何展开
- 浮点值必须是有限数；`NaN` / `Infinity` 在 debug 模式抛 `MetricsPayloadError`，release 模式丢弃该字段并记录 warning（warning 走 `warnings.warn`，不打 stdout）
- **`final_report()` 内部做一次 `json.dumps` 干跑**（即使调用方不调用 `dump`），把不可序列化错误**前置**到 `final_report` 调用点，避免下游 tools 才发现

## 4. 性能预算

- 单局典型 5000 帧 × 10 events × 5 gauges → **指标采集自身 < 5ms**（headless 0.5s 总预算的 1%）
- 不做线程、不做异步；纯 Python list/dict 累计
- gauges 的时间积分保存为 `(weighted_sum, total_dt, min, max)`；实现用 `math.fsum` / Kahan 累加或等价策略，避免 `gauge_mean` 在长局漂移
- 默认不保存完整事件流：每个事件名只保存 `count / first_t / last_t` 与最多 `sample_limit` 条带 value 的 sample；`sample_policy="ring"` 时保留最近 N 条，默认 `"first"` 保留最早 N 条

## DoD 验收清单

- [ ] `tick / record_event / set_scalar / finish` 在不调用 `dump` 时不写任何文件
- [ ] gauges 时间加权平均与"逐帧手算"误差 < 1e-9
- [ ] `final_report()` 输出 dict 顶层包含且仅包含：fish-doc 07 §6 的 6 个固定字段 + `metrics` + `engine_version` + `duration_frames` + `events` + `extra`
- [ ] `set_scalar(top_level=True)` 写入非白名单键时 raise `ValueError`
- [ ] `set_scalar` 同名键覆盖时 emit warning（可被 `warnings.catch_warnings` 捕获）
- [ ] `final_report()` 内部 `json.dumps` 干跑能在调用点暴露不可序列化字段
- [ ] `dump` 输出 JSON 在 fish 的聚合脚本中可被 `json.load` 直接解析
- [ ] 单元测试：固定输入序列下 `events.<name>.count` 精确匹配
- [ ] payload 含不可序列化对象时，debug 模式抛 `MetricsPayloadError`
- [ ] 业务可在不修改 `toy_engine.metrics` 源码的情况下新增 1 个 event、1 个 gauge 与 1 个 scalar 指标，并被 `dump` 输出
- [ ] **业务侧能在不修改引擎源码的前提下完整产出 [fish-doc 07 §6](../../fish-doc/mvp/07-test-harness.md#6-metricscollector5-大核心指标) 示例 envelope（含 5 大指标 + 顶层 6 字段）**
- [ ] `Enum` / `Path` / dataclass / `NaN` / `Infinity` 的序列化行为有单元测试覆盖
- [ ] `sample_limit` 生效：10 万次同名事件不会导致 metrics 报告线性膨胀
- [ ] headless 跑 100 局指标采集开销总和 < 0.5s（开发机）
- [ ] 兼容别名 `event` / `to_dict` 在 M2 期间可用且行为与 `record_event` / `final_report` 等价

## 未决问题

- 是否要支持 SQLite 后端便于历史对比？fish-doc 07 已决议 **MVP 写 JSON 文件**，引擎与之对齐。
- gauges 是否要支持直方图（histogram bins）？MVP **不做**，需要时业务自己 `record_event` 输出后聚合。
- `to_dict` / `event` 兼容别名的弃用时机：M2 实现期保留，M3 联调结束后视调用方使用情况决定是否移除。
