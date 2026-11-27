"""Pure-logic tests for highlight validation (no LLM, no GPU)."""
from __future__ import annotations

import re

import pytest

from app.services import highlights as hl
from app.services.highlights import Sentence


@pytest.fixture(autouse=True)
def _env(settings_env):
    yield


def fake_words(n_sentences: int = 40, sec_per_sentence: float = 5.0) -> list[dict]:
    """Sentence i spans [i*5, i*5+4.5]: 'Point number i is important.'"""
    words = []
    for i in range(n_sentences):
        toks = ["Point", "number", str(i), "is", "important."]
        t0 = i * sec_per_sentence
        for j, tok in enumerate(toks):
            words.append({"start": t0 + j * 0.9, "end": t0 + j * 0.9 + 0.8, "text": tok, "prob": 0.9})
    return words


@pytest.fixture()
def sents() -> list[Sentence]:
    return hl.build_sentences(fake_words())


DUR = 200.0


def cand(a, b, **kw):
    return {"start_sentence": a, "end_sentence": b, "title": "T", "hook": "", "reason": "r",
            "editorial_score": 7, **kw}


def test_build_sentences_splits_on_punctuation(sents):
    assert len(sents) == 40
    assert sents[3].text == "Point number 3 is important."
    assert sents[3].start == 15.0


def test_build_sentences_splits_on_long_pause():
    w = [{"start": 0, "end": 0.5, "text": "hello", "prob": 1}, {"start": 3.0, "end": 3.5, "text": "world", "prob": 1}]
    assert [s.text for s in hl.build_sentences(w)] == ["hello", "world"]


def test_short_clip_is_extended_to_minimum(sents):
    [h] = hl.validate([cand(4, 4)], sents, DUR, 4)
    assert 20 <= h.duration <= 60
    assert h.start_sentence == 4


def test_long_clip_is_trimmed_to_maximum(sents):
    [h] = hl.validate([cand(0, 30)], sents, DUR, 4)
    assert 20 <= h.duration <= 60


def test_overlapping_and_invalid_candidates_rejected(sents):
    out = hl.validate([cand(0, 6, editorial_score=9), cand(3, 9, editorial_score=8),
                       cand(99, 120), cand(-5, 2), {"start_sentence": "x"}, cand(20, 26)], sents, DUR, 4)
    ranges = [(h.start_sentence, h.end_sentence) for h in out]
    assert len(out) == 2
    for i, (a, b) in enumerate(ranges):
        for c, d in ranges[i + 1:]:
            assert b < c or d < a


def test_times_stay_inside_video_and_between_neighbours(sents):
    for h in hl.validate([cand(0, 5), cand(34, 39)], sents, DUR, 4):
        assert 0 <= h.start_time < h.end_time <= DUR
        if h.start_sentence > 0:
            assert h.start_time >= sents[h.start_sentence - 1].end - 1e-6
        if h.end_sentence + 1 < len(sents):
            assert h.end_time <= sents[h.end_sentence + 1].start + 1e-6


def test_invented_hook_replaced_with_real_words(sents):
    [h] = hl.validate([cand(10, 15, hook="This will blow your mind")], sents, DUR, 4)
    assert h.hook == sents[10].text


def test_grounded_hook_kept(sents):
    [h] = hl.validate([cand(10, 15, hook="Point number 10 is important")], sents, DUR, 4)
    assert h.hook == "Point number 10 is important"


def test_transcript_is_exact_source_text(sents):
    [h] = hl.validate([cand(10, 15)], sents, DUR, 4)
    assert h.transcript == " ".join(s.text for s in sents[h.start_sentence:h.end_sentence + 1])


def test_score_normalisation():
    assert hl._score(70) == 7 and hl._score(0) == 1 and hl._score("bad") == 5 and hl._score(11) == 1


def test_limit_respected_and_best_first(sents):
    cands = [cand(i * 8, i * 8 + 5, editorial_score=s) for i, s in enumerate([3, 9, 5, 8, 7])]
    out = hl.validate(cands, sents, DUR, 3)
    assert [h.editorial_score for h in out] == [9, 8, 7]


