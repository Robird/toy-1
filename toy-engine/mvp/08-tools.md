# 08 — tools/ 命令行框架

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[fish-doc 07 §7](../../fish-doc/mvp/07-test-harness.md)、[04-recorder.md](04-recorder.md)、[05-metrics.md](05-metrics.md)

## 1. 设计原则

- `tools/*.py` 是脚本，**不**是 `toy_engine` 包的成员；位于仓库根的 `tools/` 目录
- 引擎只提供"运行单局"的样板（`toy_engine.tools_lib`），**业务必须注入"如何构造一个 World"**——引擎不知道 fish 的 World 长什么样
- 命令行参数风格统一用 `argparse`（无新依赖）
- 输出**纯 JSON 到 stdout 或文件**，便于管道；warnings/progress/diagnostics 走 stderr；路径统一经 `pathlib.Path` 处理

## 2. 业务注入接口（`toy_engine.tools_lib`）

```python
from typing import Protocol

class GameFactory(Protocol):
    """业务必须提供的构造器。tools 通过它生成一局所需的全部对象。"""
    def make_level_config(self, *, seed: int, difficulty: float): ...
    def make_world(self, *, level_config, seed: int): ...
    def make_bot(self, *, name: str, world, rng) -> "InputSource": ...
    def serialize_config(self, level_config) -> dict: ...
    def deserialize_config(self, raw: dict): ...

# fish 在 fish/__main__.py 暴露一个 import-safe 的全局实例：
#     FISH_FACTORY: GameFactory = ...
```

### 2.1 可选 hook：`bind_metrics`

```python
class GameFactory(Protocol):
    ...
    # Optional hook（未列入 Protocol 本体以保持 isinstance / structural 向后兼容）
    def bind_metrics(self, world, metrics: "MetricsCollector") -> None: ...
```

语义：

- tools 在 `make_world(...)` 之后、`GameLoop` 启动之前，检测 factory 是否实现了 `bind_metrics`（`hasattr` 判定，不要求是 Protocol 成员）并只调用一次。仅限 **headless tools 路径**（`tools/run_headless.py` / `tools/replay.py --headless` / `tools/param_sweep.py`）；GUI 主程是否调用由业务自行决定
- **调用该 hook 即表示业务接手了 `metrics.tick(dt)` 责任**（在 `World.step` 内或 `on_frame` 闭包里逐帧调）；tools 不会再重复 tick，避免 `duration_frames` / `duration_s` 被双计
- 未实现 `bind_metrics` 的旧 factory 行为 **完全不变**：tools 自己持有 `MetricsCollector` 并逐帧 `tick`，业务拿不到它

最小示例（不规定 `World` 内部 API 形态）：

```python
class FishFactory:
    ...
    def bind_metrics(self, world, metrics):
        # 业务自选接线方式：让 World 拿到 collector、或注入 event sink
        world.attach_event_sink(metrics.record_event)
        world._metrics = metrics    # 供 World.step 内部调 tick(dt, gauges=...)
```

Factory 发现规则（按优先级）：

1. 命令行 `--factory MOD:ATTR`；例如 `--factory fish.__main__:FISH_FACTORY`
2. 环境变量 `TOY_ENGINE_GAME_FACTORY=MOD:ATTR`
3. MVP 仓库默认值 `fish.__main__:FISH_FACTORY`，用于保持 [fish-doc 07 §7](../../fish-doc/mvp/07-test-harness.md) 的命令示例不需要额外参数

`MOD:ATTR` 只用 `importlib.import_module(MOD)` + `getattr(module, ATTR)` 解析；MVP **不使用** Python packaging 的 `entry_points`。`fish.__main__` 必须保证导入无副作用（真正启动 GUI 放在 `if __name__ == "__main__"` 下）。

## 3. `tools/run_headless.py`

```
fish-doc 07 §7 的规范命令（从仓库根运行）：
  tools/run_headless.py --seed N --difficulty D
  tools/run_headless.py --seeds N --difficulty D --bot heuristic
  tools/run_headless.py --determinism-check N

通用调试可显式指定 factory：
  tools/run_headless.py --factory MOD:ATTR [选项]

选项：
  --factory MOD:ATTR       覆盖 §2 的 factory 发现规则
  --seed N                 单局，固定种子
  --seeds N                批量跑 N 局（种子从 --seed-base 起递增），输出聚合
  --seed-base N            批量起始种子（默认 0）
  --difficulty F           [0, 1] 难度参数，传给 make_level_config
  --bot NAME               使用业务侧 BotInput；fish MVP 支持 heuristic
  --max-sim-seconds F      单局最长仿真时间（默认 180s，与 fish-doc 对齐）
  --out PATH               输出 JSON 文件；PATH 为 - 时输出到 stdout
  --record-dir DIR         同时把每局的录像存到此目录（文件名 = seed_<seed>.json.gz）
  --determinism-check N    特殊模式：见 §5
  --quiet                  关闭 stderr 进度条
```

