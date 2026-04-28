"""fish/io/metrics_adapter.py — 把 World 事件 / 每帧状态翻译为 MetricsCollector 调用（M3-10）。

5 大原料指标（fish-doc/mvp/07-test-harness.md §6）：

  - ``fail_rate``           聚合层填，本步只在单局留 ``None`` 占位
  - ``first_growth_time``   首次升到 Tier 1 的 elapsed_s
  - ``starvation_ratio``    视野 120 px 内无可吃猎物的时间占比
  - ``near_miss_count``     与 tier > self 的实体距离 < 60 px 的"事件数"（rising-edge 计数）
  - ``boss_ttk``            Boss 出现 → Boss 死亡 / 玩家死亡 的耗时

顶层 6 字段（fish-doc/07 §6 envelope）：

  - ``seed`` / ``difficulty``   由 ``run_single_headless`` 在创建 collector 时已写入
  - ``result``                  finalize 时写
  - ``duration_s``              finalize 时写（= world.elapsed_s）
  - ``player_max_tier``         on_frame 时维护的最大值
    - ``death_cause``             ``"Boss_charge"`` / ``"Boss_face"`` /
                                                                fish tier name / ``None``

绑定方式：``FishGameFactory.bind_metrics`` 中 wrap ``world.step`` —— 每帧 step
之后调 ``listener.on_frame_end(dt)`` 完成 ``metrics.tick(dt)`` + 派生量计算 +
检测终态触发一次 ``finalize``。事件 dict 通过 ``world.register_listener`` 接收。
"""

from __future__ import annotations

import math
from typing import Any

from toy_engine.metrics import MetricsCollector

from fish.config.constants import BOSS_TIER, TIER_SMALL


# 启发式参数（与 fish-doc/07 §6 注脚一致）。
STARVATION_RADIUS: float = 120.0
NEAR_MISS_RADIUS: float = 60.0

_FISH_DEATH_CAUSES: dict[int, str] = {
    1: "Minnow",
    2: "Sardine",
    3: "Snapper",
    4: "Barracuda",
}


