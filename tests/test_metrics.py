"""Unit tests for ``toy_engine.metrics`` (DoD of toy-engine/mvp/05-metrics.md)."""

from __future__ import annotations

import enum
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from toy_engine import __version__ as ENGINE_VERSION
from toy_engine.metrics import (
    TOP_LEVEL_KEYS,
    MetricsCollector,
    MetricsPayloadError,
)


# ---------------------------------------------------------------------------
# 基础：DoD - finish 不调用 dump 时不写文件
# ---------------------------------------------------------------------------


def test_no_file_io_until_dump(tmp_path: Path) -> None:
    m = MetricsCollector()
    m.set_scalar("seed", 1, top_level=True)
    m.set_scalar("difficulty", 0.5, top_level=True)
    m.tick(0.016, gauges={"hp": 1.0})
    m.record_event("ate")
    m.finish(result="VICTORY")
    # 任何文件都不应在 tmp_path 中出现
    assert list(tmp_path.iterdir()) == []
    # 显式 dump 后才写
    out = tmp_path / "m.json"
    m.dump(out)
    assert out.is_file()


# ---------------------------------------------------------------------------
# DoD - envelope 顶层键集合精确
# ---------------------------------------------------------------------------


def test_envelope_top_level_keys_exact() -> None:
    m = MetricsCollector()
    m.set_scalar("seed", 7, top_level=True)
    m.tick(0.5)
    m.finish(result="DEAD")
    rep = m.final_report()
    expected = set(TOP_LEVEL_KEYS) | {
        "metrics", "engine_version", "duration_frames", "events", "extra",
    }
    assert set(rep.keys()) == expected
    assert rep["engine_version"] == ENGINE_VERSION
    assert rep["duration_frames"] == 1
    # duration_s 业务未显式写 → 引擎兜底为 sum(dt)
    assert rep["duration_s"] == pytest.approx(0.5)
    # 未写的顶层字段为 None
    assert rep["difficulty"] is None
    assert rep["death_cause"] is None


def test_duration_s_explicit_overrides_tick_sum() -> None:
    m = MetricsCollector()
    m.tick(1.0)
    m.tick(1.0)
    m.set_scalar("duration_s", 999.0, top_level=True)
    m.finish(result="OK")
    rep = m.final_report()
    assert rep["duration_s"] == 999.0
    assert rep["duration_frames"] == 2


# ---------------------------------------------------------------------------
# DoD - top_level 白名单
# ---------------------------------------------------------------------------


def test_top_level_whitelist_enforced() -> None:
    m = MetricsCollector()
    with pytest.raises(ValueError):
        m.set_scalar("not_a_top_field", 1, top_level=True)
    # 白名单内允许
    for key in TOP_LEVEL_KEYS:
        m.set_scalar(key, 0 if key != "death_cause" else None, top_level=True)


def test_metrics_segment_keys_unrestricted() -> None:
    m = MetricsCollector()
    m.set_scalar("first_growth_time", 6.4)
    m.set_scalar("totally_new_business_metric", 42)
    m.finish(result="OK")
    rep = m.final_report()
    assert rep["metrics"]["first_growth_time"] == 6.4
    assert rep["metrics"]["totally_new_business_metric"] == 42


# ---------------------------------------------------------------------------
# DoD - 同名覆盖发出 warning
# ---------------------------------------------------------------------------


def test_set_scalar_overwrite_warns() -> None:
    m = MetricsCollector()
    m.set_scalar("starvation_ratio", 0.1)
    with pytest.warns(RuntimeWarning, match="overwritten"):
        m.set_scalar("starvation_ratio", 0.2)
    rep = m.final_report()
    assert rep["metrics"]["starvation_ratio"] == 0.2


def test_set_scalar_overwrite_warns_top_level() -> None:
    m = MetricsCollector()
    m.set_scalar("seed", 1, top_level=True)
    with pytest.warns(RuntimeWarning, match="overwritten"):
        m.set_scalar("seed", 2, top_level=True)
    assert m.final_report()["seed"] == 2


