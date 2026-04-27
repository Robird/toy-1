"""Tests for ``toy_engine.render.palette`` (M2-08 / 07-render.md §4.3)."""

from __future__ import annotations

import json

import pytest

from toy_engine.render.palette import Palette
from toy_engine.rng import SeededRng


def test_construct_and_lookup():
    p = Palette({"deep": (10, 20, 30), "fish": (200, 100, 50)})
    assert p["deep"] == (10, 20, 30)
    assert p["fish"] == (200, 100, 50)
    assert "deep" in p
    assert "missing" not in p
    assert set(p.names()) == {"deep", "fish"}


def test_unknown_color_raises():
    p = Palette({"a": (1, 2, 3)})
    with pytest.raises(KeyError):
        p["b"]


def test_invalid_color_rejected():
    with pytest.raises(ValueError):
        Palette({"x": (300, 0, 0)})
    with pytest.raises(ValueError):
        Palette({"x": (0, 0)})  # type: ignore[arg-type]


def test_lighten_extremes():
    p = Palette({"c": (100, 100, 100)})
    assert p.lighten("c", 0) == (100, 100, 100)
    assert p.lighten("c", 1) == (255, 255, 255)
    # midpoint roughly between 100 and 255
    mid = p.lighten("c", 0.5)
    assert all(150 < v < 200 for v in mid)


def test_darken_extremes():
    p = Palette({"c": (200, 100, 50)})
    assert p.darken("c", 0) == (200, 100, 50)
    assert p.darken("c", 1) == (0, 0, 0)


def test_lighten_clamps_k():
    p = Palette({"c": (100, 100, 100)})
    assert p.lighten("c", 5.0) == (255, 255, 255)
    assert p.lighten("c", -1.0) == (100, 100, 100)


def test_jitter_hue_deterministic_with_same_seed():
    p = Palette({"c": (180, 60, 60)})
    rng_a = SeededRng(42)
    rng_b = SeededRng(42)
    out_a = [p.jitter_hue("c", 30.0, rng_a) for _ in range(5)]
    out_b = [p.jitter_hue("c", 30.0, rng_b) for _ in range(5)]
    assert out_a == out_b


def test_jitter_hue_zero_returns_same_color():
    p = Palette({"c": (180, 60, 60)})
    rng = SeededRng(0)
    assert p.jitter_hue("c", 0.0, rng) == (180, 60, 60)


def test_jitter_hue_requires_rng():
    p = Palette({"c": (10, 20, 30)})
    with pytest.raises(TypeError):
        p.jitter_hue("c", 30.0, None)  # type: ignore[arg-type]


def test_jitter_hue_accepts_explicit_rgb():
    rng = SeededRng(1)
    p = Palette({})
    out = p.jitter_hue((100, 50, 200), 60.0, rng)
    assert isinstance(out, tuple) and len(out) == 3
    assert all(0 <= c <= 255 for c in out)


def test_from_json_roundtrip(tmp_path):
    path = tmp_path / "palette.json"
    path.write_text(json.dumps({"sea": [10, 30, 60]}), encoding="utf-8")
    p = Palette.from_json(str(path))
    assert p["sea"] == (10, 30, 60)


def test_no_color_constants_in_module():
    """The palette module must not ship any color constants — only the
    class.  See 07-render.md §4.3 / DoD ('zero built-in color constants')."""
    import re

    from toy_engine.render import palette as palette_mod

    src = open(palette_mod.__file__, "r", encoding="utf-8").read()
    # Strip docstrings/comments crudely; just check that no module-level
    # tuple literal of three ints exists outside the helper functions.
    # We allow occurrences inside strings — the test below is heuristic but
    # sufficient given the small file size.
    public_names = [
        n for n in dir(palette_mod)
        if not n.startswith("_")
        and isinstance(getattr(palette_mod, n), tuple)
    ]
    assert public_names == [], f"unexpected public constants: {public_names}"
    # And there must be no top-level assignment matching a 3-int tuple.
    pattern = re.compile(r"^[A-Z_][A-Z0-9_]*\s*=\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)", re.M)
    assert not pattern.search(src), "palette.py must not declare color constants"