Windows / *nix 均可在上述命令前加 `python` 作为等价调用；文档中的 canonical CLI 仍以 `tools/*.py ...` 为准。

### 3.1 单局 JSON 输出

直接是 [05-metrics.md §3](05-metrics.md) 定义的格式。路径约定：

- `--seed` 单局且未传 `--out`：写当前工作目录的 `metrics.json`
- `--out PATH`：写入指定路径，父目录不存在时报错（不隐式创建多级目录，避免拼错路径）
- `--out -`：JSON 写 stdout；stderr 仍只写 warnings/progress

业务通常通过 `metrics.finish(result=...)` 写入终态。若直到运行结束业务都未写入 `result`，引擎按下列规则兑底（仅 tools 路径）：达到 `--max-sim-seconds` 且 `world.is_finished()` 为假 → `"TIMEOUT"`；否则 → `"DONE"`。`"DONE"` 是 sentinel，提示 fish 业务**应**显式覆盖；它不会进入 §3.2 的 `victory_rate / fail_rate / timeout_rate` 任一桶。

### 3.2 批量聚合 JSON 输出

```json
{
  "n_runs": 100,
  "difficulty": 0.5,
  "seeds": [0, 1, ..., 99],
  "wall_time_s": { "total": 42.1, "mean_per_run": 0.421 },
  "aggregate": {
    "fail_rate": 0.42,
    "victory_rate": 0.31,
    "timeout_rate": 0.27,
    "duration_s": { "mean": 78.4, "p50": 80.1, "p95": 142.0 },
    "metrics": {
      "first_growth_time": { "mean": 6.2, "p50": 6.0, "p95": 9.5 },
      "starvation_ratio":  { "mean": 0.09, "p50": 0.08, "p95": 0.18 },
      "near_miss_count":   { "mean": 12.3 },
      "boss_ttk":          { "mean": 32.4, "p50": 30.1, "p95": 55.0 }
    },
    "events": { "ate_fish": { "mean_count": 38.2 } }
  },
  "per_run": [
    { "seed": 0, "result": "VICTORY", "duration_s": 87.3, "metrics_path": null },
    { "seed": 1, "result": "DEAD", "duration_s": 54.8, "metrics_path": null }
  ]
}
```

聚合规则：

- 顶层字段（`result / duration_s / seed / difficulty / player_max_tier / death_cause`）路径在单局 JSON 中即顶层；`*_rate` = `count(result == X) / n_runs`
- fish 5 大指标位于单局 JSON 的 `metrics.<name>`（见 [05-metrics.md §1.2](05-metrics.md)），聚合时按 `metrics.<name>` 路径读取，输出到聚合 JSON 的 `aggregate.metrics.<name>`
- `mean / p50 / p95` 走纯 Python `statistics`，不引入 numpy
- `events.<name>` **自动**进入聚合（按名字 union），输出 `mean_count` 等
- 业务自定义 `metrics.<name>` 标量同样**自动**进入聚合（按名字 union），单局缺失视为缺失值跳过
- **`fail_rate` 是跨局聚合填充字段**：单局 JSON 中固定为 `null`（业务侧 `set_scalar("fail_rate", None)` 占位或省略），聚合时由 tools 计算后写入 `aggregate.fail_rate`
- `result == "DONE"` 的 run 不计入上述任何 *_rate（`victory_rate / fail_rate / timeout_rate`）；fish 接入完成后正常情况下不应再出现该值
- `--seeds` 未传 `--out` 时聚合 JSON 写 stdout；若传 `--out PATH` 则写入该文件

## 4. `tools/param_sweep.py`

```
fish-doc 07 §7 的规范命令：
  tools/param_sweep.py --difficulty 0.3,0.5,0.7 --seeds 50

通用调试可显式指定 factory：
  tools/param_sweep.py --factory MOD:ATTR --difficulty 0.3,0.5,0.7 --seeds 50 --out sweep.csv

输出：CSV，每行一个 difficulty；适合喂给 pandas/excel 画折线或热力图
```

字段：

固定字段（按顺序）：

```
difficulty,n_runs,seed_base,fail_rate,victory_rate,timeout_rate,entered_boss_rate,counter_kill_rate,duration_s_mean,duration_s_p50,duration_s_p95,headless_wall_s_mean,first_growth_time_mean,starvation_ratio_mean,near_miss_count_mean,boss_ttk_mean
```

