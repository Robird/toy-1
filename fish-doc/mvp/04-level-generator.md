# 04 — 参数化关卡生成器（Level Generator）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[01](01-core-loop.md) [02](02-fish-ecosystem.md) [03](03-boss.md) [07](07-test-harness.md)

## 1. 设计哲学

> **生成"生态规则"而不是"摆鱼位置"。**

生成器的产物是一份 `LevelConfig` 数据类（确定性、可序列化），驱动 Spawner / BossAI / LevelDirector。

## 2. LevelConfig 数据结构

```python
@dataclass
class PhaseConfig:
    duration_s: float                       # 该阶段持续秒数（除 BOSS/REVENGE 由事件驱动）
    population_target: dict[int, int]       # tier -> 目标在场数量
    spawn_rate:        dict[int, float]     # tier -> 每秒最大补充
    fish_speed_mul:    float = 1.0          # 全局鱼速度倍率
    threat_aggression: float = 1.0          # Tier-4 主动追击倾向

@dataclass
class BossConfig:
    appear_time_s:    float                 # 触发 PHASE_BOSS 的时间下限（与 player.tier>=2 取或）
    sense_radius:     float
    chase_speed:      float
    turn_rate:        float
    charge_cooldown:  float
    hp:               int = 3

@dataclass
class LevelConfig:
    seed:             int
    world_size:       tuple[int, int]       # 默认 (1280, 720)
    phases: dict[Phase, PhaseConfig]        # 必含 WARMUP/PRESSURE/BOSS/REVENGE
    boss:   BossConfig
    difficulty: float                       # 0.0 ~ 1.0，仅作元信息
```

## 3. 生成器 API

```python
def generate_level(seed: int, difficulty: float = 0.5) -> LevelConfig: ...
```

- 纯函数：相同 (seed, difficulty) 必出相同 LevelConfig
- 内部分两步：
  1. **采样**：用 SeededRng 从合理区间内采各项参数
  2. **校验**（见 §5）：跑硬约束检查，不通过则**重采**最多 N 次，超 N 次则降难度兜底

## 4. 难度梯度（三段式 + 段内随机）

| 阶段 | 触发 | 典型时长 | 关键特征 |
|---|---|---|---|
| WARMUP | 关卡开始 | 12 ~ 18s | 仅 Tier-1 Minnow 大量在场；无 Tier-3/4；玩家轻松升到 Tier 1~2 |
| PRESSURE | WARMUP 结束 | 15 ~ 25s | 引入 Tier-2/3，少量 Tier-4 Barracuda（密度低）；目标让玩家升到 Tier 3 |
| BOSS | 时间到 `boss_appear_time` 或 player.tier ≥ 2 | 直到 VICTORY/DEAD | Boss 进场；普通鱼维持中密度；威胁鱼下调让玩家专注躲 Boss + 升级 |
| REVENGE | player.tier 升到 4 | 直到 VICTORY/DEAD | Boss 转可吃；普通鱼刷新降低，画面让位给追逐戏 |

**段内随机化**：`duration_s`、`population_target`、`spawn_rate` 在表中区间均匀采样；段间结构（顺序、必含元素）固定，保证体感"每关都不一样但都有起承转合"。

## 5. 硬约束（生成后必须验证）

校验函数 `validate(cfg) -> list[Violation]`：

1. **可吃目标永不为零**：每个 Phase 内 `population_target[t] > 0` 至少存在一个 `t <= 玩家可达的当前最大 Tier`
2. **威胁不超量**：每个 Phase 内 `population_target[4] <= 3`（防止屏内全是大鱼）
3. **WARMUP 纯净**：`population_target[3] == 0` 且 `population_target[4] == 0`
4. **BOSS 进场时机合理**：`boss.appear_time_s ∈ [25, 60]`
5. **数值连续性**：相邻 Phase 的 `population_target` 单 Tier 差不超过 ×3，避免突变

校验失败 → 重采（带 retry counter，避免无限循环）；超过 retry 上限则按 `difficulty` 套用兜底模板。

## 6. 生成器与 bot 跑分的协同

- 命令行 `python tools/param_sweep.py --seeds 100 --difficulty 0.3,0.5,0.7` 会：
  1. 对每个 (seed, diff) 调 `generate_level`
  2. 跑 [07-test-harness.md](07-test-harness.md) 的 bot
  3. 输出每关 5 大指标 + 是否落在合格区间
  4. 把不合格的 seed 写入 `tools/blacklist.json`，玩家模式开局自动跳过

## 7. 命名空间随机数

生成器**禁止**使用全局 random，必须接受外部传入的 SeededRng 派生子流：

```python
rng = SeededRng(seed)
phase_rng = rng.spawn("phases")
boss_rng  = rng.spawn("boss")
```

理由：将来调整 Boss 采样范围不会破坏旧种子的 Phase 采样结果（指标对比有意义）。

## DoD 验收清单

- [ ] `generate_level(seed, diff)` 是纯函数（同入参 → 同出参）
- [ ] 100 个随机种子下 `validate` 一次通过率 ≥ 80%
- [ ] 三段式参数差异在 metrics 上能体现：WARMUP 死亡率近 0、PRESSURE 死亡率最高、BOSS 通关率呈钟形
- [ ] LevelConfig 可 `json.dumps` 序列化（用于录像与回放）

## 未决问题

- 是否引入"洋流方向场"作为 Phase 参数？倾向 **MVP 不做**，预留接口。
- difficulty 是否暴露给玩家选择？MVP 简化为只有"标准难度"（diff=0.5），其余靠 sweep 验证内部健康。
