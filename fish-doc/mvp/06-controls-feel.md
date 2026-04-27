# 06 — 操作与手感（Controls & Game Feel）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[01](01-core-loop.md) [05](05-visuals.md)

## 1. 控制方式

**主方案：鼠标跟随（默认）**
- 玩家鱼朝向鼠标位置，**不瞬移**——按 `turn_rate` 平滑转向
- 始终向鼠标所在方向以 `current_max_speed` 加速；鼠标距离玩家 < dead_zone (15px) 时减速到 0

**备用方案：WASD / 方向键**
- 与鼠标互斥；任一帧检测到键盘输入则切换为键盘模式
- 键盘模式下方向 = 8 向归一化

> 实际玩起来如果觉得鼠标"飘"，可加一个 `Shift` 短冲刺（消耗 growth）—— **MVP 暂不做**，留 hook。

## 2. 物理参数

```
PLAYER_TURN_RATE       = 6.0 rad/s     # 比 Boss 的 0.9 快得多 → 急转甩开
PLAYER_ACCEL           = 900 px/s²
PLAYER_DRAG            = 3.5            # 速度 *= exp(-drag * dt)
DEAD_ZONE              = 15 px
```

`PLAYER_MAX_SPEED[tier]` 见 [01 §2](01-core-loop.md)。

## 3. 手感强化（Game Juice）

按性价比排序，subagent 实现 5 与 6 之前不许跳到后面：

1. **拖尾**：每 0.05s 在玩家鱼尾部记录一个点，最近 12 个点用渐隐线段相连，颜色 = ROLE_PLAYER alpha 渐变
2. **形变**：玩家鱼按速度方向 squash（speed 0 → scale (1,1)，speed max → scale (1.15, 0.9)）
3. **轻微屏震**（screen shake）：吃鱼 = 1px×0.1s；Boss 蓄力 = 2px×0.2s；反杀 Boss 命中 = 6px×0.4s
4. **慢动作**：玩家死亡瞬间 dt 缩到 0.3× 持续 0.3s（仅渲染时间，逻辑步进同步缩放）
5. **吃鱼三件套**：见 [05 §6](05-visuals.md)
6. **气泡尾迹**：玩家移动时每 0.1s 在尾部生成 1 ~ 2 个气泡粒子
7. **音效 hook**（MVP 占位）：定义 `sfx.play("eat" | "bite" | "boss_charge" | "death" | "victory")` 接口，实现可空

## 4. 输入抽象（与 Headless 兼容）

```python
class InputSource:
    def poll(self, world_state) -> InputFrame: ...

@dataclass
class InputFrame:
    desired_dir: Vec2 | None   # None = 不动；归一化向量
    dash:        bool          # MVP 始终 False
```

实现：

- `KeyboardMouseInput` —— pygame 事件
- `ReplayInput` —— 读 `recorder` 的输入序列回放
- `BotInput` —— [07-test-harness.md](07-test-harness.md) 的启发式 bot

> `World.step` **只接受 InputFrame**，不直接读 pygame，从根上保证 headless 可跑。

## DoD 验收清单

- [ ] 鼠标控制下，玩家能稳定执行"急转 180° 拉开 Boss 距离"动作
- [ ] 三种 InputSource 都能驱动同一个 World 跑出确定性结果（同 seed + 同输入序列）
- [ ] 屏震不会破坏 UI 文本可读性（UI 在屏震图层之上）
- [ ] 慢动作期间逻辑步进同步缩放，结算指标仍然准确

## 未决问题

- 触控/手柄支持：MVP 不做。
- 是否需要"自动减速到 0"（松开鼠标键）？倾向 **不做**，鼠标版用 dead_zone 已够；键盘版自然为 0。