# ---------------------------------------------------------------------------
# DoD - gauges 时间加权 vs 手算误差 < 1e-9
# ---------------------------------------------------------------------------


def test_gauge_time_weighted_mean_matches_hand_computed() -> None:
    m = MetricsCollector()
    samples = [
        (0.016, 1.0),
        (0.020, 0.0),
        (0.011, 0.5),
        (0.033, 1.0),
        (0.017, 0.25),
    ]
    weighted = 0.0
    total = 0.0
    for dt, v in samples:
        m.tick(dt, gauges={"g": v})
        weighted += dt * v
        total += dt
    expected = weighted / total
    assert abs(m.gauge_mean("g") - expected) < 1e-9
    assert m.gauge_max("g") == 1.0
    assert m.gauge_min("g") == 0.0
    # ratio_above_zero = sum(dt for v>0) / total
    expected_ratio = sum(dt for dt, v in samples if v > 0.0) / total
    assert abs(m.gauge_ratio_above_zero("g") - expected_ratio) < 1e-9


def test_gauge_long_run_kahan_precision() -> None:
    """5000 帧 * 1e-3 dt 累计应非常接近 5.0。"""
    m = MetricsCollector()
    for _ in range(5000):
        m.tick(1e-3, gauges={"g": 0.7})
    assert abs(m.gauge_mean("g") - 0.7) < 1e-12
    rep = m.final_report()
    assert abs(rep["duration_s"] - 5.0) < 1e-9


# ---------------------------------------------------------------------------
# DoD - gauges 不直接写 envelope；业务通过 set_scalar 落到 metrics
# ---------------------------------------------------------------------------


def test_gauges_do_not_appear_in_envelope() -> None:
    m = MetricsCollector()
    m.tick(1.0, gauges={"starvation": 1.0})
    m.tick(1.0, gauges={"starvation": 0.0})
    m.finish(result="OK")
    rep = m.final_report()
    # gauges 不在 envelope 任何顶层键中
    assert "gauges" not in rep
    assert "starvation" not in rep["metrics"]
    # 业务派生为 fish 指标
    m2 = MetricsCollector()
    m2.tick(1.0, gauges={"starvation": 1.0})
    m2.tick(1.0, gauges={"starvation": 0.0})
    m2.set_scalar("starvation_ratio", m2.gauge_mean("starvation"))
    m2.finish(result="OK")
    assert m2.final_report()["metrics"]["starvation_ratio"] == 0.5


# ---------------------------------------------------------------------------
# DoD - events: 固定输入下 count 精确
# ---------------------------------------------------------------------------


def test_events_count_first_last_t_exact() -> None:
    m = MetricsCollector()
    m.tick(0.1)            # t=0.1
    m.record_event("hit")  # first_t = 0.1
    m.tick(0.2)            # t=0.3
    m.record_event("hit")
    m.tick(0.4)            # t=0.7
    m.record_event("hit")  # last_t = 0.7
    m.record_event("rare")
    m.finish(result="OK")

    rep = m.final_report()
    assert rep["events"]["hit"]["count"] == 3
    assert rep["events"]["hit"]["first_t"] == pytest.approx(0.1)
    assert rep["events"]["hit"]["last_t"] == pytest.approx(0.7)
    assert rep["events"]["rare"]["count"] == 1
    # 助手方法
    assert m.event_count("hit") == 3
    assert m.event_first_t("hit") == pytest.approx(0.1)
    assert m.event_count("never_fired") == 0
    assert m.event_first_t("never_fired") is None


# ---------------------------------------------------------------------------
# DoD - sample_limit 生效（10 万次同名事件不会线性膨胀）
# ---------------------------------------------------------------------------


def test_sample_limit_first_policy_caps_growth() -> None:
    m = MetricsCollector(sample_limit=5, sample_policy="first")
    for i in range(100_000):
        m.tick(0.001)
        m.record_event("evt", value={"i": i})
    rep = m.final_report()
    samples = rep["events"]["evt"]["samples"]
    assert len(samples) == 5
    # first 策略 → 保留最早 5 条
    assert [s["v"]["i"] for s in samples] == [0, 1, 2, 3, 4]
    assert rep["events"]["evt"]["count"] == 100_000


