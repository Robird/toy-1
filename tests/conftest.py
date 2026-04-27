"""Test bootstrap: force SDL into headless mode before pygame is imported.

All render tests rely on offscreen ``pygame.Surface``; we must never open a
real window or audio device in CI.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
