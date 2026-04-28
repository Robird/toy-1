"""fish/config/constants.py — 所有写死的数值常量集中地。

每个常量后注释指向其权威来源文档。MVP 期间禁止在其它模块硬编码本表已有的值。
"""

from __future__ import annotations

from enum import Enum
from typing import Final


# --------------------------------------------------------------------------
# 世界与时间（见 fish-doc/mvp/00-overview.md §4.2）
# --------------------------------------------------------------------------

WORLD_W: Final[int] = 1280  # 见 fish-doc/mvp/00-overview.md §4.2
WORLD_H: Final[int] = 720   # 见 fish-doc/mvp/00-overview.md §4.2
DT: Final[float] = 1.0 / 60.0  # 见 fish-doc/mvp/00-overview.md §4.2
TIMEOUT_S: Final[float] = 180.0  # 见 fish-doc/mvp/01-core-loop.md §4 (GameResult.TIMEOUT)


# --------------------------------------------------------------------------
# Tier / 体型档位（见 fish-doc/mvp/00-overview.md §4.1）
# --------------------------------------------------------------------------

TIER_FRY: Final[int] = 0     # 见 fish-doc/mvp/00-overview.md §4.1
TIER_SMALL: Final[int] = 1   # 见 fish-doc/mvp/00-overview.md §4.1
TIER_MEDIUM: Final[int] = 2  # 见 fish-doc/mvp/00-overview.md §4.1
TIER_LARGE: Final[int] = 3   # 见 fish-doc/mvp/00-overview.md §4.1
TIER_GIANT: Final[int] = 4   # 见 fish-doc/mvp/00-overview.md §4.1（Boss 体型档位）
TIER_MAX: Final[int] = TIER_GIANT  # 见 fish-doc/mvp/00-overview.md §4.1（当前最高 Tier）


# --------------------------------------------------------------------------
# 玩家成长曲线（见 fish-doc/mvp/01-core-loop.md §2）
# --------------------------------------------------------------------------

# 索引 = Tier，值 = 升入该 Tier 所需 growth
TIER_THRESHOLDS: Final[tuple[int, ...]] = (0, 8, 25, 60, 150)
# 见 fish-doc/mvp/01-core-loop.md §2

# 吃掉一条 Tier=t 的鱼增加的 growth；索引 = 被吃鱼的 Tier
GROWTH_REWARD: Final[tuple[int, ...]] = (1, 2, 5, 12, 30)
# 见 fish-doc/mvp/01-core-loop.md §2

# 玩家视觉半径（px），索引 = Tier
PLAYER_RADIUS: Final[tuple[int, ...]] = (10, 14, 20, 28, 40)
# 见 fish-doc/mvp/01-core-loop.md §2

# 玩家最大速度（px/s），索引 = Tier；Tier 4 略降
PLAYER_MAX_SPEED: Final[tuple[int, ...]] = (220, 235, 245, 250, 240)
# 见 fish-doc/mvp/01-core-loop.md §2


# --------------------------------------------------------------------------
# 玩家手感物理参数（见 fish-doc/mvp/06-controls-feel.md §2）
# --------------------------------------------------------------------------
# 文档只给出单一数值（非 tier→table）：MVP 阶段所有 tier 共享同一组手感参数；
# 仅 PLAYER_MAX_SPEED 按 tier 索引（见上 §2 表）。

PLAYER_TURN_RATE: Final[float] = 12.0  # rad/s; 见 fish-doc/mvp/06-controls-feel.md §2
# 注：试玩反馈 #25（fish-doc/mvp/progress.md）— 原 6.0 rad/s 转弯太慢、对准
# 目标困难；提至 12.0 rad/s（约 2× / 一帧约 11.5°@60fps）以保持「易控但仍
# 有一定惯性」的手感。仅影响玩家；fish/boss 的 turn_rate 由各自常量控制。
PLAYER_ACCEL: Final[float] = 900.0     # px/s²; 见 fish-doc/mvp/06-controls-feel.md §2
PLAYER_DRAG: Final[float] = 3.5        # 1/s;  vel *= exp(-drag*dt); 见 06 §2
DEAD_ZONE: Final[float] = 15.0         # px;   见 fish-doc/mvp/06-controls-feel.md §2