def test_sample_limit_ring_policy_keeps_latest() -> None:
    m = MetricsCollector(sample_limit=3, sample_policy="ring")
    for i in range(10):
        m.tick(0.001)
        m.record_event("evt", value=i)
    samples = m.final_report()["events"]["evt"]["samples"]
    assert [s["v"] for s in samples] == [7, 8, 9]


def test_event_without_value_does_not_create_samples() -> None:
    m = MetricsCollector()
    m.tick(0.1)
    m.record_event("ping")
    m.record_event("ping")
    rec = m.final_report()["events"]["ping"]
    assert rec["count"] == 2
    assert "samples" not in rec


def test_event_sample_shape_matches_schema_without_frame() -> None:
    m = MetricsCollector()
    m.tick(0.1)
    m.record_event("phase_changed", value="BOSS")
    sample = m.final_report()["events"]["phase_changed"]["samples"][0]
    assert set(sample.keys()) == {"t", "v"}
    assert sample["t"] == pytest.approx(0.1)
    assert sample["v"] == "BOSS"


def test_sample_limit_zero_omits_samples() -> None:
    m = MetricsCollector(sample_limit=0)
    m.record_event("evt", value=1)
    rec = m.final_report()["events"]["evt"]
    assert rec["count"] == 1
    assert "samples" not in rec


# ---------------------------------------------------------------------------
# DoD - final_report 干跑暴露不可序列化 payload
# ---------------------------------------------------------------------------


def test_final_report_dryrun_raises_in_debug_for_bad_payload() -> None:
    m = MetricsCollector(debug=True)
    # 强行绕过 _coerce 把 set 塞进 metrics 段
    m._metrics["weird"] = {1, 2, 3}  # type: ignore[attr-defined]
    with pytest.raises(MetricsPayloadError):
        m.final_report()


def test_final_report_dryrun_warns_in_release_for_bad_payload() -> None:
    m = MetricsCollector(debug=False)
    m._metrics["weird"] = {1, 2, 3}  # type: ignore[attr-defined]
    with pytest.warns(RuntimeWarning, match="not JSON-serializable|unserializable"):
        m.final_report()


# ---------------------------------------------------------------------------
# DoD - NaN / Infinity 在 debug 模式抛
# ---------------------------------------------------------------------------


def test_nan_inf_debug_raises() -> None:
    m = MetricsCollector(debug=True)
    with pytest.raises(MetricsPayloadError):
        m.set_scalar("bad", float("nan"))
    with pytest.raises(MetricsPayloadError):
        m.set_scalar("bad", float("inf"))


def test_nan_inf_release_drops_with_warning() -> None:
    m = MetricsCollector(debug=False)
    with pytest.warns(RuntimeWarning):
        m.set_scalar("bad", float("nan"))
    assert "bad" not in m.final_report()["metrics"]


def test_nan_gauge_release_dropped() -> None:
    m = MetricsCollector(debug=False)
    with pytest.warns(RuntimeWarning):
        m.tick(0.1, gauges={"g": float("nan")})
    assert m.gauge_mean("g") is None


# ---------------------------------------------------------------------------
# DoD - Enum / Path / dataclass 序列化
# ---------------------------------------------------------------------------


class _Phase(enum.Enum):
    WARMUP = "WARMUP"
    BOSS = "BOSS"


class _IntEnum(enum.IntEnum):
    A = 1
    B = 2


@dataclass
class _Pos:
    x: float
    y: float


def test_enum_serialization() -> None:
    m = MetricsCollector()
    m.tick(0.1)
    m.record_event("phase_changed", value=_Phase.BOSS)
    m.set_scalar("phase_int", _IntEnum.B)
    rep = m.final_report()
    # 字符串枚举 → value
    assert rep["events"]["phase_changed"]["samples"][0]["v"] == "BOSS"
    # IntEnum → 数字
    assert rep["metrics"]["phase_int"] == 2
    assert type(rep["metrics"]["phase_int"]) is int
    # 整体可 json.dumps
    json.dumps(rep, allow_nan=False)


