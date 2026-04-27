# 05 — 视觉规范（Visuals & Art-from-Code）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[02](02-fish-ecosystem.md) [03](03-boss.md) [06](06-controls-feel.md)

## 1. 风格定位

**"程序化矢量卡通风"**：纯几何图元 + 统一调色板 + 大量动态反馈。零位图素材。
风格关键词：**深海、柔和、有呼吸感、对比清晰**。

## 2. 调色板（锁死，不许 subagent 自由发挥）

```python
PALETTE_DEEP     = (11, 29, 58)     # 背景最深
PALETTE_MID      = (21, 68, 107)    # 中景
PALETTE_SHALLOW  = (43, 140, 190)   # 浅水
PALETTE_FOAM     = (126, 200, 197)  # 浪花/海草
PALETTE_HIGHLIGHT= (232, 246, 243)  # 高光/UI

ROLE_PLAYER  = (255, 215, 0)        # 金色
ROLE_PREY    = (126, 200, 197)      # 青绿（可吃）
ROLE_PEER    = (240, 196, 25)       # 琥珀（同级紧张）
ROLE_THREAT  = (220, 80, 60)        # 红（危险）
ROLE_BOSS    = (60, 20, 80)         # 深紫（可吃后偏暗红）
```

> 鱼的具体颜色 = `ROLE_*` 主色 + HSL 色相 ±15° 抖动（同 Tier 内多样性，不破坏角色识别）。

## 3. 鱼的几何模板（统一函数）

`render.visuals.draw_fish(surf, x, y, angle, length, role_color, t)`：

```
1. 椭圆身体：长 = length，宽 = length * 0.5，按 angle 旋转
   填充：从 role_color 暗版（×0.6）到 role_color 亮版（×1.2）的纵向渐变
2. 三角尾巴：附在身体尾端，三角张角 = 60°，
   绕尾根旋转 sin(t * 6 + phase) * 18°  （摆尾动画）
3. 鳍：上下各一个半透明小三角（alpha 120），随身体一起旋转
4. 眼：白色实心圆 r=length*0.08 + 内部黑点 r*0.5；位置在身体前 1/3、上 1/4
5. 高光：身体上半部一段细弧线，alpha 80
```

**Tier 区分**仅靠 `length` 与 `role_color`，不画独立美术。

## 4. Boss 视觉

- 不调用 `draw_fish`，单独函数 `draw_boss(surf, boss_state, t)`
- 主体：3 ~ 4 段贝塞尔轮廓的不规则椭圆（生成时一次性确定形状，避免抖动）
- 双眼：直径屏短边 1.5%，颜色随状态：
  - PATROL: 黄
  - CHASE: 橙
  - CHARGE_WINDUP / CHARGE: 红 + 外发光
  - STUNNED: 灰 + 头顶 3 颗旋转星星
- 嘴：每 1.5s 张合一次，张开时露出几颗白色三角"牙"
- 身体在 PHASE_REVENGE 整体偏色 +30° 红相

## 5. 背景三层视差

| 层 | 内容 | 移动速度（相对玩家） |
|---|---|---|
| Far | `PALETTE_DEEP → PALETTE_MID` 径向渐变 + 噪声 caustics（用 `perlin` 生成的灰度图，蓝化叠加，alpha 60） | 0.1× |
| Mid | 4 ~ 6 丛贝塞尔海草，控制点 +`sin(t + x*0.01)`摆动，颜色 `PALETTE_FOAM` alpha 140 | 0.4× |
| Near | 浮游气泡粒子（白色半透明小圆，向上移动 + 左右轻微抖动 + 到顶销毁，密度 ~ 30 个/屏） | 1.0× |

**MVP 不做世界卷轴**，但视差按"玩家与屏幕中心的偏移"做小幅移动（最大偏移 30 px），制造深度感。

## 6. 反馈三件套（吃鱼瞬间，决定 80% 手感）

1. **目标 0.15s 内 scale → 0** + alpha 同步降到 0
2. **粒子四散**：6 ~ 10 个小圆，颜色 = 目标主色，向四周飞 + 重力衰减
3. **玩家鱼 squash**：scale 1.0 → 1.15 → 1.0（弹性 0.2s）

被吃（玩家死）：屏幕白闪 1 帧 → 慢动作 0.3s → 黑屏 → 结算
反杀 Boss：屏震 + 大粒子爆裂 + 短暂全屏金色 vignette

## 7. UI（极简）

- 左上：玩家 Tier 徽章（5 格进度条）+ 当前 growth / next threshold
- 右上：关卡时间 + 当前 Phase 名（小字）
- 顶部居中：事件提示文字（"Boss approaching..." / "Now you can bite!"）
- 死亡/通关：居中大字 + "Press SPACE to restart"

字体复用 `font_utils.py`。

## DoD 验收清单

- [ ] 所有颜色都来自 `palette.py` 常量，无硬编码 RGB
- [ ] `draw_fish` 一个函数能画出全部 4 类普通鱼（仅参数不同）
- [ ] 60 FPS 下 100 条鱼 + Boss + 30 气泡稳定渲染（在开发机上 CPU < 30%）
- [ ] 三层视差不卡顿；可通过 `--no-bg` flag 关掉用于性能对比

## 未决问题

- caustics 噪声是否要每帧重算？倾向**预生成静态贴图 + 缓动 UV 偏移**省 CPU。
- 海草是否参与碰撞？MVP **纯装饰**。
