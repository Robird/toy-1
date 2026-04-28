"""fish/factory.py — FishGameFactory（M3-10，闭合 EQ12）。

实现 ``toy_engine.tools_lib.GameFactory`` 协议（**以代码为准**；签名为：
``make_level_config / make_world / make_bot / serialize_config /
deserialize_config``，与 toy-engine/mvp/08-tools.md §2 文档示意有差异，详见
fish-doc/mvp/progress.md M3 实施期发现 #23）。

附加 optional hook ``bind_metrics``（08-tools.md §2.1，EQ12）：

  - 创建 ``FishMetricsListener`` + 注册 World event listener
  - wrap ``world.step`` 在每帧推完后调 ``listener.on_frame_end(dt)`` —— 这是
    "业务接管 metrics.tick" 的具体落实方式
  - 终态时 listener 自动调一次 ``finalize`` 写 envelope；``run_single_headless``
    的 fallback ``finish('TIMEOUT'|'DONE')`` 因 ``result`` 已写而 no-op
"""

from __future__ import annotations

import warnings
from dataclasses import asdict
from typing import Any

from toy_engine.input import InputSource
from toy_engine.metrics import MetricsCollector
from toy_engine.rng import SeededRng

from fish.ai.bot_player import BotInput
from fish.config.constants import Phase
from fish.config.level_config import BossConfig, LevelConfig, PhaseConfig
from fish.io.metrics_adapter import FishMetricsListener
from fish.systems.level_generator import LevelGenerator
from fish.world import World


class FishGameFactory:
    """fish 业务的 GameFactory 实现。"""

    # ------------------------------------------------------------------
    # GameFactory protocol (toy_engine.tools_lib)
    # ------------------------------------------------------------------

    def make_level_config(self, *, seed: int, difficulty: float) -> LevelConfig:
        rng = SeededRng(seed=int(seed))
        return LevelGenerator.generate(seed=int(seed), difficulty=float(difficulty), rng=rng)

    def make_world(self, *, level_config: LevelConfig, seed: int) -> World:
        rng = SeededRng(seed=int(level_config.seed))
        return World(level_config, rng)

    def make_bot(self, *, name: str, world: Any, rng: SeededRng) -> InputSource:  # noqa: ARG002
        if name == "heuristic":
            return BotInput(rng)
        raise ValueError(f"unknown bot name: {name!r}")

    def serialize_config(self, level_config: LevelConfig) -> dict:
        return _level_config_to_dict(level_config)

    def deserialize_config(self, raw: dict) -> LevelConfig:
        return _level_config_from_dict(raw)

    # ------------------------------------------------------------------
    # Optional hook (EQ12 闭合点)
    # ------------------------------------------------------------------

    def bind_metrics(self, world: World, metrics: MetricsCollector) -> None:
        """注入 metrics：register listener + wrap ``world.step`` 接管 tick +
        wrap ``metrics.finish`` 保证 fallback 路径也能写入 5 大指标。
        """
        listener = FishMetricsListener(world, metrics)
        world.register_listener(listener.handle)

        original_step = world.step

        def wrapped_step(dt, input_frame):
            original_step(dt, input_frame)
            try:
                listener.on_frame_end(dt)
            except Exception as exc:  # noqa: BLE001
                warnings.warn(
                    "Fish metrics listener failed during frame-end hook: "
                    f"{exc!r}",
                    RuntimeWarning,
                    stacklevel=2,
                )

        world.step = wrapped_step  # type: ignore[method-assign]

        # 包一层 finish：tools_lib 在循环结束后若 ``result is None`` 会兜底调
        # ``metrics.finish('TIMEOUT'|'DONE')``。在那之前 listener 可能还没拿到
        # 终态事件（max_sim_seconds 截断 / Idle bot 卡住等），需要先把 5 大指标
        # 写入 envelope。listener 自身触发的 finish 走同一路径，幂等无害。
        original_finish = metrics.finish

        def wrapped_finish(result, **extra):
            try:
                listener.write_envelope_before_finish(world)
            except Exception as exc:  # noqa: BLE001
                warnings.warn(
                    "Fish metrics listener failed while finalizing envelope: "
                    f"{exc!r}",
                    RuntimeWarning,
                    stacklevel=2,
                )
            original_finish(result, **extra)

        metrics.finish = wrapped_finish  # type: ignore[method-assign]

        # 把 listener 挂上去以便外部测试 / 调试访问
        world._metrics_listener = listener  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# LevelConfig <-> dict
# ---------------------------------------------------------------------------


def _level_config_to_dict(cfg: LevelConfig) -> dict:
    return {
        "seed": int(cfg.seed),
        "world_size": [int(cfg.world_size[0]), int(cfg.world_size[1])],
        "difficulty": float(cfg.difficulty),
        "phases": {
            phase.name: _phase_to_dict(pc) for phase, pc in cfg.phases.items()
        },
        "boss": asdict(cfg.boss),
    }


def _phase_to_dict(pc: PhaseConfig) -> dict:
    return {
        "duration_s": float(pc.duration_s),
        "population_target": {str(k): int(v) for k, v in pc.population_target.items()},
        "spawn_rate": {str(k): float(v) for k, v in pc.spawn_rate.items()},
        "fish_speed_mul": float(pc.fish_speed_mul),
        "threat_aggression": float(pc.threat_aggression),
    }


def _level_config_from_dict(raw: dict) -> LevelConfig:
    phases = {}
    for name, data in raw["phases"].items():
        phases[Phase[name]] = PhaseConfig(
            duration_s=float(data["duration_s"]),
            population_target={int(k): int(v) for k, v in data["population_target"].items()},
            spawn_rate={int(k): float(v) for k, v in data["spawn_rate"].items()},
            fish_speed_mul=float(data.get("fish_speed_mul", 1.0)),
            threat_aggression=float(data.get("threat_aggression", 1.0)),
        )
    boss_raw = raw["boss"]
    boss = BossConfig(**boss_raw)
    return LevelConfig(
        seed=int(raw["seed"]),
        world_size=tuple(raw["world_size"]),  # type: ignore[arg-type]
        phases=phases,
        boss=boss,
        difficulty=float(raw["difficulty"]),
    )


# ---------------------------------------------------------------------------
# 模块级 singleton：tools CLI 用 ``--factory fish:make_factory`` 加载
# ---------------------------------------------------------------------------


# ``toy_engine.tools_lib.load_factory`` 走 ``getattr(module, attr)`` 直接拿对象，
# 不会调用 callable —— 因此 ``make_factory`` 直接 = FishGameFactory 实例。
make_factory: FishGameFactory = FishGameFactory()

# 兼容 toy_engine.tools_lib.DEFAULT_FACTORY_SPEC = "fish.__main__:FISH_FACTORY"
FISH_FACTORY: FishGameFactory = make_factory
