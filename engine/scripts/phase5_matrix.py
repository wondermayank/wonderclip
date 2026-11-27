"""Phase 5 test matrix: run every fixture through the live backend and measure it.

    backend/.venv/Scripts/python scripts/phase5_fixtures.py      # once
    backend/.venv/Scripts/python scripts/phase5_matrix.py [--only name1,name2]

Per case: upload -> process -> poll, while sampling (every 0.5 s) GPU memory/utilisation (nvidia-smi),
RSS of the backend process and of Ollama, and system RAM — tagged with the job's current stage.
Clips are verified independently with ffprobe (1080x1920, duration, audio). For videos with known
spoken text, word error rate (WER) of the transcript is computed.
Results: docs/phase5_results.json (machine-readable) — the report is written from it.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "backend" / "temp" / "phase5"
OUTPUTS = ROOT / "backend" / "outputs"
API = "http://127.0.0.1:8000"

# name, expectation
CASES: list[tuple[str, dict]] = [
    ("long_5min_en.mp4", {"clips": 4, "layout": "track"}),
    ("res_480p25.mp4", {"min_clips": 1, "layout": "track"}),
    ("res_720p60.mp4", {"min_clips": 1, "layout": "track"}),
    ("res_4k30.mp4", {"min_clips": 1, "layout": "track"}),
    ("square_1080.mp4", {"min_clips": 1, "layout": "track"}),
    ("phone_rotated.mov", {"min_clips": 1, "layout": "native"}),
    ("two_faces.mp4", {"min_clips": 1, "layout": "track"}),
    ("voice_female.mp4", {"min_clips": 1, "layout": "fit"}),
    ("voice_male_clean.mp4", {"min_clips": 1, "layout": "fit"}),
    ("voice_male_noisy.mp4", {"min_clips": 1, "layout": "fit"}),
    ("voice_male_snr0.mp4", {"min_clips": 1, "layout": "fit"}),
    ("voice_male_snr-5.mp4", {"min_clips": 1, "layout": "fit"}),
    ("corrupt_truncated.mp4", {"upload_error": "invalid_video"}),
    ("too_long_31m.mp4", {"upload_error": "too_long"}),
    ("no_speech_music.mp4", {"job_error": "no_speech"}),
]


# ---------------------------------------------------------------- measurement

def gpu() -> tuple[int, int]:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
        used, util = out.strip().split(",")
        return int(used), int(util)
    except Exception:
        return -1, -1


def backend_proc() -> psutil.Process | None:
    for c in psutil.net_connections("tcp"):
        if c.laddr and c.laddr.port == 8000 and c.status == psutil.CONN_LISTEN and c.pid:
            return psutil.Process(c.pid)
    return None


def rss_mb(procs: list[psutil.Process]) -> int:
    total = 0
    for p in procs:
        try:
            total += p.memory_info().rss
        except psutil.Error:
            pass
    return total // 2**20


class Sampler(threading.Thread):
    def __init__(self, backend: psutil.Process) -> None:
        super().__init__(daemon=True)
        self.backend, self.stage, self.samples, self.stop_ev = backend, "upload", [], threading.Event()

    def run(self) -> None:
        while not self.stop_ev.is_set():
            used, util = gpu()
            back = [self.backend] + self.backend.children(recursive=True)  # includes ffmpeg children
            ollama = [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower().startswith("ollama")]
            self.samples.append({"t": time.time(), "stage": self.stage, "vram_mb": used, "gpu_util": util,
                                 "backend_rss_mb": rss_mb(back), "ollama_rss_mb": rss_mb(ollama),
                                 "sys_ram_used_mb": (psutil.virtual_memory().total - psutil.virtual_memory().available) // 2**20})
            time.sleep(0.5)


def summarise(samples: list[dict]) -> dict:
    stages: dict[str, dict] = {}
    for s in samples:
        st = stages.setdefault(s["stage"], {"seconds": 0.0, "first": s["t"], "last": s["t"],
                                            "peak_vram_mb": 0, "peak_gpu_util": 0, "peak_backend_rss_mb": 0,
                                            "peak_ollama_rss_mb": 0, "peak_sys_ram_mb": 0})
        st["last"] = s["t"]
        st["peak_vram_mb"] = max(st["peak_vram_mb"], s["vram_mb"])
        st["peak_gpu_util"] = max(st["peak_gpu_util"], s["gpu_util"])
        st["peak_backend_rss_mb"] = max(st["peak_backend_rss_mb"], s["backend_rss_mb"])
        st["peak_ollama_rss_mb"] = max(st["peak_ollama_rss_mb"], s["ollama_rss_mb"])
        st["peak_sys_ram_mb"] = max(st["peak_sys_ram_mb"], s["sys_ram_used_mb"])
    for st in stages.values():
        st["seconds"] = round(st.pop("last") - st.pop("first") + 0.5, 1)
    return stages


# ---------------------------------------------------------------- checks

def norm_words(text: str) -> list[str]:
    text = text.lower().replace("%", " percent")
    return [w for w in re.findall(r"[a-z']+", text) if w]


def wer(ref: str, hyp: str) -> float:
    r, h = norm_words(ref), norm_words(hyp)
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        cur = [i] + [0] * len(h)
        for j in range(1, len(h) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r[i - 1] != h[j - 1]))
        prev = cur
    return round(prev[-1] / max(len(r), 1), 4)


def probe(p: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                          "-of", "json", str(p)], capture_output=True, text=True).stdout
    d = json.loads(out or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    return {"w": v.get("width"), "h": v.get("height"), "audio": any(s.get("codec_type") == "audio" for s in d.get("streams", [])),
            "duration": float(d.get("format", {}).get("duration", 0))}


# ---------------------------------------------------------------- runner

def run_case(c: httpx.Client, name: str, expect: dict, truths: dict, backend: psutil.Process,
             cold: bool = False) -> dict:
    res: dict = {"case": name, "expect": expect, "ok": False, "problems": []}
    path = FIX / name
    sampler = Sampler(backend)
    sampler.start()
    t0 = time.time()
    try:
        with path.open("rb") as fh:
            r = c.post("/api/upload", files={"file": (name, fh, "video/quicktime" if name.endswith(".mov") else "video/mp4")})
        res["upload_seconds"] = round(time.time() - t0, 1)
        body = r.json()
        if "upload_error" in expect:
            res["got"] = body.get("code")
            res["message"] = body.get("message")
            res["ok"] = r.status_code >= 400 and body.get("code") == expect["upload_error"]
            return res
        if r.status_code != 200:
            res["problems"].append(f"upload failed: {body}")
            return res
        res["source"] = body["video"]
        if cold:  # measure the full pipeline: drop any cached transcript from earlier runs
            prev = c.post("/api/process", json={"upload_id": body["upload_id"]}).json()
            if prev.get("status") in ("completed", "failed", "cancelled"):
                (OUTPUTS / prev["job_id"] / "transcript.json").unlink(missing_ok=True)
            elif prev.get("status") == "queued":  # brand-new job: it is already the cold run
                res["cold"] = True
        job = c.post("/api/process", json={"upload_id": body["upload_id"], "force": True}).json()
        jid = job["job_id"]
        res["job_id"] = jid
        while True:
            job = c.get(f"/api/jobs/{jid}").json()
            sampler.stage = job["status"]
            if job["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.5)
        res["total_seconds"] = round(time.time() - t0, 1)
        res["status"], res["error_code"], res["error_message"] = job["status"], job["error_code"], job["error_message"]
        if "job_error" in expect:
            res["ok"] = job["status"] == "failed" and job["error_code"] == expect["job_error"]
            return res
        if job["status"] != "completed":
            res["problems"].append(f"job {job['status']}: {job['error_code']} {job['error_message']}")
            return res

        tjson = OUTPUTS / jid / "transcript.json"
        if tjson.exists():
            t = json.loads(tjson.read_text("utf-8"))
            res["transcript"] = {"language": t["language"], "model": t.get("model"), "words": len(t["words"])}
            if name in truths:
                res["wer"] = wer(truths[name], " ".join(w["text"] for w in t["words"]))
        clips = c.get(f"/api/jobs/{jid}/clips").json()
        res["clips"] = []
        for cl in clips:
            pr = probe(OUTPUTS / jid / f"clip_{cl['index'] + 1}.mp4")
            good = (pr["w"], pr["h"]) == (1080, 1920) and pr["audio"] and abs(pr["duration"] - cl["duration"]) < 0.3
            entry = {"layout": cl["layout"], "faces": cl["face_coverage"], "duration": cl["duration"],
                     "source": cl["source"], "verified": good, "title": cl["title"]}
            rfp = OUTPUTS / jid / f"clip_{cl['index'] + 1}.reframe.json"
            if cl["layout"] == "track" and rfp.exists():
                rf = json.loads(rfp.read_text("utf-8"))
                s = rf["samples"]
                steps = [(abs(b[1] - a[1]), b[0] - a[0]) for a, b in zip(s, s[1:])]
                cut = rf["crop_w"] * 0.5
                entry["cuts"] = sum(1 for d, _ in steps if d > cut)
                entry["max_pan_px_s"] = round(max((d / dt for d, dt in steps if d <= cut and dt > 0), default=0))
            res["clips"].append(entry)
            if not good:
                res["problems"].append(f"clip {cl['index'] + 1} failed verification: {pr}")
        n = len(clips)
        if "clips" in expect and n != expect["clips"]:
            res["problems"].append(f"expected {expect['clips']} clips, got {n}")
        if n < expect.get("min_clips", 0):
            res["problems"].append(f"expected at least {expect['min_clips']} clips, got {n}")
        if "layout" in expect and any(cl["layout"] != expect["layout"] for cl in res["clips"]):
            res["problems"].append(f"expected layout {expect['layout']}, got {[cl['layout'] for cl in res['clips']]}")
        res["ok"] = not res["problems"]
        return res
    finally:
        sampler.stop_ev.set()
        sampler.join()
        res["resources"] = summarise(sampler.samples)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--cold", action="store_true", help="delete cached transcripts so every stage is measured")
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    truths = json.loads((FIX / "truths.json").read_text("utf-8"))
    backend = backend_proc()
    if not backend:
        raise SystemExit("backend is not running on :8000")
    idle_vram, _ = gpu()
    out_path = ROOT / "docs" / "phase5_results.json"
    results = json.loads(out_path.read_text("utf-8")) if out_path.exists() and only else {}
    results["_meta"] = {"idle_vram_mb": idle_vram, "gpu": subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip(),
        "ram_total_mb": psutil.virtual_memory().total // 2**20, "when": time.strftime("%Y-%m-%d %H:%M")}
    with httpx.Client(base_url=API, timeout=900) as c:
        for name, expect in CASES:
            if only and name not in only:
                continue
            print(f"\n=== {name}", flush=True)
            r = run_case(c, name, expect, truths, backend, a.cold)
            results[name] = r
            peak = max((s["peak_vram_mb"] for s in r.get("resources", {}).values()), default=0)
            print(f"  {'PASS' if r['ok'] else 'FAIL'}  total={r.get('total_seconds')}s  clips={len(r.get('clips', []))}"
                  f"  layouts={[x['layout'] for x in r.get('clips', [])]}  wer={r.get('wer')}  peakVRAM={peak}MB"
                  f"  {r.get('got') or r.get('error_code') or ''}  {'; '.join(r['problems'])}", flush=True)
            out_path.write_text(json.dumps(results, indent=1, ensure_ascii=False), "utf-8")
    print("\nsaved", out_path)


if __name__ == "__main__":
    main()
