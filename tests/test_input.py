"""Unit tests for ``toy_engine.input`` (DoD of toy-engine/mvp/03-input.md)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import pytest

import toy_engine.input as inp
from toy_engine.geom import Vec2
from toy_engine.input import (
    BotInputBase,
    EndOfReplay,
    InputContractError,
    InputFrame,
    InputSource,
    KeyboardMouseInput,
    ReplayInput,
)
from toy_engine.rng import SeededRng


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _Snapshot:
    """Minimal world snapshot exposing the engine's only hard contract."""

    player_pos: tuple[float, float]


class _FakePressed:
    """Mimics pygame.key.get_pressed(): index by keycode -> bool/0/1."""

    def __init__(self, down: set[int] | None = None) -> None:
        self._down = set(down or ())

    def __getitem__(self, key: int) -> int:
        return 1 if key in self._down else 0


def _patch_pygame(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pressed: _FakePressed | None = None,
    mouse_pos: tuple[int, int] = (0, 0),
    focused: bool = True,
) -> dict:
    """Install fake _pygame_* hooks; returns a state dict to mutate per-frame."""
    state: dict = {
        "pressed": pressed or _FakePressed(),
        "mouse_pos": mouse_pos,
        "focused": focused,
        "pump_calls": 0,
    }

    def _pump() -> None:
        state["pump_calls"] += 1

    monkeypatch.setattr(inp, "_pygame_pump", _pump)
    monkeypatch.setattr(inp, "_pygame_get_pressed", lambda: state["pressed"])
    monkeypatch.setattr(inp, "_pygame_get_mouse_pos", lambda: state["mouse_pos"])
    monkeypatch.setattr(inp, "_pygame_get_focused", lambda: state["focused"])
    return state


# ---------------------------------------------------------------------------
# InputFrame
# ---------------------------------------------------------------------------


class TestInputFrame:
    def test_default_is_idle(self) -> None:
        f = InputFrame()
        assert f.desired_dir is None
        assert f.dash is False

    def test_accepts_unit_vec2(self) -> None:
        f = InputFrame(desired_dir=Vec2(1.0, 0.0))
        assert isinstance(f.desired_dir, Vec2)
        assert f.desired_dir.x == pytest.approx(1.0)

    def test_accepts_vec2like_tuple_and_normalizes_type(self) -> None:
        f = InputFrame(desired_dir=(0.6, 0.8))  # type: ignore[arg-type]
        assert isinstance(f.desired_dir, Vec2)
        assert f.desired_dir.x == pytest.approx(0.6)
        assert f.desired_dir.y == pytest.approx(0.8)

    def test_zero_vector_rejected_distinct_from_none(self) -> None:
        with pytest.raises(ValueError, match="not a valid direction"):
            InputFrame(desired_dir=Vec2(0.0, 0.0))
        # None is the canonical "no input" — must not raise.
        InputFrame(desired_dir=None)

    def test_non_unit_rejected(self) -> None:
        with pytest.raises(ValueError, match="unit-length"):
            InputFrame(desired_dir=Vec2(2.0, 0.0))

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            InputFrame(desired_dir=Vec2(float("nan"), 0.0))

    def test_dash_must_be_bool(self) -> None:
        with pytest.raises(TypeError):
            InputFrame(dash=1)  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        f = InputFrame()
        with pytest.raises(Exception):
            f.dash = True  # type: ignore[misc]

    def test_json_roundtrip_via_wire(self) -> None:
        # DoD #1: serializable through Recorder helper -> json.dumps round trip
        frames = [
            InputFrame(),
            InputFrame(desired_dir=Vec2(math.sqrt(0.5), -math.sqrt(0.5))),
            InputFrame(desired_dir=Vec2(1.0, 0.0), dash=False),
        ]
        wire = [f.to_wire() for f in frames]
        text = json.dumps(wire)  # must not raise
        decoded = json.loads(text)
        restored = [InputFrame.from_wire(d) for d in decoded]
        assert restored[0].desired_dir is None
        assert restored[0].dash is False
        assert restored[1].desired_dir is not None
        assert restored[1].desired_dir.x == pytest.approx(math.sqrt(0.5))
        assert restored[1].desired_dir.y == pytest.approx(-math.sqrt(0.5))
        assert restored[2].desired_dir == Vec2(1.0, 0.0)

    def test_from_wire_requires_recorder_frame_fields(self) -> None:
        with pytest.raises(ValueError, match="dir"):
            InputFrame.from_wire({"dash": False})
        with pytest.raises(ValueError, match="dash"):
            InputFrame.from_wire({"dir": None})
        with pytest.raises(TypeError, match="dash"):
            InputFrame.from_wire({"dir": None, "dash": 0})


