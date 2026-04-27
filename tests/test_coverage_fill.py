"""Coverage-fill tests for rng/geom/recorder/metrics (M2-10 100% target).

These tests exist purely to exercise validation/error branches that the
behavioural test files do not hit. They are intentionally small and assert
only what is required to drive coverage to 100% for the four modules listed
in toy-engine/mvp/09-mvp-scope.md §7.
"""

from __future__ import annotations

import enum
import gzip
import io
import json
import math
from pathlib import Path

import pytest

from toy_engine.geom import (
    AABB,
    Vec2,
    angle_in_arc,
    circle_circle_penetration,
)
from toy_engine.input import InputFrame
from toy_engine.metrics import (
    MetricsCollector,
    MetricsPayloadError,
    _coerce,
)
from toy_engine.recorder import (
    ConfigDriftError,
    Recorder,
    _canonical_hash,
)
from toy_engine.rng import SeededRng


# ---------------------------------------------------------------------------
# rng.set_state validation
# ---------------------------------------------------------------------------


def test_rng_set_state_rejects_non_tuple():
    r = SeededRng(1)
    with pytest.raises(TypeError, match="2-tuple"):
        r.set_state([1, 2])  # not a tuple
    with pytest.raises(TypeError, match="2-tuple"):
        r.set_state((1,))  # wrong length


def test_rng_set_state_rejects_non_int_seed():
    r = SeededRng(1)
    _, rstate = r.get_state()
    with pytest.raises(TypeError, match="canonical seed"):
        r.set_state(("not-int", rstate))
    with pytest.raises(TypeError, match="canonical seed"):
        r.set_state((True, rstate))  # bool excluded


def test_rng_set_state_roundtrip_restores_sequence():
    r = SeededRng(7)
    state = r.get_state()
    a = [r.random() for _ in range(5)]
    r.set_state(state)
    b = [r.random() for _ in range(5)]
    assert a == b


# ---------------------------------------------------------------------------
# geom: NotImplemented branches + boundary helpers
# ---------------------------------------------------------------------------


def test_vec2_arith_with_non_vec_returns_notimplemented_via_typeerror():
    v = Vec2(1.0, 2.0)
    # Each binary op should fall through to Python's TypeError when the dunder
    # returns NotImplemented. We use a sentinel object that supports no math.
    with pytest.raises(TypeError):
        _ = v + "foo"  # __add__ → NotImplemented
    with pytest.raises(TypeError):
        _ = v - "foo"  # __sub__ → NotImplemented
    with pytest.raises(TypeError):
        _ = v * "foo"  # __mul__ → NotImplemented
    with pytest.raises(TypeError):
        _ = v / "foo"  # __truediv__ → NotImplemented


def test_vec2_as_tuple_and_zero_classmethod():
    assert Vec2(3.5, -1.0).as_tuple() == (3.5, -1.0)
    z = Vec2.zero()
    assert z.x == 0.0 and z.y == 0.0


def test_circle_circle_penetration_negative_radius():
    with pytest.raises(ValueError, match="non-negative"):
        circle_circle_penetration((0.0, 0.0), -1.0, (1.0, 0.0), 1.0)
    with pytest.raises(ValueError, match="non-negative"):
        circle_circle_penetration((0.0, 0.0), 1.0, (1.0, 0.0), -1.0)


def test_angle_in_arc_negative_half_width():
    with pytest.raises(ValueError, match="non-negative"):
        angle_in_arc(0.0, 0.0, -0.1)


def test_aabb_expanded_negative_collapse_raises():
    a = AABB(0.0, 0.0, 1.0, 1.0)
    with pytest.raises(ValueError, match="non-negative"):
        a.expanded(-2.0)  # would collapse to negative w/h


# ---------------------------------------------------------------------------
# recorder construction + record() validation
# ---------------------------------------------------------------------------


