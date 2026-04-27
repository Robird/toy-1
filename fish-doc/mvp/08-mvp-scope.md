# 08 — MVP 范围与验收（Definition of Done）

> 父文档：[00-overview.md](00-overview.md)
>
> 本文是 MVP **整体**的验收标准。每篇步骤文档有自己的 DoD，本文只关心"全部拼起来算不算完成"。

## 1. 玩家可见的 MVP 体验

**单次开机到关机的最小流程**：

```
1. 双击运行 fish/main.py（或 python -m fish）
2. 直接进入游戏（无菜单）
3. 鼠标控制玩家鱼，吃小鱼成长
4. 25 ~ 60s 内 Boss 进场，屏幕边缘暗红警示
5. 玩家继续吃鱼升到 Tier 4，描边变金，提示出现
6. 玩家从 Boss 尾部接近，连击 3 次咬死 Boss
7. VICTORY 画面 → 按空格重开（新种子新关）
8. 死亡也按空格重开
```

整局体验时间 **60 ~ 120s**。

## 2. 必须达成的客观指标（aggregate over 100 seeds, difficulty=0.5）

| 指标 | 验收门槛 |
|---|---|
| `--determinism-check` | 必须通过 |
| Bot fail_rate | 30% ~ 70% |
| 进入 PHASE_BOSS 的局数占比 | ≥ 90% |
| 反杀成功率（仅含进入 BOSS 的局） | 20% ~ 70% |
| 平均 `starvation_ratio` | < 0.20 |
| 单局 headless 平均耗时 | < 0.5s（开发机） |
| 60 FPS 渲染 100 鱼 + Boss + 粒子，CPU 占用 | < 40%（开发机） |

> **门槛比目标值宽松**：MVP 验收只要进入"能玩"区间，精调留给 v1.1。

## 3. 必须存在的工件

```
fish/                       业务代码（main 可跑）
toy-engine/                 引擎子包（被 fish 依赖）
fish-doc/mvp/               本套文档（活文档，progress 持续更新）
toy-engine/mvp/             引擎设计文档（subagent 起草）
tools/run_headless.py
tools/param_sweep.py
tools/replay.py
requirements.txt            （已有，可能新增 perlin-noise 之类）
```

## 4. 明确**不做**的清单（防止范围蔓延）

- 多 Boss、多关卡选择菜单
- 存档、排行榜、账号
- 音乐、复杂音效（仅 hook）
- 迷宫、机关、技能树（v2）
- 网络、多人
- 位图素材、字体外购
- 移动端 / 浏览器版

## 5. 阶段路线图

```
M0  设计文档（fish-doc/mvp/）           ← 当前
M1  引擎设计文档（toy-engine/mvp/）     ← 下一步，subagent 起草
M2  toy-engine 实现 + 自测              （subagent，逐文档落地）
M3  fish 业务实现                       （subagent，自底向上）
M4  联调 + bot 跑分调参 + 视觉打磨       （subagent + 人工试玩交错）
M5  MVP 验收（按 §2、§3）                完成
```

## 6. 验收 Checklist（最终一票否决）

- [ ] 文档：fish-doc + toy-engine 两套文档齐备且与代码一致
- [ ] 代码：可一行命令启动游戏 + 一行命令跑 100 局 headless
- [ ] 体验：人工连玩 5 局，至少 1 局达成 VICTORY，无明显 bug 中断
- [ ] 客观：§2 全部指标达标
- [ ] 工程：[07 §8 确定性自检](07-test-harness.md) 通过

> 全部勾选 ⇒ MVP 完成，可发起 v2 规划。
