"""Audio extraction with FFmpeg.

We decode audio ourselves and hand faster-whisper a float32 numpy array, instead of letting it
decode via PyAV: faster-whisper 1.2.1 passes `metadata_errors=` to av.open(), which PyAV >= 19
no longer accepts. FFmpeg is already a hard dependency, so this removes a fragile one.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from app.config import get_settings

SAMPLE_RATE = 16_000


def extract_audio(src: Path, wav_out: Path) -> Path:
    """Write 16 kHz mono 16-bit PCM WAV (what Whisper expects)."""
    s = get_settings()
    proc = subprocess.run(
        [s.ffmpeg_bin, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
         "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(wav_out)],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0 or not wav_out.exists() or wav_out.stat().st_size <= 44:
        raise RuntimeError("Audio extraction failed")
    return wav_out


def load_audio(src: Path) -> np.ndarray:
    """Decode any audio/video file to float32 mono 16 kHz in [-1, 1]."""
    s = get_settings()
    proc = subprocess.run(
        [s.ffmpeg_bin, "-v", "error", "-i", str(src), "-vn", "-ac", "1",
         "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
        capture_output=True, timeout=600,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError("Audio decoding failed")
    return np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0
