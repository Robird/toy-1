"""Render package — pygame-only zone (toy-engine MVP / 07-render.md).

Public surface:
- :class:`GeoCanvas` and :class:`ScreenShake` from :mod:`.pyg`
- :class:`Palette` from :mod:`.palette`
- :class:`ParticleSpec`, :class:`ParticleEmitter`, :class:`ParticleSystem`
  from :mod:`.particles`

``pygame`` is imported lazily by submodules; importing
``toy_engine.render`` itself only triggers the submodule re-exports below
(which do import pygame). Headless tooling that must avoid pygame should
simply not import ``toy_engine.render``.
"""

from __future__ import annotations

from .palette import Palette
from .particles import ParticleEmitter, ParticleSpec, ParticleSystem
from .pyg import GeoCanvas, ScreenShake

__all__ = [
    "GeoCanvas",
    "ScreenShake",
    "Palette",
    "ParticleSpec",
    "ParticleEmitter",
    "ParticleSystem",
]
