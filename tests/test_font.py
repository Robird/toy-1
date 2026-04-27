"""Tests for ``toy_engine.font`` thin re-export (M2-07)."""

from __future__ import annotations

import importlib
import os
import sys


def test_import_load_font_from_toy_engine():
    """``from toy_engine.font import load_font`` must work."""
    from toy_engine.font import load_font  # noqa: F401

    assert callable(load_font)


def test_load_font_is_same_object_as_font_utils():
    """The re-exported symbol must be the SAME function object as the source."""
    from toy_engine.font import load_font as engine_load_font
    from font_utils import load_font as root_load_font

    assert engine_load_font is root_load_font


def test_font_aliases_re_exported():
    from toy_engine.font import FONT_ALIASES as engine_aliases
    from font_utils import FONT_ALIASES as root_aliases

    assert engine_aliases is root_aliases


def test_import_has_no_display_side_effects(monkeypatch):
    """Importing ``toy_engine.font`` must not open a window or init video.

    We force the SDL dummy video driver, drop any cached copy of the module,
    re-import it, and assert that ``pygame.display`` was not initialized.
    """
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")

    for mod_name in ("toy_engine.font", "font_utils"):
        sys.modules.pop(mod_name, None)

    import pygame

    if pygame.display.get_init():
        pygame.display.quit()

    importlib.import_module("toy_engine.font")

    assert not pygame.display.get_init(), (
        "Importing toy_engine.font must not initialize pygame.display"
    )


def test_load_font_returns_pygame_font(monkeypatch):
    """Smoke test: ``load_font`` returns a usable ``pygame.font.Font``.

    Runs under the SDL dummy driver so no real window is created.
    """
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")

    import pygame

    if not pygame.font.get_init():
        pygame.font.init()

    from toy_engine.font import load_font

    font = load_font(16, "definitely-not-a-real-font-name-xyz")
    assert isinstance(font, pygame.font.Font)
