"""fish/systems/level_director.py — 阶段切换调度器（M3-06）。

按 fish-doc/mvp/01-core-loop.md §4 / fish-doc/mvp/03-boss.md §2 / §5 / §4
推进 4 个阶段：

    WARMUP → PRESSURE → BOSS → REVENGE → 终态

切换条件（本步在 M3-07 Boss 实体落地前用 ``getattr(world, 'boss', None)``
兼容；Boss 真正进场后由 M3-07 / M3-09 的 hook 同步 ``world.boss``）：

    - WARMUP → PRESSURE：``phase_elapsed_s >= cfg.phases[WARMUP].duration_s``
    - PRESSURE → BOSS：``world.player.tier >= 2``，或 PRESSURE 时长已到且
        ``world.elapsed_s + dt >= cfg.boss.appear_time_s``（fish-doc/03 §2「关卡时间
        到达 boss_appear_time 或 player.tier>=2」；PRESSURE duration 作为段内节奏下限）
  - BOSS → REVENGE：``world.player.tier >= TIER_GIANT(4)``
    （fish-doc/03 §5「pt 升到 4 的瞬间触发 ... 进入 PHASE_REVENGE」）
    或「曾出现 boss 但已被吃」(`world.boss is None and was_present`)
    - REVENGE → 终态：Boss 已不存在且 ``phase_elapsed_s`` 达到
        ``cfg.phases[REVENGE].duration_s`` 后 → ``GameResult.VICTORY``；若该时长为
        0 则下一帧立即胜利。

外加全局 ``TIMEOUT_S`` 兜底（fish-doc/01 §4）：``world.elapsed_s + dt >= TIMEOUT_S``
且 ``game_result is None`` → 写入 ``GameResult.TIMEOUT``。

设计要点：
- 不重新定义 ``Phase``；复用 ``fish.config.constants.Phase`` 枚举。
- 切换时 ``phase_elapsed_s`` 重置为 0；``current_phase`` 记录新阶段。
- ``get_active_population_target()`` 提供给 ``Spawner`` 查询：BOSS 阶段返回
  全 0，抑制普通鱼刷新（任务书要求；普通鱼仍存留场上消化掉）。
- 不接 metrics / 不接 render；M3-09 / M3-10 自行 hook。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fish.config.constants import (
    Phase,
    TIER_GIANT,
    TIMEOUT_S,
)

if TYPE_CHECKING:
    from fish.world import World


__all__ = ["LevelDirector"]


# Phase 顺序与索引；切换时按此线性推进
_PHASE_ORDER: tuple[Phase, ...] = (
    Phase.WARMUP,
    Phase.PRESSURE,
    Phase.BOSS,
    Phase.REVENGE,
)


class LevelDirector:
    """关卡阶段调度器。

    Attributes
    ----------
    world:
        反向引用，用于读取 ``cfg.phases`` / ``player.tier`` / ``boss``。
    current_phase:
        当前阶段；初始 ``Phase.WARMUP``。
    phase_elapsed_s:
        进入当前阶段以来的累计仿真时间（不含 dt=0 的帧）。
    """

    def __init__(self, world: "World") -> None:
        self.world = world
        self.current_phase: Phase = Phase.WARMUP
        self.phase_elapsed_s: float = 0.0
        # 是否曾出现过 Boss 实体；M3-07 后由 Boss spawn / death hook 维护
        self._boss_was_present: bool = False
        # 阶段切换日志（仅供 main 演示打印）；不写入 snapshot，避免 hash 抖动
        self._transition_log: list[tuple[float, Phase, Phase]] = []

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def step(self, world: "World", dt: float) -> None:
        """每帧推进；在终态写入后短路。"""
        if dt <= 0.0:
            return
        if world.game_result is not None:
            return

        dt_f = float(dt)
        self.phase_elapsed_s += dt_f
        sim_time_s = float(world.elapsed_s) + dt_f

        # 维护 _boss_was_present（M3-07 后 world.boss 会变成 Boss 实例）
        boss = getattr(world, "boss", None)
        if boss is not None:
            self._boss_was_present = True

        # 全局 TIMEOUT 兜底（fish-doc/01 §4）
        if sim_time_s >= TIMEOUT_S:
            from fish.world import GameResult
            world.game_result = GameResult.TIMEOUT
            return

        # 阶段切换（用 while 处理「一帧内可能跨多阶段」的极端情况，例如
        # WARMUP duration 极短 + PRESSURE duration 极短 + 玩家瞬间升 tier）
        # 但每帧最多前进一个阶段，避免无穷循环：用 if 链 + 一次切换。
        next_phase = self._compute_next_phase(world, sim_time_s)
        if next_phase is not None and next_phase != self.current_phase:
            self._transition_to(next_phase, world, sim_time_s)
        elif self.current_phase == Phase.REVENGE:
            # REVENGE 终态判定（即使没有阶段切换）
            self._maybe_finish_revenge(world)

    # ------------------------------------------------------------------
    # 业务查询
    # ------------------------------------------------------------------

    def get_active_population_target(self) -> dict[int, int]:
        """供 Spawner 查询当前阶段的 ``population_target``。

        BOSS 阶段：保留 Tier-3/4 的目标值（让玩家仍有 *成长链* 食物可吃，
        否则若玩家入 Boss 时仅 tier=2，将永远卡在 tier=2/3 而无法反杀
        Boss——见试玩反馈 #27），但抑制 Tier-1/2 新刷以让画面让位给 Boss。
        其它阶段直接返回 cfg 中的目标值。
        """
        if self.current_phase == Phase.BOSS:
            cfg_target = self.world.config.phases[Phase.BOSS].population_target
            out: dict[int, int] = {}
            for tier, n in cfg_target.items():
                try:
                    t_int = int(tier)
                except (TypeError, ValueError):
                    t_int = tier  # type: ignore[assignment]
                if isinstance(t_int, int) and t_int >= 3:
                    out[tier] = int(n) if isinstance(n, (int, float)) else 0
                else:
                    out[tier] = 0
            # 兜底：保证 key 集合不丢，便于 spawner 既有逻辑兼容
            for t in (1, 2, 3, 4):
                out.setdefault(t, 0)
            return out
        return dict(self.world.config.phases[self.current_phase].population_target)

    # ------------------------------------------------------------------
    # 内部：决定下一帧应处的阶段
    # ------------------------------------------------------------------

    def _compute_next_phase(self, world: "World", sim_time_s: float) -> Phase | None:
        cfg = world.config
        cur = self.current_phase

        if cur == Phase.WARMUP:
            if self.phase_elapsed_s >= cfg.phases[Phase.WARMUP].duration_s:
                return Phase.PRESSURE
            return None

        if cur == Phase.PRESSURE:
            # 文档触发：关卡时间到 boss.appear_time，或 player.tier >= 2。
            # 同时保留 PRESSURE duration 作为段内节奏下限，避免在 WARMUP 后
            # boss.appear_time 已过时立刻跳过 PRESSURE 的极端配置。
            if int(world.player.tier) >= 2:
                return Phase.BOSS
            pressure_elapsed = (
                self.phase_elapsed_s >= cfg.phases[Phase.PRESSURE].duration_s
            )
            boss_time_elapsed = sim_time_s >= cfg.boss.appear_time_s
            if pressure_elapsed and boss_time_elapsed:
                return Phase.BOSS
            return None

        if cur == Phase.BOSS:
            # fish-doc/03 §5：玩家升到 Tier-4（GIANT）→ 进入 REVENGE
            if int(world.player.tier) >= TIER_GIANT:
                return Phase.REVENGE
            # 兜底：曾出现过 Boss 且 boss 现在 None（已被吃）→ REVENGE
            boss = getattr(world, "boss", None)
            if self._boss_was_present and boss is None:
                return Phase.REVENGE
            return None

        if cur == Phase.REVENGE:
            # REVENGE 不再切换到下一个阶段（已是末段）；终态由
            # _maybe_finish_revenge 处理
            return None

        return None

    def _maybe_finish_revenge(self, world: "World") -> None:
        """在 REVENGE 阶段判定终态。"""
        from fish.world import GameResult

        revenge_timeout = world.config.phases[Phase.REVENGE].duration_s

        # Boss 已不存在 → 等 REVENGE 庆祝/收束窗口结束后 VICTORY。
        boss = getattr(world, "boss", None)
        if (
            boss is None
            and (revenge_timeout <= 0.0 or self.phase_elapsed_s >= revenge_timeout)
        ):
            world.game_result = GameResult.VICTORY
            return

    # ------------------------------------------------------------------
    # 内部：执行切换
    # ------------------------------------------------------------------

    def _transition_to(self, new_phase: Phase, world: "World", at_s: float) -> None:
        old = self.current_phase
        self.current_phase = new_phase
        self.phase_elapsed_s = 0.0
        self._transition_log.append(
            (float(at_s), old, new_phase)
        )
        # M3-07：进入 BOSS 阶段 → 让 World 生成 Boss 实体
        if new_phase == Phase.BOSS and getattr(world, "boss", None) is None:
            spawn = getattr(world, "spawn_boss", None)
            if callable(spawn):
                spawn()
        # 一旦 boss 实体被创建（无论本帧 spawn 还是已存在），都标记 _boss_was_present
        # 让后续 BOSS→REVENGE 判定可以基于「曾出现」+「已被吃」二元事实。
        if getattr(world, "boss", None) is not None:
            self._boss_was_present = True
        # 通知 Spawner 立即按新阶段调度（重置 _time_since_last_check 让下一帧
        # 即可补刷，避免「切到 PRESSURE 后还要等半秒才看到第一条 Tier-2」）
        spawner = getattr(world, "_spawner", None)
        if spawner is not None and hasattr(spawner, "_time_since_last_check"):
            # 触发即将到来的 check：下一 step 必然 > 0
            spawner._time_since_last_check = 1e9

    # ------------------------------------------------------------------
    # 调试 / main 演示
    # ------------------------------------------------------------------

    @property
    def transition_log(self) -> list[tuple[float, Phase, Phase]]:
        """返回 ``[(at_elapsed_s, from_phase, to_phase), ...]``。只读列表（拷贝）。"""
        return list(self._transition_log)
