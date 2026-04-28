"""fish/systems/level_generator.py — 参数化关卡生成器（M3-06）。

按 fish-doc/mvp/04-level-generator.md：

- ``LevelGenerator.generate(seed, difficulty, rng) → LevelConfig``
  - 纯函数：相同 ``(seed, difficulty)`` + 相同 ``rng`` 上下文 → 相同 LevelConfig
  - 内部用 ``rng.spawn("level_gen")`` 子流采样 phase 时长 / population_target /
    spawn_rate / Boss appear_time，保证与其它子流（如 spawner）相互隔离
  - 校验 §5 五条硬约束；失败 → 重采（最多 ``LEVEL_GEN_MAX_RETRIES``）；超过
    上限抛 ``LevelGenerationError``

采样区间均**严格落在文档区间内**（04 §4 / §5 表），具体每条来源见
`_sample_*` 内联注释；所有数值参数集中在 ``fish.config.constants``，本文件
不重复硬编码。

注意：
- 玩家初始 tier=0；按主会话裁决 #13，``can_eat`` 取「同 tier 或 tier-1」语义
  → WARMUP 至少 1 条 Tier-1 即可满足「可吃目标永不为零」（§5 #1）。
- ``LevelConfig.frozen=True``；嵌套 dict / dataclass MVP 阶段约定为只读。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from toy_engine.rng import SeededRng

from fish.config.constants import (
    BOSS_APPEAR_TIME_RANGE_S,
    BOSS_CHARGE_COOLDOWN_S,
    BOSS_CHASE_SPEED,
    BOSS_HP,
    BOSS_PHASE_TIMEOUT_S,
    BOSS_SENSE_RADIUS,
    BOSS_TURN_RATE,
    LEVEL_GEN_MAX_RETRIES,
    PHASE_PRESSURE_DURATION_RANGE_S,
    PHASE_TIER4_POPULATION_MAX,
    PHASE_WARMUP_DURATION_RANGE_S,
    Phase,
    REVENGE_PHASE_TIMEOUT_S,
    WORLD_H,
    WORLD_W,
)
from fish.config.level_config import BossConfig, LevelConfig, PhaseConfig

__all__ = [
    "LevelGenerator",
    "LevelGenerationError",
    "Violation",
]


# ---------------------------------------------------------------------------
# 采样区间常量（仅本文件内使用；MVP 占位，M4 调参可挪入 constants.py）
# ---------------------------------------------------------------------------

# WARMUP：仅 Tier-1（§5 #3 硬约束 + §4 表「仅 Tier-1 Minnow 大量在场」）
_WARMUP_TIER1_RANGE: tuple[int, int] = (6, 10)

# PRESSURE：引入 Tier-2/3，少量 Tier-4（§4 表 + §5 #2 / #5 数值连续性）
# Tier-2/3/4 上限受 §5 #5 约束（WARMUP 全部为 0 → 相邻 ≤ 3 才合法）。
# 试玩反馈 #27（fish-doc/mvp/progress.md）：Tier-3/4 原 “可能为 0” 会造成
# 玩家成长链断档（无法吃到 Tier-4 → 不能反杀 Boss）；将 下限提到 » 1。
_PRESSURE_TIER1_RANGE: tuple[int, int] = (5, 8)
_PRESSURE_TIER2_RANGE: tuple[int, int] = (3, 4)
_PRESSURE_TIER3_RANGE: tuple[int, int] = (2, 3)
_PRESSURE_TIER4_RANGE: tuple[int, int] = (1, 2)

# BOSS：维持中密度普通鱼，威胁鱼下调（§4 表）
# 试玩反馈 #27：Boss 阶段 spawner 仍会依据 LevelDirector 的裁决保留
# Tier-3/4 的补刷（抵消 Tier-1/2 的噪音），这里括充下限以避免 « 刚进
# Boss 场上 Tier-3/4 为 0 » 的极端采样。
_BOSS_TIER1_RANGE: tuple[int, int] = (4, 7)
_BOSS_TIER2_RANGE: tuple[int, int] = (2, 4)
_BOSS_TIER3_RANGE: tuple[int, int] = (2, 3)
_BOSS_TIER4_RANGE: tuple[int, int] = (1, 2)

# REVENGE：刷新降低；窄区间避免与 BOSS 段连续性 ×3 突变（§5 #5）
_REVENGE_TIER1_RANGE: tuple[int, int] = (3, 5)
_REVENGE_TIER2_RANGE: tuple[int, int] = (2, 3)
_REVENGE_TIER3_RANGE: tuple[int, int] = (0, 2)
# Tier-4 在 REVENGE 不刷（玩家自身已是 Tier-4，画面让位给 Boss 追逐）

# spawn_rate 经验：每秒最多补充 = max(0.05, target / _SPAWN_RATE_REFRESH_S)
# 让一波被消灭后约 _SPAWN_RATE_REFRESH_S 秒内补满。MVP 占位。
_SPAWN_RATE_REFRESH_S: float = 8.0
_SPAWN_RATE_FLOOR: float = 0.05  # 仅当 target > 0 时生效


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    """单条硬约束违规。``code`` 与 fish-doc/04 §5 序号对齐。"""

    code: str
    message: str


class LevelGenerationError(RuntimeError):
    """重采次数超过 ``LEVEL_GEN_MAX_RETRIES`` 仍未通过校验。"""

    def __init__(self, attempts: int, last_violations: list[Violation]) -> None:
        super().__init__(
            f"LevelGenerator failed after {attempts} attempts; "
            f"last violations: {[v.code + ':' + v.message for v in last_violations]}"
        )
        self.attempts = attempts
        self.last_violations = list(last_violations)


# Phase 顺序，用于 §5 #5「相邻 Phase」检查
_PHASE_ORDER: tuple[Phase, ...] = (
    Phase.WARMUP,
    Phase.PRESSURE,
    Phase.BOSS,
    Phase.REVENGE,
)

# §5 #1 的「可吃目标」按阶段给出保守上限：
# WARMUP 玩家从 tier=0 开始，按裁决 #13 只能稳定吃到 tier=1；PRESSURE
# 目标是把玩家推到 tier=3，至少要保留 tier<=3 的猎物；BOSS/REVENGE 阶段
# 玩家可能已接近 / 达到 tier=4，普通鱼 tier<=4 都可作为成长或追逐目标。
_PHASE_MAX_EDIBLE_TIER: dict[Phase, int] = {
    Phase.WARMUP: 1,
    Phase.PRESSURE: 3,
    Phase.BOSS: 4,
    Phase.REVENGE: 4,
}


# C6（试玩反馈 #27）：成长链最低保证。
# 玩家 can_eat = a.tier ≥ b.tier-1（裁决 #13）→ 从 tier 0 反杀 tier-5 Boss
# 必须能稳定吃到 tier 4。WARMUP 已由 C3 强制 ≥1 条 Tier-1，不再列入此表。
# REVENGE 阶段玩家已经是 Tier-4，不再依赖成长链，故仅约束 PRESSURE / BOSS。
_GROWTH_CHAIN_MIN: dict[Phase, dict[int, int]] = {
    Phase.PRESSURE: {1: 3, 2: 2, 3: 1, 4: 1},
    Phase.BOSS: {3: 1, 4: 1},
}


def _is_finite_number(value: object) -> bool:
    """配置数值必须是有限 int/float；bool 不视为合法数值。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _population_count(pcfg: PhaseConfig, tier: int) -> int | None:
    """取 population_target[tier]；非有限 / 非数值返回 None，交给 C0 报告。"""
    raw = pcfg.population_target.get(tier, 0)
    if not _is_finite_number(raw):
        return None
    return int(raw)


