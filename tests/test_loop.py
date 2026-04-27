"""Unit tests for ``toy_engine.loop`` (DoD of toy-engine/mvp/02-scene.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from toy_engine.input import InputFrame
from toy_engine.loop import (
    GameLoop,
    HashableSteppable,
    Steppable,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Snap:
    """Minimal snapshot exposing the engine's only hard contract."""

    player_pos: tuple[float, float]
    frame_idx: int = 0
    last_effective_dt: float = 0.0
    flag: bool = False


@dataclass
class _FakeWorld:
    """Configurable stub satisfying ``Steppable``.

    - ``stop_after`` step calls -> ``is_finished()`` becomes True
    - records every (dt, input_frame) pair into ``calls``
    - ``flag`` snapshot field flips True after first step (for slowmo callable test)
    """

    stop_after: int = 10
    pos: tuple[float, float] = (0.0, 0.0)
    calls: list[tuple[float, InputFrame]] = field(default_factory=list)
    snapshots_taken: int = 0
    _frame: int = 0
    _last_dt: float = 0.0

    def step(self, dt: float, input_frame: InputFrame) -> None:
        self._last_dt = dt
        self.calls.append((dt, input_frame))
        self._frame += 1

    def snapshot(self) -> _Snap:
        self.snapshots_taken += 1
        return _Snap(
            player_pos=self.pos,
            frame_idx=self._frame,
            last_effective_dt=self._last_dt,
            flag=self._frame > 0,
        )

    def is_finished(self) -> bool:
        return self._frame >= self.stop_after


class _ConstInput:
    """Returns the same InputFrame every poll; records snapshots received."""

    def __init__(self, frame: InputFrame | None = None) -> None:
        self.frame = frame if frame is not None else InputFrame()
        self.seen: list[Any] = []

    def poll(self, world_state: Any) -> InputFrame:
        self.seen.append(world_state)
        return self.frame


class _ScriptedClock:
    """Returns successive values from a list; raises StopIteration when exhausted.

    Falls back to a constant tail so ``run_realtime`` can keep ticking even after
    the recorded values are consumed.
    """

    def __init__(self, values: list[float], tail: float | None = None) -> None:
        self._it = iter(values)
        self._tail = tail if tail is not None else (values[-1] if values else 0.0)

    def __call__(self) -> float:
        try:
            return next(self._it)
        except StopIteration:
            return self._tail


# ---------------------------------------------------------------------------
# Steppable / HashableSteppable protocol
# ---------------------------------------------------------------------------


class TestProtocols:
    def test_world_is_steppable(self) -> None:
        assert isinstance(_FakeWorld(), Steppable)

    def test_missing_method_not_steppable(self) -> None:
        class Half:
            def step(self, dt, ifr): ...
            def snapshot(self): ...

        assert not isinstance(Half(), Steppable)

    def test_hashable_steppable(self) -> None:
        class W(_FakeWorld):
            def snapshot_hash(self) -> str:
                return "x"

        assert isinstance(W(), HashableSteppable)
        assert not isinstance(_FakeWorld(), HashableSteppable)


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_rejects_non_steppable(self) -> None:
        with pytest.raises(TypeError):
            GameLoop(world=object(), input_source=_ConstInput())  # type: ignore[arg-type]

    @pytest.mark.parametrize("dt", [0.0, -1e-9])
    def test_rejects_non_positive_dt(self, dt: float) -> None:
        with pytest.raises(ValueError):
            GameLoop(world=_FakeWorld(), input_source=_ConstInput(), dt=dt)

    def test_rejects_zero_max_steps(self) -> None:
        with pytest.raises(ValueError):
            GameLoop(
                world=_FakeWorld(),
                input_source=_ConstInput(),
                max_steps_per_frame=0,
            )

    def test_rejects_negative_speed(self) -> None:
        with pytest.raises(ValueError):
            GameLoop(world=_FakeWorld(), input_source=_ConstInput(), speed=-0.1)

    def test_rejects_negative_max_sim_seconds(self) -> None:
        with pytest.raises(ValueError):
            GameLoop(
                world=_FakeWorld(),
                input_source=_ConstInput(),
                max_sim_seconds=-1.0,
            )

    def test_default_max_steps_per_frame_is_8(self) -> None:
        # DoD: 默认 8 帧覆盖 100ms 卡顿追帧
        loop = GameLoop(world=_FakeWorld(), input_source=_ConstInput())
        assert loop._max_steps_per_frame == 8

    def test_default_dt_is_60hz(self) -> None:
        loop = GameLoop(world=_FakeWorld(), input_source=_ConstInput())
        assert loop.dt == pytest.approx(1.0 / 60.0)


# ---------------------------------------------------------------------------
# Headless does not import pygame.display
# ---------------------------------------------------------------------------


