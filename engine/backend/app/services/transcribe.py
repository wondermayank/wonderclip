"""Speech-to-text with faster-whisper. Loads the model, transcribes, then frees VRAM."""
from __future__ import annotations

import gc
import logging
from pathlib import Path
from typing import Callable

from app.config import get_settings
from app.services.audio import SAMPLE_RATE, load_audio
from app.services.system import gpu_info
from app.utils.cuda import register_cuda_dlls

log = logging.getLogger("clipmitra.transcribe")


class PipelineError(Exception):
    """Error whose message is safe to show to the user."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Cancelled(Exception):
    pass


def _pick_device() -> tuple[str, str, str]:
    """Returns (model, device, compute_type) based on free VRAM.

    Low VRAM / no CUDA -> the SAME model on the CPU (int8): slower but accurate. Phase 5 measured
    the `small` model on Hindi: garbled Devanagari and under half the words — unusable captions.
    `whisper_low_vram_strategy="small_gpu"` restores the fast-but-weaker behaviour.
    """
    s = get_settings()
    register_cuda_dlls()
    import ctranslate2

    cpu = (s.whisper_model, "cpu", "int8")
    if ctranslate2.get_cuda_device_count() == 0:
        return cpu
    gpu = gpu_info()
    if gpu and gpu.vram_free_mb < s.whisper_min_vram_mb:
        if s.whisper_low_vram_strategy == "small_gpu":
            log.warning("only %d MB VRAM free, using %s on GPU", gpu.vram_free_mb, s.whisper_fallback_model)
            return s.whisper_fallback_model, "cuda", s.whisper_compute_type
        log.warning("only %d MB VRAM free, running %s on CPU", gpu.vram_free_mb, s.whisper_model)
        return cpu
    return s.whisper_model, "cuda", s.whisper_compute_type


def transcribe(
    audio_path: Path,
    on_progress: Callable[[float, str], None],
    should_cancel: Callable[[], bool],
) -> dict:
    """Returns {"language", "duration", "model", "segments": [...], "words": [...]}.

    Words carry real timestamps from Whisper; nothing is synthesised.
    """
    s = get_settings()
    audio = load_audio(audio_path)
    total = len(audio) / SAMPLE_RATE
    if total <= 0:
        raise PipelineError("no_audio", "The video's audio track is empty.")

    model_name, device, compute = _pick_device()
    from faster_whisper import WhisperModel

    model = None
    try:
        try:
            model = WhisperModel(model_name, device=device, compute_type=compute,
                                 download_root=str(s.model_dir / "whisper"))
        except RuntimeError as e:  # typically CUDA out of memory: same model on the CPU
            if device == "cpu":
                raise
            log.warning("whisper GPU load failed (%s); running %s on CPU", e, model_name)
            device, compute = "cpu", "int8"
            model = WhisperModel(model_name, device=device, compute_type=compute,
                                 download_root=str(s.model_dir / "whisper"))

        seg_iter, info = model.transcribe(
            audio, language=s.whisper_language, word_timestamps=True, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500}, beam_size=5,
            condition_on_previous_text=False,  # reduces hallucinated repetition loops
        )
        segments, words = [], []
        for seg in seg_iter:  # generator: decoding happens here
            if should_cancel():
                raise Cancelled()
            text = seg.text.strip()
            segments.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": text})
            for w in seg.words or []:
                if w.word.strip():
                    words.append({"start": round(w.start, 3), "end": round(w.end, 3),
                                  "text": w.word.strip(), "prob": round(w.probability, 3)})
            on_progress(min(seg.end / total, 1.0), text)
    finally:
        del model
        gc.collect()

    if not words:
        raise PipelineError("no_speech", "We couldn't hear any speech in this video.")
    return {"language": info.language, "duration": round(total, 3), "model": model_name,
            "device": device, "segments": segments, "words": words}
