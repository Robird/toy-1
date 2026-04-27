"""fish/systems/growth.py — 玩家成长系统（M3-05）。

每帧检查 ``player.exp`` 是否跨过 ``TIER_THRESHOLDS[next_tier]``，若是则升级
``player.tier``，并通过 ``Player.grow_to`` 同步 ``radius`` / ``max_speed``，
最后触发 ``world.on_player_grow(old, new)`` hook。

EXP 来源：本步 **使用 fish-doc/mvp/01-core-loop.md §2 的 ``GROWTH_REWARD``**
``{0:1, 1:2, 2:5, 3:12, 4:30}``，由 ``CollisionSystem.step → world.on_fish_eaten``
在吃鱼瞬间累加到 ``player.exp``；本系统只负责跨阈值升级。

Tier 上限：``TIER_MAX = 4``（00 §4.1 / 01 §2）。超过后 exp 仍累加但不再升 tier。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fish.config.constants import TIER_MAX, TIER_THRESHOLDS

if TYPE_CHECKING:
    from fish.world import World


__all__ = ["GrowthSystem"]


class GrowthSystem:
    """无状态：每帧扫一次 player.exp，跨阈值时调 ``Player.grow_to`` 升级。"""

    def step(self, world: "World", dt: float) -> None:
        if dt <= 0.0:
            return
        if world.game_result is not None:
            return
        player = world.player
        if not player.alive:
            return

        # while 循环：理论上 1 帧内吃多条 fish 也可能跨多个阈值。
        while player.tier < TIER_MAX and player.exp >= float(
            TIER_THRESHOLDS[player.tier + 1]
        ):
            old = int(player.tier)
            player.grow_to(player.tier + 1)
            world.on_player_grow(old, int(player.tier))