def _tier_key_leq(tier: object, limit: int) -> bool:
    try:
        return int(tier) <= limit
    except (TypeError, ValueError):
        return False


def validate(cfg: LevelConfig) -> list[Violation]:
    """跑 §5 五条硬约束；返回空列表表示全部通过。

        1. 可吃目标永不为零：每个 Phase 至少有一个 ``population_target[t] > 0``，
             且 ``t`` 不超过该阶段的保守可吃上限（WARMUP 必须含 Tier-1）。
    2. 威胁不超量：所有 Phase ``population_target[4] <= PHASE_TIER4_POPULATION_MAX``。
    3. WARMUP 纯净：``population_target[3] == 0 and population_target[4] == 0``。
    4. BOSS 进场时机合理：``boss.appear_time_s ∈ [25, 60]``（左右闭区间）。
    5. 数值连续性：相邻 Phase 单 Tier ``max(a,b) <= 3 * max(min(a,b), 1)``。    6. 成长链完整：PRESSURE 与 BOSS 阶段对每个 Tier ``t ∈ {1..4}`` 至少有
       ``_GROWTH_CHAIN_MIN[phase][t]`` 条 ``population_target``，确保玩家从
       Tier 0 一路吃到 Tier 4（反杀 Boss 的前置条件）。试玩反馈 #27。    """
    vs: list[Violation] = []

    missing = [ph for ph in _PHASE_ORDER if ph not in cfg.phases]
    for ph in missing:
        vs.append(Violation("C0", f"missing required phase {ph.name}"))
    if missing:
        return vs

    if not _is_finite_number(cfg.difficulty) or not (0.0 <= float(cfg.difficulty) <= 1.0):
        vs.append(
            Violation(
                "C0",
                f"difficulty={cfg.difficulty!r} must be a finite number in [0, 1]",
            )
        )

    for ph in _PHASE_ORDER:
        pcfg = cfg.phases[ph]
        if not _is_finite_number(pcfg.duration_s) or float(pcfg.duration_s) < 0.0:
            vs.append(
                Violation(
                    "C0",
                    f"phase {ph.name} duration_s={pcfg.duration_s!r} must be finite and >= 0",
                )
            )
        for tier, count in pcfg.population_target.items():
            if not _is_finite_number(count) or float(count) < 0.0:
                vs.append(
                    Violation(
                        "C0",
                        f"phase {ph.name} population_target[{tier!r}]={count!r} must be finite and >= 0",
                    )
                )
        for tier, rate in pcfg.spawn_rate.items():
            if not _is_finite_number(rate) or float(rate) < 0.0:
                vs.append(
                    Violation(
                        "C0",
                        f"phase {ph.name} spawn_rate[{tier!r}]={rate!r} must be finite and >= 0",
                    )
                )

    for field_name in (
        "sense_radius",
        "chase_speed",
        "turn_rate",
        "charge_cooldown",
    ):
        value = getattr(cfg.boss, field_name)
        if not _is_finite_number(value) or float(value) < 0.0:
            vs.append(
                Violation(
                    "C0",
                    f"boss.{field_name}={value!r} must be finite and >= 0",
                )
            )
    if not _is_finite_number(cfg.boss.hp) or int(cfg.boss.hp) <= 0:
        vs.append(
            Violation("C0", f"boss.hp={cfg.boss.hp!r} must be finite and > 0")
        )

    # #1：每个 Phase 至少有一个当前阶段可吃的正数量目标。
    for ph in _PHASE_ORDER:
        pcfg = cfg.phases[ph]
        max_edible_tier = _PHASE_MAX_EDIBLE_TIER[ph]
        if not any(
            _tier_key_leq(tier, max_edible_tier)
            and _is_finite_number(count)
            and float(count) > 0.0
            for tier, count in pcfg.population_target.items()
        ):
            vs.append(
                Violation(
                    "C1",
                    f"phase {ph.name} has no edible target for max edible tier "
                    f"{max_edible_tier}; population_target={dict(pcfg.population_target)}",
                )
            )

    # #2：Tier-4 不超量
    for ph in _PHASE_ORDER:
        pcfg = cfg.phases[ph]
        n4 = _population_count(pcfg, 4)
        if n4 is not None and n4 > PHASE_TIER4_POPULATION_MAX:
            vs.append(
                Violation(
                    "C2",
                    f"phase {ph.name} population_target[4]={n4} > {PHASE_TIER4_POPULATION_MAX}",
                )
            )

    # #3：WARMUP 纯净
    warmup = cfg.phases[Phase.WARMUP]
    warmup_t3 = _population_count(warmup, 3)
    if warmup_t3 is not None and warmup_t3 != 0:
        vs.append(
            Violation(
                "C3",
                f"WARMUP population_target[3]={warmup_t3} != 0",
            )
        )
    warmup_t4 = _population_count(warmup, 4)
    if warmup_t4 is not None and warmup_t4 != 0:
        vs.append(
            Violation(
                "C3",
                f"WARMUP population_target[4]={warmup_t4} != 0",
            )
        )
    # 额外：WARMUP 必须至少 1 条 Tier-1（玩家 tier=0；裁决 #13 → can_eat=tier-1）
    warmup_t1 = _population_count(warmup, 1)
    if warmup_t1 is None or warmup_t1 <= 0:
        vs.append(
            Violation(
                "C3",
                "WARMUP must contain at least one Tier-1 fish (player.tier=0 can only eat tier<=1)",
            )
        )

    # #4：BOSS appear_time
    lo, hi = BOSS_APPEAR_TIME_RANGE_S
    if not _is_finite_number(cfg.boss.appear_time_s):
        vs.append(
            Violation(
                "C4",
                f"boss.appear_time_s={cfg.boss.appear_time_s!r} is not finite",
            )
        )
    elif not (lo <= float(cfg.boss.appear_time_s) <= hi):
        vs.append(
            Violation(
                "C4",
                f"boss.appear_time_s={cfg.boss.appear_time_s} not in [{lo}, {hi}]",
            )
        )

    # #5：相邻 Phase 数值连续性
    for i in range(len(_PHASE_ORDER) - 1):
        a_ph = _PHASE_ORDER[i]
        b_ph = _PHASE_ORDER[i + 1]
        a_tgt = cfg.phases[a_ph].population_target
        b_tgt = cfg.phases[b_ph].population_target
        all_tiers = set(a_tgt.keys()) | set(b_tgt.keys())
        for t in sorted(all_tiers):
            raw_a = a_tgt.get(t, 0)
            raw_b = b_tgt.get(t, 0)
            if not (_is_finite_number(raw_a) and _is_finite_number(raw_b)):
                continue
            a = int(raw_a)
            b = int(raw_b)
            hi_v = max(a, b)
            lo_v = min(a, b)
            allowed = 3 * max(lo_v, 1)
            if hi_v > allowed:
                vs.append(
                    Violation(
                        "C5",
                        f"adjacent {a_ph.name}->{b_ph.name} tier{t} "
                        f"jumps {a}->{b}; allowed <= {allowed} "
                        "by max(a,b) <= 3*max(min(a,b),1)",
                    )
                )

    # #6：成长链最低保证（试玩反馈 #27）
    for ph, mins in _GROWTH_CHAIN_MIN.items():
        pcfg = cfg.phases[ph]
        for tier, min_count in mins.items():
            n = _population_count(pcfg, tier)
            if n is None or n < min_count:
                vs.append(
                    Violation(
                        "C6",
                        f"phase {ph.name} population_target[{tier}]="
                        f"{n!r} < required min {min_count} "
                        "(player growth chain to tier 4 not guaranteed)",
                    )
                )

    return vs


