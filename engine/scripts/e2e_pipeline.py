"""End-to-end run against a live backend: upload -> process -> poll -> verify clips.

    backend/.venv/Scripts/python scripts/e2e_pipeline.py path/to/video.mp4 [--force]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import httpx

API = "http://127.0.0.1:8000"


def vram() -> str:
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except OSError:
        return "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--force", action="store_true", help="regenerate clips for a completed job")
    a = ap.parse_args()
    c = httpx.Client(base_url=API, timeout=600)

    with a.video.open("rb") as fh:
        up = c.post("/api/upload", files={"file": (a.video.name, fh, "video/mp4")})
    up.raise_for_status()
    uid = up.json()["upload_id"]
    print(f"upload {uid} duplicate={up.json()['duplicate']} dur={up.json()['video']['duration_seconds']}s")

    job = c.post("/api/process", json={"upload_id": uid, "force": a.force}).json()
    jid, t0, last, peak = job["job_id"], time.time(), None, 0
    while True:
        job = c.get(f"/api/jobs/{jid}").json()
        used = vram()
        try:
            peak = max(peak, int(used.split()[0]))
        except (ValueError, IndexError):
            pass
        line = f"{job['status']:<20} {job['progress'] * 100:5.1f}%"
        if (job["status"], round(job["progress"], 1)) != last:
            print(f"[{time.time() - t0:6.1f}s] {line}  vram={used}  {job['live_text'][:70]!r}", flush=True)
            last = (job["status"], round(job["progress"], 1))
        if job["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(1)

    print(f"\nfinal: {job['status']} in {time.time() - t0:.0f}s, peak VRAM {peak} MiB, "
          f"error={job['error_code']} {job['error_message'] or ''}")
    if job["status"] != "completed":
        return 1
    clips = c.get(f"/api/jobs/{jid}/clips").json()
    ok = True
    for cl in clips:
        r = c.get(cl["download_url"])
        size = len(r.content)
        good = r.status_code == 200 and size > 10_000 and 20 <= cl["duration"] <= 61
        ok &= good
        print(f"\n#{cl['index'] + 1} [{cl['source']}] layout={cl['layout']} faces={cl['face_coverage']:.0%} "
              f"captions={cl['caption_style']} score={cl['editorial_score']} "
              f"{cl['start_time']:.1f}-{cl['end_time']:.1f}s ({cl['duration']:.1f}s) {size // 1024} KB "
              f"{'OK' if good else 'BAD'}\n   title : {cl['title']}\n   hook  : {cl['hook']}\n"
              f"   reason: {cl['reason']}\n   text  : {cl['transcript'][:160]}…")
    print(f"\n{len(clips)} clips, all verified: {ok}")
    return 0 if ok and clips else 1


if __name__ == "__main__":
    sys.exit(main())
