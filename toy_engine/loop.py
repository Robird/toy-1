"""GameLoop — 固定步长 + 输入/逻辑/渲染解耦的极简循环辅助 (toy-engine MVP / 02-scene.md)。

设计要点：
- 只封装"固定步长 + 累加器 + headless/GUI 共用 _tick_once"，**不**做 Scene/System/ECS、
  **不**内置暂停 UI（EQ1 已否决）、**不**感知 metrics（业务自行在 ``on_frame`` 钩子里调）。
- ``Steppable`` 为结构化协议；fish 的 ``World`` 直接满足即可。``HashableSteppable``
  额外要求 ``snapshot_hash``，仅 ``tools/run_headless.py --determinism-check`` 使用，
  普通 ``GameLoop`` 不调用。
- ``run_realtime`` 与 ``run_headless`` 共用 ``_tick_once``；前者用 ``time_source``
  （默认 ``time.perf_counter``）切片真实时间，后者每轮固定推进 ``dt``。
- 不 import ``pygame``、不持有 ``GeoCanvas``；headless 路径完全不触碰 display。
- ``effective_dt = dt * max(0.0, logic_dt_scale)``，仅传给 ``world.step``；帧节奏
  与 sim_time 上限语义见 02-scene.md §2.3。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol, runtime_checkable

from toy_engine.input import InputFrame, InputSource

__all__ = [
    "GameLoop",
    "Steppable",
    "HashableSteppable",
    "SnapshotLike",
]


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class SnapshotLike(Protocol):
    """``world.snapshot()`` 的最小只读形状（02-scene.md §2.2.1）。"""

    @property
    def player_pos(self) -> tuple[float, float]: ...  # pragma: no cover - protocol


@runtime_checkable
class Steppable(Protocol):
    """任何拥有 step / snapshot / is_finished 的对象均可被 ``GameLoop`` 驱动。

    ``@runtime_checkable`` 仅做粗粒度 ``isinstance`` 防呆；完整签名一致性靠
    类型检查、单测与 DoD 保证。
    """

    def step(self, dt: float, input_frame: InputFrame) -> None: ...  # pragma: no cover
    def snapshot(self) -> Any: ...  # pragma: no cover
    def is_finished(self) -> bool: ...  # pragma: no cover


@runtime_checkable
class HashableSteppable(Steppable, Protocol):
    """``--determinism-check`` 额外要求；普通 ``GameLoop`` 不调用。"""

    def snapshot_hash(self) -> str: ...  # pragma: no cover


# ---------------------------------------------------------------------------
# GameLoop
# ---------------------------------------------------------------------------


# 防止断点 / 断网恢复时单帧 elapsed 过大导致一次性追几百帧。
_REALTIME_MAX_ELAPSED = 0.25


class GameLoop:
    """固定步长循环辅助。

    Parameters
    ----------
    world:
        满足 ``Steppable`` 的对象（fish 中即 ``World``）。
    input_source:
        每个逻辑帧调用一次 ``poll(snapshot)``。
    dt:
        固定逻辑步长，默认 1/60。
    on_frame:
        每个逻辑帧 ``step`` 之后回调（参数为 step 后的 snapshot）；renderer /
        recorder / metrics 三者共用此钩子，由业务自行组合。
    max_sim_seconds:
        仿真时间上限（基于 ``effective_dt`` 累计）。``None`` 表示不限。
    max_steps_per_frame:
        spiral-of-death 防护；默认 8 可覆盖 100ms 卡顿追帧。
    time_source:
        ``run_realtime`` 用的时钟，默认 ``time.perf_counter``；测试可注入。
        ``run_headless`` 不读时钟。
    speed:
        真实时间倍率：``0`` = 暂停、``2`` = 快进。必须 ``>= 0``。
    logic_dt_scale:
        ``float`` 或 ``Callable[[snapshot], float]``；用于把世界内 dt 缩放
        （如 fish 死亡慢动作返回 0.3）。
    """

    def __init__(
        self,
        world: Steppable,
        input_source: InputSource,
        *,
        dt: float = 1.0 / 60.0,
        on_frame: Callable[[Any], None] | None = None,
        max_sim_seconds: float | None = None,
        max_steps_per_frame: int = 8,
        time_source: Callable[[], float] | None = None,
        speed: float = 1.0,
        logic_dt_scale: float | Callable[[Any], float] = 1.0,
    ) -> None:
        if dt <= 0.0:
            raise ValueError(f"GameLoop.dt must be > 0, got {dt!r}")
        if max_steps_per_frame < 1:
            raise ValueError(
                f"GameLoop.max_steps_per_frame must be >= 1, got {max_steps_per_frame!r}"
            )
        if max_sim_seconds is not None and max_sim_seconds < 0.0:
            raise ValueError(
                f"GameLoop.max_sim_seconds must be >= 0 or None, got {max_sim_seconds!r}"
            )
        if speed < 0.0:
            raise ValueError(f"GameLoop.speed must be >= 0, got {speed!r}")

        if not isinstance(world, Steppable):
            raise TypeError(
                "GameLoop.world must implement Steppable (step / snapshot / is_finished)"
            )

        self._world = world
        self._input_source = input_source
        self._dt = float(dt)
        self._on_frame = on_frame
        self._max_sim_seconds = max_sim_seconds
        self._max_steps_per_frame = int(max_steps_per_frame)
        self._time_source: Callable[[], float] = time_source or time.perf_counter
        self._speed = float(speed)
        self._logic_dt_scale = logic_dt_scale

        # 已运行统计（也供测试断言）。
        self._frame_idx: int = 0
        self._sim_time: float = 0.0

    # ------------------------------------------------------------------
    # 只读属性
    # ------------------------------------------------------------------

    @property
    def dt(self) -> float:
        return self._dt

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def frame_idx(self) -> int:
        return self._frame_idx

    @property
    def sim_time(self) -> float:
        return self._sim_time

    # ------------------------------------------------------------------
    # 控制点
    # ------------------------------------------------------------------

    def set_speed(self, speed: float) -> None:
        """调整真实时间倍率；``0`` 暂停，``> 0`` 继续。"""
        if speed < 0.0:
            raise ValueError(f"speed must be >= 0, got {speed!r}")
        self._speed = float(speed)

    def step_once(self, n: int = 1) -> None:
        """调试 / 暂停单步：固定推进 ``n`` 个逻辑帧。

        与 ``run_*`` 共用 ``_tick_once``；遇到 ``world.is_finished()`` 即停止，
        但不再检查 ``max_sim_seconds``（这是一个显式的调试入口）。
        """
        if n < 0:
            raise ValueError(f"step_once n must be >= 0, got {n!r}")
        for _ in range(n):
            if self._world.is_finished():
                return
            self._tick_once()

    # ------------------------------------------------------------------
    # 共享 tick
    # ------------------------------------------------------------------

    def _tick_once(self) -> float:
        """执行一次固定步长 tick；返回本帧的 ``effective_dt``。"""
        pre = self._world.snapshot()
        input_frame = self._input_source.poll(pre)

        scale_raw = self._logic_dt_scale
        if callable(scale_raw):
            scale = float(scale_raw(pre))
        else:
            scale = float(scale_raw)
        if scale < 0.0:
            scale = 0.0
        effective_dt = self._dt * scale

        self._world.step(effective_dt, input_frame)
        self._frame_idx += 1
        self._sim_time += effective_dt

        if self._on_frame is not None:
            post = self._world.snapshot()
            self._on_frame(post)

        return effective_dt

    # ------------------------------------------------------------------
    # 钩子：默认 yield 给宿主；测试可子类化覆盖。
    # ------------------------------------------------------------------

    def _yield_to_host(self) -> None:
        """realtime 模式下让出 CPU / 处理宿主 GUI tick；不进入 headless 路径。

        默认走 ``time.sleep(0)``：在大多数 OS 上等价于一次主动调度让步，避免
        无 vsync / 无渲染时 busy spin 占满核心；不影响 ``time_source``。
        """
        time.sleep(0)

    # ------------------------------------------------------------------
    # run_realtime
    # ------------------------------------------------------------------

    def run_realtime(self) -> None:
        """GUI 模式：用 ``time_source`` 驱动，固定步长 + 累加器。

        与 ``run_headless`` 共用 ``_tick_once``，差别只在"时间从哪里来"。
        """
        dt = self._dt
        acc = 0.0
        last = self._time_source()

        while not self._world.is_finished():
            cur = self._time_source()
            elapsed = cur - last
            if elapsed < 0.0:
                elapsed = 0.0
            last = cur

            if self._speed == 0.0:
                acc = 0.0
                self._yield_to_host()
                continue

            inc = elapsed * self._speed
            if inc > _REALTIME_MAX_ELAPSED:
                inc = _REALTIME_MAX_ELAPSED
            acc += inc

            steps = 0
            stopped_by_cap = False
            while (
                acc >= dt
                and steps < self._max_steps_per_frame
                and not self._world.is_finished()
            ):
                self._tick_once()
                acc -= dt
                steps += 1
                if (
                    self._max_sim_seconds is not None
                    and self._sim_time >= self._max_sim_seconds
                ):
                    stopped_by_cap = True
                    break

            if stopped_by_cap:
                return

            if steps == self._max_steps_per_frame and acc >= dt:
                # spiral-of-death 防护：丢弃积压，优先保证下一帧交互。
                acc = 0.0
            elif acc < dt:
                self._yield_to_host()

    # ------------------------------------------------------------------
    # run_headless
    # ------------------------------------------------------------------

    def run_headless(self) -> None:
        """Headless 模式：不睡眠、不读真实时钟，每轮固定推进 ``dt``。"""
        while not self._world.is_finished():
            self._tick_once()
            if (
                self._max_sim_seconds is not None
                and self._sim_time >= self._max_sim_seconds
            ):
                break