class TestHeadlessNoDisplay:
    def test_headless_does_not_init_display(self, monkeypatch) -> None:
        # If anything tries to read pygame.display, blow up.
        def boom(*a, **kw):
            raise AssertionError("GameLoop must not touch pygame.display")

        # Force import then sabotage the dangerous attrs.
        import pygame.display as disp

        monkeypatch.setattr(disp, "init", boom, raising=True)
        monkeypatch.setattr(disp, "set_mode", boom, raising=True)
        monkeypatch.setattr(disp, "flip", boom, raising=True)
        monkeypatch.setattr(disp, "update", boom, raising=True)

        world = _FakeWorld(stop_after=3)
        GameLoop(world=world, input_source=_ConstInput()).run_headless()
        assert world._frame == 3

    def test_loop_module_does_not_import_pygame(self) -> None:
        # 02-scene.md: GameLoop 本身不 import pygame.
        # Allow other modules (input.py uses pygame) to have already imported it,
        # but loop.py must not be a contributor.
        import toy_engine.loop as loop_mod
        # The module's own globals must not bind pygame.
        assert "pygame" not in vars(loop_mod)


# ---------------------------------------------------------------------------
# _tick_once order: snapshot -> poll -> step -> snapshot -> on_frame
# ---------------------------------------------------------------------------


class TestTickOrder:
    def test_call_order(self) -> None:
        order: list[str] = []

        class W:
            def __init__(self) -> None:
                self.frame = 0

            def step(self, dt, ifr):
                order.append("step")
                self.frame += 1

            def snapshot(self):
                order.append("snapshot")
                return _Snap(player_pos=(0.0, 0.0), frame_idx=self.frame)

            def is_finished(self) -> bool:
                return self.frame >= 1

        class Inp:
            def poll(self, ws):
                order.append("poll")
                return InputFrame()

        def on_frame(state):
            order.append("on_frame")

        GameLoop(
            world=W(), input_source=Inp(), on_frame=on_frame
        ).run_headless()

        assert order == ["snapshot", "poll", "step", "snapshot", "on_frame"]

    def test_on_frame_receives_post_step_snapshot(self) -> None:
        seen: list[int] = []

        def on_frame(state) -> None:
            seen.append(state.frame_idx)

        loop = GameLoop(
            world=_FakeWorld(stop_after=3),
            input_source=_ConstInput(),
            on_frame=on_frame,
        )
        loop.run_headless()
        # post-step frames are 1, 2, 3
        assert seen == [1, 2, 3]

    def test_input_source_receives_pre_step_snapshot(self) -> None:
        inp = _ConstInput()
        loop = GameLoop(
            world=_FakeWorld(stop_after=3), input_source=inp
        )
        loop.run_headless()
        # poll receives pre-step snapshots: frame_idx 0, 1, 2
        assert [s.frame_idx for s in inp.seen] == [0, 1, 2]


# ---------------------------------------------------------------------------
# headless / realtime parity (DoD: same _tick_once)
# ---------------------------------------------------------------------------


class TestHeadlessRealtimeParity:
    def _run(self, runner: str) -> tuple[list[float], list[float], list[int]]:
        world = _FakeWorld(stop_after=5)
        inp = _ConstInput(InputFrame(dash=True))
        captured_dts: list[float] = []
        captured_frames: list[int] = []

        def on_frame(state):
            captured_dts.append(state.last_effective_dt)
            captured_frames.append(state.frame_idx)

        clock = _ScriptedClock(
            [0.0] + [i * (1.0 / 60.0) for i in range(1, 50)]
        )
        loop = GameLoop(
            world=world,
            input_source=inp,
            on_frame=on_frame,
            time_source=clock,
        )
        # Suppress yield so realtime test stays deterministic & quick.
        loop._yield_to_host = lambda: None  # type: ignore[assignment]

        if runner == "headless":
            loop.run_headless()
        else:
            loop.run_realtime()

        # The dts seen at on_frame time and the world's call dts must match.
        return [dt for dt, _ in world.calls], captured_dts, captured_frames

    def test_same_step_dts(self) -> None:
        head_calls, head_hook_dts, head_hook_frames = self._run("headless")
        rt_calls, rt_hook_dts, rt_hook_frames = self._run("realtime")
        assert head_calls == rt_calls
        assert head_hook_dts == rt_hook_dts == head_calls
        assert head_hook_frames == rt_hook_frames == [1, 2, 3, 4, 5]
        assert all(dt == pytest.approx(1.0 / 60.0) for dt in head_calls)


# ---------------------------------------------------------------------------
# Slow machine: 100ms/frame should still advance correct logical step count
# ---------------------------------------------------------------------------


