"""tests/fish/test_feel.py — M3-09 手感层测试。

约束（任务书 + fish-doc/06 §3）：
- TrailRenderer 队列长度上限
- Squash 高低速比例反向单调
- FeelEventBus 收事件不抛
- FeelEffects.step 推进粒子寿命；慢镜剩余时间到 0 后 dt_scale=1.0
- **关键**：World snapshot/hash **不**因 listener 加入而变（同 seed 跑 60 帧，
  注册/不注册 listener，hash 序列必须严格相等）

所有测试 headless：``SDL_VIDEODRIVER=dummy``（tests/conftest.py 已设置）。
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from toy_engine.geom import Vec2
from toy_engine.input import InputFrame
from toy_engine.loop import GameLoop
from toy_engine.render import GeoCanvas
from toy_engine.rng import SeededRng

from fish.config.constants import DT
from fish.config.level_config import LevelConfig
from fish.render import FISH_PALETTE
from fish.render.feel import (
    FeelEffects,
    FeelEventBus,
    SquashRenderer,
    TrailRenderer,
)
from fish.world import World


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


class _FixedDirInput:
    """每帧返回固定方向的输入；用于决定性比对。"""

    def __init__(self, dx: float = 1.0, dy: float = 0.0) -> None:
        n = (dx * dx + dy * dy) ** 0.5
        if n <= 1e-9:
            self._frame = InputFrame()
        else:
            self._frame = InputFrame(desired_dir=Vec2(dx / n, dy / n))

    def poll(self, _world_state: Any) -> InputFrame:
        return self._frame


def _new_canvas() -> GeoCanvas:
    return GeoCanvas.offscreen(1280, 720)


def _new_world(seed: int = 0) -> World:
    cfg = LevelConfig.default()
    return World(cfg, SeededRng(seed=seed))


# ---------------------------------------------------------------------------
# TrailRenderer
# ---------------------------------------------------------------------------


class TestTrailRenderer:
    def test_capacity_bound(self) -> None:
        tr = TrailRenderer(max_points=12, sample_interval_s=0.05)
        # 推 100 个采样间隔的时间，远大于 12
        for i in range(200):
            tr.step((float(i), 0.0), 0.05)
        assert len(tr) == 12
        # 应保留最新 12 个点（FIFO 经过 deque maxlen 自动剔除）
        pts = tr.points()
        assert pts[-1][0] >= pts[0][0]
        # 最新点必须是最后一次推入的
        assert pts[-1] == (199.0, 0.0)

    def test_only_samples_on_interval(self) -> None:
        tr = TrailRenderer(max_points=12, sample_interval_s=0.05)
        # 单次 step 一个 1/60s 的 dt，应不立刻入队
        tr.step((10.0, 10.0), 1.0 / 60.0)
        assert len(tr) == 0
        # 再 step 一个间隔 → 至少入 1 个
        tr.step((10.0, 10.0), 1.0 / 60.0)
        # 0.0166*2 = 0.0333 still < 0.05; need one more
        tr.step((10.0, 10.0), 1.0 / 60.0)
        assert len(tr) == 1

    def test_render_no_crash(self) -> None:
        canvas = _new_canvas()
        tr = TrailRenderer()
        tr.render(canvas, FISH_PALETTE)  # 0 点
        for i in range(5):
            tr.step((100.0 + i * 5, 200.0), 0.06)
        tr.render(canvas, FISH_PALETTE)


# ---------------------------------------------------------------------------
# SquashRenderer
# ---------------------------------------------------------------------------


class TestSquashRenderer:
    def test_zero_speed_is_identity(self) -> None:
        s = SquashRenderer().compute(0.0, 250.0)
        assert s == (1.0, 1.0)

    def test_high_speed_pulls_x_long_y_short(self) -> None:
        sq = SquashRenderer()
        sx_max, sy_max = sq.compute(250.0, 250.0)
        assert sx_max > 1.0
        assert sy_max < 1.0
        sx_lo, sy_lo = sq.compute(50.0, 250.0)
        # 单调：高速 sx 更大、sy 更小
        assert sx_max > sx_lo > 1.0
        assert sy_max < sy_lo < 1.0

    def test_overspeed_clamps(self) -> None:
        sq = SquashRenderer()
        s_at_max = sq.compute(250.0, 250.0)
        s_over = sq.compute(10000.0, 250.0)
        assert s_over == s_at_max

    def test_zero_max_speed_safe(self) -> None:
        s = SquashRenderer().compute(100.0, 0.0)
        assert s == (1.0, 1.0)
        sq = SquashRenderer()
        for speed, max_speed in (
            (math.nan, 250.0),
            (math.inf, 250.0),
            (250.0, math.nan),
            (250.0, math.inf),
        ):
            assert sq.compute(speed, max_speed) == (1.0, 1.0)


# ---------------------------------------------------------------------------
# FeelEventBus
# ---------------------------------------------------------------------------


class TestFeelEventBus:
    def test_push_drain_roundtrip(self) -> None:
        bus = FeelEventBus()
        assert len(bus) == 0
        bus.push({"type": "fish_eaten", "victim_pos": (1.0, 2.0), "victim_tier": 1})
        bus.push({"type": "boss_killed", "boss_pos": (3.0, 4.0)})
        assert len(bus) == 2
        evs = bus.drain()
        assert len(evs) == 2
        assert evs[0]["type"] == "fish_eaten"
        assert len(bus) == 0

    def test_push_isolates_caller_dict(self) -> None:
        bus = FeelEventBus()
        d = {"type": "fish_eaten", "victim_pos": (1.0, 2.0), "victim_tier": 1}
        bus.push(d)
        d["victim_tier"] = 99  # mutate after push
        evs = bus.drain()
        assert evs[0]["victim_tier"] == 1


# ---------------------------------------------------------------------------
# FeelEffects
# ---------------------------------------------------------------------------


class TestFeelEffects:
    def test_handle_each_event_does_not_raise(self) -> None:
        canvas = _new_canvas()
        feel = FeelEffects(FISH_PALETTE, rng=SeededRng(0).spawn("test"))
        feel.attach_canvas(canvas)
        events = [
            {"type": "fish_eaten", "victim_pos": (100.0, 100.0), "victim_tier": 1, "player_tier": 0},
            {"type": "fish_eaten", "victim_pos": (200.0, 200.0), "victim_tier": 4, "player_tier": 4},
            {"type": "player_eaten", "predator_pos": (300.0, 300.0)},
            {"type": "boss_bitten", "boss_pos": (400.0, 400.0)},
            {"type": "boss_killed", "boss_pos": (500.0, 500.0)},
            {"type": "player_grow", "old_tier": 1, "new_tier": 2, "player_pos": (640.0, 360.0)},
            {"type": "unknown_event_kind"},  # 静默忽略
        ]
        for ev in events:
            feel.handle(ev)
        # step 一次，应吞掉所有事件
        feel.step(DT, player_pos=Vec2(640.0, 360.0))
        # 至少产生了一些粒子（吃鱼 + 大爆炸 + 升级）
        assert feel.particle_count() > 0
        # 飘字至少 2 条（fish_eaten ×2 + player_grow ×1 = 3）
        assert feel.floating_text_count() >= 3

    def test_step_advances_particle_life(self) -> None:
        canvas = _new_canvas()
        feel = FeelEffects(FISH_PALETTE, rng=SeededRng(1).spawn("test"))
        feel.attach_canvas(canvas)
        feel.handle({"type": "fish_eaten", "victim_pos": (100.0, 100.0),
                     "victim_tier": 2, "player_tier": 1})
        feel.step(DT, player_pos=Vec2(0.0, 0.0))
        n0 = feel.particle_count()
        assert n0 > 0
        # 跑 2s 应当让所有粒子寿命到期（最大 0.55s）
        for _ in range(120):
            feel.step(DT, player_pos=Vec2(0.0, 0.0))
        assert feel.particle_count() == 0

    def test_slow_motion_expires_back_to_one(self) -> None:
        canvas = _new_canvas()
        feel = FeelEffects(FISH_PALETTE, rng=SeededRng(2).spawn("test"))
        feel.attach_canvas(canvas)
        assert feel.get_dt_scale() == 1.0
        feel.handle({"type": "player_eaten", "predator_pos": (0.0, 0.0)})
        feel.step(DT)
        # player_eaten 触发 0.3 速 1s
        assert feel.get_dt_scale() == pytest.approx(0.3)

        # GameLoop 的 logic_dt_scale callable 应读取当前 feel scale。
        world = _new_world(seed=0)
        loop = GameLoop(
            world=world,
            input_source=_FixedDirInput(dx=0.0, dy=0.0),
            dt=DT,
            logic_dt_scale=lambda _snapshot: feel.get_dt_scale(),
        )
        loop.step_once(1)
        assert world.last_effective_dt == pytest.approx(DT * 0.3)

        # 跑 2s 应失效并回到 1.0；后续 loop tick 也必须恢复基准 dt。
        for _ in range(120):
            feel.step(DT)
        assert feel.get_dt_scale() == 1.0
        loop.step_once(1)
        assert world.last_effective_dt == pytest.approx(DT)

    def test_flash_overlay_decays_to_none(self) -> None:
        canvas = _new_canvas()
        feel = FeelEffects(FISH_PALETTE, rng=SeededRng(3).spawn("test"))
        feel.attach_canvas(canvas)
        assert feel.get_flash_overlay() is None
        feel.handle({"type": "player_eaten", "predator_pos": (0.0, 0.0)})
        feel.step(DT)
        ov = feel.get_flash_overlay()
        assert ov is not None
        color, alpha = ov
        # 红色 flash
        assert color == FISH_PALETTE["role_threat"]
        assert alpha > 0
        for _ in range(120):
            feel.step(DT)
        assert feel.get_flash_overlay() is None

    def test_render_with_canvas_no_crash(self) -> None:
        canvas = _new_canvas()
        feel = FeelEffects(FISH_PALETTE, rng=SeededRng(4).spawn("test"))
        feel.attach_canvas(canvas)
        for ev in [
            {"type": "fish_eaten", "victim_pos": (100.0, 100.0),
             "victim_tier": 1, "player_tier": 0},
            {"type": "boss_bitten", "boss_pos": (200.0, 200.0)},
        ]:
            feel.handle(ev)
        feel.step(DT, player_pos=Vec2(640.0, 360.0))
        feel.render(canvas, FISH_PALETTE, font=None)
        feel.render_flash_overlay(canvas)


# ---------------------------------------------------------------------------
# 决定性：World hash 序列与 listener 注册无关（M3-09 关键 DoD）
# ---------------------------------------------------------------------------


class TestDeterminismUnchanged:
    def _hash_sequence(self, seed: int, frames: int, *, with_listener: bool) -> list[str]:
        world = _new_world(seed=seed)
        if with_listener:
            canvas = _new_canvas()
            feel = FeelEffects(FISH_PALETTE, rng=SeededRng(99).spawn("feel"))
            feel.attach_canvas(canvas)
            world.register_listener(feel.handle)
        hashes: list[str] = []
        inp = _FixedDirInput(dx=1.0, dy=0.3)
        for _ in range(frames):
            world.step(DT, inp.poll(world.snapshot()))
            hashes.append(world.snapshot_hash())
        return hashes

    def test_hash_sequence_identical_with_or_without_listener(self) -> None:
        a = self._hash_sequence(seed=0, frames=60, with_listener=False)
        b = self._hash_sequence(seed=0, frames=60, with_listener=True)
        assert a == b
        assert len(a) == 60
        # sanity：seed=0 下 hash 不全是同一个值
        assert len(set(a)) > 1

    def test_listener_receives_events_when_collision_happens(self) -> None:
        """触发真实事件时，listener 收到事件且不改变 World hash。"""
        world = _new_world(seed=0)
        world_without_listener = _new_world(seed=0)
        events: list[dict] = []
        world.register_listener(events.append)
        # 直接造一条小鱼贴在玩家身上，跑一帧触发吃
        from toy_engine.geom import Vec2 as _V
        from fish.entities.fish import Fish
        for target_world in (world, world_without_listener):
            f = Fish.spawn(
                eid=target_world.alloc_eid(),
                tier=1,
                pos=_V(target_world.player.pos.x, target_world.player.pos.y),
                heading=0.0,
                rng=SeededRng(123),
            )
            target_world.fishes.append(f)
            target_world.entities.append(f)
        world.step(DT, InputFrame())
        world_without_listener.step(DT, InputFrame())
        # 至少 1 条 fish_eaten
        kinds = [e.get("type") for e in events]
        assert "fish_eaten" in kinds
        assert world.snapshot_hash() == world_without_listener.snapshot_hash()

    def test_listener_exception_does_not_break_world(self) -> None:
        """listener 抛异常不能影响 World 推进。"""
        world = _new_world(seed=0)

        def bad_listener(_ev: dict) -> None:
            raise RuntimeError("intentional")

        world.register_listener(bad_listener)
        # 触发一次 fish_eaten
        from toy_engine.geom import Vec2 as _V
        from fish.entities.fish import Fish
        f = Fish.spawn(
            eid=world.alloc_eid(),
            tier=1,
            pos=_V(world.player.pos.x, world.player.pos.y),
            heading=0.0,
            rng=SeededRng(124),
        )
        world.fishes.append(f)
        world.entities.append(f)
        # 不应抛
        with pytest.warns(RuntimeWarning, match="World listener failed"):
            world.step(DT, InputFrame())
        assert world.frame_count == 1
