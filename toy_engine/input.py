"""InputSource / InputFrame — toy-engine MVP（参考 03-input.md）。

设计要点：
- ``InputFrame`` 为 ``frozen, slots`` dataclass；``desired_dir`` canonical 类型为
  ``Vec2 | None``。``__post_init__`` 将 ``Vec2Like`` 规范化为 ``Vec2``、并校验
  非 NaN/有限/非零向量。``None`` 与零向量必须区分（零向量非法）。
- ``InputSource`` 为 ``Protocol``，结构化子类型即兼容；``poll`` 不得修改 world_state。
- ``KeyboardMouseInput`` 内部走可注入的 IO 桩（``_pump``/``_get_pressed``/...），
  方便测试 monkeypatch；引擎不创建 pygame 窗口。
- ``ReplayInput`` 按逻辑帧序号驱动；越界默认返回静止帧，``strict_end=True`` 抛
  ``EndOfReplay``。``from_recording`` 实现稀疏 → 稠密展开（见 04-recorder.md §3.1）。
- ``BotInputBase`` 只是基类骨架，构造统一接受 ``SeededRng``，启发式留 fish。
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from os import PathLike
from typing import Any, Callable, Protocol, runtime_checkable

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # 顶层 import 不会创建窗口；KeyboardMouseInput 也不调用 pygame.display.*

from toy_engine.geom import Vec2, _to_vec2
from toy_engine.rng import SeededRng

__all__ = [
    "InputFrame",
    "InputSource",
    "KeyboardMouseInput",
    "ReplayInput",
    "BotInputBase",
    "InputContractError",
    "EndOfReplay",
]


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class InputContractError(RuntimeError):
    """``InputSource.poll`` 期间 world_state 不符合契约时抛出。"""


class EndOfReplay(RuntimeError):
    """``ReplayInput`` 在 ``strict_end=True`` 模式下越界时抛出。"""


# ---------------------------------------------------------------------------
# InputFrame
# ---------------------------------------------------------------------------


def _is_finite_pair(v: Vec2) -> bool:
    return math.isfinite(v.x) and math.isfinite(v.y)


@dataclass(frozen=True, slots=True)
class InputFrame:
    """一帧输入快照（详见 03-input.md §2）。

    ``desired_dir``：``None`` 表示本帧无方向意图（自然减速 / 待命）；非 ``None``
    时必须是有限、长度约为 1 的归一化 ``Vec2``。零向量与 NaN 均非法。
    构造时接受 ``Vec2Like``，规范化为 ``Vec2``。
    """

    desired_dir: Vec2 | None = None
    dash: bool = False

    def __post_init__(self) -> None:
        d = self.desired_dir
        if d is not None:
            # 允许 Vec2Like（含 tuple）入参
            if not isinstance(d, Vec2):
                d = _to_vec2(d)  # type: ignore[arg-type]
                object.__setattr__(self, "desired_dir", d)
            if not _is_finite_pair(d):
                raise ValueError(
                    f"InputFrame.desired_dir must be finite, got {d!r}"
                )
            length = math.hypot(d.x, d.y)
            if length == 0.0:
                raise ValueError(
                    "InputFrame.desired_dir=Vec2(0, 0) is not a valid direction; "
                    "use desired_dir=None to express 'no input'."
                )
            if not (0.999 <= length <= 1.001):
                raise ValueError(
                    f"InputFrame.desired_dir must be unit-length (~1.0), "
                    f"got length={length!r}"
                )
        if not isinstance(self.dash, bool):
            raise TypeError(
                f"InputFrame.dash must be bool, got {type(self.dash).__name__}"
            )

    # ----- 序列化辅助（Recorder 复用） -----
    def to_wire(self) -> dict:
        """JSON 友好的 wire 表示：``{"dir": [x,y]|None, "dash": bool}``。"""
        if self.desired_dir is None:
            d: list[float] | None = None
        else:
            d = [self.desired_dir.x, self.desired_dir.y]
        return {"dir": d, "dash": self.dash}

    @classmethod
    def from_wire(cls, payload: dict) -> "InputFrame":
        if not isinstance(payload, dict):
            raise TypeError(
                f"InputFrame wire payload must be dict, got {type(payload).__name__}"
            )
        if "dir" not in payload:
            raise ValueError("InputFrame wire payload missing required field 'dir'")
        if "dash" not in payload:
            raise ValueError("InputFrame wire payload missing required field 'dash'")

        dash = payload["dash"]
        if not isinstance(dash, bool):
            raise TypeError(
                f"InputFrame wire field 'dash' must be bool, got {type(dash).__name__}"
            )

        d = payload["dir"]
        if d is None:
            return cls(desired_dir=None, dash=dash)
        if not isinstance(d, (list, tuple)) or len(d) != 2:
            raise ValueError("InputFrame wire field 'dir' must be None or [x, y]")
        x, y = d
        return cls(desired_dir=Vec2(float(x), float(y)), dash=dash)


# ---------------------------------------------------------------------------
# InputSource Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class InputSource(Protocol):
    """每帧输入来源的结构化协议（见 03-input.md §3）。

    ``GameLoop`` 每个逻辑帧只调用一次 ``poll``；实现可以维护内部状态，因此
    ``poll`` 不是幂等 API。``poll`` 不得修改 ``world_state``。
    """

    def poll(self, world_state: Any) -> InputFrame:  # pragma: no cover - protocol
        ...


# ---------------------------------------------------------------------------
# KeyboardMouseInput
# ---------------------------------------------------------------------------


# 通过模块级函数间接调用 pygame，便于 headless 测试 monkeypatch；
# 不在 import 期或构造期创建窗口 / 调用 pygame.display.*。
def _pygame_pump() -> None:
    pygame.event.pump()


def _pygame_get_pressed() -> Any:
    return pygame.key.get_pressed()


def _pygame_get_mouse_pos() -> tuple[int, int]:
    return pygame.mouse.get_pos()


def _pygame_get_focused() -> bool:
    return bool(pygame.key.get_focused())


# 方向键集合（用 pygame 常量；常量本身不需要 display init 即可读取）。
_KEY_LEFT = (pygame.K_a, pygame.K_LEFT)
_KEY_RIGHT = (pygame.K_d, pygame.K_RIGHT)
_KEY_UP = (pygame.K_w, pygame.K_UP)
_KEY_DOWN = (pygame.K_s, pygame.K_DOWN)


def _axis(pressed: Any, neg_keys: tuple[int, ...], pos_keys: tuple[int, ...]) -> int:
    pos = any(pressed[k] for k in pos_keys)
    neg = any(pressed[k] for k in neg_keys)
    return (1 if pos else 0) - (1 if neg else 0)


class KeyboardMouseInput:
    """键鼠输入源（见 03-input.md §4.1）。

    Parameters
    ----------
    dead_zone_px:
        鼠标距 ``player_pos`` 小于该值时返回 ``desired_dir=None``。
    screen_to_world:
        将屏幕坐标转换为世界坐标的可调用对象；``None`` 视为 identity。
    viewport:
        可选 ``(width, height)``；若提供则鼠标坐标先 clamp 到 viewport 再做
        ``screen_to_world``，避免越界值进入业务方。
    initial_mode:
        起始模式，``"mouse"`` 或 ``"keyboard"``；默认 ``"mouse"``。
    """

    __slots__ = (
        "_dead_zone_px",
        "_screen_to_world",
        "_viewport",
        "_mode",
        "_last_mouse_pos",
    )

    def __init__(
        self,
        dead_zone_px: float = 15.0,
        screen_to_world: Callable[[tuple[float, float]], tuple[float, float]] | None = None,
        *,
        viewport: tuple[int, int] | None = None,
        initial_mode: str = "mouse",
    ) -> None:
        if dead_zone_px < 0:
            raise ValueError("dead_zone_px must be >= 0")
        if initial_mode not in ("mouse", "keyboard"):
            raise ValueError("initial_mode must be 'mouse' or 'keyboard'")
        self._dead_zone_px = float(dead_zone_px)
        self._screen_to_world = screen_to_world
        self._viewport = viewport
        self._mode: str = initial_mode
        self._last_mouse_pos: tuple[float, float] | None = None

    # 暴露给测试观察的只读属性
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def last_mouse_pos(self) -> tuple[float, float] | None:
        return self._last_mouse_pos

    def poll(self, world_state: Any) -> InputFrame:
        _pygame_pump()

        # 失焦：直接返回静止；不更新内部状态以免使用脏键鼠数据。
        if not _pygame_get_focused():
            return InputFrame(desired_dir=None)

        # 引擎对 world_state 的唯一硬约束：必须暴露 player_pos: (float, float)。
        # 优先支持文档中的属性形式；同时容忍 dict / Mapping snapshot 的 key 形式。
        if hasattr(world_state, "player_pos"):
            player_pos = world_state.player_pos
        elif isinstance(world_state, Mapping) and "player_pos" in world_state:
            player_pos = world_state["player_pos"]
        else:
            raise InputContractError(
                "world_state.snapshot() must expose `player_pos: tuple[float, float]` "
                "as an attribute or mapping key for KeyboardMouseInput."
            )
        try:
            px, py = player_pos
            px = float(px)
            py = float(py)
        except Exception as exc:  # noqa: BLE001
            raise InputContractError(
                f"world_state.player_pos must be a 2-tuple of floats, "
                f"got {player_pos!r}"
            ) from exc

        pressed = _pygame_get_pressed()
        dx = _axis(pressed, _KEY_LEFT, _KEY_RIGHT)
        dy = _axis(pressed, _KEY_UP, _KEY_DOWN)
        has_kb_dir = (dx, dy) != (0, 0)

        raw_mouse = _pygame_get_mouse_pos()
        if self._viewport is not None:
            vw, vh = self._viewport
            mx, my = raw_mouse
            raw_mouse = (max(0, min(vw, mx)), max(0, min(vh, my)))

        if has_kb_dir:
            # 切到/保持 keyboard，并冻结当前鼠标位置作为后续运动检测基准
            self._mode = "keyboard"
            self._last_mouse_pos = (float(raw_mouse[0]), float(raw_mouse[1]))
            n = math.hypot(dx, dy)
            return InputFrame(desired_dir=Vec2(dx / n, dy / n))

        if self._mode == "keyboard":
            # 无键盘输入：保持 keyboard 直到鼠标相对冻结点移动
            if (
                self._last_mouse_pos is not None
                and (float(raw_mouse[0]), float(raw_mouse[1])) != self._last_mouse_pos
            ):
                self._mode = "mouse"
                # 落入下方 mouse 处理；last_mouse_pos 在 mouse 分支统一更新
            else:
                # 仍 keyboard，无方向意图
                return InputFrame(desired_dir=None)

        # ---- mouse 模式 ----
        self._last_mouse_pos = (float(raw_mouse[0]), float(raw_mouse[1]))
        if self._screen_to_world is not None:
            world_mouse = self._screen_to_world(self._last_mouse_pos)
            wmx, wmy = float(world_mouse[0]), float(world_mouse[1])
        else:
            wmx, wmy = self._last_mouse_pos

        ddx = wmx - px
        ddy = wmy - py
        dist = math.hypot(ddx, ddy)
        if dist < self._dead_zone_px:
            return InputFrame(desired_dir=None)
        return InputFrame(desired_dir=Vec2(ddx / dist, ddy / dist))


# ---------------------------------------------------------------------------
# ReplayInput
# ---------------------------------------------------------------------------


class ReplayInput:
    """按帧号驱动的回放输入源（见 03-input.md §4.2）。

    ``frames_by_index`` 必须是已展开的稠密 ``list[InputFrame]``。越界时：
    ``strict_end=False`` 默认返回静止帧；``strict_end=True`` 抛 ``EndOfReplay``。
    """

    __slots__ = ("_frames", "_strict_end", "_idx")

    def __init__(
        self,
        frames_by_index: list[InputFrame],
        *,
        strict_end: bool = False,
    ) -> None:
        if not isinstance(frames_by_index, list):
            raise TypeError("frames_by_index must be a list[InputFrame]")
        for i, f in enumerate(frames_by_index):
            if not isinstance(f, InputFrame):
                raise TypeError(
                    f"frames_by_index[{i}] must be InputFrame, "
                    f"got {type(f).__name__}"
                )
        self._frames: list[InputFrame] = frames_by_index
        self._strict_end = bool(strict_end)
        self._idx = 0

    @property
    def frame_idx(self) -> int:
        return self._idx

    def __len__(self) -> int:
        return len(self._frames)

    def poll(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        # ReplayInput 不读取 world_state；纯按 frame_idx 推进
        if self._idx >= len(self._frames):
            if self._strict_end:
                raise EndOfReplay(
                    f"ReplayInput exhausted at frame_idx={self._idx} "
                    f"(len={len(self._frames)})"
                )
            return InputFrame(desired_dir=None, dash=False)
        frame = self._frames[self._idx]
        self._idx += 1
        return frame

    # ----- from_recording -----
    @classmethod
    def from_recording(
        cls,
        path: str | PathLike[str],
        *,
        strict_end: bool = False,
    ) -> "tuple[Any, ReplayInput]":
        """读取 Recorder 录像 JSON / JSON.gz，返回 ``(config, ReplayInput)``。

        薄包装：所有解析、hash 校验、稀疏 → 稠密展开均委托给
        :class:`toy_engine.recorder.Recorder`。返回的 ``config`` 即
        ``Recording.level_config``（无 deserializer 时为原始 dict）；调用方
        若需要 ``Recording`` 的其它字段（``seed``、``meta`` 等），应直接使用
        ``Recorder.load(path)``。
        """
        # 延迟 import，打破 ``input <-> recorder`` 循环依赖。
        from toy_engine.recorder import Recorder

        rec = Recorder.load(path)
        return rec.level_config, cls(rec.frames, strict_end=strict_end)


# ---------------------------------------------------------------------------
# BotInputBase
# ---------------------------------------------------------------------------


class BotInputBase:
    """Bot 输入源基类（见 03-input.md §4.3）。

    引擎只提供骨架；具体启发式（避险、追星、Boss 特判等）属业务知识，住在
    ``fish/ai/bot_player.py``。
    """

    def __init__(self, rng: SeededRng) -> None:
        if not isinstance(rng, SeededRng):
            raise TypeError(
                f"BotInputBase requires SeededRng, got {type(rng).__name__}"
            )
        self.rng = rng

    def poll(self, world_state: Any) -> InputFrame:
        return self.decide(world_state)

    def decide(self, world_state: Any) -> InputFrame:  # noqa: ARG002
        raise NotImplementedError("BotInputBase subclasses must implement decide().")

    def reset(self) -> None:
        """同一实例在批量跑分前清空内部缓存的 hook；默认无状态。"""
        return None
