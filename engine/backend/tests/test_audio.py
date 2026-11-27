from pathlib import Path

from app.services.audio import SAMPLE_RATE, extract_audio, load_audio
from tests.test_upload import make_video


def test_extract_and_load(tmp_path: Path):
    vid = make_video(tmp_path / "a.mp4", 2)
    wav = extract_audio(vid, tmp_path / "a.wav")
    assert wav.stat().st_size > SAMPLE_RATE * 2 * 1.9  # ~2 s of 16-bit mono
    pcm = load_audio(vid)
    assert pcm.dtype.name == "float32"
    assert abs(len(pcm) / SAMPLE_RATE - 2.0) < 0.1
    assert 0.1 < abs(pcm).max() <= 1.0  # the sine tone is actually there
