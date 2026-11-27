"""Make pip-installed CUDA 12 DLLs (nvidia-cublas-cu12, nvidia-cudnn-cu12) visible on Windows.

CTranslate2 loads cublas/cudnn lazily via LoadLibrary, so both os.add_dll_directory and PATH
are set. Call register_cuda_dlls() before importing faster_whisper / ctranslate2.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_done = False


def register_cuda_dlls() -> list[str]:
    global _done
    if _done or sys.platform != "win32":
        return []
    added: list[str] = []
    try:
        import nvidia  # namespace package from nvidia-*-cu12 wheels
    except ImportError:
        return added
    for root in map(Path, nvidia.__path__):
        for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
            bin_dir = root / sub / "bin"
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                added.append(sub)
    _done = True
    return added
