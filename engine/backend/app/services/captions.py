"""Word-synchronised captions as ASS subtitles (rendered by FFmpeg/libass).

Words come straight from Whisper's word timestamps — caption text is never generated.
Styles are data (CaptionStyle) so the Phase 4 editor can change any field.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace

from app.services.highlights import MIN_WORD_PROB, _NO_SPACE_BEFORE
from app.services.translit import romanize

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


@dataclass
class CaptionStyle:
    preset: str = "bold"
    animation: str = "highlight"      # highlight (active word pops) | karaoke (fill) | none
    font: str = "Poppins"             # family from app.services.fonts
    bold: bool = True
    size: int = 88                    # px at 1080x1920
    uppercase: bool = True
    text_color: str = "#FFFFFF"
    highlight_color: str = "#FFD60A"
    outline_color: str = "#000000"
    outline: float = 6.0
    shadow: float = 2.0
    box: bool = False                 # opaque box behind text
    box_color: str = "#000000"
    box_opacity: float = 0.55
    position: str = "lower"           # lower | middle | upper
    max_words: int = 3
    max_chars: int = 18
    highlight_scale: int = 112        # % size of the active word (highlight animation)


PRESETS: dict[str, CaptionStyle] = {
    "bold": CaptionStyle(),
    "karaoke": CaptionStyle(preset="karaoke", animation="karaoke", size=76, max_words=5, max_chars=26,
                            highlight_color="#A78BFA", uppercase=False),
    "minimal": CaptionStyle(preset="minimal", animation="none", bold=False, size=56, uppercase=False,
                            outline=0, shadow=0, box=True, box_opacity=0.5, max_words=7, max_chars=34),
    "headline": CaptionStyle(preset="headline", font="Anton", bold=False, size=112, highlight_color="#4ADE80",
                             outline=7, max_words=2, max_chars=14, highlight_scale=118),
}

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_LIMITS = {"size": (30, 160), "outline": (0, 12), "shadow": (0, 8), "box_opacity": (0.0, 1.0),
           "max_words": (1, 8), "max_chars": (8, 40), "highlight_scale": (100, 140)}
_ENUMS = {"animation": {"highlight", "karaoke", "none"}, "position": {"lower", "middle", "upper"}}


class StyleError(ValueError):
    pass


def get_style(name: str | None, overrides: dict | None = None) -> CaptionStyle:
    """Preset + validated overrides. Unknown keys are ignored; bad values raise StyleError."""
    from app.services.fonts import BY_FAMILY

    base = PRESETS.get(name or "bold", PRESETS["bold"])
    fields = asdict(base)
    clean = {}
    for k, v in (overrides or {}).items():
        if k not in fields or k == "preset":
            continue
        cur = fields[k]
        if k == "font":
            if v not in BY_FAMILY:
                raise StyleError(f"Unknown font: {v}")
        elif k.endswith("_color"):
            if not isinstance(v, str) or not _HEX.match(v):
                raise StyleError(f"{k} must be a colour like #FFD60A")
        elif k in _ENUMS:
            if v not in _ENUMS[k]:
                raise StyleError(f"{k} must be one of {sorted(_ENUMS[k])}")
        elif isinstance(cur, bool):
            if not isinstance(v, bool):
                raise StyleError(f"{k} must be true or false")
        elif isinstance(cur, (int, float)):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise StyleError(f"{k} must be a number")
            lo, hi = _LIMITS.get(k, (float("-inf"), float("inf")))
            if not lo <= v <= hi:
                raise StyleError(f"{k} must be between {lo} and {hi}")
            v = type(cur)(v)
        clean[k] = v
    st = replace(base, **clean)
    if st.bold and not BY_FAMILY[st.font].bold:
        st = replace(st, bold=False)  # single-weight display fonts: never fake-bold
    return st


# ------------------------------------------------------------------ words -> pages

@dataclass
class Word:
    start: float
    end: float
    text: str


def clip_words(words: list[dict], start: float, end: float, script: str = "native") -> list[Word]:
    """Words inside [start, end), times relative to the clip, punctuation glued to its word.

    script="roman" turns Devanagari into Hinglish word-for-word (timing unchanged).
    """
    out: list[Word] = []
    for w in words:
        if w.get("prob", 1.0) < MIN_WORD_PROB or w["end"] <= start or w["start"] >= end:
            continue
        ws, we = max(0.0, w["start"] - start), min(end - start, w["end"] - start)
        text = (romanize(w["text"]) if script == "roman" else w["text"]).strip()
        if not text:  # hidden by the user in the editor
            continue
        if out and _NO_SPACE_BEFORE.match(text):
            out[-1].text += text
            out[-1].end = we
        else:
            out.append(Word(ws, we, text))
    return out


def paginate(words: list[Word], max_words: int, max_chars: int, gap: float = 0.6) -> list[list[Word]]:
    """Short caption 'pages': break on word/char limits, pauses, and sentence ends."""
    pages: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        chars = sum(len(x.text) + 1 for x in cur) + len(w.text)
        if cur and (len(cur) >= max_words or chars > max_chars or w.start - cur[-1].end > gap):
            pages.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.?!।]$", w.text):
            pages.append(cur)
            cur = []
    if cur:
        pages.append(cur)
    return pages


# ------------------------------------------------------------------ ASS output

def ass_color(hex_rgb: str, opacity: float = 1.0) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    alpha = int(round((1 - opacity) * 255))
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _clean(text: str, st: CaptionStyle) -> str:
    text = text.replace("\\", "").replace("{", "(").replace("}", ")")
    if st.preset == "bold":
        text = re.sub(r"[.,;:]+$", "", text)  # creator style drops trailing commas/periods
    return text.upper() if st.uppercase else text


def build_ass(words: list[Word], duration: float, st: CaptionStyle, width: int = 1080, height: int = 1920) -> str:
    from app.services.fonts import BY_FAMILY, DEVANAGARI_FALLBACK

    font = st.font
    if any(_DEVANAGARI.search(w.text) for w in words) and not BY_FAMILY[font].devanagari:
        font = DEVANAGARI_FALLBACK  # e.g. Anton has no Devanagari glyphs
    align = {"lower": 2, "middle": 5, "upper": 8}.get(st.position, 2)
    margin_v = {"lower": int(height * 0.24), "middle": 0, "upper": int(height * 0.14)}.get(st.position, 0)
    border_style = 3 if st.box else 1
    outline = 18 if st.box else st.outline  # BorderStyle 3: outline = box padding
    outline_col = ass_color(st.box_color, st.box_opacity) if st.box else ass_color(st.outline_color)
    # Karaoke fills from Secondary -> Primary, so Primary is the highlight colour there.
    primary = ass_color(st.highlight_color if st.animation == "karaoke" else st.text_color)
    secondary = ass_color(st.text_color)
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cap,{font},{st.size},{primary},{secondary},{outline_col},{ass_color('#000000', 0.6)},"
        f"{-1 if st.bold else 0},0,0,0,100,100,0,0,{border_style},{outline},{st.shadow},{align},"
        f"90,90,{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines: list[str] = []
    pages = paginate(words, st.max_words, st.max_chars)
    hi = ass_color(st.highlight_color)
    for pi, page in enumerate(pages):
        nxt = pages[pi + 1][0].start if pi + 1 < len(pages) else duration
        p_end = min(page[-1].end + 0.35, nxt, duration)
        texts = [_clean(w.text, st) for w in page]
        if st.animation == "highlight":
            for wi, w in enumerate(page):
                s = page[0].start if wi == 0 else w.start
                e = page[wi + 1].start if wi + 1 < len(page) else p_end
                if e <= s:
                    continue
                parts = [
                    (f"{{\\c{hi}\\fscx{st.highlight_scale}\\fscy{st.highlight_scale}}}{t}{{\\r}}" if j == wi else t)
                    for j, t in enumerate(texts)
                ]
                lines.append(f"Dialogue: 0,{_ts(s)},{_ts(e)},Cap,,0,0,0,,{' '.join(parts)}")
        elif st.animation == "karaoke":
            cursor, parts = page[0].start, []
            for w, t in zip(page, texts):
                if w.start - cursor > 0.01:
                    parts.append(f"{{\\k{int(round((w.start - cursor) * 100))}}}")
                parts.append(f"{{\\kf{max(1, int(round((w.end - w.start) * 100)))}}}{t} ")
                cursor = w.end
            lines.append(f"Dialogue: 0,{_ts(page[0].start)},{_ts(p_end)},Cap,,0,0,0,,{''.join(parts).rstrip()}")
        else:
            lines.append(f"Dialogue: 0,{_ts(page[0].start)},{_ts(p_end)},Cap,,0,0,0,,{' '.join(texts)}")
    return header + "\n".join(lines) + "\n"