class TestSlowMachine:
    def test_100ms_per_frame_catches_up(self) -> None:
        # Each "frame" of the host advances 100ms.  At dt=1/60 that's 6 ticks
        # per frame; max_steps_per_frame=8 must comfortably absorb it.
        world = _FakeWorld(stop_after=18)  # 3 host frames * 6 ticks
        inp = _ConstInput()

        # time_source values: realtime calls now() once before loop, then once
        # at the top of every iteration of the outer while.
        # Provide enough monotonically-increasing values.
        times = [0.0]
        for k in range(1, 50):
            times.append(0.1 * k)
        clock = _ScriptedClock(times)

        loop = GameLoop(
            world=world,
            input_source=inp,
            time_source=clock,
        )
        loop._yield_to_host = lambda: None  # type: ignore[assignment]
        loop.run_realtime()

        assert world._frame == 18
        # With max_steps_per_frame=8, 6 ticks per host frame is fine.
        assert loop.frame_idx == 18

    def test_spiral_of_death_clamp_drops_excess(self) -> None:
        # Force a single huge elapsed; must run only max_steps_per_frame=8
        # ticks then drop the excess instead of hanging.
        world = _FakeWorld(stop_after=10_000)
        inp = _ConstInput()

        # First call returns 0; subsequent returns 10s -> elapsed=10s, but the
        # internal cap is 0.25s. With dt=1/60, 0.25s = 15 ticks; max_steps=8
        # caps to 8 inside one host frame.
        clock = _ScriptedClock([0.0, 10.0], tail=10.0)
        loop = GameLoop(world=world, input_source=inp, time_source=clock)

        # After the first yield_to_host (which only fires after the inner cap
        # drops the excess), declare the world finished so we can inspect the
        # burst size and the loop terminates.
        yields = [0]

        def fake_yield() -> None:
            yields[0] += 1
            world.stop_after = 0  # is_finished() -> True next outer iter

        loop._yield_to_host = fake_yield  # type: ignore[assignment]
        loop.run_realtime()

        # After spiral-of-death clamp the inner loop drops the leftover acc to 0,
        # falls through to neither branch (steps==max && acc<dt now false; acc<dt
        # false either) -> we then expect the next outer iter to find acc=0,
        # yield_to_host, then exit. So exactly one burst of 8 ticks.
        assert loop.frame_idx == 8
        assert yields[0] >= 1


# ---------------------------------------------------------------------------
# logic_dt_scale: float and callable
# ---------------------------------------------------------------------------


class TestLogicDtScale:
    def test_constant_scale(self) -> None:
        world = _FakeWorld(stop_after=4)
        loop = GameLoop(
            world=world,
            input_source=_ConstInput(),
            logic_dt_scale=0.5,
        )
        loop.run_headless()
        assert all(dt == pytest.approx((1.0 / 60.0) * 0.5) for dt, _ in world.calls)
        # sim_time tracks effective_dt sum
        assert loop.sim_time == pytest.approx(4 * (1.0 / 60.0) * 0.5)

    def test_callable_scale_receives_pre_snapshot(self) -> None:
        world = _FakeWorld(stop_after=3)

        seen_flags: list[bool] = []

        def scale(state) -> float:
            seen_flags.append(state.flag)
            return 0.3 if state.flag else 1.0

        loop = GameLoop(
            world=world,
            input_source=_ConstInput(),
            logic_dt_scale=scale,
        )
        loop.run_headless()
        # First step sees flag=False (pre snapshot), subsequent see flag=True.
        assert seen_flags == [False, True, True]
        dts = [dt for dt, _ in world.calls]
        assert dts[0] == pytest.approx(1.0 / 60.0)
        assert dts[1] == pytest.approx((1.0 / 60.0) * 0.3)
        assert dts[2] == pytest.approx((1.0 / 60.0) * 0.3)

    def test_negative_scale_clamped_to_zero(self) -> None:
        world = _FakeWorld(stop_after=2)
        loop = GameLoop(
            world=world,
            input_source=_ConstInput(),
            logic_dt_scale=-3.0,
        )
        loop.run_headless()
        assert all(dt == 0.0 for dt, _ in world.calls)


# ---------------------------------------------------------------------------
# max_sim_seconds, set_speed, step_once, pause
# ---------------------------------------------------------------------------


