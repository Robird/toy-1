# 07 — 工程化测试脚手架（Test Harness）

> 父文档：[00-overview.md](00-overview.md) ｜ **本文档优先级 P0，是项目地基**

## 0. 为什么这是地基

LLM Agent 不能"凭手感"调游戏，因此必须把"好不好玩"翻译成**可重复实验**：

1. 同输入永远出同结果（seeded RNG）
2. 输入可录制可回放（recorder）
3. 不开窗口也能跑（headless）
4. 自动化数值评估（metrics + bot）
5. 参数批量扫描（sweep）

**不先把这套打底，后面所有调参都是猜。**

## 1. SeededRng

```python
class SeededRng:
    def __init__(self, seed: int): ...
    def random(self) -> float: ...        # [0, 1)
    def uniform(self, a, b) -> float: ...
    def randint(self, a, b) -> int: ...
    def choice(self, seq): ...
    def gauss(self, mu, sigma) -> float: ...
    def spawn(self, name: str) -> "SeededRng":  # 派生命名空间子流（基于 hash(seed, name)）
```

**禁止**任何业务代码使用 `random.*` 或 `numpy.random` 全局函数。

## 2. World 的纯函数性

- `World.step(dt: float, input_frame: InputFrame) -> None`
- 不读系统时间（用累积 sim_time）
- 不写文件、不打日志（日志走 `MetricsCollector` 接口）
- 不直接画画（渲染从 `world.snapshot()` 读快照）

## 3. Recorder（录像）

```python
class Recorder:
    def __init__(self, level_config, seed=None): ...
    def record(self, frame_idx: int, input_frame: InputFrame): ...
    def save(self, path: str, gzip: bool | None = None): ...

    @classmethod
    def load(cls, path: str) -> "Recording": ...

# Recording 是引擎暴露的 dataclass（toy_engine.recorder.Recording），
# 含 config / seed / config_hash / engine_version / frames(list[InputFrame]) 等字段。
# 详细 schema 与 gzip/魔数识别见 toy-engine/mvp/04-recorder.md。
```

存储格式：JSON（gzip 可选）。**只录输入，不录状态**——回放靠确定性。

**权威格式定义见 [`toy-engine/mvp/04-recorder.md`](../../toy-engine/mvp/04-recorder.md)，本文档仅给出业务调用要点。**

## 4. ReplayInput

读录像后实现 `InputSource.poll`，按帧返回 `InputFrame`。`tools/replay.py` 命令行：

```
python tools/replay.py path/to/recording.json [--render | --headless] [--speed N]
```

## 5. BotInput（启发式自动玩家）

> **实现位置**：具体启发式实现位于 `fish/ai/bot_player.py`，继承 `toy_engine.input.BotInputBase`（见 [契约变更 #4](progress.md#与-toy-engine-的接口假设清单)）。

行为伪代码：

```
input.poll(state):
    threats = [e for e in state.entities
               if e.tier > player.tier and dist(e, player) < danger_radius]
    if threats:
        return flee_direction(threats)        # 朝威胁的合矢量反方向
    prey = nearest(e for e in state.entities if e.tier <= player.tier)
    if prey:
        return normalize(prey.pos - player.pos)
    return None                                # 待命
```

参数：

```
danger_radius      = 120 px (随玩家 Tier 调整)
flee_weight        > prey_weight    威胁优先
boss_special:      Boss 始终视为最高威胁，但 Tier=4 后转为追击目标（仅尾部接近：调整目标点为 boss.tail_pos）
```

> Bot 不要写得太聪明——它的目的是**测平衡**，不是给玩家秀操作。

## 6. MetricsCollector（5 大核心指标）

每局结束输出 JSON：

```json
{
  "seed": 12345,
  "difficulty": 0.5,
  "result": "VICTORY|DEAD|TIMEOUT",
  "duration_s": 87.3,
  "player_max_tier": 4,
  "metrics": {
    "fail_rate":          null,        // 仅在批量跑时有意义（脚本聚合）
    "first_growth_time":  6.4,         // 升到 Tier 1 的时间
    "starvation_ratio":   0.08,        // 视野 120 px 内无可吃目标的时间占比
    "near_miss_count":    11,          // 与 tier>self 实体距离 < 60 px 的事件数
    "boss_ttk":           14.2         // 进入 PHASE_BOSS 到 Boss 死亡/玩家死亡的耗时
  },
  "death_cause": "Barracuda" | "Boss_charge" | "Boss_face" | null
}
```

**目标区间**（v1 验收基准）：

| 指标 | 目标 |
|---|---|
| `fail_rate`（聚合） | 30% ~ 60% |
| `first_growth_time` | 4 ~ 10s |
| `starvation_ratio` | < 0.15 |
| `boss_ttk`（VICTORY 子集） | 25 ~ 60s |
| 反杀成功率（VICTORY / 进入 BOSS 的局数） | 25% ~ 60% |

## 7. tools 脚本

| 脚本 | 用途 |
|---|---|
| `tools/run_headless.py --seed N --difficulty D` | 单局无窗口跑，输出 metrics.json |
| `tools/run_headless.py --seeds N --difficulty D --bot heuristic` | N 局批量，聚合指标 |
| `tools/param_sweep.py --difficulty 0.3,0.5,0.7 --seeds 50` | 难度扫描，输出热力图 CSV |
| `tools/replay.py recording.json [--headless] [--speed]` | 回放 |
| `tools/run_headless.py --determinism-check N` | 同 seed 跑两次，断言 state hash 一致 |

## 8. 确定性自检

CI/手工触发：跑 10 个固定种子各 60s，比对两次的 state hash 序列必须完全一致。任何破坏确定性的改动**必须在 PR 中标注**。

## DoD 验收清单

- [ ] `SeededRng.spawn` 在重命名子流时不影响其它子流的输出
- [ ] `--determinism-check` 通过（10 seeds × 2 runs，零差异）
- [ ] `run_headless --seeds 100` 在开发机 < 60s 完成
- [ ] BotInput 在 difficulty=0.5 下 fail_rate 落在 30% ~ 60%（迭代调参后达成）
- [ ] Recorder 录的 JSON 在新进程中能完整复现游戏帧序列

## 未决问题

- 是否需要把 metrics 推到 SQLite 便于历史对比？MVP **写 JSON 文件**就行。
- bot 的"聪明度档位"（low/mid/stress）是否都做？MVP 只做一档启发式，第二档作为下一轮目标。
