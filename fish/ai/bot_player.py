"""fish/ai/bot_player.py — 启发式 BotInput（M3-10）。

继承 ``toy_engine.input.BotInputBase``。决策完全基于 ``world.snapshot()`` 的
只读 dict（GameLoop._tick_once 把 snapshot 传给 ``poll``），不直接读 World。

启发式（按优先级，参考 fish-doc/mvp/07-test-harness.md §5）：

  1. 逃避：若有 ``fish.tier >= player.tier + 2`` 的鱼在 ``SAFE_RADIUS`` 内 →
     朝威胁合矢量的反方向。
  2. 反杀 Boss：若 player.tier >= TIER_GIANT 且 boss 存在；STUNNED 时直接朝
     boss；否则只在 player 已经处于 boss 尾后 240° 弧上时朝 boss 尾点。
  3. 远离 Boss：boss 存在且非 STUNNED 且 player.tier < TIER_GIANT → 远离。
  4. 追猎物：最近的 ``fish.tier <= player.tier + 1`` 的鱼（裁决 #13 的
     "以小搏大一档"）。
  5. 漂移：返回 ``InputFrame()`` （desired_dir=None，沿当前 heading 衰减）。

所有需要打破平局 / 抖动的随机决策走 ``self.rng``，保证同 seed 决定性。
"""

from __future__ import annotations

import math
from typing import Any

from toy_engine.geom import Vec2, angle_in_arc
from toy_engine.input import BotInputBase, InputFrame

from fish.config.constants import BOSS_TIER, TIER_GIANT


# 启发式参数（MVP 占位；M4 调参）。
SAFE_RADIUS: float = 200.0          # 威胁鱼进入此半径触发逃避
BOSS_FLEE_RADIUS: float = 320.0     # boss 非 STUNNED 时的安全距离
BOSS_TAIL_ARC_HALF_RAD: float = math.radians(120.0)  # 尾后 240° 弧 = ±120°
PREY_MAX_DIST: float = 800.0        # 追猎物的最大有效距离（屏幕对角线之内）


class BotInput(BotInputBase):
    """启发式自动玩家。决策基于 snapshot dict。"""

    def decide(self, world_state: Any) -> InputFrame:  # noqa: D401
        snap = world_state
        # snapshot 必备字段 → 直接信任 World 契约
        try:
            ppos = snap["player_pos"]
            ptier = int(snap["player_tier"])
            entities = snap.get("entities") or []
            boss_snap = snap.get("boss")
        except (KeyError, TypeError):
            return InputFrame(desired_dir=None)

        px, py = float(ppos[0]), float(ppos[1])

        # 拆分实体：fish vs boss 已在 snapshot 顶层 boss 字段
        fishes = [
            e for e in entities
            if e.get("kind") == "fish" and e.get("alive", True)
        ]

        # ---- 1. 威胁鱼逃避 ----
        threat_dx = 0.0
        threat_dy = 0.0
        for f in fishes:
            ftier = int(f.get("tier", 0))
            if ftier < ptier + 2:
                continue
            fx, fy = f["pos"]
            dx = px - float(fx)
            dy = py - float(fy)
            dist2 = dx * dx + dy * dy
            if dist2 < SAFE_RADIUS * SAFE_RADIUS:
                d = math.sqrt(dist2) + 1e-9
                threat_dx += dx / d
                threat_dy += dy / d
        if threat_dx != 0.0 or threat_dy != 0.0:
            return _to_unit_frame(threat_dx, threat_dy, self.rng)

        # ---- 2/3. Boss 处理 ----
        if boss_snap is not None:
            bx, by = boss_snap["pos"]
            bx = float(bx); by = float(by)
            bheading = float(boss_snap.get("heading", 0.0))
            bstate = boss_snap.get("state", "PATROL")
            intro = float(boss_snap.get("intro_remaining", 0.0))

            if intro <= 0.0:
                if ptier >= TIER_GIANT:
                    # 反杀目标
                    if bstate == "STUNNED":
                        # STUNNED 全身可咬 → 直冲 boss 中心
                        return _to_unit_frame(bx - px, by - py, self.rng)
                    # 检查 player 当前是否已在尾后 240° 弧
                    rel_angle = math.atan2(py - by, px - bx)
                    if angle_in_arc(rel_angle, bheading + math.pi, BOSS_TAIL_ARC_HALF_RAD):
                        # 朝 boss 尾点
                        radius = float(boss_snap.get("radius", 90.0)) if "radius" in boss_snap else 90.0
                        # boss snapshot 没暴露 radius；用 1.2 倍粗略估算（90 * 1.2）
                        tail_x = bx - math.cos(bheading) * 90.0 * 1.2
                        tail_y = by - math.sin(bheading) * 90.0 * 1.2
                        return _to_unit_frame(tail_x - px, tail_y - py, self.rng)
                    # 还没绕到尾后 → 绕到尾后：朝尾点而非正面
                    tail_x = bx - math.cos(bheading) * 90.0 * 1.5
                    tail_y = by - math.sin(bheading) * 90.0 * 1.5
                    return _to_unit_frame(tail_x - px, tail_y - py, self.rng)
                else:
                    # player 尚未到 Tier-4 → 把 boss 当威胁
                    dx = px - bx
                    dy = py - by
                    dist2 = dx * dx + dy * dy
                    if dist2 < BOSS_FLEE_RADIUS * BOSS_FLEE_RADIUS:
                        return _to_unit_frame(dx, dy, self.rng)

        # ---- 4. 追最近猎物 ----
        nearest = None
        nearest_d2 = float("inf")
        for f in fishes:
            ftier = int(f.get("tier", 0))
            if ftier > ptier + 1:
                continue
            fx, fy = f["pos"]
            dx = float(fx) - px
            dy = float(fy) - py
            d2 = dx * dx + dy * dy
            if d2 < nearest_d2:
                nearest_d2 = d2
                nearest = (dx, dy)
        if nearest is not None and nearest_d2 < PREY_MAX_DIST * PREY_MAX_DIST:
            return _to_unit_frame(nearest[0], nearest[1], self.rng)

        # ---- 5. 漂移 ----
        return InputFrame(desired_dir=None)


def _to_unit_frame(dx: float, dy: float, rng) -> InputFrame:
    """把 (dx, dy) 单位化为 ``InputFrame``；零向量 / 非有限值时随机抖动。"""
    if not (math.isfinite(dx) and math.isfinite(dy)):
        # 退回到一个由 rng 决定的随机方向
        a = rng.uniform(-math.pi, math.pi)
        return InputFrame(desired_dir=Vec2(math.cos(a), math.sin(a)))
    n = math.hypot(dx, dy)
    if n <= 1e-9:
        a = rng.uniform(-math.pi, math.pi)
        return InputFrame(desired_dir=Vec2(math.cos(a), math.sin(a)))
    return InputFrame(desired_dir=Vec2(dx / n, dy / n))
