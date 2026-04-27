# 02 — 鱼群生态（Fish Ecosystem）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[01](01-core-loop.md) [04](04-level-generator.md) [05](05-visuals.md)

## 1. 鱼的种类（按 Tier 划分，MVP 共 4 类普通鱼）

| Class | Tier | 体长 px | 速度 px/s | 行为 | 颜色角色（见 05） |
|---|---|---|---|---|---|
| Minnow（白鲦） | 1 | 8 | 70 | 成群（boid） | ROLE_PREY |
| Sardine（沙丁） | 2 | 14 | 95 | 弱成群 + 见到大鱼逃 | ROLE_PREY |
| Snapper（鲷鱼） | 3 | 22 | 110 | 单独 + 弱追击玩家若 player.tier < 3 | ROLE_PEER |
| Barracuda（梭鱼） | 4 | 36 | 130（追击时 160） | 主动追击玩家若 player.tier < 4 | ROLE_THREAT |

> Tier 0 = 玩家初始，无 NPC。Boss 单列（见 [03](03-boss.md)）。
> 上述数值是**起点**，由 bot 跑分调整。

## 2. 鱼的状态机（统一的轻量 FSM）

```
WANDER → FLEE     当感知到 tier > self 的实体进入 flee_radius
WANDER → CHASE    当 (self.aggression == True) 且 player.tier < self.tier - 1
FLEE   → WANDER   当威胁离开 flee_radius * 1.5
CHASE  → WANDER   当目标超出 chase_radius
```

- 所有鱼共用此 FSM，差异通过参数表达：
  ```
  FishParams(tier, max_speed, turn_rate, perception_radius, flee_radius,
             chase_radius, aggression, school_weight)
  ```
- `school_weight > 0` 启用简化 boid（仅对**同种**鱼）：分离 + 对齐 + 聚合，权重经验值见实现注释

## 3. 移动模型（统一）

- 二维点 + 速度向量
- 转向受 `turn_rate (rad/s)` 限制（避免瞬间 180°）
- 边界处理：碰世界边缘 → 反射 + 速度衰减 0.7
- 鱼之间**不做硬碰撞**（仅玩家与鱼、Boss 与鱼/玩家做碰撞）以免群体卡死

## 4. 刷新（Spawner）

- 由 [04 关卡生成器](04-level-generator.md) 决定**目标种群分布**：
  ```
  population_target: dict[tier -> int]    # 当前阶段每类鱼的目标在场数量
  spawn_rate:       dict[tier -> float]   # 每秒补充上限
  ```
- Spawner 每 0.5s 检查实际数量，按需在**屏幕外缘**生成（避免在玩家眼前凭空出现）
- **硬约束**（生成器层面已保证，spawner 兜底）：
  - 任意时刻屏内 `count(tier <= player.tier) >= 1`，否则强制就近 spawn 一条 `tier == player.tier` 的猎物
  - Tier-4 Barracuda 在 `PHASE_WARMUP` 阶段绝不出现

## 5. 鱼的视觉模板（与 05 协调）

每条鱼用 5 个几何图元拼出（详见 [05](05-visuals.md)）：

```
[椭圆身体（径向渐变：背深腹浅）]
[三角尾巴（按 sin(t * tail_freq) 摆动）]
[一对小三角鳍（半透明）]
[白圆 + 黑点 = 眼睛]
[一道高光弧线（白色低透明）]
```

不同 Tier 通过**整体缩放 + 配色 + 尾巴比例**区分。Subagent 实现时不要给每个 Tier 画独立 asset，必须共用模板函数。

## DoD 验收清单

- [ ] 4 类鱼用同一个 `Fish` 类 + 不同 `FishParams` 实现
- [ ] FSM 切换在边界种子下不抖动（不会每帧反复切 FLEE/WANDER）
- [ ] 不存在"屏内 0 可吃目标超过 3 秒"的事件（由 metrics 验证）
- [ ] Boid 在 100 条同种鱼下仍 < 2ms/帧（headless 实测）

## 未决问题

- 是否需要"营养鱼"（吃一条顶 5 条的稀有鱼）来制造记忆点？倾向：**MVP 不做**，留给 v2。
- Tier-3 Snapper 是否真的应该在玩家小时主动追击？可能让前期太挫败——需 bot 实测。
