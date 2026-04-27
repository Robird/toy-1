# 01 — 核心循环（Core Loop）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[02](02-fish-ecosystem.md) [03](03-boss.md) [07](07-test-harness.md)

## 1. 一局的生命周期

```
[启动]
  │
  ├─ 读取 LevelConfig（来自参数化生成器，见 04）
  ├─ 初始化 SeededRng(seed)
  ├─ 重置 World：放置 Player（屏幕中心）、初始鱼群、记录起始时间
  │
[主循环：每帧]
  ├─ 拉取 InputSource → 得到本帧期望速度方向
  ├─ World.step(DT, input)
  │     ├─ 玩家移动（带惯性，见 06）
  │     ├─ 鱼群 AI 更新（见 02）
  │     ├─ Boss 更新（见 03，仅 PHASE_BOSS/REVENGE）
  │     ├─ Spawner 按当前 Phase 刷新鱼（见 04）
  │     ├─ 碰撞与吃/被吃判定
  │     ├─ 玩家成长结算
  │     ├─ Phase 切换判定（LevelDirector）
  │     └─ 录像帧追加（Recorder）
  ├─ Renderer.draw(world.state)
  └─ 检查 GameResult：胜利 / 死亡 / 进行中
  │
[结束]
  ├─ 写出 metrics.json（headless 模式）
  └─ 显示结算（GUI 模式）
```

## 2. 玩家成长公式

成长以"成长值 growth"为内部计量，而非鱼的数量。

- 吃掉一条 `Tier=t` 的鱼，`growth += GROWTH_REWARD[t]`，参考值：`{0:1, 1:2, 2:5, 3:12, 4:30}`
- 玩家当前 Tier 由阈值表决定：

  ```
  TIER_THRESHOLDS = [0, 8, 25, 60, 150]    # 索引 = Tier，值 = 升入该 Tier 所需 growth
  ```

- 玩家**视觉半径**与 Tier 关联：`PLAYER_RADIUS[tier] = [10, 14, 20, 28, 40]` px
- **速度**随 Tier 缓增（防止小鱼无敌）：`PLAYER_MAX_SPEED[tier] = [220, 235, 245, 250, 240]` px/s
  - Tier 4 略降，让"反杀阶段"靠走位而非速度碾压

> 上述数值为**初始建议**，必须由 [07-test-harness.md](07-test-harness.md) 的 bot 跑分迭代调整。

## 3. 吃 / 被吃判定

- 碰撞模型：圆形（player.r vs entity.r），相交即触发判定
- 判定规则：

  | 自身 Tier vs 对方 Tier | 结果 |
  |---|---|
  | self > other | 吃掉对方，`growth += reward` |
  | self == other | **互相弹开**（不互伤；防止同级僵局） |
  | self < other | 被吃，**GameResult = DEAD** |

- Boss 例外：见 [03-boss.md §4](03-boss.md)（反杀阶段前 Boss 不可吃；反杀后必须从尾部接近）

## 4. GameResult 枚举

```
RUNNING        游戏进行中
DEAD           被任何 Tier > self 的实体吃掉
VICTORY        反杀 Boss 完成（Boss.hp <= 0）
TIMEOUT        到达硬上限 180s 仍未通关（用于 bot 防死循环）
```

## 5. 死亡 / 重开

- MVP：按任意键回到"新局"，**重新生成关卡**（用新种子，除非命令行指定 `--seed`）
- 不做存档、不做记分板（指标走 metrics.json）

## DoD 验收清单

- [ ] `World.step(dt, input)` 是纯逻辑、不触碰 pygame、不读全局时钟
- [ ] 同一 seed + 同一输入序列，跑两次得到同一帧序列（state hash 一致）
- [ ] 玩家在空场景从 fry 长到 giant 所需"理想吃鱼数"与上表 `TIER_THRESHOLDS` 数学吻合
- [ ] 同 Tier 碰撞触发弹开，不会互伤
- [ ] GameResult 4 种状态都能被外部读取并触发对应行为

## 未决问题

- 是否引入"饥饿衰减"（每秒 growth 微减）以避免玩家躲角落不动？倾向：**MVP 不做**，靠 Boss 压迫已足。
- 同 Tier 弹开的力度系数（影响是否会卡死）——留给手感调参。
