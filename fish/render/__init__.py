"""fish.render — visual layer (M3-08).

Submodule overview:
- :mod:`.palette`     — fish-specific Palette (constants from fish-doc/05 §1).
- :mod:`.visuals`     — pure draw functions on top of GeoCanvas.
- :mod:`.pyg_renderer`— PygRenderer that composes background → fishes → player
  → boss → UI → game-over.

Importing this package is safe in both GUI and headless modes (modules below
import pygame indirectly via toy_engine.render; SDL_VIDEODRIVER=dummy in test
conftest keeps it offscreen).
"""

from __future__ import annotations

from .palette import FISH_PALETTE, build_fish_palette, tier_to_role_name
from .pyg_renderer import PygRenderer

__all__ = [
    "FISH_PALETTE",
    "build_fish_palette",
    "tier_to_role_name",
    "PygRenderer",
]
