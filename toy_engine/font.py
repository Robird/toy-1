"""Thin re-export of repository-root ``font_utils`` for engine consumers.

See ``toy-engine/mvp/00-overview.md`` §5 (decision A): the legacy
``font_utils.py`` at the repo root is kept untouched to avoid breaking the
older standalone games (snake.py, suika_game.py, ...). The engine exposes a
single public entry point, ``toy_engine.font``, which simply re-exports the
public symbols from ``font_utils``.
"""

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from font_utils import FONT_ALIASES, load_font  # noqa: E402, F401  re-export

__all__ = ["load_font", "FONT_ALIASES"]
