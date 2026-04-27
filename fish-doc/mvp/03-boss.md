# 03 — Boss 战（Leviathan）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[01](01-core-loop.md) [04](04-level-generator.md) [05](05-visuals.md)

## 1. 设计意图

> **Boss 不是"很难打的怪"，而是"不断逼近的倒计时"。**

它的存在让"吃小鱼"这件事获得方向感和紧迫感。视觉上 Boss 必须够大、够明显、够"压迫"。

## 2. 进场与离场

- 触发条件（满足任一即进入 `PHASE_BOSS`）：
  - 关卡时间到达 `boss_appear_time`（生成器配置，建议 25 ~ 40s）
  - 玩家 Tier 升至 ≥ 2
- 进场表现（关键，避免"偷袭"不公平感）：
  1. 屏幕边缘渐显暗红 vignette（持续 3s）
  2. Boss 从距离玩家最远的世界边缘游入
  3. 远处剪影由小渐大（前 3s 不参与碰撞）
- 离场：仅在 `VICTORY` 或 `DEAD` 时

## 3. Boss 状态机（BossAI）

```
PATROL                慢速绕场 8s（首次进场后强制）
  │ player 进入 sense_radius
  ▼
CHASE                 直线追击玩家
  │ 距离 < charge_trigger_dist 且冷却就绪
  ▼
CHARGE_WINDUP         蓄力 0.8s（眼睛变红，身体后缩，速度=0）
  │ 蓄力结束
  ▼
CHARGE                冲刺 1.5s，速度 = chase_speed * 1.6，方向锁定蓄力时刻
  │ 撞墙 / 撞 Boss / 时间到
  ▼
STUNNED               僵直 2s （**反杀关键窗口**）
  │ 僵直结束
  ▼
CHASE                 ...

ENRAGED               血量 < 30% 时叠加：感知半径 +30%，CHARGE 冷却 -40%
```

参数初值：

```
sense_radius        = 380 px
chase_speed         = 130 px/s        # 略低于玩家 Tier-3 的 245
turn_rate           = 0.9 rad/s       # 比玩家慢得多 → 急转可甩开
charge_trigger_dist = 220 px
charge_cooldown     = 9 s
hp                  = 3               # 玩家咬一口扣 1
```

## 4. 玩家与 Boss 的交互规则

设玩家 Tier = `pt`，Boss 状态为 `bs`：

| 条件 | 结果 |
|---|---|
| 任意状态 + `pt < 4` + 任意接触 | 玩家死亡（DEAD） |
| `pt == 4` + `bs != STUNNED` + 玩家从 Boss **正面 120°** 接触 | 玩家被反咬死 |
| `pt == 4` + 玩家从 Boss **尾部 240°** 接触 | Boss `hp -= 1`，玩家短暂无敌 0.5s + 屏震 + 粒子，Boss 进入 STUNNED |
| `pt == 4` + `bs == STUNNED` + 任意接触 | Boss `hp -= 1`，玩家无敌 0.5s |
| `Boss.hp <= 0` | GameResult = VICTORY |

> "尾部 240°"判定：玩家位置相对 Boss 朝向角的夹角 > 60°（即玩家在 Boss 后方扇形内）。

## 5. 玩家"够大"提示（公平性关键）

`pt` 升到 4 的瞬间触发：

- 玩家鱼描边变金色 + 持续脉冲发光
- 屏幕顶端短提示：**"Now you can bite the Leviathan!"**（持续 3s 后淡出）
- Boss 颜色由深紫 → 暗红，表示进入"可被反杀"语义
- 进入 `PHASE_REVENGE`（Spawner 减少新鱼刷新，让画面专注于追逐）

## 6. Boss 视觉

- 整体 silhouette：占屏幕短边 ~25% 的不规则深色椭圆轮廓
- 双发光眼（黄→红，跟状态切换）
- 缓慢张合的嘴巴弧线（每 1.5s 一次）
- 蓄力时眼睛变红 + 身后出现箭头粒子指示冲刺方向
- 僵直时身体倾斜 + 头顶冒星星（统一粒子）

## DoD 验收清单

- [ ] BossAI 完整实现 5 个状态 + 转移条件
- [ ] 进场前 3s 无碰撞、有清晰视觉警示
- [ ] 玩家 Tier=4 之前任何接触都死，Tier=4 之后正面接触必死、尾部安全
- [ ] Boss STUNNED 期间玩家可稳定咬到 1 次（不会因为弹开而漏判）
- [ ] bot 测试中，反杀成功率 ∈ [25%, 60%]（过高=无脑，过低=挫败）

## 未决问题

- 是否给玩家"每咬一次自身缩水一档"的代价？会让反杀更紧张但难度陡增——MVP 倾向**不做**。
- Boss 撞普通鱼时鱼是否被吃？倾向 **是**，且不计入玩家成长，纯视觉震撼。