def test_recorder_seed_must_be_int():
    with pytest.raises(TypeError, match="seed must be int"):
        Recorder({"seed": 0}, seed="0")  # type: ignore[arg-type]


def test_recorder_engine_version_property_exposed():
    rec = Recorder({"x": 1}, seed=0)
    assert isinstance(rec.engine_version, str)
    assert rec.engine_version  # non-empty


def test_recorder_record_rejects_non_int_frame_idx():
    rec = Recorder({"x": 1}, seed=0)
    f = InputFrame(desired_dir=None, dash=False)
    with pytest.raises(TypeError, match="frame_idx"):
        rec.record("0", f)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="frame_idx"):
        rec.record(True, f)  # bool excluded


def test_recorder_record_rejects_non_input_frame():
    rec = Recorder({"x": 1}, seed=0)
    with pytest.raises(TypeError, match="input_frame"):
        rec.record(0, {"dir": None, "dash": False})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# recorder.load: structural validation
# ---------------------------------------------------------------------------


def _good_payload() -> dict:
    cfg = {"seed": 0, "difficulty": 0.5}
    return {
        "engine_version": "0.1.0",
        "seed": 0,
        "config_hash": _canonical_hash(cfg),
        "config": cfg,
        "meta": {"recorded_at": "2026-01-01T00:00:00Z", "duration_frames": 1},
        "frames": [{"i": 0, "dir": None, "dash": False}],
    }


def _write(tmp_path: Path, payload) -> Path:
    p = tmp_path / "rec.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_recorder_load_top_level_must_be_object(tmp_path):
    p = _write(tmp_path, ["not", "an", "object"])
    with pytest.raises(ValueError, match="must be a JSON object"):
        Recorder.load(p)


