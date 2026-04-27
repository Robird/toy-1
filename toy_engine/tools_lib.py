"""tools_lib — ``GameFactory`` 协议与 ``tools/*.py`` 共用样板 (toy-engine MVP / 08-tools.md).

提供：
- :class:`GameFactory` ``runtime_checkable`` Protocol（08-tools.md §2 五方法签名）
- :func:`load_factory`：按 CLI > env > MVP 默认值的优先级解析 ``MOD:ATTR`` 规范
- :func:`run_single_headless`：跑一局 headless，返回 ``MetricsCollector.final_report()``
- :func:`aggregate_runs`：08-tools.md §3.2 聚合 schema

引擎仅提供"跑一局"样板；业务必须通过 :class:`GameFactory` 注入 World/Bot/序列化能力。
"""

from __future__ import annotations

import importlib
import os
import statistics
import time
from typing import Any, Callable, Protocol, runtime_checkable

from toy_engine.input import BotInputBase, InputFrame, InputSource
from toy_engine.loop import GameLoop, Steppable
from toy_engine.metrics import MetricsCollector
from toy_engine.recorder import Recorder
from toy_engine.rng import SeededRng

__all__ = [
    "GameFactory",
    "FactoryResolutionError",
    "load_factory",
    "run_single_headless",
    "aggregate_runs",
    "DEFAULT_FACTORY_SPEC",
    "DEFAULT_MAX_SIM_SECONDS",
    "DEFAULT_DT",
]


#: MVP 仓库默认 factory（fish 项目尚未实现，仅作为 fallback 字符串占位）。
DEFAULT_FACTORY_SPEC = "fish.__main__:FISH_FACTORY"
#: 单局仿真上限秒数（与 fish-doc 对齐）。
DEFAULT_MAX_SIM_SECONDS = 180.0
#: 默认逻辑步长 1/60。
DEFAULT_DT = 1.0 / 60.0


# ---------------------------------------------------------------------------
# GameFactory 协议
# ---------------------------------------------------------------------------


@runtime_checkable
class GameFactory(Protocol):
    """业务必须实现的 5 方法构造器（08-tools.md §2）。

    ``@runtime_checkable`` 仅做粗粒度 ``isinstance`` 防呆；签名一致性靠类型
    检查与单测保证。

    Optional hook (未加入 Protocol 本体以保持 ``isinstance`` 向后兼容)：

    .. code-block:: python

        def bind_metrics(self, world: Any, metrics: MetricsCollector) -> None:
            ...

    若 factory 提供该方法，:func:`run_single_headless` 将在创建世界后、循环启动前
    调用一次，同时将 ``metrics.tick(dt)`` 的责任交给业务侧（避免重复 tick）。
    未提供时路径与以前完全一致。
    """

    def make_level_config(self, *, seed: int, difficulty: float) -> Any: ...  # pragma: no cover
    def make_world(self, *, level_config: Any, seed: int) -> Any: ...  # pragma: no cover
    def make_bot(
        self, *, name: str, world: Any, rng: SeededRng
    ) -> InputSource: ...  # pragma: no cover
    def serialize_config(self, level_config: Any) -> dict: ...  # pragma: no cover
    def deserialize_config(self, raw: dict) -> Any: ...  # pragma: no cover


class FactoryResolutionError(RuntimeError):
    """``MOD:ATTR`` 解析或 import 失败。"""


def load_factory(spec: str | None = None) -> GameFactory:
    """按 CLI > env (``TOY_ENGINE_GAME_FACTORY``) > 默认值解析 factory。

    解析规则严格按 ``MOD:ATTR`` 字符串走 ``importlib.import_module(MOD)`` +
    ``getattr(module, ATTR)``；MVP 不使用 packaging entry_points。
    """
    if spec is None or spec == "":
        spec = os.environ.get("TOY_ENGINE_GAME_FACTORY") or DEFAULT_FACTORY_SPEC
    if ":" not in spec:
        raise FactoryResolutionError(
            f"factory spec must look like 'MOD:ATTR', got {spec!r}"
        )
    mod_name, attr = spec.split(":", 1)
    if not mod_name or not attr:
        raise FactoryResolutionError(
            f"factory spec must look like 'MOD:ATTR', got {spec!r}"
        )
    try:
        module = importlib.import_module(mod_name)
    except Exception as exc:  # noqa: BLE001 - re-raise as domain error
        raise FactoryResolutionError(
            f"failed to import factory module {mod_name!r}: {exc}"
        ) from exc
    try:
        factory = getattr(module, attr)
    except AttributeError as exc:
        raise FactoryResolutionError(
            f"module {mod_name!r} has no attribute {attr!r}"
        ) from exc
    return factory