# --------------------------------------------------------------------------
# 关卡阶段（见 fish-doc/mvp/00-overview.md §4.4）
# --------------------------------------------------------------------------

class Phase(Enum):
    """四个关卡阶段。名称与 fish-doc/mvp/00-overview.md §4.4 一致。"""

    WARMUP = "WARMUP"      # 见 fish-doc/mvp/00-overview.md §4.4
    PRESSURE = "PRESSURE"  # 见 fish-doc/mvp/00-overview.md §4.4
    BOSS = "BOSS"          # 见 fish-doc/mvp/00-overview.md §4.4
    REVENGE = "REVENGE"    # 见 fish-doc/mvp/00-overview.md §4.4


# --------------------------------------------------------------------------
# Boss 状态机时长 / 参数（见 fish-doc/mvp/03-boss.md §3 & §4）
# --------------------------------------------------------------------------

BOSS_PATROL_DURATION_S: Final[float] = 8.0       # 见 fish-doc/mvp/03-boss.md §3 (PATROL)
BOSS_CHARGE_WINDUP_S: Final[float] = 0.8         # 见 fish-doc/mvp/03-boss.md §3 (CHARGE_WINDUP)
BOSS_CHARGE_DURATION_S: Final[float] = 1.5       # 见 fish-doc/mvp/03-boss.md §3 (CHARGE)
BOSS_CHARGE_SPEED_MUL: Final[float] = 1.6        # 见 fish-doc/mvp/03-boss.md §3 (CHARGE)
BOSS_STUNNED_DURATION_S: Final[float] = 2.0      # 见 fish-doc/mvp/03-boss.md §3 (STUNNED)

BOSS_SENSE_RADIUS: Final[float] = 380.0          # 见 fish-doc/mvp/03-boss.md §3
BOSS_CHASE_SPEED: Final[float] = 130.0           # 见 fish-doc/mvp/03-boss.md §3
BOSS_TURN_RATE: Final[float] = 0.9               # 见 fish-doc/mvp/03-boss.md §3 (rad/s)
BOSS_CHARGE_TRIGGER_DIST: Final[float] = 220.0   # 见 fish-doc/mvp/03-boss.md §3
BOSS_CHARGE_COOLDOWN_S: Final[float] = 9.0       # 见 fish-doc/mvp/03-boss.md §3
BOSS_HP: Final[int] = 3                          # 见 fish-doc/mvp/03-boss.md §3

# ENRAGED 触发：HP 比例 < 此阈值
BOSS_ENRAGE_HP_RATIO: Final[float] = 0.30        # 见 fish-doc/mvp/03-boss.md §3 (ENRAGED)
BOSS_ENRAGED_SENSE_MUL: Final[float] = 1.30      # 见 fish-doc/mvp/03-boss.md §3
BOSS_ENRAGED_COOLDOWN_MUL: Final[float] = 0.60   # 见 fish-doc/mvp/03-boss.md §3 (-40%)

# 进场前的无碰撞渐显窗口
BOSS_INTRO_DURATION_S: Final[float] = 3.0        # 见 fish-doc/mvp/03-boss.md §2

# 玩家咬中 Boss 后的短暂无敌
PLAYER_INVULN_AFTER_BITE_S: Final[float] = 0.5   # 见 fish-doc/mvp/03-boss.md §4

# Boss 尾部安全扇区半角（度）。240° 扇区 → 半角 120°
BOSS_TAIL_ARC_HALF_DEG: Final[float] = 120.0     # 见 fish-doc/mvp/03-boss.md §4
# Boss 正面危险扇区半角（度）。120° 扇区 → 半角 60°
BOSS_FRONT_ARC_HALF_DEG: Final[float] = 60.0     # 见 fish-doc/mvp/03-boss.md §4