def test_path_and_dataclass_serialization(tmp_path: Path) -> None:
    m = MetricsCollector()
    m.tick(0.1)
    m.record_event("snapshot", value={"path": tmp_path, "pos": _Pos(1.0, 2.0)})
    rep = m.final_report()
    sample = rep["events"]["snapshot"]["samples"][0]["v"]
    assert sample["path"] == str(tmp_path)
    assert sample["pos"] == {"x": 1.0, "y": 2.0}
    json.dumps(rep, allow_nan=False)


def test_unknown_object_rejected_in_debug() -> None:
    class Foo:
        pass
    m = MetricsCollector(debug=True)
    with pytest.raises(MetricsPayloadError):
        m.set_scalar("blob", Foo())


# ---------------------------------------------------------------------------
# DoD - dump 产物可被 json.load 直接解析
# ---------------------------------------------------------------------------


def test_dump_loadable(tmp_path: Path) -> None:
    m = MetricsCollector()
    m.set_scalar("seed", 12345, top_level=True)
    m.set_scalar("difficulty", 0.5, top_level=True)
    m.tick(0.5)
    m.record_event("hit")
    m.set_scalar("near_miss_count", 3)
    m.finish(result="VICTORY")
    out = tmp_path / "metrics.json"
    m.dump(out)
    with out.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["seed"] == 12345
    assert data["metrics"]["near_miss_count"] == 3
    assert data["events"]["hit"]["count"] == 1


# ---------------------------------------------------------------------------
# DoD - 业务可在不修改引擎源码下添加 1 event + 1 gauge + 1 scalar
# DoD - 完整产出 fish-doc 07 §6 envelope
# ---------------------------------------------------------------------------


def test_full_fish_envelope_can_be_produced(tmp_path: Path) -> None:
    """模拟 fish 业务侧的全流程：5 大指标 + 顶层 6 字段 + 自定义业务键全产出。"""
    m = MetricsCollector()

    # 开局
    m.set_scalar("seed", 12345, top_level=True)
    m.set_scalar("difficulty", 0.5, top_level=True)
    m.set_scalar("fail_rate", None)  # 跨局占位

    # 帧循环（构造已知输入）
    # 共 100 帧，每帧 dt=0.1 → duration_s ≈ 10s
    for frame in range(100):
        starvation = 1.0 if frame < 8 else 0.0  # ratio = 0.08
        m.tick(0.1, gauges={"starvation": starvation})
        if frame == 64:  # first_growth_time = 6.5（第65帧前累计 6.4，tick 后 6.5）
            m.record_event("growth_tier_up", value={"tier": 2})
        if frame in (10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99):
            m.record_event("near_miss")

    # 终局派生
    m.set_scalar("starvation_ratio", m.gauge_mean("starvation"))
    m.set_scalar("near_miss_count", m.event_count("near_miss"))
    m.set_scalar("first_growth_time", m.event_first_t("growth_tier_up"))
    m.set_scalar("boss_ttk", 14.2)
    m.set_scalar("player_max_tier", 4, top_level=True)
    m.set_scalar("death_cause", None, top_level=True)
    m.finish(result="VICTORY")

    out = tmp_path / "metrics.json"
    m.dump(out)
    rep = json.loads(out.read_text(encoding="utf-8"))

    # 顶层 6 字段
    assert rep["seed"] == 12345
    assert rep["difficulty"] == 0.5
    assert rep["result"] == "VICTORY"
    assert rep["duration_s"] == pytest.approx(10.0, abs=1e-9)
    assert rep["player_max_tier"] == 4
    assert rep["death_cause"] is None

    # 5 大指标
    metrics = rep["metrics"]
    assert metrics["fail_rate"] is None
    assert metrics["starvation_ratio"] == pytest.approx(0.08, abs=1e-9)
    assert metrics["near_miss_count"] == 11
    assert metrics["first_growth_time"] == pytest.approx(6.5, abs=1e-9)
    assert metrics["boss_ttk"] == 14.2

    # 引擎附加段
    assert rep["engine_version"] == ENGINE_VERSION
    assert rep["duration_frames"] == 100
    assert "growth_tier_up" in rep["events"]
    assert rep["events"]["growth_tier_up"]["count"] == 1
    assert rep["events"]["near_miss"]["count"] == 11
    assert rep["extra"] == {}


