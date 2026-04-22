import os

import pygame


FONT_ALIASES = {
    "simhei": ("simhei.ttf",),
    "microsoftyahei": ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"),
    "simsun": ("simsun.ttc", "simsun.ttc", "simhei.ttf"),
    "consolas": ("consola.ttf", "consolab.ttf"),
    "segoeuiemoji": ("seguiemj.ttf",),
}


def _normalize_name(font_name):
    return font_name.lower().replace(" ", "")


def _expand_candidates(font_names):
    for font_name in font_names:
        if not font_name:
            continue

        if os.path.splitext(font_name)[1]:
            yield font_name
            continue

        normalized = _normalize_name(font_name)
        if normalized in FONT_ALIASES:
            yield from FONT_ALIASES[normalized]
            continue

        yield font_name
        yield f"{font_name}.ttf"
        yield f"{font_name}.ttc"


def load_font(size, *font_names, fallback_size=None, bold=False, italic=False):
    windows_dir = os.environ.get("WINDIR", r"C:\Windows")
    fonts_dir = os.path.join(windows_dir, "Fonts")

    for candidate in _expand_candidates(font_names):
        if os.path.isabs(candidate):
            font_path = candidate
        else:
            font_path = os.path.join(fonts_dir, candidate)

        if not os.path.exists(font_path):
            continue

        try:
            font = pygame.font.Font(font_path, size)
            font.set_bold(bold)
            font.set_italic(italic)
            return font
        except Exception:
            continue

    font = pygame.font.Font(None, fallback_size or size)
    font.set_bold(bold)
    font.set_italic(italic)
    return font