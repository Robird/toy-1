"""fish/systems/spawner.py — 普通鱼刷新系统（M3-04）。

实现 fish-doc/mvp/02-fish-ecosystem.md §4 的"按 population_target 刷新到屏幕
外缘"的基础版。**不**做 Boss 刷新（M3-07）；**不**做 §4 末尾的"屏内 0 可吃
目标 → 强制就近 spawn"硬约束兜底（生成器层面的事，留 M3-06）。

阶段切换由 LevelDirector（M3-06）接入。本步先用
``cfg.phases[Phase.WARMUP].population_target`` 作占位。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from toy_engine.geom import Vec2
from toy_engine.rng import SeededRng

from fish.config.constants import (
    Phase,
    SPAWNER_CHECK_INTERVAL_S,
    SPAWNER_EDGE_MARGIN,
    WORLD_H,
    WORLD_W,
)
from fish.entities.fish import Fish

if TYPE_CHECKING:
    from fish.world import World


__all__ = ["Spawner"]


# 屏外四条边：left / right / top / bottom。choice 用稳定列表保证决定性。
_EDGES: tuple[str, ...] = ("left", "right", "top", "bottom")


class Spawner:
    """每 ``SPAWNER_CHECK_INTERVAL_S`` 秒检查一次：若某 tier 在场数 < target，
    则在屏幕外缘生成一条朝屏内方向的 fish。

    所有随机决策都走 ``self.rng``（``world.rng.spawn("spawner")``），保证
    snapshot_hash 决定性。
    """

    def __init__(self, world: "World", rng: SeededRng) -> None:
        self.world = world
        self.rng: SeededRng = rng
        self._time_since_last_check: float = 0.0

    def step(self, world: "World", dt: float) -> None:
        if dt <= 0.0:
            return
        self._time_since_last_check += dt
        if self._time_since_last_check < SPAWNER_CHECK_INTERVAL_S:
            return
        self._time_since_last_check = 0.0

        # TODO M3-06：接入 LevelDirector 取当前阶段的 population_target；
        # 当前固定用 WARMUP（保留首阶段语义：仅 Tier-1）。
        target = world.config.phases[Phase.WARMUP].population_target

        # 当前每 tier 在场计数
        counts: dict[int, int] = {t: 0 for t in target}
        for f in world.fishes:
            if f.alive and f.tier in counts:
                counts[f.tier] += 1

        # 按 tier 升序遍历（决定性）；每次 check 每 tier 最多刷一条，避免一次性
        # 把屏内塞满，让画面节奏更自然。
        for tier in sorted(target):
            need = int(target[tier]) - counts[tier]
            if need <= 0:
                continue
            self._spawn_one(world, tier)

    # ------------------------------------------------------------------
    def _spawn_one(self, world: "World", tier: int) -> None:
        """从屏外某条边缘生成一条该 tier 的 fish，朝屏内某点。"""
        edge = self.rng.choice(_EDGES)
        margin = SPAWNER_EDGE_MARGIN
        if edge == "left":
            x = -margin
            y = self.rng.uniform(0.0, float(WORLD_H))
            heading = 0.0  # 朝右
        elif edge == "right":
            x = float(WORLD_W) + margin
            y = self.rng.uniform(0.0, float(WORLD_H))
            heading = math.pi  # 朝左
        elif edge == "top":
            x = self.rng.uniform(0.0, float(WORLD_W))
            y = -margin
            heading = math.pi / 2.0  # 朝下（屏幕坐标 y 向下）
        else:  # bottom
            x = self.rng.uniform(0.0, float(WORLD_W))
            y = float(WORLD_H) + margin
            heading = -math.pi / 2.0  # 朝上

        eid = world.alloc_eid()
        # 每条 fish 拿一份独立 SeededRng 子流，FishAI 的随机决策走它，保证
        # 与 spawner 流隔离 + 与 eid 强绑定（重放时 eid 顺序稳定）。
        fish_rng = self.rng.spawn(f"fish_{eid}")
        fish = Fish.spawn(
            eid=eid,
            tier=tier,
            pos=Vec2(x, y),
            heading=heading,
            rng=fish_rng,
        )
        world.fishes.append(fish)
        world.entities.append(fish)