class TestControl:
    def test_max_sim_seconds_caps_headless(self) -> None:
        world = _FakeWorld(stop_after=10_000)
        loop = GameLoop(
            world=world,
            input_source=_ConstInput(),
            max_sim_seconds=10 * (1.0 / 60.0),
        )
        loop.run_headless()
        assert loop.frame_idx == 10
        assert loop.sim_time >= 10 * (1.0 / 60.0)

    def test_max_sim_seconds_caps_realtime(self) -> None:
        world = _FakeWorld(stop_after=10_000)
        clock = _ScriptedClock([0.0] + [0.05 * k for k in range(1, 200)])
        loop = GameLoop(
            world=world,
            input_source=_ConstInput(),
            max_sim_seconds=5 * (1.0 / 60.0),
            time_source=clock,
        )
        loop._yield_to_host = lambda: None  # type: ignore[assignment]
        loop.run_realtime()
        assert loop.frame_idx == 5

    def test_step_once_uses_same_tick(self) -> None:
        world = _FakeWorld(stop_after=10)
        loop = GameLoop(world=world, input_source=_ConstInput())
        loop.step_once(3)
        assert loop.frame_idx == 3
        assert world._frame == 3
        assert all(dt == pytest.approx(1.0 / 60.0) for dt, _ in world.calls)

    def test_step_once_stops_on_finished(self) -> None:
        world = _FakeWorld(stop_after=2)
        loop = GameLoop(world=world, input_source=_ConstInput())
        loop.step_once(10)
        assert loop.frame_idx == 2

    def test_step_once_default_n_is_one(self) -> None:
        world = _FakeWorld(stop_after=10)
        loop = GameLoop(world=world, input_source=_ConstInput())
        loop.step_once()
        assert loop.frame_idx == 1

    def test_step_once_negative_rejected(self) -> None:
        loop = GameLoop(world=_FakeWorld(), input_source=_ConstInput())
        with pytest.raises(ValueError):
            loop.step_once(-1)

    def test_set_speed_zero_pauses(self) -> None:
        # When speed=0, no logic ticks; loop must yield_to_host then either
        # spin forever or exit when is_finished.  We arrange is_finished to
        # become True after a couple of yield calls so the test terminates.
        world = _FakeWorld(stop_after=10_000)
        clock = _ScriptedClock([0.0, 0.1, 0.2, 0.3, 0.4])

        yield_count = [0]

        loop = GameLoop(
            world=world,
            input_source=_ConstInput(),
            time_source=clock,
            speed=0.0,
        )

        def fake_yield() -> None:
            yield_count[0] += 1
            if yield_count[0] >= 3:
                world.stop_after = 0  # is_finished -> True next iteration

        loop._yield_to_host = fake_yield  # type: ignore[assignment]
        loop.run_realtime()

        # Zero ticks while paused.
        assert loop.frame_idx == 0
        assert yield_count[0] >= 3

    def test_set_speed_validates(self) -> None:
        loop = GameLoop(world=_FakeWorld(), input_source=_ConstInput())
        loop.set_speed(2.0)
        assert loop.speed == 2.0
        with pytest.raises(ValueError):
            loop.set_speed(-0.1)


# ---------------------------------------------------------------------------
# on_frame composition: renderer / recorder / metrics all driven by same hook
# ---------------------------------------------------------------------------


class TestOnFrameComposition:
    def test_three_consumers(self) -> None:
        # DoD: on_frame can drive renderer + recorder + metrics simultaneously.
        rendered: list[int] = []
        recorded: list[int] = []
        metrics_ticks: list[float] = []

        def on_frame(state) -> None:
            rendered.append(state.frame_idx)
            recorded.append(state.frame_idx)
            metrics_ticks.append(state.last_effective_dt)

        world = _FakeWorld(stop_after=4)
        GameLoop(
            world=world, input_source=_ConstInput(), on_frame=on_frame
        ).run_headless()
        assert rendered == [1, 2, 3, 4]
        assert recorded == [1, 2, 3, 4]
        assert len(metrics_ticks) == 4

    def test_no_on_frame_is_ok(self) -> None:
        world = _FakeWorld(stop_after=3)
        GameLoop(world=world, input_source=_ConstInput()).run_headless()
        assert world._frame == 3


# ---------------------------------------------------------------------------
# Initially finished world should run zero ticks
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_initially_finished(self) -> None:
        world = _FakeWorld(stop_after=0)
        loop = GameLoop(world=world, input_source=_ConstInput())
        loop.run_headless()
        assert loop.frame_idx == 0

    def test_initially_finished_realtime(self) -> None:
        world = _FakeWorld(stop_after=0)
        clock = _ScriptedClock([0.0, 1.0])
        loop = GameLoop(
            world=world, input_source=_ConstInput(), time_source=clock
        )
        loop._yield_to_host = lambda: None  # type: ignore[assignment]
        loop.run_realtime()
        assert loop.frame_idx == 0

    def test_clock_going_backward_is_safe(self) -> None:
        # Defensive: a non-monotonic clock should not crash or run negative dt.
        world = _FakeWorld(stop_after=3)
        # Backwards then forwards.
        clock = _ScriptedClock([0.0, -1.0, 0.5, 1.0, 2.0, 3.0])
        loop = GameLoop(
            world=world, input_source=_ConstInput(), time_source=clock
        )
        loop._yield_to_host = lambda: None  # type: ignore[assignment]
        loop.run_realtime()
        assert loop.frame_idx == 3
        assert all(dt >= 0.0 for dt, _ in world.calls)
