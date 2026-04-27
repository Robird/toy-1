"""Mock GameFactory used by tests/test_tools_*.py.

Lives under ``tests/`` so it is importable as ``tests._mock_factory`` from
``--factory`` CLI args; the leading underscore prevents pytest from
auto-collecting it as a test module.
"""

from __future__ import annotations

import random
import time
from typing import Any

from toy_engine.input import BotInputBase, InputFrame
from toy_engine.rng import SeededRng


class MockSnapshot:
    """Frozen snapshot exposing the contract-required ``player_pos``."""

    __slots__ = ("player_pos", "frame_idx")

    def __init__(self, player_pos: tuple[float, float], frame_idx: int) -> None:
        self.player_pos = player_pos
        self.frame_idx = frame_idx


class MockWorld:
    """A toy world: snapshot_hash deterministic in ``(seed, frame)`` by default.

    ``non_deterministic=True`` deliberately breaks determinism by reading wall-clock
    time and the module-level ``random`` generator from ``snapshot_hash``.
    """

    def __init__(
        self,
        *,
        seed: int,
        max_frames: int | None = None,
        non_deterministic: bool = False,
    ) -> None:
        self._seed = seed
        self._max = max_frames
        self._frame = 0
        self._non_deterministic = non_deterministic

    def step(self, dt: float, input_frame: InputFrame) -> None:  # noqa: ARG002
        self._frame += 1

    def snapshot(self) -> MockSnapshot:
        return MockSnapshot(player_pos=(0.0, 0.0), frame_idx=self._frame)

    def is_finished(self) -> bool:
        return self._max is not None and self._frame >= self._max

    def snapshot_hash(self) -> str:
        if self._non_deterministic:
            return f"{self._seed}:{self._frame}:{time.time_ns()}:{random.random()}"
        return f"{self._seed}:{self._frame}"


class _IdleBot(BotInputBase):
    def decide(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        return InputFrame(desired_dir=None, dash=False)


class MockFactory:
    """Default deterministic factory for tools_lib tests."""

    def __init__(
        self,
        *,
        max_frames: int | None = None,
        non_deterministic: bool = False,
    ) -> None:
        self._max_frames = max_frames
        self._non_deterministic = non_deterministic

    def make_level_config(self, *, seed: int, difficulty: float) -> dict:
        return {"seed": seed, "difficulty": difficulty}

    def make_world(self, *, level_config: dict, seed: int) -> MockWorld:
        return MockWorld(
            seed=seed,
            max_frames=self._max_frames,
            non_deterministic=self._non_deterministic,
        )

    def make_bot(self, *, name: str, world: MockWorld, rng: SeededRng) -> _IdleBot:  # noqa: ARG002
        if name not in ("heuristic", "idle"):
            raise ValueError(f"unknown bot: {name}")
        return _IdleBot(rng)

    def serialize_config(self, level_config: dict) -> dict:
        return dict(level_config)

    def deserialize_config(self, raw: dict) -> dict:
        return dict(raw)


# Module-level singletons for `--factory tests._mock_factory:NAME` CLI use.
DET_FACTORY = MockFactory(max_frames=None)
NON_DET_FACTORY = MockFactory(max_frames=None, non_deterministic=True)
SHORT_FACTORY = MockFactory(max_frames=10)
# Convenience singleton for end-to-end smoke tests: deterministic, finishes quickly
# so subprocess-driven CLI runs stay fast.
MOCK_FACTORY = MockFactory(max_frames=8)