def test_business_can_add_arbitrary_event_gauge_scalar() -> None:
    """业务无需改 toy_engine.metrics 即可新增 1 个 event/gauge/scalar。"""
    m = MetricsCollector()
    m.tick(0.1, gauges={"my_brand_new_gauge": 0.7})
    m.tick(0.1, gauges={"my_brand_new_gauge": 0.3})
    m.record_event("brand_new_event", value={"k": 1})
    m.set_scalar("brand_new_metric", 42)
    m.finish(result="OK")
    rep = m.final_report()
    assert rep["metrics"]["brand_new_metric"] == 42
    assert rep["events"]["brand_new_event"]["count"] == 1
    assert m.gauge_mean("my_brand_new_gauge") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# finish 的 extras 分流
# ---------------------------------------------------------------------------


def test_finish_extras_routed_top_level_metrics_extra() -> None:
    m = MetricsCollector()
    m.set_scalar("starvation_ratio", 0.1)  # 已在 metrics 中存在
    m.finish(
        result="OK",
        seed=42,                  # → 顶层
        difficulty=0.7,           # → 顶层
        starvation_ratio=0.2,     # → 已存在于 metrics → 覆盖到 metrics
        debug_blob="anything",    # → 兜底 extra
    )
    rep = m.final_report()
    assert rep["seed"] == 42
    assert rep["difficulty"] == 0.7
    assert rep["metrics"]["starvation_ratio"] == 0.2
    assert rep["extra"]["debug_blob"] == "anything"


# ---------------------------------------------------------------------------
# DoD - 兼容别名 event / to_dict
# ---------------------------------------------------------------------------


def test_compat_aliases() -> None:
    m = MetricsCollector()
    m.event("x", value=1)  # 别名
    m.tick(0.1)
    m.event("x")
    rep_a = m.to_dict()
    rep_b = m.final_report()
    assert rep_a == rep_b
    assert rep_a["events"]["x"]["count"] == 2


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------


def test_tick_rejects_negative_or_nan_dt() -> None:
    m = MetricsCollector()
    with pytest.raises(ValueError):
        m.tick(-0.001)
    with pytest.raises(ValueError):
        m.tick(float("nan"))
    with pytest.raises(TypeError):
        m.tick("0.1")  # type: ignore[arg-type]


def test_set_scalar_rejects_empty_name() -> None:
    m = MetricsCollector()
    with pytest.raises(ValueError):
        m.set_scalar("", 1)


def test_constructor_validates_args() -> None:
    with pytest.raises(ValueError):
        MetricsCollector(sample_limit=-1)
    with pytest.raises(ValueError):
        MetricsCollector(sample_policy="weird")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 性能 smoke：100 局 < 0.5s（开发机预算）。CI 抖动留 4x 余量。
# ---------------------------------------------------------------------------


@pytest.mark.perf
def test_perf_budget_100_runs_under_2s() -> None:
    import time
    if sys.gettrace() is not None:
        pytest.skip("tracing active (coverage/debugger); perf budget not meaningful")
    t0 = time.perf_counter()
    for _ in range(100):
        m = MetricsCollector()
        m.set_scalar("seed", 1, top_level=True)
        for f in range(5000):
            m.tick(0.001, gauges={"g1": (f % 3) * 0.5, "g2": 1.0})
            if f % 500 == 0:
                m.record_event("evt", value=f)
        m.set_scalar("starvation_ratio", m.gauge_mean("g1"))
        m.finish(result="OK")
        m.final_report()
    elapsed = time.perf_counter() - t0
    # 文档预算 0.5s；CI 噪声放宽到 2s
    assert elapsed < 2.0, f"metrics perf budget exceeded: {elapsed:.3f}s"
