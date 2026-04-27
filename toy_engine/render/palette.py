"""Palette — named color storage + lighten/darken/jitter helpers.

See ``toy-engine/mvp/07-render.md`` §4.3.

The engine intentionally ships **no** color constants; concrete palettes
(e.g. fish ``PALETTE_DEEP``) live in the consuming game.
"""

from __future__ import annotations

import colorsys
import json
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from ..rng import SeededRng

__all__ = ["Palette"]

Color3 = tuple[int, int, int]


def _coerce_color(c) -> Color3:
    if not hasattr(c, "__iter__"):
        raise TypeError(f"color must be iterable of 3 ints, got {type(c).__name__}")
    parts = tuple(c)
    if len(parts) != 3:
        raise ValueError(f"color must have exactly 3 channels, got {len(parts)}")
    out = []
    for v in parts:
        iv = int(v)
        if iv < 0 or iv > 255:
            raise ValueError(f"color channel out of range [0,255]: {v}")
        out.append(iv)
    return (out[0], out[1], out[2])


def _lerp_channel(a: int, b: int, k: float) -> int:
    v = a + (b - a) * k
    if v < 0:
        v = 0.0
    elif v > 255:
        v = 255.0
    return int(round(v))


class Palette:
    """命名颜色集合。

    构造时拷贝 + 校验输入。``__getitem__`` 返回的是 tuple，调用方修改不会
    影响内部状态。
    """

    __slots__ = ("_named",)

    def __init__(self, named: Mapping[str, Color3]) -> None:
        if not isinstance(named, Mapping):
            raise TypeError("Palette requires a Mapping[str, (int,int,int)]")
        self._named: dict[str, Color3] = {}
        for k, v in named.items():
            if not isinstance(k, str):
                raise TypeError(f"palette keys must be str, got {type(k).__name__}")
            self._named[k] = _coerce_color(v)

    @classmethod
    def from_json(cls, path: str) -> "Palette":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"palette JSON root must be object, got {type(data).__name__}")
        return cls(data)

    # ---- access ----
    def __getitem__(self, name: str) -> Color3:
        try:
            return self._named[name]
        except KeyError:
            raise KeyError(f"unknown palette color: {name!r}") from None

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._named

    def names(self) -> list[str]:
        return list(self._named.keys())

    # ---- mixing ----
    def lighten(self, name: str, k: float) -> Color3:
        """朝白色 lerp，``k`` 自动 clamp 到 ``[0, 1]``。"""
        if k < 0:
            k = 0.0
        elif k > 1:
            k = 1.0
        r, g, b = self[name]
        return (_lerp_channel(r, 255, k), _lerp_channel(g, 255, k), _lerp_channel(b, 255, k))

    def darken(self, name: str, k: float) -> Color3:
        """朝黑色 lerp，``k`` 自动 clamp 到 ``[0, 1]``。"""
        if k < 0:
            k = 0.0
        elif k > 1:
            k = 1.0
        r, g, b = self[name]
        return (_lerp_channel(r, 0, k), _lerp_channel(g, 0, k), _lerp_channel(b, 0, k))

    def jitter_hue(self, color, deg: float, rng: "SeededRng") -> Color3:
        """色相在 ``[-deg/2, +deg/2]`` 范围内随机抖动。

        ``color`` 可以是已有命名色（``str``）或显式 ``(r,g,b)``。**必须**
        外部传入 ``SeededRng``——禁止内部使用 ``random.*``，否则破坏
        determinism。
        """
        if rng is None:
            raise TypeError("jitter_hue requires an explicit SeededRng instance")
        if isinstance(color, str):
            rgb = self[color]
        else:
            rgb = _coerce_color(color)
        if deg == 0:
            return rgb
        # convert RGB→HLS, jitter H by ±deg/2 degrees, back to RGB
        r, g, b = rgb
        h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
        # rng.uniform from external SeededRng
        offset_deg = rng.uniform(-deg / 2.0, deg / 2.0)
        h_new = (h + offset_deg / 360.0) % 1.0
        nr, ng, nb = colorsys.hls_to_rgb(h_new, l, s)
        return (
            int(round(nr * 255)),
            int(round(ng * 255)),
            int(round(nb * 255)),
        )
