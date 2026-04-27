"""Unit tests for ``toy_engine.recorder`` (DoD of toy-engine/mvp/04-recorder.md)."""

from __future__ import annotations

import enum
import gzip
import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame, ReplayInput
from toy_engine.recorder import (
    ConfigDriftError,
    EmptyRecordingError,
    EngineVersionWarning,
    Recorder,
    Recording,
    to_jsonable,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Cfg:
    width: int
    height: int
    seed: int
    note: str = "hello"


def _basic_recorder(tmp_path: Path, *, seed: int = 42) -> tuple[Recorder, _Cfg]:
    cfg = _Cfg(width=800, height=600, seed=seed)
    return Recorder(cfg), cfg


def _fill_frames(rec: Recorder, n: int = 4) -> list[InputFrame]:
    """Record n frames with a single direction change at frame 1; return the
    dense expected sequence."""
    f0 = InputFrame()
    f1 = InputFrame(desired_dir=Vec2(1.0, 0.0))
    rec.record(0, f0)
    for i in range(1, n):
        rec.record(i, f1)
    return [f0] + [f1] * (n - 1)


# ---------------------------------------------------------------------------
# to_jsonable
# ---------------------------------------------------------------------------


class TestToJsonable:
    def test_primitives_passthrough(self) -> None:
        assert to_jsonable(None) is None
        assert to_jsonable(True) is True
        assert to_jsonable(1) == 1
        assert to_jsonable(1.5) == 1.5
        assert to_jsonable("x") == "x"

    def test_list_tuple_become_list(self) -> None:
        assert to_jsonable((1, 2, 3)) == [1, 2, 3]
        assert to_jsonable([1, (2, 3)]) == [1, [2, 3]]

    def test_dict_str_keys(self) -> None:
        assert to_jsonable({"a": 1, "b": [2, 3]}) == {"a": 1, "b": [2, 3]}

    def test_enum_value_uses_name(self) -> None:
        class E(enum.Enum):
            FOO = 1
            BAR = 2

        class IE(enum.IntEnum):
            BAZ = 3

        assert to_jsonable(E.FOO) == "FOO"
        assert to_jsonable(IE.BAZ) == "BAZ"
        assert to_jsonable({E.FOO: 1, E.BAR: 2}) == {"FOO": 1, "BAR": 2}

    def test_dataclass_recursive(self) -> None:
        @dataclass
        class Inner:
            k: int

        @dataclass
        class Outer:
            name: str
            children: list

        out = to_jsonable(Outer(name="x", children=[Inner(1), Inner(2)]))
        assert out == {"name": "x", "children": [{"k": 1}, {"k": 2}]}

    def test_unknown_object_raises(self) -> None:
        class Opaque:
            pass

        with pytest.raises(TypeError, match="cannot serialize"):
            to_jsonable(Opaque())

    def test_non_str_non_enum_dict_key_raises(self) -> None:
        with pytest.raises(TypeError, match="dict key"):
            to_jsonable({1: "a"})

    def test_nonfinite_float_raises(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            to_jsonable(float("nan"))
        with pytest.raises(ValueError, match="finite"):
            to_jsonable(float("inf"))

    def test_bytes_and_path_raise_instead_of_stringifying(self) -> None:
        with pytest.raises(TypeError, match="bytes"):
            to_jsonable(b"abc")
        with pytest.raises(TypeError, match="WindowsPath|PosixPath"):
            to_jsonable(Path("recordings/run.json"))

    def test_duplicate_enum_key_after_normalization_raises(self) -> None:
        class E(enum.Enum):
            FOO = 1

        with pytest.raises(ValueError, match="duplicate dict key"):
            to_jsonable({E.FOO: 1, "FOO": 2})


# ---------------------------------------------------------------------------
# Recorder construction
# ---------------------------------------------------------------------------


class TestRecorderInit:
    def test_seed_from_level_config_attr(self, tmp_path: Path) -> None:
        rec, cfg = _basic_recorder(tmp_path, seed=99)
        assert rec.seed == 99

    def test_explicit_seed_overrides_level_config(self) -> None:
        cfg = _Cfg(width=1, height=1, seed=10)
        rec = Recorder(cfg, seed=20)
        assert rec.seed == 20

    def test_missing_seed_raises(self) -> None:
        @dataclass
        class CfgNoSeed:
            x: int

        with pytest.raises(ValueError, match="seed"):
            Recorder(CfgNoSeed(x=1))

    def test_dict_level_config_seed(self) -> None:
        rec = Recorder({"seed": 7, "w": 1})
        assert rec.seed == 7

    def test_config_serializer_used(self) -> None:
        cfg = _Cfg(width=800, height=600, seed=1)

        def ser(c: _Cfg) -> dict:
            return {"w": c.width, "h": c.height, "seed": c.seed}

        rec = Recorder(cfg, config_serializer=ser)
        # hash should match the serializer output, not the dataclass dump
        rec2 = Recorder({"w": 800, "h": 600, "seed": 1}, seed=1)
        assert rec.config_hash == rec2.config_hash

    def test_config_serializer_must_return_dict(self) -> None:
        cfg = _Cfg(width=800, height=600, seed=1)

        def bad_serializer(_cfg: _Cfg) -> list[str]:
            return ["not", "a", "dict"]

        with pytest.raises(TypeError, match="JSON dict"):
            Recorder(cfg, config_serializer=bad_serializer)  # type: ignore[arg-type]

    def test_config_serializer_output_is_frozen_snapshot(
        self, tmp_path: Path
    ) -> None:
        raw = {"seed": 1, "nested": {"difficulty": 0.5}}

        def ser(_cfg: dict) -> dict:
            return raw

        rec = Recorder({"seed": 1}, config_serializer=ser)
        raw["nested"]["difficulty"] = 0.9
        _fill_frames(rec, n=1)
        path = tmp_path / "r.json"
        rec.save(path)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["config"]["nested"]["difficulty"] == 0.5
        assert Recorder.load(path).level_config["nested"]["difficulty"] == 0.5

    def test_unknown_object_in_default_serializer_raises(self) -> None:
        @dataclass
        class Bad:
            seed: int
            handle: object

        with pytest.raises(TypeError):
            Recorder(Bad(seed=1, handle=object()))


# ---------------------------------------------------------------------------
# record() semantics
# ---------------------------------------------------------------------------


class TestRecorderRecord:
    def test_first_frame_must_be_zero(self) -> None:
        rec = Recorder({"seed": 1})
        with pytest.raises(ValueError, match="first frame_idx must be 0"):
            rec.record(1, InputFrame())

    def test_strictly_increasing(self) -> None:
        rec = Recorder({"seed": 1})
        rec.record(0, InputFrame())
        rec.record(2, InputFrame(desired_dir=Vec2(1.0, 0.0)))
        with pytest.raises(ValueError, match="strictly increasing"):
            rec.record(2, InputFrame())
        with pytest.raises(ValueError, match="strictly increasing"):
            rec.record(1, InputFrame())

    def test_first_frame_always_written_even_if_idle(self) -> None:
        rec = Recorder({"seed": 1})
        rec.record(0, InputFrame())  # idle
        # The first frame must be persisted even when equal to the implicit
        # initial idle state, so that an all-still legitimate recording is not
        # mistaken for empty.
        assert len(rec.sparse_frames) == 1
        assert rec.sparse_frames[0]["i"] == 0

    def test_unchanged_frames_compressed_out(self) -> None:
        rec = Recorder({"seed": 1})
        f = InputFrame(desired_dir=Vec2(1.0, 0.0))
        rec.record(0, f)
        rec.record(1, f)
        rec.record(2, f)
        rec.record(3, InputFrame(desired_dir=Vec2(0.0, 1.0)))
        rec.record(4, InputFrame(desired_dir=Vec2(0.0, 1.0)))
        # Only change points: i=0 and i=3
        ids = [e["i"] for e in rec.sparse_frames]
        assert ids == [0, 3]

    def test_sparse_frames_property_does_not_mutate_internal(self) -> None:
        rec = Recorder({"seed": 1})
        rec.record(0, InputFrame())
        exposed = rec.sparse_frames
        exposed[0]["i"] = 99
        assert rec.sparse_frames[0]["i"] == 0

    def test_record_after_save_raises(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        rec.save(tmp_path / "r.json")
        with pytest.raises(RuntimeError, match="frozen"):
            rec.record(99, InputFrame())

    def test_save_after_save_raises(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        rec.save(tmp_path / "r.json")
        with pytest.raises(RuntimeError, match="only be called once"):
            rec.save(tmp_path / "r2.json")


# ---------------------------------------------------------------------------
# save() / load() round trip
# ---------------------------------------------------------------------------


class TestRecorderSaveLoad:
    def test_empty_recording_refused(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        with pytest.raises(EmptyRecordingError):
            rec.save(tmp_path / "r.json")

    def test_json_roundtrip(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 7, "w": 100})
        expected = _fill_frames(rec, n=5)
        path = tmp_path / "r.json"
        rec.save(path)

        loaded = Recorder.load(path)
        assert isinstance(loaded, Recording)
        assert loaded.seed == 7
        assert loaded.engine_version == "0.1.0"
        assert loaded.config_hash.startswith("sha256:")
        assert loaded.level_config == {"seed": 7, "w": 100}
        assert loaded.meta["duration_frames"] == 5
        assert "recorded_at" in loaded.meta
        assert loaded.frames == expected

    def test_gzip_by_suffix(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        path = tmp_path / "r.json.gz"
        rec.save(path)
        # Verify it really is gzip on disk
        with open(path, "rb") as fh:
            assert fh.read(2) == b"\x1f\x8b"

    def test_explicit_gzip_overrides_suffix(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        path = tmp_path / "r.json"  # no .gz suffix
        rec.save(path, gzip=True)
        with open(path, "rb") as fh:
            assert fh.read(2) == b"\x1f\x8b"

    def test_load_detects_gzip_by_magic_not_suffix(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        # Save gzip but with a misleading name
        gz_path = tmp_path / "lying.json"
        rec.save(gz_path, gzip=True)
        loaded = Recorder.load(gz_path)
        assert loaded.seed == 1

    def test_load_plain_json_with_gz_suffix(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        plain = tmp_path / "tricky.json.gz"
        rec.save(plain, gzip=False)  # plain JSON despite .gz name
        loaded = Recorder.load(plain)
        assert loaded.seed == 1

    def test_config_deserializer_round_trip(self, tmp_path: Path) -> None:
        cfg = _Cfg(width=320, height=240, seed=11)

        def ser(c: _Cfg) -> dict:
            return {"width": c.width, "height": c.height, "seed": c.seed,
                    "note": c.note}

        def deser(d: dict) -> _Cfg:
            return _Cfg(**d)

        rec = Recorder(cfg, config_serializer=ser)
        _fill_frames(rec)
        path = tmp_path / "r.json"
        rec.save(path)

        loaded = Recorder.load(path, config_deserializer=deser)
        assert loaded.level_config == cfg

    def test_no_nan_or_inf_allowed(self, tmp_path: Path) -> None:
        # config with nan/inf should fail before it can be written.
        for bad in (float("nan"), float("inf")):
            with pytest.raises(ValueError):
                Recorder({"seed": 1, "x": bad})


# ---------------------------------------------------------------------------
# Drift / version error modes
# ---------------------------------------------------------------------------


class TestErrorModes:
    def test_config_drift_detected(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1, "w": 100})
        _fill_frames(rec)
        path = tmp_path / "r.json"
        rec.save(path)

        # Tamper with config without updating config_hash.
        data = json.loads(path.read_text(encoding="utf-8"))
        data["config"]["w"] = 999
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ConfigDriftError):
            Recorder.load(path)

    def test_engine_version_major_mismatch_warns(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        path = tmp_path / "r.json"
        rec.save(path)

        data = json.loads(path.read_text(encoding="utf-8"))
        data["engine_version"] = "9.9.9"
        path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.warns(EngineVersionWarning):
            loaded = Recorder.load(path)
        assert loaded.engine_version == "9.9.9"

    def test_minor_version_does_not_warn(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1}, engine_version="0.1.5")
        _fill_frames(rec)
        path = tmp_path / "r.json"
        rec.save(path)

        import warnings as _w

        with _w.catch_warnings():
            _w.simplefilter("error", EngineVersionWarning)
            Recorder.load(path)  # must not raise

    def test_unknown_top_level_field_rejected(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        path = tmp_path / "r.json"
        rec.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["surprise"] = 42
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="unknown top-level"):
            Recorder.load(path)

    def test_missing_top_level_field_rejected(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        path = tmp_path / "r.json"
        rec.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["meta"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="missing required top-level"):
            Recorder.load(path)

    def test_config_field_must_be_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "bad_config.json"
        path.write_text(
            json.dumps(
                {
                    "engine_version": "0.1.0",
                    "seed": 1,
                    "config_hash": "sha256:not-checked-before-type",
                    "config": [],
                    "meta": {"duration_frames": 0},
                    "frames": [],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(TypeError, match="config must be dict"):
            Recorder.load(path)

    def test_missing_duration_frames_rejected(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        path = tmp_path / "r.json"
        rec.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["meta"] = {}
        # Recompute hash not required since we touched meta only; but we did
        # not touch config so config_hash is still valid.
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="duration_frames"):
            Recorder.load(path)

    def test_sparse_frame_first_index_must_be_zero(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        path = tmp_path / "r.json"
        rec.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["frames"][0]["i"] = 1
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="frames\\[0\\].i"):
            Recorder.load(path)

    def test_sparse_frame_i_beyond_duration_rejected(
        self, tmp_path: Path
    ) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec, n=3)  # duration_frames will be 3
        path = tmp_path / "r.json"
        rec.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        # Append a fake change point past duration boundary.
        data["frames"].append({"i": 99, "dir": None, "dash": False})
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match=">="):
            Recorder.load(path)

    def test_sparse_frame_unknown_field_rejected(self, tmp_path: Path) -> None:
        rec = Recorder({"seed": 1})
        _fill_frames(rec)
        path = tmp_path / "r.json"
        rec.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["frames"][0]["extra"] = "not in wire format"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="unknown fields"):
            Recorder.load(path)


# ---------------------------------------------------------------------------
# Sparse compression behaviour & file-size sanity
# ---------------------------------------------------------------------------


class TestCompression:
    def test_static_run_compresses_to_one_change_point(
        self, tmp_path: Path
    ) -> None:
        rec = Recorder({"seed": 1})
        f = InputFrame(desired_dir=Vec2(1.0, 0.0))
        for i in range(3600):  # 60s @ 60fps
            rec.record(i, f)
        path = tmp_path / "static.json"
        rec.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        # Only one change point: the first frame.
        assert len(data["frames"]) == 1
        # Plain JSON well under 200 KB; gzip should be well under 30 KB.
        assert path.stat().st_size < 5_000

    def test_gzip_size_under_DoD_budget(self, tmp_path: Path) -> None:
        # 60s @ 60fps with a direction flip every ~30 frames.
        rec = Recorder({"seed": 1})
        cur_dir = Vec2(1.0, 0.0)
        flip = Vec2(-1.0, 0.0)
        for i in range(3600):
            if i % 30 == 0 and i > 0:
                cur_dir = flip if cur_dir == Vec2(1.0, 0.0) else Vec2(1.0, 0.0)
            rec.record(i, InputFrame(desired_dir=cur_dir))
        path = tmp_path / "live.json.gz"
        rec.save(path)
        assert path.stat().st_size < 30_000  # DoD: gzip < 30KB at 60s

    def test_save_uses_streaming_not_megastring(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Sanity: json.dump (file stream) must be used, not json.dumps
        # (returns full string in memory). We monkeypatch json.dumps on the
        # recorder module to detect if it would be called.
        from toy_engine import recorder as rec_mod

        orig_dumps = rec_mod.json.dumps
        called = {"dumps_for_save": 0}
        # Save path uses json.dump, but the canonical hash also uses
        # json.dumps; we only detect a *new* dumps call during save.
        rec = Recorder({"seed": 1})
        _fill_frames(rec, n=4)

        def spy_dumps(*a, **kw):
            called["dumps_for_save"] += 1
            return orig_dumps(*a, **kw)

        monkeypatch.setattr(rec_mod.json, "dumps", spy_dumps)
        rec.save(tmp_path / "x.json")
        assert called["dumps_for_save"] == 0

    def test_ten_minute_plain_and_gzip_size_sanity(
        self, tmp_path: Path
    ) -> None:
        # 10min @ 60fps with sparse human-like changes. This checks the DoD
        # upper budgets and verifies gzip gives a smaller body than plain JSON.
        dirs = [
            Vec2(1.0, 0.0),
            Vec2(0.0, 1.0),
            Vec2(-1.0, 0.0),
            Vec2(0.0, -1.0),
        ]
        frames = [InputFrame(desired_dir=d) for d in dirs]

        def make_rec() -> Recorder:
            rec = Recorder({"seed": 1})
            for i in range(36_000):
                rec.record(i, frames[(i // 20) % len(frames)])
            return rec

        plain = tmp_path / "ten_min.json"
        gz = tmp_path / "ten_min.json.gz"
        make_rec().save(plain, gzip=False)
        make_rec().save(gz, gzip=True)

        assert plain.stat().st_size < 1_000_000
        assert gz.stat().st_size < 300_000
        assert gz.stat().st_size < plain.stat().st_size


# ---------------------------------------------------------------------------
# End-to-end: dump -> load -> ReplayInput equivalence
# ---------------------------------------------------------------------------


class TestEndToEndReplay:
    def test_replay_input_matches_original_sequence(
        self, tmp_path: Path
    ) -> None:
        # Record a varied sequence with gaps that exercise sparse compression.
        rec = Recorder({"seed": 99})
        seq: list[InputFrame] = []
        f_idle = InputFrame()
        f_right = InputFrame(desired_dir=Vec2(1.0, 0.0))
        f_up = InputFrame(desired_dir=Vec2(0.0, -1.0))
        f_dash = InputFrame(desired_dir=Vec2(1.0, 0.0), dash=True)

        # Build a 20-frame plan with intentional repeats.
        plan = (
            [f_idle] * 3
            + [f_right] * 5
            + [f_up] * 4
            + [f_dash] * 2
            + [f_right] * 6
        )
        for i, f in enumerate(plan):
            rec.record(i, f)
            seq.append(f)

        path = tmp_path / "rec.json.gz"
        rec.save(path)

        # Round trip via the public ReplayInput.from_recording wrapper.
        cfg, replay = ReplayInput.from_recording(path)
        assert cfg == {"seed": 99}
        assert len(replay) == len(seq)
        for i, want in enumerate(seq):
            got = replay.poll(None)
            assert got == want, f"frame {i}: {got!r} != {want!r}"

    def test_roundtrip_preserves_unit_dir_floats_exactly(
        self, tmp_path: Path
    ) -> None:
        # No NaN/Inf and exact JSON round trip for unit vectors.
        rec = Recorder({"seed": 1})
        d = Vec2(0.6, 0.8)  # unit
        rec.record(0, InputFrame(desired_dir=d))
        rec.record(1, InputFrame(desired_dir=d, dash=True))
        path = tmp_path / "rec.json"
        rec.save(path)
        loaded = Recorder.load(path)
        assert isinstance(loaded.frames[0].desired_dir, Vec2)
        assert loaded.frames[0].desired_dir.x == 0.6
        assert loaded.frames[0].desired_dir.y == 0.8
        assert loaded.frames[1].dash is True