def test_fallback_fill_avoids_chosen(sents):
    chosen = hl.validate([cand(0, 6)], sents, DUR, 4)
    extra = hl.fallback_fill(sents, chosen, 3, DUR)
    assert len(extra) == 3 and all(h.source == "fallback" for h in extra)
    used = set(range(chosen[0].start_sentence, chosen[0].end_sentence + 1))
    for h in extra:
        assert not used & set(range(h.start_sentence, h.end_sentence + 1))
        assert 20 <= h.duration <= 60


def test_join_tokens_attaches_punctuation():
    assert hl.join_tokens(["That", "clip", "got", "300", ",000", "views."]) == "That clip got 300,000 views."
    assert hl.join_tokens(["Around", "80", "%", "of", "people"]) == "Around 80% of people"
    assert hl.join_tokens(["I", "don", "n't", "know"]) == "I donn't know"  # attaches, never drops text
    assert hl.join_tokens(["my", "10", "-minute", "videos", "-", "ok"]) == "my 10-minute videos - ok"


def test_low_confidence_hallucinations_dropped():
    w = [{"start": 0, "end": 0.3, "text": "anymore.", "prob": 1.0},
         {"start": 0.35, "end": 0.5, "text": "4.", "prob": 0.07},
         {"start": 0.6, "end": 0.9, "text": "When", "prob": 0.99}]
    assert [s.text for s in hl.build_sentences(w)] == ["anymore.", "When"]


def test_forced_split_never_becomes_a_clip_boundary():
    # One 70-word run-on sentence (forced split at 60), then normal 5 s sentences.
    words = [{"start": i * 0.4, "end": i * 0.4 + 0.3, "text": f"w{i}", "prob": 1} for i in range(69)]
    words.append({"start": 27.6, "end": 27.9, "text": "end.", "prob": 1})
    words += [w | {"start": w["start"] + 30, "end": w["end"] + 30} for w in fake_words(20)]
    s = hl.build_sentences(words)
    assert s[1].cont and not s[0].cont and not s[2].cont
    [h] = hl.validate([cand(1, 4)], s, 140.0, 4)  # LLM picks the fragment as a start
    assert h.start_sentence == 0 and h.transcript.startswith("w0 ")


def unpunctuated(n_segments: int = 20, seg_sec: float = 3.0, words_per_seg: int = 8):
    """Like Whisper's Hindi output: no punctuation, tiny pauses, clean segments."""
    words, segments = [], []
    for k in range(n_segments):
        t0 = k * seg_sec
        segments.append({"start": t0, "end": t0 + seg_sec, "text": f"seg{k}"})
        step = seg_sec / words_per_seg
        words += [{"start": t0 + j * step, "end": t0 + j * step + step * 0.9, "text": f"शब्द{k}_{j}", "prob": 0.9}
                  for j in range(words_per_seg)]
    return words, segments


def test_unpunctuated_transcript_splits_on_whisper_segments():
    words, segs = unpunctuated()
    s = hl.build_sentences(words, segs)
    assert len(s) == 20 and not any(x.cont for x in s)
    out = hl.validate([cand(2, 9), cand(12, 19)], s, 60.0, 2)
    assert len(out) == 2 and all(20 <= h.duration <= 60 for h in out)


def test_unpunctuated_without_segments_still_produces_clips():
    """Regression: a 65 s Hindi video with no punctuation produced zero clips."""
    words, _ = unpunctuated()
    s = hl.build_sentences(words)  # no segments -> forced 60-word splits, all `cont`
    assert any(x.cont for x in s)
    assert hl.validate([cand(0, 1)], s, 60.0, 2) or hl.fallback_fill(s, [], 2, 60.0)


def test_hindi_hook_grounding_keeps_matras():
    text = "अगर आप एक Indian Creator हो तो आपको यह Caption Generator जरूर ट्राइ करना चाहिए"
    assert hl.is_grounded("आपको यह Caption Generator जरूर ट्राइ करना", text)
    assert not hl.is_grounded("यह वीडियो वायरल होगा", text)


def test_sentence_pasted_as_title_is_shortened(sents):
    long = "Point number 10 is important and here is a very long sentence used as a title"
    [h] = hl.validate([cand(10, 15, title=long)], sents, DUR, 4)
    assert len(h.title.split()) <= 9 and h.title.endswith("…")


