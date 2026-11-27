"""Minimal Ollama client. Always unloads the model after use (6 GB VRAM budget)."""
from __future__ import annotations

import json
import logging
import time

import httpx

from app.config import get_settings
from app.services.transcribe import PipelineError

log = logging.getLogger("clipmitra.llm")

_OFFLINE = PipelineError("llm_unavailable",
                         "The local AI (Ollama) isn't running. Start Ollama, then press Retry.")


def unload_all(timeout: float = 15.0) -> None:
    """Evict every model Ollama holds in memory so Whisper gets the GPU. No-op if Ollama is down."""
    s = get_settings()
    try:
        loaded = httpx.get(f"{s.ollama_url}/api/ps", timeout=3).json().get("models", [])
        for m in loaded:
            httpx.post(f"{s.ollama_url}/api/generate",
                       json={"model": m["name"], "keep_alive": 0}, timeout=10)
        deadline = time.time() + timeout
        while loaded and time.time() < deadline:
            time.sleep(0.5)
            loaded = httpx.get(f"{s.ollama_url}/api/ps", timeout=3).json().get("models", [])
    except httpx.HTTPError:
        return


def chat_json(system: str, user: str, schema: dict, temperature: float = 0.3, max_tokens: int = 1500) -> dict:
    s = get_settings()
    try:
        r = httpx.post(f"{s.ollama_url}/api/chat", timeout=s.llm_timeout_seconds, json={
            "model": s.llm_model, "stream": False, "think": False, "keep_alive": 0,
            "format": schema,
            # num_predict caps runaway generations (a small model can loop at higher temperature)
            "options": {"temperature": temperature, "num_ctx": s.llm_context, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        })
    except httpx.ConnectError as e:
        raise _OFFLINE from e
    except httpx.TimeoutException as e:
        raise PipelineError("llm_timeout", "The local AI took too long to respond. Please retry.") from e
    if r.status_code == 404:
        raise PipelineError("llm_model_missing",
                            f"The AI model {s.llm_model} isn't installed. Run: ollama pull {s.llm_model}")
    if r.status_code != 200:
        log.error("ollama %s: %s", r.status_code, r.text[:500])
        raise PipelineError("llm_error", "The local AI returned an error. Please retry.")
    body = r.json()
    ns = 1e9
    log.info("llm: %s prompt tok, %s output tok | load %.1fs, prompt %.1fs, generate %.1fs, total %.1fs",
             body.get("prompt_eval_count"), body.get("eval_count"), body.get("load_duration", 0) / ns,
             body.get("prompt_eval_duration", 0) / ns, body.get("eval_duration", 0) / ns,
             body.get("total_duration", 0) / ns)
    try:
        return json.loads(body["message"]["content"])
    except (KeyError, json.JSONDecodeError) as e:
        raise PipelineError("llm_bad_output", "The local AI returned an unreadable answer. Please retry.") from e
