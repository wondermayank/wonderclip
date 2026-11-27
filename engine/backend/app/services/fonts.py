"""Caption font registry. The same TTF files are used by libass (render) and the browser (preview)."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True)
class FontFamily:
    family: str             # name libass / CSS use
    regular: str | None     # file names in assets/fonts
    bold: str | None
    devanagari: bool        # has Devanagari glyphs
    category: str           # for grouping in the UI


FONTS: list[FontFamily] = [
    FontFamily("Poppins", "Poppins-Regular.ttf", "Poppins-Bold.ttf", True, "Clean"),
    FontFamily("Mukta", "Mukta-Regular.ttf", "Mukta-Bold.ttf", True, "Clean"),
    FontFamily("Hind", "Hind-Regular.ttf", "Hind-Bold.ttf", True, "Clean"),
    FontFamily("Anton", "Anton-Regular.ttf", None, False, "Headline"),
    FontFamily("Bebas Neue", "BebasNeue-Regular.ttf", None, False, "Headline"),
    FontFamily("Archivo Black", "ArchivoBlack-Regular.ttf", None, False, "Headline"),
    FontFamily("Lilita One", "LilitaOne-Regular.ttf", None, False, "Fun"),
    FontFamily("Bangers", "Bangers-Regular.ttf", None, False, "Fun"),
    FontFamily("Kalam", "Kalam-Regular.ttf", "Kalam-Bold.ttf", True, "Handwritten"),
]
BY_FAMILY = {f.family: f for f in FONTS}
DEVANAGARI_FALLBACK = "Poppins"


def font_files() -> set[str]:
    return {n for f in FONTS for n in (f.regular, f.bold) if n}


def available() -> list[FontFamily]:
    """Fonts whose files are actually present (scripts/fetch_fonts.ps1)."""
    d = get_settings().fonts_dir
    from pathlib import Path

    return [f for f in FONTS if f.regular and (Path(d) / f.regular).exists()]
