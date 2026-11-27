"""Phase 1 smoke test of the local AI stack. Run with the backend venv:

    backend/.venv/Scripts/python scripts/verify_stack.py [--whisper-model small]

Checks: GPU, FFmpeg NVENC encode, faster-whisper GPU transcription (on speech synthesised with
Windows SAPI), Qwen3 structured JSON via Ollama, and that VRAM is released between stages.
"""
from __future__ import annotations

import argparse
import gc
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.services.system import gpu_info  # noqa: E402
from app.utils.cuda import register_cuda_dlls  # noqa: E402

SENTENCE = ("Artificial intelligence is not here to replace creativity. "
            "It is here to give creators more power and more time.")
results: dict[str, str] = {}


def vram_free() -> int:
    g = gpu_info()
    return g.vram_free_mb if g else -1


def step(name: str):
    def deco(fn):
        def run(*a, **k):
            t = time.perf_counter()
            try:
                msg = fn(*a, **k)
                results[name] = f"PASS  {msg}  ({time.perf_counter() - t:.1f}s)"
            except Exception as e:  # report every failure, keep going
                results[name] = f"FAIL  {type(e).__name__}: {e}"
            print(f"[{name}] {results[name]}", flush=True)
        return run
    return deco


@step("gpu")
def check_gpu():
    g = gpu_info()
    assert g, "nvidia-smi returned nothing"
    return f"{g.name}, {g.vram_total_mb} MB total, {g.vram_free_mb} MB free"


@step("ffmpeg_nvenc")
def check_nvenc(tmp: Path):
    s = get_settings()
    out = tmp / "nvenc.mp4"
    subprocess.run([s.ffmpeg_bin, "-y", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=1080x1920:r=30:d=2", "-c:v", "h264_nvenc", str(out)], check=True)
    probe = subprocess.run([s.ffprobe_bin, "-v", "error", "-show_entries", "stream=width,height,codec_name",
                            "-of", "json", str(out)], capture_output=True, text=True, check=True)
    st = json.loads(probe.stdout)["streams"][0]
    assert (st["width"], st["height"]) == (1080, 1920), st
    return f"encoded 1080x1920 {st['codec_name']} via NVENC"


def synth_speech(path: Path) -> None:
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{SENTENCE}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


@step("whisper")
def check_whisper(tmp: Path, model_name: str):
    register_cuda_dlls()
    import ctranslate2
    from faster_whisper import WhisperModel

    assert ctranslate2.get_cuda_device_count() > 0, "CTranslate2 sees no CUDA device"
    wav = tmp / "speech.wav"
    synth_speech(wav)
    s = get_settings()
    before = vram_free()
    model = WhisperModel(model_name, device="cuda", compute_type=s.whisper_compute_type,
                         download_root=str(s.model_dir / "whisper"))
    loaded = vram_free()
    from app.services.audio import load_audio

    segs, info = model.transcribe(load_audio(wav), word_timestamps=True, vad_filter=True)
    segs = list(segs)
    words = [w for sg in segs for w in (sg.words or [])]
    text = " ".join(sg.text.strip() for sg in segs)
    del model, segs
    gc.collect()
    time.sleep(1)
    after = vram_free()
    assert words, "no words transcribed"
    assert "creativity" in text.lower(), f"unexpected transcript: {text!r}"
    return (f"{model_name}: {len(words)} words with timestamps, lang={info.language}; "
            f"VRAM used {before - loaded} MB, released to {after} MB free | {text!r}")


@step("ollama_qwen3")
def check_llm():
    import httpx

    s = get_settings()
    schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}, "hook": {"type": "string"},
                       "editorial_score": {"type": "integer"}},
        "required": ["title", "hook", "editorial_score"],
    }
    before = vram_free()
    r = httpx.post(f"{s.ollama_url}/api/chat", timeout=300, json={
        "model": s.llm_model, "stream": False, "think": False, "keep_alive": 0,
        "format": schema, "options": {"temperature": 0.2, "num_ctx": s.llm_context},
        "messages": [{"role": "user", "content":
                      f"Transcript: \"{SENTENCE}\"\nGive this as a short-form clip: a title, "
                      "the hook line (quote from the transcript), and an editorial_score 1-10."}],
    })
    r.raise_for_status()
    body = r.json()
    data = json.loads(body["message"]["content"])
    assert {"title", "hook", "editorial_score"} <= data.keys(), data
    tps = body.get("eval_count", 0) / max(body.get("eval_duration", 1) / 1e9, 1e-6)
    time.sleep(2)
    return f"valid JSON {data}; {tps:.0f} tok/s; VRAM free before {before} MB / after unload {vram_free()} MB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--whisper-model", default=get_settings().whisper_model)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        check_gpu()
        check_nvenc(tmp)
        check_whisper(tmp, a.whisper_model)
        check_llm()
    print("\n=== SUMMARY ===")
    for k, v in results.items():
        print(f"{k:14} {v}")
    return 0 if all(v.startswith("PASS") for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
