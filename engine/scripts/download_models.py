"""Pre-download the Whisper model into the configured model folder (used by install.ps1),
so the first video doesn't stall on a 1.6 GB download."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # harmless on Windows, just noisy
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # settings read backend/.env

from app.config import get_settings  # noqa: E402
from faster_whisper import download_model  # noqa: E402

s = get_settings()
path = download_model(s.whisper_model, cache_dir=str(s.model_dir / "whisper"))
print(f"whisper {s.whisper_model} ready")
