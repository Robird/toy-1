"""fish/config/level_config.py — LevelConfig 与子配置 dataclass。

字段定义严格遵循 fish-doc/mvp/04-level-generator.md §2。本文件**不**实现
生成器逻辑（那是 M3-06 的 systems/level_generator.py 的职责），只承载数据形状。
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    BOSS_CHARGE_COOLDOWN_S,
    BOSS_CHASE_SPEED,
    BOSS_HP,
    BOSS_SENSE_RADIUS,
    BOSS_TURN_RATE,
    Phase,
    WORLD_H,
    WORLD_W,
)


# --------------------------------------------------------------------------
# PhaseConfig / BossConfig （见 fish-doc/mvp/04-level-generator.md §2）
# --------------------------------------------------------------------------

@dataclass
class PhaseConfig:
    """单个关卡阶段的参数。字段对齐 fish-doc/mvp/04-level-generator.md §2。"""

    duration_s: float
    population_target: dict[int, int]
    spawn_rate: dict[int, float]
    fish_speed_mul: float = 1.0
    threat_aggression: float = 1.0


@dataclass
class BossConfig:
    """Boss 实例参数。字段对齐 fish-doc/mvp/04-level-generator.md §2。"""

    appear_time_s: float
    sense_radius: float
    chase_speed: float
    turn_rate: float
    charge_cooldown: float
    hp: int = BOSS_HP


# --------------------------------------------------------------------------
# LevelConfig（见 fish-doc/mvp/04-level-generator.md §2）
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class LevelConfig:
    """一关游戏的完整可序列化配置。

    字段定义来源：fish-doc/mvp/04-level-generator.md §2。
    `frozen=True` 阻止顶层字段被重新赋值；嵌套 dict / dataclass
    在 MVP 阶段约定为只读（生成器一次性产出后不应再就地修改）。
    """

    seed: int
    world_size: tuple[int, int]
    phases: dict[Phase, PhaseConfig]
    boss: BossConfig
    difficulty: float

    # ----------------------------------------------------------------------
    # 工厂方法
    # ----------------------------------------------------------------------
    @staticmethod
    def default() -> "LevelConfig":
        """返回一个最小可用的占位 LevelConfig。

        注意：本工厂**仅供测试/骨架阶段使用**；正式关卡必须经 M3-06 的
        `LevelGenerator` 产出（带种子 + 校验）。各字段的取值参考
        fish-doc/mvp/04-level-generator.md §4 表的时长中点 / §5 硬约束。
        文档尚未给出 `population_target` / `spawn_rate` 的精确采样区间，
        因此这些数量只作为骨架期占位模板；正式数值由 M3-06 生成器裁决。
        """

        # WARMUP：仅 Tier-1 在场（§5 硬约束 #3：Tier-3/4 必须为 0）
        warmup = PhaseConfig(
            duration_s=15.0,  # §4 区间 12~18 中点
            population_target={1: 8, 2: 0, 3: 0, 4: 0},
            spawn_rate={1: 1.0, 2: 0.0, 3: 0.0, 4: 0.0},
        )
        # PRESSURE：引入 Tier-2/3，少量 Tier-4（§5 #2：Tier-4 ≤ 3）
        pressure = PhaseConfig(
            duration_s=20.0,  # §4 区间 15~25 中点
            population_target={1: 6, 2: 4, 3: 2, 4: 1},
            spawn_rate={1: 1.0, 2: 0.6, 3: 0.3, 4: 0.1},
        )
        # BOSS：维持中密度普通鱼，威胁鱼下调（§4 表）
        boss_phase = PhaseConfig(
            duration_s=0.0,  # 事件驱动：直到 VICTORY/DEAD
            population_target={1: 6, 2: 4, 3: 2, 4: 1},
            spawn_rate={1: 0.8, 2: 0.5, 3: 0.3, 4: 0.05},
        )
        # REVENGE：刷新降低，让位给追逐戏（§4 表）
        revenge = PhaseConfig(
            duration_s=0.0,  # 事件驱动：直到 VICTORY/DEAD
            population_target={1: 3, 2: 2, 3: 1, 4: 0},
            spawn_rate={1: 0.4, 2: 0.2, 3: 0.1, 4: 0.0},
        )

        boss = BossConfig(
            appear_time_s=30.0,  # §5 硬约束 #4 区间 [25, 60] 内
            sense_radius=BOSS_SENSE_RADIUS,
            chase_speed=BOSS_CHASE_SPEED,
            turn_rate=BOSS_TURN_RATE,
            charge_cooldown=BOSS_CHARGE_COOLDOWN_S,
            hp=BOSS_HP,
        )

        return LevelConfig(
            seed=0,
            world_size=(WORLD_W, WORLD_H),
            phases={
                Phase.WARMUP: warmup,
                Phase.PRESSURE: pressure,
                Phase.BOSS: boss_phase,
                Phase.REVENGE: revenge,
            },
            boss=boss,
            difficulty=0.5,
        )