# Tier 4 提示文案持续秒数
TIER4_HINT_DURATION_S: Final[float] = 3.0        # 见 fish-doc/mvp/03-boss.md §5

# Boss 体型档位（"超 tier"标识；与 Fish.tier∈{1..4} 区分；can_eat 不用于 boss
# 判定，仅用作 snapshot/视觉档位标识。MVP 占位 = 5；M3-08 渲染按它选 silhouette）
BOSS_TIER: Final[int] = 5                        # 见 fish-doc/mvp/03-boss.md §6（"够大、够明显、够压迫"）+ MVP 占位
# Boss 视觉/碰撞半径（px）：fish-doc/03 §6 "占屏幕短边 ~25%" → 720*0.25/2 ≈ 90
BOSS_RADIUS: Final[float] = 90.0                 # 见 fish-doc/mvp/03-boss.md §6 + MVP 占位
# 玩家咬中 Boss 的伤害；fish-doc/03 §3 "玩家咬一口扣 1"
BOSS_BITE_DAMAGE: Final[int] = 1                 # 见 fish-doc/mvp/03-boss.md §3
# Boss PATROL 巡航速度比例（fish-doc/03 §3 "慢速绕场"，未给数值；MVP 占位）
BOSS_PATROL_SPEED_RATIO: Final[float] = 0.40     # 见 fish-doc/mvp/03-boss.md §3 + MVP 占位
# PATROL 期间每隔多少秒切换一次目标方位（避免线性穿屏）；MVP 占位
BOSS_PATROL_TURN_INTERVAL_S: Final[float] = 2.5  # MVP 占位
# ENRAGED 时 windup 时长缩短倍率（fish-doc/03 §3 "windup 缩短"未给数；MVP 占位）
BOSS_ENRAGED_WINDUP_MUL: Final[float] = 0.50     # 见 fish-doc/mvp/03-boss.md §3 + MVP 占位


# --------------------------------------------------------------------------
# 普通鱼（Fish）按 Tier 的体型 / 速度（见 fish-doc/mvp/02-fish-ecosystem.md §1）
# 索引 = Tier；Tier 0 留空（玩家初始档位，不存在 NPC fish）。
# 半径 = 表中"体长 px"的一半（02 §1 给的是体长，不是半径）。
# --------------------------------------------------------------------------

# 仅 Tier 1..4 有效；索引 0 用占位值，禁止 spawn。
FISH_RADIUS: Final[tuple[float, ...]] = (0.0, 4.0, 7.0, 11.0, 18.0)
# 见 fish-doc/mvp/02-fish-ecosystem.md §1（体长 8/14/22/36 → 半径 4/7/11/18）

FISH_MAX_SPEED: Final[tuple[float, ...]] = (0.0, 70.0, 95.0, 110.0, 130.0)
# 见 fish-doc/mvp/02-fish-ecosystem.md §1

# 转向上限（rad/s）：02 §3 只给"受 turn_rate 限制"，未列具体数值；
# MVP 占位：小鱼灵活、大鱼笨重。M4 调参可改。
FISH_TURN_RATE_RAD_S: Final[tuple[float, ...]] = (0.0, 5.0, 4.0, 3.0, 2.5)
# 见 fish-doc/mvp/02-fish-ecosystem.md §3 + MVP 占位

# 感知 / 逃跑 / 追击半径（px）：02 §2 列了 perception/flee/chase 三个字段
# 但未给具体值；MVP 占位，与体型成正比。
FISH_PERCEPTION_RADIUS: Final[tuple[float, ...]] = (0.0, 100.0, 140.0, 180.0, 240.0)
FISH_FLEE_RADIUS: Final[tuple[float, ...]] = FISH_PERCEPTION_RADIUS
FISH_CHASE_RADIUS: Final[tuple[float, ...]] = FISH_PERCEPTION_RADIUS
# 见 fish-doc/mvp/02-fish-ecosystem.md §2 + MVP 占位

