"""fish/render/feel.py — M3-09 手感（trail / squash / particles / shake / slow-mo / flash）。

设计原则（任务书 + fish-doc/06 §3）：

- **不**进 World snapshot / hash：所有手感状态全部驻留在本模块；World 通过
  ``register_listener`` 推送事件（dict），FeelEffects 自己积累并按渲染时间步推进。
  这样无论 listener 注册与否，World 在同 seed 下的 ``snapshot_hash`` 序列
  必须严格相等（M3-09 DoD 关键不变量）。
- 慢镜（``logic_dt_scale``）只在 GUI 模式生效；headless 不实例化 FeelEffects
  以保持决定性（M3-08 hash 与 M3-09 hash 应一致）。
- 屏震走 ``GeoCanvas.shake``（toy_engine 已下沉），由 ``attach_canvas`` 注入。

事件 dict 形状（Word._emit 推送，此处消费）：

- ``{"type": "fish_eaten", "victim_pos": (x,y), "victim_tier": int, "player_tier": int}``
- ``{"type": "player_eaten", "predator_pos": (x,y)}``
- ``{"type": "boss_killed", "boss_pos": (x,y)}``
- ``{"type": "boss_bitten", "boss_pos": (x,y)}``
- ``{"type": "player_grow", "old_tier": int, "new_tier": int, "player_pos": (x,y)}``
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from toy_engine.geom import Vec2
from toy_engine.render import GeoCanvas, Palette, ParticleSystem
from toy_engine.rng import SeededRng

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


__all__ = [
    "TrailRenderer",
    "SquashRenderer",
    "FeelEventBus",
    "FeelEffects",
]


# ---------------------------------------------------------------------------
# 常量（fish-doc/06 §3）
# ---------------------------------------------------------------------------

TRAIL_MAX_POINTS: int = 12
TRAIL_SAMPLE_INTERVAL_S: float = 0.05
SQUASH_X_MAX: float = 1.15  # 高速时 scale_x
SQUASH_Y_MIN: float = 0.90  # 高速时 scale_y


# ---------------------------------------------------------------------------
# Trail
# ---------------------------------------------------------------------------


class TrailRenderer:
    """玩家拖尾：每 ``sample_interval_s`` 在玩家位置打点，最多 ``max_points`` 个。

    线段从最旧（透明）→ 最新（不透明）线性渐变，颜色 ``role_player``。
    """

    __slots__ = ("_max", "_interval", "_acc", "_points")

    def __init__(
        self,
        max_points: int = TRAIL_MAX_POINTS,
        sample_interval_s: float = TRAIL_SAMPLE_INTERVAL_S,
    ) -> None:
        if max_points < 0:
            raise ValueError("max_points must be >= 0")
        if sample_interval_s <= 0.0:
            raise ValueError("sample_interval_s must be > 0")
        self._max = int(max_points)
        self._interval = float(sample_interval_s)
        self._acc: float = 0.0
        self._points: deque[tuple[float, float]] = deque(maxlen=self._max)

    def step(self, player_pos, dt: float) -> None:
        if dt <= 0.0 or self._max == 0:
            return
        self._acc += dt
        # Cap iterations: spikes (e.g. first frame after pause) shouldn't fill
        # the whole buffer with the same point.
        while self._acc >= self._interval:
            self._acc -= self._interval
            if hasattr(player_pos, "x"):
                x, y = float(player_pos.x), float(player_pos.y)
            else:
                x, y = float(player_pos[0]), float(player_pos[1])
            self._points.append((x, y))

    def reset(self) -> None:
        self._points.clear()
        self._acc = 0.0

    def __len__(self) -> int:
        return len(self._points)

    def points(self) -> list[tuple[float, float]]:
        return list(self._points)

    def render(self, canvas: GeoCanvas, palette: Palette) -> None:
        if len(self._points) < 2:
            return
        color = palette["role_player"]
        pts = list(self._points)
        n = len(pts)
        # 老 → 新；i=1..n-1 段，alpha 与 width 随 i 升高
        for i in range(1, n):
            t = i / (n - 1)
            alpha = int(40 + 180 * t)
            width = max(1, int(round(2 + 3 * t)))
            canvas.line(pts[i - 1], pts[i], color, width=width, alpha=alpha)


# ---------------------------------------------------------------------------
# Squash
# ---------------------------------------------------------------------------


class SquashRenderer:
    """按 player.vel 大小算横纵压缩比例（fish-doc/06 §3 #2）。

    speed=0 → ``(1.0, 1.0)``；speed=max → ``(SQUASH_X_MAX, SQUASH_Y_MIN)``。
    线性插值；速度 > max 时按 1.0 截断。
    """

    __slots__ = ()

    def compute(self, speed: float, max_speed: float) -> tuple[float, float]:
        try:
            speed_f = float(speed)
            max_speed_f = float(max_speed)
        except (TypeError, ValueError):
            return (1.0, 1.0)

        if (
            not math.isfinite(speed_f)
            or not math.isfinite(max_speed_f)
            or max_speed_f <= 0.0
            or speed_f <= 0.0
        ):
            return (1.0, 1.0)

        r = speed_f / max_speed_f
        if r < 0.0:
            r = 0.0
        elif r > 1.0:
            r = 1.0
        sx = 1.0 + (SQUASH_X_MAX - 1.0) * r
        sy = 1.0 + (SQUASH_Y_MIN - 1.0) * r
        return (sx, sy)


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------


class FeelEventBus:
    """Append-only 事件队列，FeelEffects 在 ``step`` 中 ``drain`` 后处理。"""

    __slots__ = ("_events",)

    def __init__(self) -> None:
        self._events: list[dict] = []

    def push(self, event: dict) -> None:
        # 拷贝一份，免得调用方后续 mutate
        self._events.append(dict(event))

    def drain(self) -> list[dict]:
        evs = self._events
        self._events = []
        return evs

    def __len__(self) -> int:
        return len(self._events)


# ---------------------------------------------------------------------------
# Floating text
# ---------------------------------------------------------------------------


@dataclass
class _FloatingText:
    text: str
    x: float
    y: float
    age: float
    life: float
    color_name: str


def _victim_color_name(victim_tier: int, player_tier: int) -> str:
    """与 ``palette.tier_to_role_name`` 同口径：用于受害鱼粒子配色。"""
    if victim_tier == player_tier:
        return "role_peer"
    if victim_tier <= player_tier + 1:
        return "role_prey"
    return "role_threat"


# ---------------------------------------------------------------------------
# FeelEffects（核心）
# ---------------------------------------------------------------------------


class FeelEffects:
    """组合 ``ParticleSystem`` + ``ScreenShake`` + 事件总线。

    用法（GUI 路径）::

        feel = FeelEffects(palette)
        feel.attach_canvas(canvas)
        world.register_listener(feel.handle)
        loop = GameLoop(world, input, dt=DT, logic_dt_scale=lambda _s: feel.get_dt_scale())
        # 每帧：
        loop.step_once(1)
        feel.step(DT, player_pos=world.player.pos, ...)
        renderer.render(world, feel=feel)
    """

    __slots__ = (
        "trail",
        "squash",
        "_bus",
        "_particles",
        "_canvas",
        "_palette",
        "_rng",
        "_slow_remaining_s",
        "_slow_duration_s",
        "_slow_scale",
        "_flash_color",
        "_flash_remaining_s",
        "_flash_duration_s",
        "_floating_texts",
    )

    def __init__(
        self,
        palette: Palette,
        *,
        rng: SeededRng | None = None,
        particle_capacity: int = 256,
    ) -> None:
        self._palette = palette
        self._rng = rng if rng is not None else SeededRng(0).spawn("feel")
        self.trail = TrailRenderer()
        self.squash = SquashRenderer()
        self._bus = FeelEventBus()
        self._particles = ParticleSystem(capacity=particle_capacity)
        self._canvas: GeoCanvas | None = None
        self._slow_remaining_s: float = 0.0
        self._slow_duration_s: float = 0.0
        self._slow_scale: float = 1.0
        self._flash_color: tuple[int, int, int] | None = None
        self._flash_remaining_s: float = 0.0
        self._flash_duration_s: float = 0.0
        self._floating_texts: list[_FloatingText] = []

    # ------------------------------------------------------------------
    # 集成
    # ------------------------------------------------------------------

    def attach_canvas(self, canvas: GeoCanvas) -> None:
        """渲染器构造后调用一次：把屏震委托给 canvas 自带的 ``ScreenShake``。"""
        self._canvas = canvas

    def handle(self, event: dict) -> None:
        """``World.register_listener`` 注入的回调；只入队，不立刻处理。"""
        self._bus.push(event)

    # ------------------------------------------------------------------
    # 公开查询
    # ------------------------------------------------------------------

    def get_dt_scale(self) -> float:
        """慢镜剩余时间 > 0 时返回 < 1 的 scale；否则 1.0。"""
        if self._slow_remaining_s <= 0.0:
            return 1.0
        return self._slow_scale

    def get_flash_overlay(self) -> tuple[tuple[int, int, int], int] | None:
        """返回 (color_rgb, alpha) 或 None；alpha 随剩余时间线性衰减。"""
        if self._flash_color is None or self._flash_remaining_s <= 0.0:
            return None
        if self._flash_duration_s <= 0.0:
            return None
        ratio = self._flash_remaining_s / self._flash_duration_s
        if ratio < 0.0:
            ratio = 0.0
        elif ratio > 1.0:
            ratio = 1.0
        alpha = int(round(180.0 * ratio))
        return (self._flash_color, alpha)

    def particle_count(self) -> int:
        return len(self._particles)

    def floating_text_count(self) -> int:
        return len(self._floating_texts)

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def step(
        self,
        dt: float,
        *,
        player_pos=None,
    ) -> None:
        """推进所有手感状态（粒子、屏震、慢镜计时、闪屏计时、飘字、拖尾）。

        ``dt`` 应传入「真实/基准」时间（GUI 中 = ``DT = 1/60``），不要乘慢镜
        scale；否则慢镜永远不结束。
        """
        if dt <= 0.0:
            return

        # 1. 处理事件队列
        for ev in self._bus.drain():
            self._apply_event(ev)

        # 2. 拖尾采样
        if player_pos is not None:
            self.trail.step(player_pos, dt)

        # 3. 粒子 + 屏震
        self._particles.update(dt)
        if self._canvas is not None:
            self._canvas.shake.update(dt)

        # 4. 慢镜计时
        if self._slow_remaining_s > 0.0:
            self._slow_remaining_s -= dt
            if self._slow_remaining_s <= 0.0:
                self._slow_remaining_s = 0.0
                self._slow_scale = 1.0
                self._slow_duration_s = 0.0

        # 5. 闪屏计时
        if self._flash_remaining_s > 0.0:
            self._flash_remaining_s -= dt
            if self._flash_remaining_s <= 0.0:
                self._flash_remaining_s = 0.0
                self._flash_color = None
                self._flash_duration_s = 0.0

        # 6. 飘字推进
        if self._floating_texts:
            survivors: list[_FloatingText] = []
            for t in self._floating_texts:
                t.age += dt
                t.y -= 30.0 * dt  # 30 px/s 上飘
                if t.age < t.life:
                    survivors.append(t)
            self._floating_texts = survivors

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def render(self, canvas: GeoCanvas, palette: Palette, *, font=None) -> None:
        """画拖尾 + 粒子 + 飘字。flash overlay 由调用方在最外层叠加。"""
        self.trail.render(canvas, palette)
        self._particles.draw(canvas)
        if font is not None and self._floating_texts:
            for t in self._floating_texts:
                ratio = max(0.0, 1.0 - t.age / t.life) if t.life > 0 else 0.0
                alpha = int(round(255 * ratio))
                color = palette[t.color_name]
                # UI 类文字不应受屏震影响：放到 with_no_shake() 里画。
                with canvas.with_no_shake():
                    canvas.text(
                        t.text, (t.x, t.y), color, font,
                        anchor="center", alpha=alpha,
                    )

    def render_flash_overlay(self, canvas: GeoCanvas) -> None:
        """便捷：把 flash overlay 画成全屏半透矩形。"""
        ov = self.get_flash_overlay()
        if ov is None:
            return
        color, alpha = ov
        if alpha <= 0:
            return
        w, h = canvas.size
        with canvas.with_no_shake():
            canvas.rect((0, 0, w, h), color, alpha=alpha)

    # ------------------------------------------------------------------
    # 事件分发
    # ------------------------------------------------------------------

    def _apply_event(self, ev: dict) -> None:
        kind = ev.get("type")
        if kind == "fish_eaten":
            self._on_fish_eaten(ev)
        elif kind == "player_eaten":
            self._on_player_eaten(ev)
        elif kind == "boss_killed":
            self._on_boss_killed(ev)
        elif kind == "boss_bitten":
            self._on_boss_bitten(ev)
        elif kind == "player_grow":
            self._on_player_grow(ev)
        # 未识别事件：静默忽略（向后兼容）

    def _shake(self, magnitude: float, duration_s: float) -> None:
        if self._canvas is None:
            return
        self._canvas.shake.shake(magnitude, duration_s)

    def _start_slow(self, scale: float, duration_s: float) -> None:
        """叠加规则：取更夸张的 scale（更小）和更长的 duration。"""
        if duration_s <= 0.0:
            return
        if self._slow_remaining_s <= 0.0 or scale < self._slow_scale:
            self._slow_scale = float(scale)
        if duration_s > self._slow_remaining_s:
            self._slow_remaining_s = float(duration_s)
            self._slow_duration_s = float(duration_s)

    def _start_flash(self, color: tuple[int, int, int], duration_s: float) -> None:
        if duration_s <= 0.0:
            return
        self._flash_color = (int(color[0]), int(color[1]), int(color[2]))
        self._flash_remaining_s = float(duration_s)
        self._flash_duration_s = float(duration_s)

    # ---- 单事件处理 ----

    def _on_fish_eaten(self, ev: dict) -> None:
        pos = ev.get("victim_pos") or (0.0, 0.0)
        victim_tier = int(ev.get("victim_tier", 1))
        player_tier = int(ev.get("player_tier", 0))
        center = Vec2(float(pos[0]), float(pos[1]))
        color_name = _victim_color_name(victim_tier, player_tier)

        # (1) 彩色碎屑：8 颗，目标主色
        self._particles.emit_burst(
            8, center=center, speed_range=(60.0, 180.0),
            color=self._palette[color_name], radius_range=(2.0, 4.0),
            life_range=(0.25, 0.55), rng=self._rng,
        )
        # (2) 气泡：4 颗高光小圆
        self._particles.emit_burst(
            4, center=center, speed_range=(20.0, 60.0),
            color=self._palette["bg_highlight"], radius_range=(1.5, 3.0),
            life_range=(0.4, 0.8), rng=self._rng,
        )
        # (3) "+N" 数字飘字
        from fish.config.constants import GROWTH_REWARD

        idx = max(0, min(victim_tier, len(GROWTH_REWARD) - 1))
        self._floating_texts.append(_FloatingText(
            text=f"+{int(GROWTH_REWARD[idx])}",
            x=center.x, y=center.y - 18.0,
            age=0.0, life=0.7, color_name="role_player",
        ))
        # (4) 微屏震（fish-doc/06 §3 1px × 0.1s）
        self._shake(1.0, 0.1)

    def _on_player_eaten(self, ev: dict) -> None:
        pos = ev.get("predator_pos") or (0.0, 0.0)
        center = Vec2(float(pos[0]), float(pos[1]))
        # 大爆炸（红）
        self._particles.emit_burst(
            16, center=center, speed_range=(80.0, 240.0),
            color=self._palette["role_threat"], radius_range=(2.0, 5.0),
            life_range=(0.4, 0.8), rng=self._rng,
        )
        self._shake(8.0, 0.5)
        # 任务规格：玩家死亡 0.3 速 1s（fish-doc/06 §3 给的是 0.3s，本步以
        # 任务书为准；游戏感更强）
        self._start_slow(0.3, 1.0)
        self._start_flash(self._palette["role_threat"], 0.4)

    def _on_boss_killed(self, ev: dict) -> None:
        pos = ev.get("boss_pos") or (0.0, 0.0)
        center = Vec2(float(pos[0]), float(pos[1]))
        self._particles.emit_burst(
            32, center=center, speed_range=(120.0, 320.0),
            color=self._palette["role_player"], radius_range=(3.0, 6.0),
            life_range=(0.6, 1.2), rng=self._rng,
        )
        self._particles.emit_burst(
            16, center=center, speed_range=(60.0, 180.0),
            color=self._palette["role_boss"], radius_range=(2.0, 5.0),
            life_range=(0.5, 1.0), rng=self._rng,
        )
        self._shake(10.0, 0.6)
        self._start_slow(0.4, 1.5)
        self._start_flash(self._palette["bg_highlight"], 0.5)

    def _on_boss_bitten(self, ev: dict) -> None:
        pos = ev.get("boss_pos") or (0.0, 0.0)
        center = Vec2(float(pos[0]), float(pos[1]))
        self._particles.emit_burst(
            12, center=center, speed_range=(80.0, 200.0),
            color=self._palette["role_threat"], radius_range=(2.0, 4.5),
            life_range=(0.3, 0.6), rng=self._rng,
        )
        # fish-doc/06 §3：反杀 Boss 命中 = 6px × 0.4s。
        self._shake(6.0, 0.4)

    def _on_player_grow(self, ev: dict) -> None:
        pos = ev.get("player_pos") or (0.0, 0.0)
        center = Vec2(float(pos[0]), float(pos[1]))
        self._particles.emit_burst(
            14, center=center, speed_range=(40.0, 140.0),
            color=self._palette["role_player"], radius_range=(2.0, 4.0),
            life_range=(0.5, 0.9), rng=self._rng,
        )
        new_tier = int(ev.get("new_tier", 0))
        self._floating_texts.append(_FloatingText(
            text=f"TIER UP! ({new_tier})",
            x=center.x, y=center.y - 32.0,
            age=0.0, life=1.2, color_name="role_player",
        ))
        self._shake(2.0, 0.2)
