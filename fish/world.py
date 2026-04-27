"""fish/world.py — World 骨架 + GameResult 枚举（M3-02/M3-03）。

实现 toy_engine ``Steppable`` 协议（见 toy-engine/mvp/02-scene.md §2.2.1）：
``step / snapshot / is_finished``，外加 fish 业务侧契约 ``snapshot_hash``
（见 toy-engine/mvp/08-tools.md §5；fish-doc/mvp/progress.md 接口契约 #3）。

当前实现范围：
- M3-03 已接入 Player 与 MovementSystem；Fish/Boss/AI/Spawner/Collision 仍留后续步骤。
- ``snapshot()["player_pos"]`` 返回玩家实际位置，供 ``KeyboardMouseInput`` 计算方向。
- ``game_result`` 仍由后续 M3-05/07 的死亡 / 胜利判定写入。
"""

from __future__ import annotations

import enum
import hashlib
import json
import math
from typing import Any

from toy_engine.input import InputFrame
from toy_engine.rng import SeededRng

from fish.ai.fish_ai import FishAI
from fish.config.level_config import LevelConfig
from fish.entities.fish import Fish
from fish.entities.player import Player
from fish.systems.movement import MovementSystem
from fish.systems.spawner import Spawner


# ---------------------------------------------------------------------------
# GameResult
# ---------------------------------------------------------------------------


class GameResult(enum.Enum):
    """单局终态。

    与 fish-doc/mvp/01-core-loop.md §4 完全对齐：
      - ``RUNNING``：游戏进行中（M3-02 阶段不会出现在 snapshot 中；snapshot
        用 ``game_result=None`` 表达"进行中"以便 JSON 友好）
      - ``DEAD``：被任何 Tier > self 的实体吃掉
      - ``VICTORY``：反杀 Boss 完成（Boss.hp <= 0）
      - ``TIMEOUT``：到达硬上限 180s 仍未通关（用于 bot 防死循环）
    """

    RUNNING = "RUNNING"
    DEAD = "DEAD"
    VICTORY = "VICTORY"
    TIMEOUT = "TIMEOUT"


# ---------------------------------------------------------------------------
# Snapshot 序列化辅助
# ---------------------------------------------------------------------------


# 浮点字段在 snapshot_hash 时统一规范化到 6 位小数，避免不同平台 / 累加顺序
# 引入末位差异（关键：sim_time = N * DT 在 60Hz 下并非精确十进制）。
_HASH_FLOAT_PRECISION: int = 6
_HASH_MAX_DEPTH: int = 64