业务额外指标可追加为 `extra_<name>` 列；某 difficulty 下缺失的指标留空字符串，不写 `NaN`，方便 Excel 直接打开。

> 复杂的"网格扫描"（如 difficulty × spawn_density 二维）MVP **不做**——靠用户多跑几次单维 sweep 后自己拼。

## 5. `tools/run_headless.py --determinism-check N`

特殊子命令，对应 [fish-doc 07 §8](../../fish-doc/mvp/07-test-harness.md)：

```
对 N 个固定种子（默认 seed_base..seed_base+N-1），各跑两次 60s headless：
  - 每个逻辑帧 world.step(...) 后立即调用 World.snapshot_hash()，不做抽样
  - 比对两次 hash 序列必须完全一致（长度与每帧 hash 都一致）
  - 成功：退出码 0，stdout 输出 {"ok": true, "n_seeds": N, "frames_per_run": 3600}
  - 失败：退出码 1，stderr 打印第一处不一致的完整诊断
```

失败诊断格式（单行，便于 CI grep）：

```
DETERMINISM_MISMATCH seed=7 difficulty=0.5 frame=1234 sim_t=20.5667 config_hash=ab3f... prev_a=... prev_b=... hash_a=... hash_b=...
```

若 hash 序列长度不同，使用 `DETERMINISM_LENGTH_MISMATCH`，并输出 `seed / difficulty / len_a / len_b / last_hash_a / last_hash_b`。

**对 fish/World 的硬约束**：业务必须实现 `World.snapshot_hash() -> str`（建议 `blake2b` over `(player_pos, vel, growth, all_entities_sorted_by_id)`）。该方法**不属于 InputSource 契约**，而是 `--determinism-check` 单独要求；记录在此处而非 [03-input.md](03-input.md)。

## 6. `tools/replay.py`

```
fish-doc 07 §7 的规范命令：
  tools/replay.py recording.json [--headless] [--speed F]

选项：
  --factory MOD:ATTR       覆盖 §2 的 factory 发现规则
  --render                 GUI 模式（默认）
  --headless               无窗口，只跑确定性 + 输出 metrics
  --speed F                播放速度倍率（仅 --render，默认 1.0）
  --force                  忽略 ConfigDriftError：底层调用 `Recorder.load(..., strict_hash=False)`，发 `ConfigDriftWarning` 后继续加载
  --out PATH               metrics 输出路径（仅 --headless；默认 metrics.json）
```

GUI 模式：用 `GameLoop.run_realtime`，但**不修改录制帧的逻辑 `dt`**；`speed=2` 表示按两倍速消费录像帧 / 缩短帧间等待，保证回放逻辑状态仍与原始录像逐帧一致。

## 7. 业务对接示例（fish 侧）

`fish/__main__.py` 大致：

```python
class FishFactory:
    def make_world(self, *, level_config, seed):
        return World(level_config, seed)
    def make_level_config(self, *, seed, difficulty):
        return LevelGenerator(seed=seed, difficulty=difficulty).generate()
    def make_bot(self, *, name, world, rng):
        if name == "heuristic":
            from fish.ai.bot_player import HeuristicBot
            return HeuristicBot(world.snapshot(), rng)
        raise ValueError(f"unknown bot: {name}")
    def serialize_config(self, c):   return level_config_to_dict(c)
    def deserialize_config(self, r): return level_config_from_dict(r)

FISH_FACTORY = FishFactory()
```

## 8. **不**做

- 不内置 metrics 可视化（dashboard / matplotlib）——CSV/JSON 喂给外部工具
- 不做并行/多进程（MVP 100 局 < 60s 单进程够用）
- 不做录像回归测试套件（MVP 由 `--determinism-check` 兜底）

## DoD 验收清单

- [ ] `tools/run_headless.py --seeds 100 --difficulty 0.5 --bot heuristic` 在开发机 < 60s 完成
- [ ] `tools/run_headless.py --determinism-check 10` 在固定 fish 实现下退出码 0
- [ ] `tools/param_sweep.py --difficulty 0.3,0.5,0.7 --seeds 50` 输出 CSV 行数 = 3，列集合与 §4 固定字段一致
- [ ] `tools/replay.py PATH --headless` 输出的 metrics 与原局一致
- [ ] 业务侧只需实现 `GameFactory` 协议的 5 个方法即可接入全部 3 个 tools

## 未决问题

- 是否支持 packaging `entry_points` 自动发现？MVP **不做**，只走 §2 的 import 字符串。
- 是否输出 NDJSON 流式格式以便实时观察长时间 sweep？MVP **不做**，写完一次性输出。