# WANDER 状态：每隔多少秒重选一次随机偏航 + 巡航速度比例
WANDER_TURN_INTERVAL_S: Final[float] = 1.0       # MVP 占位（02 §2 未给具体值）
WANDER_SPEED_RATIO: Final[float] = 0.4           # MVP 占位：巡航 = 40% max_speed
WANDER_HEADING_JITTER_RAD: Final[float] = 1.0    # MVP 占位：±1 rad 偏航采样区间半宽

# 群行为（MVP 仅做 separation；alignment/cohesion 留 M4）：
# 同 tier 鱼若距离 < (r_a + r_b) * SEPARATION_OVERLAP_MUL，则互相施加推力。
FISH_SEPARATION_OVERLAP_MUL: Final[float] = 1.5  # 见 fish-doc/mvp/02-fish-ecosystem.md §4 + MVP 简化
FISH_SEPARATION_PUSH_SPEED: Final[float] = 30.0  # MVP 占位：分离推开速度（px/s）


# --------------------------------------------------------------------------
# Spawner（见 fish-doc/mvp/02-fish-ecosystem.md §4）
# --------------------------------------------------------------------------

SPAWNER_CHECK_INTERVAL_S: Final[float] = 0.5     # 见 fish-doc/mvp/02-fish-ecosystem.md §4

# 屏外缘 spawn margin（生成点位于世界矩形外 N px 处，朝屏内）
SPAWNER_EDGE_MARGIN: Final[float] = 20.0         # MVP 占位（02 §4 "在屏幕外缘生成"）


# --------------------------------------------------------------------------
# 边界反射速度衰减（见 fish-doc/mvp/02-fish-ecosystem.md §3）
# --------------------------------------------------------------------------

WALL_BOUNCE_DAMPING: Final[float] = 0.7          # 见 fish-doc/mvp/02-fish-ecosystem.md §3


# --------------------------------------------------------------------------
# LevelGenerator 阶段时长采样区间（见 fish-doc/mvp/04-level-generator.md §4 表）
# 仅作为常量集中保存的"区间端点"；具体采样在 systems/level_generator.py 实现
# --------------------------------------------------------------------------

PHASE_WARMUP_DURATION_RANGE_S: Final[tuple[float, float]] = (12.0, 18.0)
# 见 fish-doc/mvp/04-level-generator.md §4
PHASE_PRESSURE_DURATION_RANGE_S: Final[tuple[float, float]] = (15.0, 25.0)
# 见 fish-doc/mvp/04-level-generator.md §4
BOSS_APPEAR_TIME_RANGE_S: Final[tuple[float, float]] = (25.0, 60.0)
# 见 fish-doc/mvp/04-level-generator.md §5（硬约束 #4：boss.appear_time_s ∈ [25, 60]）

# 单 Phase 内 Tier-4 在场上限（硬约束 #2）
PHASE_TIER4_POPULATION_MAX: Final[int] = 3
# 见 fish-doc/mvp/04-level-generator.md §5

# 校验失败重试上限（见 fish-doc/mvp/04-level-generator.md §3）
LEVEL_GEN_MAX_RETRIES: Final[int] = 10
# 见 fish-doc/mvp/04-level-generator.md §3：「不通过则重采最多 N 次」

# BOSS / REVENGE 阶段为事件驱动；以下为 LevelDirector 在事件未触发时的兜底
# 超时（避免 bot 在 Boss 未实现的早期版本里永远卡住）。
# 见 fish-doc/mvp/04-level-generator.md §4 表（BOSS/REVENGE 时长「直到 VICTORY/DEAD」），
# 以及 fish-doc/mvp/01-core-loop.md §4 (TIMEOUT_S=180)。
BOSS_PHASE_TIMEOUT_S: Final[float] = 60.0
REVENGE_PHASE_TIMEOUT_S: Final[float] = 30.0