def _normalize_for_hash(obj: Any, *, _depth: int = 0) -> Any:
    """递归把 snapshot 中的浮点 / 枚举 / Vec2-like 转成稳定可哈希形式。

    非有限浮点会被转成明确字符串哨兵，避免 ``json.dumps`` 输出非标准
    ``NaN`` / ``Infinity``；过深嵌套会清晰报错，避免递归栈溢出。
    """
    if _depth > _HASH_MAX_DEPTH:
        raise ValueError(
            f"snapshot is nested deeper than {_HASH_MAX_DEPTH} levels; "
            "refuse to produce an unstable hash"
        )
    if isinstance(obj, float):
        if math.isnan(obj):
            return "__float__:nan"
        if math.isinf(obj):
            return "__float__:+inf" if obj > 0.0 else "__float__:-inf"
        return round(obj, _HASH_FLOAT_PRECISION)
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, str) or obj is None:
        return obj
    if isinstance(obj, enum.Enum):
        return obj.name
    if isinstance(obj, dict):
        return {
            str(k): _normalize_for_hash(v, _depth=_depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [_normalize_for_hash(v, _depth=_depth + 1) for v in obj]
    # Vec2 / 其它：按 (x, y) 兜底；进一步类型由后续步骤接入实体后补全。
    if hasattr(obj, "x") and hasattr(obj, "y"):
        return [
            _normalize_for_hash(float(obj.x), _depth=_depth + 1),
            _normalize_for_hash(float(obj.y), _depth=_depth + 1),
        ]
    return repr(obj)


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


class World:
    """fish 业务世界骨架。

    满足 toy_engine ``Steppable`` 协议；可被 ``GameLoop`` 直接驱动：
    ``isinstance(world, Steppable) is True``。

    M3-03 起包含一个玩家实体，并在 ``step`` 中调用 ``MovementSystem`` 推进
    玩家移动；其它业务系统由后续步骤接入。
    """

    def __init__(self, config: LevelConfig, rng: SeededRng) -> None:
        self.config: LevelConfig = config
        self.rng: SeededRng = rng

        # 计时
        self.frame_count: int = 0
        self.elapsed_s: float = 0.0

        # 实体 ID 分配器（稳定的递增整数；snapshot 排序与 hash 依赖之）
        self._next_eid: int = 0

        # 玩家：M3-03 起在世界中央生成
        self.player: Player = Player.from_config(config, eid=self.alloc_eid())

        # 普通鱼列表（M3-04 起由 Spawner 追加；M3-05 起由碰撞淘汰）
        self.fishes: list[Fish] = []

        # 实体表：始终包含 player + fishes，使 snapshot/碰撞统一遍历。
        self.entities: list = [self.player]

        # 终态；M3-05 / M3-07 在死亡 / 反杀判定中写入
        self.game_result: GameResult | None = None

        # 最近一帧 InputFrame；供 MovementSystem 消费
        self.last_input_frame: InputFrame | None = None
        # 最近一次 step 的 effective_dt；供 metrics / 慢动作回溯
        self.last_effective_dt: float = 0.0

        # 系统实例（一次构造、复用）
        self._movement = MovementSystem()
        self._fish_ai = FishAI()
        self._spawner = Spawner(self, rng.spawn("spawner"))

        # 关卡总时长（仅供 ``is_finished`` 占位判定使用）。
        # （留在末尾，避免与 system 初始化顺序耦合。）
        # NOTE: 下方注释保留原文。
        # NOTE: BOSS / REVENGE 阶段在 fish-doc 04 §2 中为事件驱动
        # （duration_s == 0 表示直到 VICTORY/DEAD），因此这里的 sum 仅是
        # WARMUP+PRESSURE 的"线性时长"；M3-06/07 会改用 LevelDirector 推进
        # 阶段切换并在那里更新终态判定。
        self._total_duration_s: float = sum(
            p.duration_s for p in config.phases.values()
        )

    # ------------------------------------------------------------------
    # Steppable
    # ------------------------------------------------------------------

    def step(self, dt: float, input_frame: InputFrame) -> None:
        """推进一帧。

        M3-04 起调用顺序固定为：spawner → fish_ai（按 eid 升序） →
        movement（玩家+所有 fish）→ 计时器累加。该顺序保证 snapshot_hash
        在相同 seed 下逐帧可重现（契约 #3）。
        """
        self.last_input_frame = input_frame
        self.last_effective_dt = float(dt)
        dt_f = float(dt)

        self._spawner.step(self, dt_f)
        # AI 按 eid 升序遍历，避免 list 顺序变化影响决定性
        for fish in sorted(self.fishes, key=lambda f: f.eid):
            self._fish_ai.step(fish, self, dt_f)
        self._movement.step(self, dt_f)

        self.frame_count += 1
        self.elapsed_s += float(dt)

    def snapshot(self) -> dict:
        """返回当前世界的只读快照（dict 形态）。

        必须包含的契约字段（见 fish-doc/mvp/progress.md 接口契约 #2/#3）：
                    - ``player_pos: tuple[float, float]`` —— 实际玩家位置
                        （``KeyboardMouseInput`` 依赖此字段计算鼠标方向）
          - ``frame_count: int``
          - ``elapsed_s: float``
                    - ``entities: list[dict]`` —— 当前至少包含 player
                    - ``game_result: GameResult | None`` —— 进行中为 None

                返回 dict 而非 frozen dataclass：M3 阶段尚未稳定字段集合，dict
        便于后续步骤平滑追加；待 M3-10 收尾时再视情况升级为 frozen dataclass。
        """
        # entities 按 eid 升序输出，使 snapshot_hash 不依赖 list 插入顺序。
        ents = sorted(self.entities, key=lambda e: e.eid)
        return {
            "player_pos": (float(self.player.pos.x), float(self.player.pos.y)),
            "frame_count": self.frame_count,
            "elapsed_s": self.elapsed_s,
            "entities": [self._entity_snapshot(e) for e in ents],
            "game_result": self.game_result.name if self.game_result is not None else None,
        }

    # ------------------------------------------------------------------
    # 内部 helper
    # ------------------------------------------------------------------

    def alloc_eid(self) -> int:
        """分配下一个稳定递增 eid。被 World 自身（player）与 Spawner 共用。"""
        eid = self._next_eid
        self._next_eid += 1
        return eid

    def _entity_snapshot(self, ent) -> dict:
        """把单个 Entity 序列化为 snapshot dict。

        Player / Fish 携带额外业务字段（tier/heading/state 等）；其它实体只
        暴露通用字段。所有 Vec2 走 ``[x, y]`` 列表表示，便于稳定哈希。
        """
        if isinstance(ent, Player):
            kind = "player"
        elif isinstance(ent, Fish):
            kind = "fish"
        else:
            kind = "entity"
        d = {
            "eid": int(ent.eid),
            "kind": kind,
            "pos": [float(ent.pos.x), float(ent.pos.y)],
            "vel": [float(ent.vel.x), float(ent.vel.y)],
            "radius": float(ent.radius),
            "alive": bool(ent.alive),
        }
        if isinstance(ent, Player):
            d["heading"] = float(ent.heading)
            d["tier"] = int(ent.tier)
        elif isinstance(ent, Fish):
            d["heading"] = float(ent.heading)
            d["tier"] = int(ent.tier)
            d["state"] = ent.state.name
        return d

    def snapshot_hash(self) -> str:
        """返回当前 snapshot 的稳定哈希。

        见 toy-engine/mvp/08-tools.md §5：``tools/run_headless.py
        --determinism-check`` 比对帧序列时使用。

        规范化策略：
          1. 取 ``self.snapshot()``；
          2. 经 ``_normalize_for_hash`` 递归规范化（浮点四舍五入到 6 位小数；
             枚举 → name；Vec2 → ``[x, y]``；嵌套 dict 键统一为 str）；
          3. ``json.dumps(..., sort_keys=True)`` + ``sha1.hexdigest()``。

        浮点规范化保证不同平台 / 同一线性步长下不同累加顺序得到的
        ``elapsed_s`` 在末位 ULP 抖动时仍输出同一哈希。
        """
        snap = self.snapshot()
        canon = _normalize_for_hash(snap)
        payload = json.dumps(
            canon,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def is_finished(self) -> bool:
        """是否到达终态。

        M3-02 占位规则：
          - ``game_result`` 已写入 → True
          - ``elapsed_s >= total_duration``（WARMUP+PRESSURE 时长之和）→ True

        正式终态判定（DEAD / VICTORY / TIMEOUT 三类）由 M3-05 / M3-07 接入。
        """
        if self.game_result is not None:
            return True
        if self._total_duration_s > 0.0 and self.elapsed_s >= self._total_duration_s:
            return True
        return False
