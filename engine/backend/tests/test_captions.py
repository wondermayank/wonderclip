from __future__ import annotations

import re

from app.services import captions as cap
from app.services.captions import Word


def W(*items):
    return [Word(s, e, t) for s, e, t in items]


def test_clip_words_relative_times_and_glued_punctuation():
    words = [{"start": 9.0, "end": 9.5, "text": "before", "prob": 1},
             {"start": 10.2, "end": 10.5, "text": "got", "prob": 1},
             {"start": 10.6, "end": 10.9, "text": "300", "prob": 1},
             {"start": 10.9, "end": 11.2, "text": ",000", "prob": 1},
             {"start": 11.3, "end": 11.4, "text": "4.", "prob": 0.05},   # hallucination dropped
             {"start": 11.5, "end": 11.9, "text": "views.", "prob": 1},
             {"start": 20.5, "end": 21.0, "text": "after", "prob": 1}]
    out = cap.clip_words(words, 10.0, 20.0)
    assert [w.text for w in out] == ["got", "300,000", "views."]
    assert abs(out[0].start - 0.2) < 1e-9 and abs(out[1].end - 1.2) < 1e-9


def test_roman_script_keeps_timing_and_uses_latin_font():
    words = [{"start": 1.0, "end": 1.4, "text": "इतना", "prob": 1}, {"start": 1.5, "end": 1.9, "text": "आसान", "prob": 1},
             {"start": 2.0, "end": 2.3, "text": "free", "prob": 1}]
    roman = cap.clip_words(words, 1.0, 3.0, script="roman")
    native = cap.clip_words(words, 1.0, 3.0)
    assert [w.text for w in roman] == ["itna", "aasan", "free"]
    assert [(w.start, w.end) for w in roman] == [(w.start, w.end) for w in native]
    assert "Style: Cap,Poppins," in cap.build_ass(roman, 2.0, cap.get_style("headline", {"font": "Poppins"}))
    assert "Style: Cap,Poppins," in cap.build_ass(native, 2.0, cap.get_style("headline"))  # Anton has no Devanagari


def test_paginate_limits_pauses_and_sentence_ends():
    ws = W((0, .3, "one"), (.4, .7, "two"), (.8, 1.0, "three"), (1.1, 1.3, "four"),
           (3.0, 3.3, "after-pause"), (3.4, 3.6, "end."), (3.7, 4.0, "next"))
    pages = cap.paginate(ws, max_words=3, max_chars=40)
    assert [[w.text for w in p] for p in pages] == [["one", "two", "three"], ["four"], ["after-pause", "end."], ["next"]]


def test_ass_color_is_bgr_with_alpha():
    assert cap.ass_color("#FFD60A") == "&H000AD6FF"
    assert cap.ass_color("#000000", 0.5) == "&H80000000"


def _events(ass: str) -> list[str]:
    return [l for l in ass.splitlines() if l.startswith("Dialogue:")]


def test_highlight_one_event_per_word_and_no_gaps_within_page():
    ws = W((0.0, 0.4, "hello"), (0.5, 0.9, "big"), (1.0, 1.5, "world"))
    ev = _events(cap.build_ass(ws, 5.0, cap.get_style("bold")))
    assert len(ev) == 3
    assert "{\\c&H000AD6FF" in ev[1] and "BIG" in ev[1]  # active word coloured, uppercase preset
    times = [re.match(r"Dialogue: 0,([^,]+),([^,]+)", e).groups() for e in ev]
    assert times[0][1] == times[1][0] and times[1][1] == times[2][0]  # contiguous
    assert times[2][1] == "0:00:01.85"  # last word end + 0.35 hold


def test_karaoke_durations_match_words():
    ws = W((0.0, 0.4, "a"), (0.6, 1.0, "b"))
    [ev] = _events(cap.build_ass(ws, 3.0, cap.get_style("karaoke")))
    assert "{\\kf40}a" in ev and "{\\k20}" in ev and "{\\kf40}b" in ev


def test_minimal_uses_box_and_plain_text():
    ass = cap.build_ass(W((0, .5, "Hi"), (.6, 1, "there")), 2.0, cap.get_style("minimal"))
    style = next(l for l in ass.splitlines() if l.startswith("Style:"))
    assert style.split(",")[15] == "3"  # BorderStyle 3 = opaque box
    assert _events(ass)[0].endswith("Hi there")


def test_devanagari_picks_devanagari_font_and_braces_escaped():
    ass = cap.build_ass(W((0, .5, "नमस्ते"), (.6, 1, "{x}")), 2.0, cap.get_style("bold"))
    assert "Style: Cap,Poppins," in ass
    assert "{X}" not in ass and "(X)" in ass


def test_style_overrides_only_known_fields():
    st = cap.get_style("bold", {"size": 70, "evil": "x"})
    assert st.size == 70 and not hasattr(st, "evil")


import pytest  # noqa: E402


@pytest.mark.parametrize("bad", [{"font": "Comic Sans"}, {"text_color": "red"}, {"text_color": "#FFF"},
                                 {"size": 500}, {"size": "big"}, {"position": "left"}, {"bold": "yes"},
                                 {"box_opacity": 2}, {"animation": "spin"}])
def test_style_rejects_bad_values(bad):
    with pytest.raises(cap.StyleError):
        cap.get_style("bold", bad)


def test_single_weight_font_is_never_fake_bold():
    assert cap.get_style("bold", {"font": "Anton", "bold": True}).bold is False
    assert cap.get_style("minimal", {"font": "Mukta", "bold": True}).bold is True