# ---------------------------------------------------------------------------
# 内部 input wrappers
# ---------------------------------------------------------------------------


class _IdleInput:
    """无 ``--bot`` 时使用的静默输入源（永远 ``desired_dir=None``）。"""

    def poll(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        return InputFrame(desired_dir=None, dash=False)


class _RecordingInputSource:
    """包一层 ``Recorder.record(frame_idx, frame)``；不破坏内层语义。"""

    __slots__ = ("_inner", "_recorder", "_idx")

    def __init__(self, inner: InputSource, recorder: Recorder) -> None:
        self._inner = inner
        self._recorder = recorder
        self._idx = 0

    def poll(self, world_state: Any) -> InputFrame:
        frame = self._inner.poll(world_state)
        self._recorder.record(self._idx, frame)
        self._idx += 1
        return frame


def _build_input_source(
    factory: GameFactory,
    *,
    bot_name: str | None,
    world: Any,
    seed: int,
) -> InputSource:
    if bot_name is None or bot_name == "":
        return _IdleInput()
    rng = SeededRng(seed).spawn("bot")
    bot = factory.make_bot(name=bot_name, world=world, rng=rng)
    if not isinstance(bot, (BotInputBase, _IdleInput)) and not hasattr(bot, "poll"):
        raise TypeError(
            f"factory.make_bot must return an InputSource, got {type(bot).__name__}"
        )
    return bot


# ---------------------------------------------------------------------------
# run_single_headless
# ---------------------------------------------------------------------------


def run_single_headless(
    factory: GameFactory,
    *,
    seed: int,
    difficulty: float,
    bot_name: str | None = None,
    max_sim_seconds: float | None = DEFAULT_MAX_SIM_SECONDS,
    dt: float = DEFAULT_DT,
    record_path: str | None = None,
    on_frame_extra: Callable[[Any], None] | None = None,
) -> tuple[dict[str, Any], float]:
    """跑一局 headless 游戏。

    返回 ``(metrics_envelope, wall_time_s)``；其中 envelope 由
    :class:`MetricsCollector` 产出（见 05-metrics.md §3）。

    若业务未在 ``World.step / on_frame`` 内通过 metrics 写 ``result``，本函数
    在收尾时根据 ``world.is_finished()`` / ``sim_time vs max_sim_seconds`` 自动
    填 ``DONE`` / ``TIMEOUT``，避免聚合时全是 ``None``。

    ``record_path`` 非空时同时写出录像（仅当至少录到 1 帧）。
    """
    level_config = factory.make_level_config(seed=seed, difficulty=difficulty)
    world = factory.make_world(level_config=level_config, seed=seed)
    if not isinstance(world, Steppable):
        raise TypeError(
            "factory.make_world(...) must return a Steppable "
            "(step / snapshot / is_finished); got "
            f"{type(world).__name__}"
        )

    input_source: InputSource = _build_input_source(
        factory, bot_name=bot_name, world=world, seed=seed
    )

    metrics = MetricsCollector()
    metrics.set_scalar("seed", seed, top_level=True)
    metrics.set_scalar("difficulty", difficulty, top_level=True)

    # Optional hook: 业务接管 metrics tick 所有权 (EQ12 / 08-tools.md §2)
    bind = getattr(factory, "bind_metrics", None)
    business_owns_tick = False
    if callable(bind):
        bind(world, metrics)
        business_owns_tick = True

    recorder: Recorder | None = None
    if record_path is not None:
        recorder = Recorder(
            level_config,
            seed=seed,
            config_serializer=factory.serialize_config,
        )
        input_source = _RecordingInputSource(input_source, recorder)

    def _on_frame(snapshot: Any) -> None:
        if not business_owns_tick:
            metrics.tick(dt)
        if on_frame_extra is not None:
            on_frame_extra(snapshot)

    loop = GameLoop(
        world,
        input_source,
        dt=dt,
        on_frame=_on_frame,
        max_sim_seconds=max_sim_seconds,
    )

    t0 = time.perf_counter()
    loop.run_headless()
    wall = time.perf_counter() - t0

    # 业务未给出 result → 兜底
    snapshot_envelope = metrics.final_report()
    if snapshot_envelope.get("result") is None:
        if (
            max_sim_seconds is not None
            and not world.is_finished()
            and loop.sim_time + 1e-9 >= max_sim_seconds
        ):
            metrics.finish("TIMEOUT")
        else:
            metrics.finish("DONE")

    if recorder is not None and recorder.sparse_frames:
        recorder.save(record_path)

    return metrics.final_report(), wall


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------


def _stats(xs: list[float], with_p95: bool = True) -> dict[str, float]:
    if not xs:
        return {}
    out: dict[str, float] = {
        "mean": statistics.fmean(xs),
        "p50": statistics.median(xs),
    }
    if with_p95:
        sorted_xs = sorted(xs)
        # 稳健的近似 p95：(n-1) * 0.95 取最近邻，n=1 退化为唯一值
        k = int(round(0.95 * (len(sorted_xs) - 1)))
        k = max(0, min(len(sorted_xs) - 1, k))
        out["p95"] = sorted_xs[k]
    return out


def aggregate_runs(
    per_run: list[dict[str, Any]],
    wall_times: list[float],
    *,
    difficulty: float,
    seeds: list[int],
) -> dict[str, Any]:
    """把 N 个 :func:`run_single_headless` 输出聚合成 08-tools.md §3.2 schema。

    - ``fail_rate`` = ``count(result in {'DEAD', 'FAIL'}) / n_runs``
    - ``victory_rate`` / ``timeout_rate`` 分别按 ``'VICTORY'`` / ``'TIMEOUT'`` 命中
    - ``aggregate.metrics.<name>`` 自动按 union 收集所有出现过的 ``metrics`` 标量
    - ``aggregate.events.<name>.mean_count`` 同样按 union
    - 每条单局缺失某指标不报错，跳过
    """
    n = len(per_run)
    results = [r.get("result") for r in per_run]
    durations: list[float] = []
    for r in per_run:
        v = r.get("duration_s")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            durations.append(float(v))

    metric_names: set[str] = set()
    for r in per_run:
        for k in (r.get("metrics") or {}).keys():
            metric_names.add(k)
    metrics_agg: dict[str, dict[str, float]] = {}
    for name in sorted(metric_names):
        xs: list[float] = []
        for r in per_run:
            v = (r.get("metrics") or {}).get(name)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                xs.append(float(v))
        if xs:
            metrics_agg[name] = _stats(xs, with_p95=True)

    event_names: set[str] = set()
    for r in per_run:
        for k in (r.get("events") or {}).keys():
            event_names.add(k)
    events_agg: dict[str, dict[str, float]] = {}
    for name in sorted(event_names):
        counts = [
            float((r.get("events") or {}).get(name, {}).get("count", 0))
            for r in per_run
        ]
        events_agg[name] = {"mean_count": statistics.fmean(counts) if counts else 0.0}

    def _rate(predicate: Callable[[Any], bool]) -> float:
        if n == 0:
            return 0.0
        return sum(1 for x in results if predicate(x)) / n

    aggregate: dict[str, Any] = {
        "fail_rate": _rate(lambda x: x in ("DEAD", "FAIL")),
        "victory_rate": _rate(lambda x: x == "VICTORY"),
        "timeout_rate": _rate(lambda x: x == "TIMEOUT"),
        "duration_s": _stats(durations, with_p95=True),
        "metrics": metrics_agg,
        "events": events_agg,
    }

    return {
        "n_runs": n,
        "difficulty": difficulty,
        "seeds": list(seeds),
        "wall_time_s": {
            "total": float(sum(wall_times)),
            "mean_per_run": (float(sum(wall_times)) / n) if n else 0.0,
        },
        "aggregate": aggregate,
        "per_run": [
            {
                "seed": s,
                "result": r.get("result"),
                "duration_s": r.get("duration_s"),
                "metrics_path": None,
            }
            for s, r in zip(seeds, per_run)
        ],
    }
