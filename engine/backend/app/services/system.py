"""Readiness checks for the local AI stack. Cheap: no model is loaded here."""
from __future__ import annotations

import subprocess

import httpx

from app.config import get_settings
from app.models.schemas import ComponentStatus, GpuInfo, SystemOut


def gpu_info() -> GpuInfo | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return None
        name, total, free = [x.strip() for x in out.stdout.strip().splitlines()[0].split(",")]
        return GpuInfo(name=name, vram_total_mb=int(total), vram_free_mb=int(free))
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def _ffmpeg() -> ComponentStatus:
    s = get_settings()
    try:
        v = subprocess.run([s.ffmpeg_bin, "-hide_banner", "-version"],
                           capture_output=True, text=True, timeout=10)
        enc = subprocess.run([s.ffmpeg_bin, "-hide_banner", "-encoders"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ComponentStatus(ok=False, detail="FFmpeg not found")
    ver = v.stdout.split("\n", 1)[0].replace("ffmpeg version ", "").split(" ")[0]
    nvenc = "h264_nvenc" in enc.stdout
    return ComponentStatus(ok=v.returncode == 0, detail=f"{ver}{' · NVENC' if nvenc else ''}")


def _ollama() -> ComponentStatus:
    s = get_settings()
    try:
        r = httpx.get(f"{s.ollama_url}/api/tags", timeout=3)
        r.raise_for_status()
    except httpx.HTTPError:
        return ComponentStatus(ok=False, detail="Ollama is not running")
    names = {m.get("name", "") for m in r.json().get("models", [])}
    if s.llm_model in names or f"{s.llm_model}:latest" in names:
        return ComponentStatus(ok=True, detail=s.llm_model)
    return ComponentStatus(ok=False, detail=f"Model {s.llm_model} not pulled")


def _whisper() -> ComponentStatus:
    from app.utils.cuda import register_cuda_dlls

    register_cuda_dlls()
    try:
        import ctranslate2
        import faster_whisper  # noqa: F401
    except ModuleNotFoundError:
        return ComponentStatus(ok=False, detail="faster-whisper not installed")
    except ImportError:  # e.g. DLL load failure (CUDA libs, or project path > 260 chars)
        return ComponentStatus(ok=False, detail="faster-whisper installed but failed to load")
    n = ctranslate2.get_cuda_device_count()
    s = get_settings()
    if n == 0:
        return ComponentStatus(ok=True, detail=f"{s.whisper_model} · CPU only (no CUDA device)")
    return ComponentStatus(ok=True, detail=f"{s.whisper_model} · CUDA")


def system_status() -> SystemOut:
    s = get_settings()
    comps = {"ffmpeg": _ffmpeg(), "ollama": _ollama(), "whisper": _whisper()}
    gpu = gpu_info()
    comps["gpu"] = (
        ComponentStatus(ok=True, detail=f"{gpu.name} · {gpu.vram_free_mb} MB free")
        if gpu else ComponentStatus(ok=False, detail="No NVIDIA GPU detected (CPU fallback)")
    )
    return SystemOut(
        gpu=gpu,
        components=comps,
        ready_for_processing=all(comps[k].ok for k in ("ffmpeg", "ollama", "whisper")),
        limits={"max_duration_seconds": s.max_duration_seconds,
                "max_upload_mb": s.max_upload_bytes / 1024**2},
    )