class FishMetricsListener:
    """把 World 事件与每帧状态翻译为 MetricsCollector 调用。

    必须由 ``FishGameFactory.bind_metrics`` 构造并接好 listener + step wrap。
    """

    def __init__(self, world, metrics: MetricsCollector) -> None:
        self._world = world
        self._metrics = metrics

        # 派生量内部状态
        self._first_growth_time: float | None = None
        self._starve_dt: float = 0.0
        self._near_eids: set[int] = set()  # 上一帧已经在 60px 内的威胁 eid
        self._near_miss_count: int = 0
        self._boss_appear_t: float | None = None
        self._boss_killed_t: float | None = None
        self._player_death_t: float | None = None
        self._player_max_tier: int = int(world.player.tier)

        self._finalized: bool = False

    # ------------------------------------------------------------------
    # World event listener (注册到 world.register_listener)
    # ------------------------------------------------------------------

    def handle(self, event: dict) -> None:
        et = event.get("type")
        t = float(self._world.elapsed_s)
        if et == "fish_eaten":
            tier = int(event.get("victim_tier", 0))
            self._metrics.record_event("fish_eaten", value=tier)
        elif et == "player_grow":
            new_tier = int(event.get("new_tier", 0))
            if self._first_growth_time is None and new_tier >= TIER_SMALL:
                self._first_growth_time = t
            if new_tier > self._player_max_tier:
                self._player_max_tier = new_tier
            self._metrics.record_event("player_grow", value=new_tier)
        elif et == "boss_bitten":
            self._metrics.record_event("boss_bitten")
        elif et == "boss_killed":
            self._boss_killed_t = t
            self._metrics.record_event("boss_killed")
            # param_sweep 用 counter_kill_rate 统计「进入 BOSS 后成功反杀」比例。
            self._metrics.record_event("counter_kill")
        elif et == "player_eaten":
            self._player_death_t = t
            self._metrics.record_event("player_eaten")

    # ------------------------------------------------------------------
    # Per-frame hook (调用入口由 FishGameFactory.bind_metrics wrap)
    # ------------------------------------------------------------------

    def on_frame_end(self, dt: float) -> None:
        if self._finalized:
            return
        self._metrics.tick(float(dt))
        world = self._world

        # boss 出现时间（rising edge：boss 由 None → not None）
        if self._boss_appear_t is None and world.boss is not None:
            self._boss_appear_t = float(world.elapsed_s)
            # param_sweep 用 entered_boss_rate 统计进入 PHASE_BOSS 的局数占比。
            self._metrics.record_event("entered_boss")

        # player_max_tier 滚动维护
        cur_tier = int(world.player.tier)
        if cur_tier > self._player_max_tier:
            self._player_max_tier = cur_tier

        if not world.player.alive:
            # 玩家死亡后不再统计 starvation / near-miss
            if world.is_finished() and not self._finalized:
                self._finalize()
            return

        # 计算可吃猎物 + 威胁
        ptier = int(world.player.tier)
        ppos = world.player.pos
        px, py = float(ppos.x), float(ppos.y)
        starve_radius2 = STARVATION_RADIUS * STARVATION_RADIUS
        near_radius2 = NEAR_MISS_RADIUS * NEAR_MISS_RADIUS

        has_prey = False
        new_near: set[int] = set()
        for f in world.fishes:
            if not f.alive:
                continue
            fx = float(f.pos.x); fy = float(f.pos.y)
            d2 = (fx - px) ** 2 + (fy - py) ** 2
            ftier = int(f.tier)
            # 可吃判定：与 fish/systems/collision.can_eat 对齐（player 可吃 ≤ tier+1）
            if ftier <= ptier + 1 and d2 <= starve_radius2:
                has_prey = True
            # 威胁判定：tier > self
            if ftier > ptier and d2 <= near_radius2:
                new_near.add(int(f.eid))
        # boss 也算威胁（tier=BOSS_TIER=5）
        if world.boss is not None and world.boss.alive:
            bx = float(world.boss.pos.x); by = float(world.boss.pos.y)
            d2 = (bx - px) ** 2 + (by - py) ** 2
            if d2 <= near_radius2:
                new_near.add(int(world.boss.eid))

        # rising-edge 计数：本帧新增的 eid 即一次 near-miss
        for eid in new_near:
            if eid not in self._near_eids:
                self._near_miss_count += 1
        self._near_eids = new_near

        if not has_prey:
            self._starve_dt += float(dt)

        if world.is_finished():
            self._finalize()

    # ------------------------------------------------------------------
    # 终局 envelope
    # ------------------------------------------------------------------

    def _finalize(self) -> None:
        """游戏内部触发终态（DEAD/VICTORY）→ 写 metrics + 调 finish。"""
        if self._finalized:
            return
        self._finalized = True
        result_name: str
        if self._world.game_result is not None:
            result_name = self._world.game_result.name
        else:
            result_name = "TIMEOUT"
        self._write_envelope_fields(self._world)
        self._metrics.finish(result_name)

    def write_envelope_before_finish(self, world) -> None:
        """tools_lib 的 fallback ``metrics.finish('TIMEOUT'|'DONE')`` 触发前
        把 5 大指标 + 顶层派生字段写入；外层会再调一次 ``metrics.finish``。

        与 ``_finalize`` 互斥（两条路径只走一条）；幂等。
        """
        if self._finalized:
            return
        self._finalized = True
        self._write_envelope_fields(world)

    def finalize(self, world) -> None:
        """显式触发完整终局（写字段 + 调 finish）。重复调用 no-op。"""
        if self._finalized:
            return
        self._finalize()

    def _write_envelope_fields(self, world) -> None:
        m = self._metrics
        elapsed = float(world.elapsed_s)

        # ---- metrics 段（5 大原料）----
        m.set_scalar("fail_rate", None, top_level=False)
        m.set_scalar(
            "first_growth_time",
            float(self._first_growth_time) if self._first_growth_time is not None else None,
            top_level=False,
        )
        starvation_ratio: float | None
        if elapsed > 0.0:
            ratio = self._starve_dt / elapsed
            starvation_ratio = max(0.0, min(1.0, ratio))
        else:
            starvation_ratio = None
        m.set_scalar("starvation_ratio", starvation_ratio, top_level=False)
        m.set_scalar("near_miss_count", int(self._near_miss_count), top_level=False)

        # boss_ttk = (boss 死亡 or 玩家死亡 or 当前) - boss 出现
        boss_ttk: float | None = None
        if self._boss_appear_t is not None:
            end_t: float | None
            if self._boss_killed_t is not None:
                end_t = self._boss_killed_t
            elif self._player_death_t is not None and self._player_death_t >= self._boss_appear_t:
                end_t = self._player_death_t
            else:
                end_t = None
            if end_t is not None:
                boss_ttk = max(0.0, float(end_t - self._boss_appear_t))
        m.set_scalar("boss_ttk", boss_ttk, top_level=False)

        # ---- 顶层 ----
        m.set_scalar("player_max_tier", int(self._player_max_tier), top_level=True)
        m.set_scalar("duration_s", elapsed, top_level=True)

        # death_cause 字符串映射；对齐 fish-doc/07 §6 示例命名，避免把
        # 泛化的 "fish" / "boss" 写进严格 envelope。
        cause_tier = int(world.stats.get("death_cause_tier", -1))
        death_cause = _death_cause_from_world(world, cause_tier)
        m.set_scalar("death_cause", death_cause, top_level=True)

        # 注意：``result`` / ``finish()`` 不在这里调；由 ``_finalize`` 或外层
        # ``run_single_headless`` 的 fallback ``metrics.finish`` 写入，避免
        # 双重 finish 触发 set_scalar 重复警告。


def _death_cause_from_world(world, cause_tier: int) -> str | None:
    if cause_tier == BOSS_TIER:
        boss = getattr(world, "boss", None)
        state = getattr(getattr(boss, "state", None), "name", None)
        if state == "CHARGE":
            return "Boss_charge"
        return "Boss_face"
    if cause_tier > 0:
        return _FISH_DEATH_CAUSES.get(cause_tier, f"Fish_tier{cause_tier}")
    return None