def test_unreadable_llm_answer_retries_then_falls_back(monkeypatch):
    from app.services.transcribe import PipelineError
    calls = []

    def bad(*a, **kw):
        calls.append(kw)
        raise PipelineError("llm_bad_output", "x")

    monkeypatch.setattr(hl.llm, "chat_json", bad)
    out = hl.select_highlights({"words": fake_words(), "duration": DUR, "segments": []})
    assert len(calls) == 2 and calls[0]["max_tokens"] <= 2000
    assert len(out) == 4 and all(h.source == "fallback" for h in out)


def test_llm_offline_is_not_masked(monkeypatch):
    from app.services.transcribe import PipelineError

    def offline(*a, **kw):
        raise PipelineError("llm_unavailable", "start ollama")

    monkeypatch.setattr(hl.llm, "chat_json", offline)
    with pytest.raises(PipelineError):
        hl.select_highlights({"words": fake_words(), "duration": DUR, "segments": []})


def test_schema_bounds_output():
    sc = hl.schema(6)["properties"]["clips"]
    assert sc["maxItems"] == 6 and sc["items"]["properties"]["reason"]["maxLength"] == 220


def test_target_clip_count():
    assert hl.target_clip_count(300) == 4
    assert hl.target_clip_count(65) == 2
    assert hl.target_clip_count(15) == 1
    assert hl.target_clip_count(600) == 4     # 10 min
    assert hl.target_clip_count(1200) == 5    # 20 min
    assert hl.target_clip_count(1800) == 8    # 30 min


def long_transcript(minutes: int = 30, hindi: bool = False) -> dict:
    """Synthetic 30-min talk: a 12-word sentence every 5 s."""
    words, n = [], minutes * 12
    for i in range(n):
        toks = (["यह", "बहुत", "ज़रूरी", "बात", "है", "जो", "मैं", "आज", "बताने", "वाला", "हूँ", f"{i}।"] if hindi
                else ["This", "is", "point", "number", str(i), "about", "growing", "your", "channel", "every", "single", "day."])
        t0 = i * 5.0
        words += [{"start": t0 + j * 0.35, "end": t0 + j * 0.35 + 0.3, "text": t, "prob": 0.9} for j, t in enumerate(toks)]
    return {"words": words, "duration": n * 5.0, "segments": []}


def test_long_video_uses_windows_that_fit_the_context(monkeypatch):
    prompts = []

    def fake(system, user, schema, temperature=0.3, max_tokens=1500):
        prompts.append(user)
        idx = [int(x) for x in re.findall(r"^\[(\d+)\]", user, re.M)]
        a = idx[len(idx) // 3]  # suggest one clip from the middle of each window
        return {"clips": [{"start_sentence": a, "end_sentence": a + 6, "title": "T", "hook": "",
                           "reason": "r", "editorial_score": 8}]}

    monkeypatch.setattr(hl.llm, "chat_json", fake)
    for hindi in (False, True):
        prompts.clear()
        out = hl.select_highlights(long_transcript(30, hindi))
        assert len(prompts) >= 4                                  # windowed, not one huge prompt
        assert all(hl.estimate_tokens(p) < 5500 for p in prompts) # each fits next to system + answer in 8k
        assert all("part from" in p for p in prompts)
        ai = [h for h in out if h.source == "ai"]
        assert len(out) == 8 and len(ai) >= 4
        starts = sorted(h.start_time for h in ai)
        assert starts[-1] - starts[0] > 15 * 60                   # spread across the video, not bunched
        spans = sorted((h.start_time, h.end_time) for h in out)
        assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))  # never overlapping


def test_window_answers_outside_the_window_are_ignored(monkeypatch):
    monkeypatch.setattr(hl.llm, "chat_json", lambda *a, **k: {"clips": [
        {"start_sentence": 99999, "end_sentence": 100005, "title": "x", "hook": "", "reason": "", "editorial_score": 9}]})
    out = hl.select_highlights(long_transcript(20))
    assert out and all(h.source == "fallback" for h in out)   # bogus indices never become clips


def test_windows_cover_everything_with_overlap():
    s = hl.build_sentences(long_transcript(30)["words"])
    ws = hl.windows(s, 480, 60)
    covered = {x.idx for w in ws for x in w}
    assert covered == {x.idx for x in s}
    assert all(ws[i][-1].start > ws[i + 1][0].start for i in range(len(ws) - 1))  # consecutive windows overlap
