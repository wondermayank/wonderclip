"""Long-video end-to-end test: fetch a link, process it cold, sample GPU/RAM per stage, verify clips.

    backend/.venv/Scripts/python scripts/e2e_long_link.py <url>     (engine must be running)

Only use videos you own or that are licensed for reuse (e.g. Creative Commons).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from phase5_matrix import OUTPUTS, Sampler, backend_proc, probe, summarise  # noqa: E402

url = sys.argv[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=900)
sampler = Sampler(backend_proc())
sampler.stage = "fetching"
sampler.start()
t0 = time.time()
f = c.post("/api/fetch", json={"url": url, "confirm_rights": True}).json()
while (f := c.get(f"/api/fetch/{f['fetch_id']}").json())["status"] not in ("completed", "failed"):
    time.sleep(1)
fetch_s = time.time() - t0
if f["status"] != "completed":
    sys.exit(f"fetch failed: {f['error_code']} {f['error_message']}")
up = f["upload"]
print(f"fetched in {fetch_s:.0f}s: {up['filename']} | {up['size_bytes'] / 1e6:.0f} MB | "
      f"{up['video']['width']}x{up['video']['height']} {up['video']['duration_seconds'] / 60:.1f} min")

job = c.post("/api/process", json={"upload_id": up["upload_id"]}).json()
jid = job["job_id"]
(OUTPUTS / jid / "transcript.json").unlink(missing_ok=True) if job["status"] == "completed" else None
if job["status"] == "completed":
    job = c.post("/api/process", json={"upload_id": up["upload_id"], "force": True}).json()
t1 = time.time()
while (job := c.get(f"/api/jobs/{jid}").json())["status"] not in ("completed", "failed", "cancelled"):
    sampler.stage = job["status"]
    time.sleep(0.5)
sampler.stop_ev.set()
sampler.join()
res = summarise(sampler.samples)
print(f"job {job['status']} in {time.time() - t1:.0f}s {job['error_message'] or ''}")
print("stage            seconds  peakVRAM  GPU%  backendRAM")
for k, v in res.items():
    print(f"  {k:<18} {v['seconds']:>6.0f}  {v['peak_vram_mb']:>7}  {v['peak_gpu_util']:>4}  {v['peak_backend_rss_mb']:>8}")
clips = c.get(f"/api/jobs/{jid}/clips").json()
print(f"\n{len(clips)} clips:")
ok = True
for cl in sorted(clips, key=lambda x: x["start_time"]):
    pr = probe(OUTPUTS / jid / f"clip_{cl['index'] + 1}.mp4")
    good = (pr["w"], pr["h"]) == (1080, 1920) and pr["audio"] and abs(pr["duration"] - cl["duration"]) < 0.3
    ok &= good
    print(f"  {cl['start_time'] / 60:5.1f}-{cl['end_time'] / 60:5.1f} min  {cl['duration']:4.0f}s  {cl['layout']:<6} "
          f"faces={cl['face_coverage']:.0%}  [{cl['source']}] {'OK ' if good else 'BAD'} {cl['title']}")
t = json.loads((OUTPUTS / jid / "transcript.json").read_text("utf-8"))
print(f"\ntranscript: {len(t['words'])} words, model {t['model']} on {t['device']}; all clips verified: {ok}")