# ---------------------------------------------------------------------------
# InputSource Protocol structural compatibility
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_keyboard_mouse_is_input_source(self) -> None:
        # runtime_checkable Protocol: structural subtype check
        km = KeyboardMouseInput()
        assert isinstance(km, InputSource)

    def test_replay_is_input_source(self) -> None:
        r = ReplayInput([InputFrame()])
        assert isinstance(r, InputSource)

    def test_bot_subclass_is_input_source(self) -> None:
        class MyBot(BotInputBase):
            def decide(self, ws):  # noqa: ARG002
                return InputFrame()

        b = MyBot(SeededRng(42))
        assert isinstance(b, InputSource)


# ---------------------------------------------------------------------------
# KeyboardMouseInput
# ---------------------------------------------------------------------------


class TestKeyboardMouseInput:
    def test_missing_player_pos_raises_clear_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_pygame(monkeypatch)
        km = KeyboardMouseInput()
        with pytest.raises(InputContractError, match="player_pos"):
            km.poll(object())  # bare object lacks player_pos

    def test_mapping_player_pos_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_pygame(monkeypatch, mouse_pos=(200, 100))
        km = KeyboardMouseInput(dead_zone_px=1.0)
        f = km.poll({"player_pos": (100.0, 100.0)})
        assert f.desired_dir == Vec2(1.0, 0.0)

    def test_unfocused_returns_idle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_pygame(monkeypatch, focused=False)
        km = KeyboardMouseInput()
        f = km.poll(_Snapshot(player_pos=(0.0, 0.0)))
        assert f.desired_dir is None
        assert f.dash is False

    def test_dead_zone_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_pygame(monkeypatch, mouse_pos=(105, 100))
        km = KeyboardMouseInput(dead_zone_px=15.0)
        # Mouse is 5px from player → within dead zone.
        f = km.poll(_Snapshot(player_pos=(100.0, 100.0)))
        assert f.desired_dir is None

    def test_mouse_outside_dead_zone_returns_unit_dir(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_pygame(monkeypatch, mouse_pos=(200, 100))
        km = KeyboardMouseInput(dead_zone_px=15.0)
        f = km.poll(_Snapshot(player_pos=(100.0, 100.0)))
        assert f.desired_dir is not None
        assert f.desired_dir.x == pytest.approx(1.0)
        assert f.desired_dir.y == pytest.approx(0.0)

    def test_keyboard_pressed_switches_to_keyboard_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pygame

        state = _patch_pygame(
            monkeypatch,
            pressed=_FakePressed({pygame.K_d}),
            mouse_pos=(50, 50),
        )
        km = KeyboardMouseInput()
        assert km.mode == "mouse"
        f = km.poll(_Snapshot(player_pos=(0.0, 0.0)))
        assert km.mode == "keyboard"
        assert f.desired_dir == Vec2(1.0, 0.0)

        # Diagonal: D + W  → normalized (1/√2, -1/√2)
        state["pressed"] = _FakePressed({pygame.K_d, pygame.K_w})
        f2 = km.poll(_Snapshot(player_pos=(0.0, 0.0)))
        assert f2.desired_dir is not None
        assert f2.desired_dir.x == pytest.approx(math.sqrt(0.5))
        assert f2.desired_dir.y == pytest.approx(-math.sqrt(0.5))
        assert f2.desired_dir.length() == pytest.approx(1.0)

    def test_keyboard_mode_no_keys_returns_none_but_stays(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pygame

        state = _patch_pygame(
            monkeypatch,
            pressed=_FakePressed({pygame.K_a}),
            mouse_pos=(50, 50),
        )
        km = KeyboardMouseInput()
        km.poll(_Snapshot(player_pos=(0.0, 0.0)))
        assert km.mode == "keyboard"

        # release keys; mouse position unchanged → stay keyboard, output None
        state["pressed"] = _FakePressed(set())
        f = km.poll(_Snapshot(player_pos=(0.0, 0.0)))
        assert f.desired_dir is None
        assert km.mode == "keyboard"

    def test_mouse_move_switches_back_to_mouse(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pygame

        state = _patch_pygame(
            monkeypatch,
            pressed=_FakePressed({pygame.K_a}),
            mouse_pos=(50, 50),
        )
        km = KeyboardMouseInput(dead_zone_px=1.0)
        km.poll(_Snapshot(player_pos=(0.0, 0.0)))  # → keyboard, frozen mouse=(50,50)

        state["pressed"] = _FakePressed(set())
        state["mouse_pos"] = (50, 50)  # unchanged
        f1 = km.poll(_Snapshot(player_pos=(0.0, 0.0)))
        assert f1.desired_dir is None
        assert km.mode == "keyboard"

        state["mouse_pos"] = (200, 0)  # moved
        f2 = km.poll(_Snapshot(player_pos=(0.0, 0.0)))
        assert km.mode == "mouse"
        assert f2.desired_dir is not None
        assert f2.desired_dir.x == pytest.approx(1.0)

    def test_screen_to_world_callback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_pygame(monkeypatch, mouse_pos=(10, 0))

        def s2w(p: tuple[float, float]) -> tuple[float, float]:
            return (p[0] * 10.0, p[1] * 10.0)

        km = KeyboardMouseInput(dead_zone_px=1.0, screen_to_world=s2w)
        f = km.poll(_Snapshot(player_pos=(0.0, 0.0)))
        # World mouse = (100, 0) → unit dir (1, 0)
        assert f.desired_dir == Vec2(1.0, 0.0)

    def test_viewport_clamps_mouse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_pygame(monkeypatch, mouse_pos=(9999, -50))
        km = KeyboardMouseInput(dead_zone_px=1.0, viewport=(800, 600))
        f = km.poll(_Snapshot(player_pos=(0.0, 0.0)))
        # Clamped mouse = (800, 0) → angle ~ 0
        assert f.desired_dir is not None
        assert f.desired_dir.x == pytest.approx(1.0)
        assert f.desired_dir.y == pytest.approx(0.0)

    def test_pump_called_each_poll(self, monkeypatch: pytest.MonkeyPatch) -> None:
        state = _patch_pygame(monkeypatch, mouse_pos=(50, 50))
        km = KeyboardMouseInput()
        snap = _Snapshot(player_pos=(0.0, 0.0))
        km.poll(snap)
        km.poll(snap)
        km.poll(snap)
        assert state["pump_calls"] == 3

    def test_does_not_mutate_world_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_pygame(monkeypatch, mouse_pos=(150, 100))
        km = KeyboardMouseInput()
        snap = _Snapshot(player_pos=(100.0, 100.0))
        km.poll(snap)
        assert snap.player_pos == (100.0, 100.0)


# ---------------------------------------------------------------------------
# ReplayInput
# ---------------------------------------------------------------------------


class TestReplayInput:
    def test_advances_by_index(self) -> None:
        frames = [
            InputFrame(),
            InputFrame(desired_dir=Vec2(1.0, 0.0)),
            InputFrame(desired_dir=Vec2(0.0, 1.0)),
        ]
        r = ReplayInput(frames)
        assert r.frame_idx == 0
        assert r.poll(None) is frames[0]
        assert r.frame_idx == 1
        assert r.poll(None) is frames[1]
        assert r.poll(None) is frames[2]
        assert r.frame_idx == 3

    def test_out_of_range_returns_idle_by_default(self) -> None:
        r = ReplayInput([InputFrame(desired_dir=Vec2(1.0, 0.0))])
        r.poll(None)
        f = r.poll(None)
        assert f.desired_dir is None
        assert f.dash is False
        # Repeated polls keep returning idle, do not raise
        for _ in range(5):
            assert r.poll(None).desired_dir is None

    def test_strict_end_raises(self) -> None:
        r = ReplayInput([InputFrame()], strict_end=True)
        r.poll(None)
        with pytest.raises(EndOfReplay):
            r.poll(None)

    def test_does_not_read_world_state(self) -> None:
        r = ReplayInput([InputFrame(desired_dir=Vec2(1.0, 0.0))])
        # Poll with a sentinel that would explode on attribute access
        class Boom:
            def __getattr__(self, _name):
                raise AssertionError("ReplayInput must not read world_state")

        f = r.poll(Boom())
        assert f.desired_dir == Vec2(1.0, 0.0)

    def test_rejects_non_input_frame(self) -> None:
        with pytest.raises(TypeError):
            ReplayInput([InputFrame(), "not a frame"])  # type: ignore[list-item]

    def test_from_recording_expands_sparse_gaps(self, tmp_path) -> None:
        # Sparse: frame 0 idle, frame 2 right, frame 5 up. duration=8
        recording = {
            "engine_version": "0.1.0",
            "seed": 123,
            "config_hash": "sha256:00",
            "config": {"foo": 1},
            "meta": {"duration_frames": 8},
            "frames": [
                {"i": 0, "dir": None, "dash": False},
                {"i": 2, "dir": [1.0, 0.0], "dash": False},
                {"i": 5, "dir": [0.0, -1.0], "dash": False},
            ],
        }
        path = tmp_path / "rec.json"
        path.write_text(json.dumps(recording), encoding="utf-8")
        cfg, replay = ReplayInput.from_recording(path)
        assert cfg == {"foo": 1}
        assert len(replay) == 8
        # Expected dense expansion:
        expected = [
            None, None,             # i=0,1 idle (gap repeats last=idle)
            Vec2(1.0, 0.0), Vec2(1.0, 0.0), Vec2(1.0, 0.0),  # i=2,3,4
            Vec2(0.0, -1.0), Vec2(0.0, -1.0), Vec2(0.0, -1.0),  # i=5,6,7
        ]
        for i, want in enumerate(expected):
            got = replay.poll(None)
            assert got.desired_dir == want, f"frame {i}: got {got.desired_dir}"

    def test_from_recording_missing_duration_warns(self, tmp_path) -> None:
        recording = {
            "engine_version": "0.1.0",
            "seed": 1,
            "config_hash": "sha256:00",
            "config": None,
            "meta": {},  # no duration_frames
            "frames": [
                {"i": 0, "dir": None, "dash": False},
                {"i": 3, "dir": [1.0, 0.0], "dash": False},
            ],
        }
        path = tmp_path / "rec.json"
        path.write_text(json.dumps(recording), encoding="utf-8")
        with pytest.warns(UserWarning, match="duration_frames"):
            _, replay = ReplayInput.from_recording(path)
        # Falls back to last_index + 1 = 4
        assert len(replay) == 4

    def test_from_recording_gzip(self, tmp_path) -> None:
        import gzip

        recording = {
            "engine_version": "0.1.0",
            "seed": 1,
            "config_hash": "sha256:00",
            "config": {},
            "meta": {"duration_frames": 2},
            "frames": [{"i": 0, "dir": [1.0, 0.0], "dash": False}],
        }
        path = tmp_path / "rec.json.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(recording, f)
        _, replay = ReplayInput.from_recording(path)
        assert len(replay) == 2
        assert replay.poll(None).desired_dir == Vec2(1.0, 0.0)
        assert replay.poll(None).desired_dir == Vec2(1.0, 0.0)


# ---------------------------------------------------------------------------
# BotInputBase
# ---------------------------------------------------------------------------


class TestBotInputBase:
    def test_requires_seeded_rng(self) -> None:
        with pytest.raises(TypeError):
            BotInputBase(rng="not a rng")  # type: ignore[arg-type]

    def test_decide_must_be_overridden(self) -> None:
        b = BotInputBase(SeededRng(0))
        with pytest.raises(NotImplementedError):
            b.poll(None)

    def test_poll_delegates_to_decide(self) -> None:
        seen: list = []

        class B(BotInputBase):
            def decide(self, ws):
                seen.append(ws)
                return InputFrame(desired_dir=Vec2(1.0, 0.0))

        b = B(SeededRng(0))
        snap = _Snapshot(player_pos=(0.0, 0.0))
        f = b.poll(snap)
        assert seen == [snap]
        assert f.desired_dir == Vec2(1.0, 0.0)

    def test_reset_default_noop(self) -> None:
        BotInputBase(SeededRng(0)).reset()  # must not raise

    def test_same_rng_seed_yields_same_output(self) -> None:
        # With identical SeededRng state and identical snapshot stream, two
        # bot instances must produce identical InputFrame sequences.
        class RandomBot(BotInputBase):
            def __init__(self, rng: SeededRng) -> None:
                super().__init__(rng)
                self.decide_rng = self.rng.spawn("RandomBot.decide")

            def decide(self, ws):  # noqa: ARG002
                # Use a named substream so different bot decisions don't share
                # the root RNG's consumption state.
                v = self.decide_rng.uniform(-1.0, 1.0)
                w = self.decide_rng.uniform(-1.0, 1.0)
                n = math.hypot(v, w)
                if n == 0:
                    return InputFrame(desired_dir=None)
                return InputFrame(desired_dir=Vec2(v / n, w / n))

        snap = _Snapshot(player_pos=(0.0, 0.0))
        a = RandomBot(SeededRng(42))
        b = RandomBot(SeededRng(42))
        for _ in range(20):
            assert a.poll(snap) == b.poll(snap)

    def test_named_substream_isolates_consumption(self) -> None:
        # 03-input.md §4.3 motivation: avoid sharing the same root RNG across
        # decisions. Two child substreams of the same parent must be independent.
        root = SeededRng(7)
        a = root.spawn("decide.choose_target")
        b = root.spawn("decide.jitter")
        # Same name → logically equivalent (deterministic by name).
        a2 = root.spawn("decide.choose_target")
        seq_a = [a.random() for _ in range(5)]
        seq_b = [b.random() for _ in range(5)]
        seq_a2 = [a2.random() for _ in range(5)]
        assert seq_a == seq_a2
        assert seq_a != seq_b