# ---------------------------------------------------------------------------
# LevelGenerator
# ---------------------------------------------------------------------------


class LevelGenerator:
    """参数化关卡生成器。

    用法：
        cfg = LevelGenerator.generate(seed=0, difficulty=0.5, rng=SeededRng(0))

    内部生成步骤：
      1. ``rng.spawn("level_gen")`` 派生独立子流（保证不影响 spawner / fish_ai 流）；
      2. 第 ``k`` 次 attempt 用 ``level_gen_rng.spawn(f"attempt_{k}")`` 派生采样流，
         避免某次 attempt 的失败采样影响后续 attempt 的随机序列；
      3. 跑 ``validate(cfg)``；通过则返回，否则 attempt+=1；
      4. 超过 ``LEVEL_GEN_MAX_RETRIES`` → 抛 ``LevelGenerationError``。
    """

    MAX_RETRIES: int = LEVEL_GEN_MAX_RETRIES

    @classmethod
    def generate(
        cls,
        seed: int,
        difficulty: float,
        rng: SeededRng,
    ) -> LevelConfig:
        if not isinstance(rng, SeededRng):
            raise TypeError(f"rng must be SeededRng, got {type(rng).__name__}")
        if not (0.0 <= float(difficulty) <= 1.0):
            raise ValueError(f"difficulty must be in [0, 1], got {difficulty}")

        gen_rng = rng.spawn("level_gen")
        last_violations: list[Violation] = []
        for attempt in range(cls.MAX_RETRIES):
            attempt_rng = gen_rng.spawn(f"attempt_{attempt}")
            cfg = cls._sample(seed=seed, difficulty=float(difficulty), rng=attempt_rng)
            violations = validate(cfg)
            if not violations:
                return cfg
            last_violations = violations
        raise LevelGenerationError(cls.MAX_RETRIES, last_violations)

    # ------------------------------------------------------------------
    # 采样
    # ------------------------------------------------------------------

    @classmethod
    def _sample(
        cls,
        *,
        seed: int,
        difficulty: float,
        rng: SeededRng,
    ) -> LevelConfig:
        # 各子项使用命名子流，避免「调整 Boss 采样范围破坏 Phase 采样」的耦合
        # （fish-doc/04 §7 显式要求）。
        phase_rng = rng.spawn("phases")
        boss_rng = rng.spawn("boss")

        warmup = cls._sample_warmup(phase_rng.spawn("warmup"))
        pressure = cls._sample_pressure(phase_rng.spawn("pressure"), difficulty)
        boss_phase = cls._sample_boss_phase(phase_rng.spawn("boss_phase"), difficulty)
        revenge = cls._sample_revenge(phase_rng.spawn("revenge"))

        boss_cfg = cls._sample_boss(boss_rng, difficulty)

        return LevelConfig(
            seed=int(seed),
            world_size=(WORLD_W, WORLD_H),
            phases={
                Phase.WARMUP: warmup,
                Phase.PRESSURE: pressure,
                Phase.BOSS: boss_phase,
                Phase.REVENGE: revenge,
            },
            boss=boss_cfg,
            difficulty=float(difficulty),
        )

    @staticmethod
    def _spawn_rate_for(target: dict[int, int]) -> dict[int, float]:
        out: dict[int, float] = {}
        for t, n in target.items():
            if n <= 0:
                out[int(t)] = 0.0
            else:
                out[int(t)] = max(_SPAWN_RATE_FLOOR, n / _SPAWN_RATE_REFRESH_S)
        return out

    @classmethod
    def _sample_warmup(cls, rng: SeededRng) -> PhaseConfig:
        lo, hi = PHASE_WARMUP_DURATION_RANGE_S
        duration = rng.uniform(lo, hi)
        target = {
            1: rng.randint(*_WARMUP_TIER1_RANGE),
            2: 0,
            3: 0,
            4: 0,
        }
        return PhaseConfig(
            duration_s=duration,
            population_target=target,
            spawn_rate=cls._spawn_rate_for(target),
        )

    @classmethod
    def _sample_pressure(cls, rng: SeededRng, difficulty: float) -> PhaseConfig:
        lo, hi = PHASE_PRESSURE_DURATION_RANGE_S
        duration = rng.uniform(lo, hi)
        # difficulty 仅影响 Tier-4 上限的「向上偏」（高难度更容易出 1~2 条）
        t4_hi = _PRESSURE_TIER4_RANGE[1] if difficulty >= 0.5 else max(
            _PRESSURE_TIER4_RANGE[0], _PRESSURE_TIER4_RANGE[1] - 1
        )
        target = {
            1: rng.randint(*_PRESSURE_TIER1_RANGE),
            2: rng.randint(*_PRESSURE_TIER2_RANGE),
            3: rng.randint(*_PRESSURE_TIER3_RANGE),
            4: rng.randint(_PRESSURE_TIER4_RANGE[0], t4_hi),
        }
        return PhaseConfig(
            duration_s=duration,
            population_target=target,
            spawn_rate=cls._spawn_rate_for(target),
            threat_aggression=1.0 + 0.2 * float(difficulty),
        )

    @classmethod
    def _sample_boss_phase(cls, rng: SeededRng, difficulty: float) -> PhaseConfig:
        # 04 §2：BOSS / REVENGE 的 duration_s 为「事件驱动」；这里写入 director
        # 兜底超时（避免 Boss 实体未实现时永远卡住）。
        target = {
            1: rng.randint(*_BOSS_TIER1_RANGE),
            2: rng.randint(*_BOSS_TIER2_RANGE),
            3: rng.randint(*_BOSS_TIER3_RANGE),
            4: rng.randint(*_BOSS_TIER4_RANGE),
        }
        return PhaseConfig(
            duration_s=BOSS_PHASE_TIMEOUT_S,
            population_target=target,
            spawn_rate=cls._spawn_rate_for(target),
            threat_aggression=1.0 + 0.3 * float(difficulty),
        )

    @classmethod
    def _sample_revenge(cls, rng: SeededRng) -> PhaseConfig:
        target = {
            1: rng.randint(*_REVENGE_TIER1_RANGE),
            2: rng.randint(*_REVENGE_TIER2_RANGE),
            3: rng.randint(*_REVENGE_TIER3_RANGE),
            4: 0,
        }
        return PhaseConfig(
            duration_s=REVENGE_PHASE_TIMEOUT_S,
            population_target=target,
            spawn_rate=cls._spawn_rate_for(target),
            fish_speed_mul=0.9,  # 让位给 Boss 追逐戏（§4 表）
        )

    @classmethod
    def _sample_boss(cls, rng: SeededRng, difficulty: float) -> BossConfig:
        lo, hi = BOSS_APPEAR_TIME_RANGE_S
        # difficulty 高 → Boss 更早进场。把 [lo, hi] 收窄到 difficulty 偏置区间
        # 内均匀采样；保证仍落在 §5 #4 区间内。
        span = hi - lo
        # 难度 0 → 中点附近~hi；难度 1 → lo~中点附近
        mid = lo + span * (1.0 - float(difficulty))
        sub_lo = max(lo, mid - span * 0.25)
        sub_hi = min(hi, mid + span * 0.25)
        appear = rng.uniform(sub_lo, sub_hi)
        return BossConfig(
            appear_time_s=appear,
            sense_radius=BOSS_SENSE_RADIUS,
            chase_speed=BOSS_CHASE_SPEED,
            turn_rate=BOSS_TURN_RATE,
            charge_cooldown=BOSS_CHARGE_COOLDOWN_S,
            hp=BOSS_HP,
        )