def test_recorder_load_engine_version_must_be_str(tmp_path):
    pl = _good_payload()
    pl["engine_version"] = 123  # type: ignore[assignment]
    # config_hash still valid (we didn't touch config)
    with pytest.raises(TypeError, match="engine_version must be str"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_seed_must_be_int(tmp_path):
    pl = _good_payload()
    pl["seed"] = "0"  # type: ignore[assignment]
    with pytest.raises(TypeError, match="seed must be int"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_config_must_be_dict(tmp_path):
    pl = _good_payload()
    pl["config"] = ["not", "a", "dict"]
    pl["config_hash"] = _canonical_hash(pl["config"])  # avoid drift
    with pytest.raises(TypeError, match="config must be dict"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_config_hash_must_be_str(tmp_path):
    pl = _good_payload()
    pl["config_hash"] = 123
    with pytest.raises(TypeError, match="config_hash must be str"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_meta_must_be_dict(tmp_path):
    pl = _good_payload()
    pl["meta"] = ["nope"]
    with pytest.raises(TypeError, match="meta must be dict"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_meta_duration_must_be_int(tmp_path):
    pl = _good_payload()
    pl["meta"]["duration_frames"] = "1"
    with pytest.raises(TypeError, match="duration_frames"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_meta_duration_must_be_non_negative(tmp_path):
    pl = _good_payload()
    pl["meta"]["duration_frames"] = -1
    pl["frames"] = []  # avoid the idx >= duration trip first
    with pytest.raises(ValueError, match=">= 0"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_frames_must_be_list(tmp_path):
    pl = _good_payload()
    pl["frames"] = {"not": "a list"}
    with pytest.raises(TypeError, match="frames must be list"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_frame_entry_must_be_dict(tmp_path):
    pl = _good_payload()
    pl["frames"] = ["not-a-dict"]
    with pytest.raises(TypeError, match=r"frames\[0\] must be dict"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_frame_missing_required_fields(tmp_path):
    pl = _good_payload()
    pl["frames"] = [{"i": 0, "dir": None}]  # no 'dash'
    with pytest.raises(ValueError, match="missing required fields"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_frame_idx_must_be_int(tmp_path):
    pl = _good_payload()
    pl["frames"] = [{"i": "0", "dir": None, "dash": False}]
    with pytest.raises(TypeError, match=r"frames\[0\]\.i must be int"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_frame_idx_must_be_within_duration(tmp_path):
    pl = _good_payload()
    pl["meta"]["duration_frames"] = 1
    pl["frames"] = [{"i": 0, "dir": None, "dash": False},
                    {"i": 5, "dir": None, "dash": True}]
    with pytest.raises(ValueError, match="meta.duration_frames"):
        Recorder.load(_write(tmp_path, pl))


def test_recorder_load_frame_idx_must_strictly_increase(tmp_path):
    pl = _good_payload()
    pl["meta"]["duration_frames"] = 10
    pl["frames"] = [{"i": 0, "dir": None, "dash": False},
                    {"i": 0, "dir": None, "dash": True}]
    with pytest.raises(ValueError, match="must be > previous"):
        Recorder.load(_write(tmp_path, pl))


# ---------------------------------------------------------------------------
# metrics: validation + read-only accessors + coerce edge cases
# ---------------------------------------------------------------------------


def test_metrics_gauge_mean_and_ratio_none_when_no_samples():
    m = MetricsCollector()
    # No tick yet → total_dt.sum is 0.0; accessor must return None.
    # First we need a gauge entry to even ask.
    m.tick(0.0, gauges={"g": 1.0})  # zero dt → total_dt stays 0
    assert m.gauge_mean("g") is None
    assert m.gauge_ratio_above_zero("g") is None


def test_metrics_event_last_t_returns_none_and_value():
    m = MetricsCollector()
    assert m.event_last_t("nope") is None
    m.tick(0.5)
    m.record_event("hit")
    assert m.event_last_t("hit") == 0.5


def test_metrics_record_event_rejects_empty_name():
    m = MetricsCollector()
    with pytest.raises(ValueError, match="event name"):
        m.record_event("")


def test_metrics_record_event_with_bad_value_drops_in_release():
    m = MetricsCollector()
    with pytest.warns(RuntimeWarning, match="record_event"):
        m.record_event("evt", value=object())  # not coercible
    # Still recorded (count) even though value was dropped.
    assert m.event_count("evt") == 1


def test_metrics_tick_gauge_name_must_be_str():
    m = MetricsCollector()
    with pytest.raises(ValueError, match="gauge name"):
        m.tick(0.1, gauges={"": 1.0})


def test_metrics_tick_gauge_value_must_be_number_release_drops():
    m = MetricsCollector()
    with pytest.warns(RuntimeWarning, match="gauge"):
        m.tick(0.1, gauges={"g": "not-a-number"})  # type: ignore[dict-item]


def test_metrics_tick_gauge_value_non_finite_release_drops():
    m = MetricsCollector()
    with pytest.warns(RuntimeWarning, match="gauge"):
        m.tick(0.1, gauges={"g": float("inf")})


def test_metrics_finish_extra_uncoercible_dropped_in_release():
    m = MetricsCollector()
    with pytest.warns(RuntimeWarning, match="finish extra"):
        m.finish("OK", weird=object())


def test_metrics_finish_extra_uncoercible_raises_in_debug():
    m = MetricsCollector(debug=True)
    with pytest.raises(MetricsPayloadError, match="finish extra"):
        m.finish("OK", weird=object())


def test_metrics_coerce_enum_with_complex_value_returns_name():
    class E(enum.Enum):
        A = (1, 2)  # tuple value → falls through to .name branch
    assert _coerce(E.A) == "A"


def test_metrics_coerce_dict_key_must_be_str():
    with pytest.raises(TypeError, match="dict key must be str"):
        _coerce({1: "v"})


def test_metrics_coerce_list_and_tuple():
    assert _coerce((1, "x", None)) == [1, "x", None]
    assert _coerce([1.5, 2]) == [1.5, 2]
