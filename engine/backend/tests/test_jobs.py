"""Job API: duplicate prevention, retry, cancel, regenerate. Worker disabled (no GPU)."""
from __future__ import annotations

from tests.test_upload import make_video, post


def _upload(client, tmp_media, name="j.mp4", color="purple"):
    return post(client, make_video(tmp_media / name, 2, color=color)).json()["upload_id"]


def test_process_is_idempotent(client, tmp_media):
    uid = _upload(client, tmp_media)
    a = client.post("/api/process", json={"upload_id": uid}).json()
    b = client.post("/api/process", json={"upload_id": uid}).json()
    assert a["job_id"] == b["job_id"] and a["status"] == "queued"
    assert [s["key"] for s in a["stages"]][:3] == ["extracting_audio", "transcribing", "finding_highlights"]
    assert a["upload"]["upload_id"] == uid


def test_cancel_then_retry_reuses_job(client, tmp_media):
    uid = _upload(client, tmp_media, "c.mp4", "orange")
    job = client.post("/api/process", json={"upload_id": uid}).json()
    c = client.post(f"/api/jobs/{job['job_id']}/cancel").json()
    assert c["status"] == "cancelled"
    r = client.post("/api/process", json={"upload_id": uid}).json()
    assert r["job_id"] == job["job_id"] and r["status"] == "queued" and r["error_code"] is None


def test_completed_job_returned_unless_force(client, tmp_media):
    uid = _upload(client, tmp_media, "d.mp4", "pink")
    jid = client.post("/api/process", json={"upload_id": uid}).json()["job_id"]
    client.app.state.db.update_job(jid, status="completed", progress=1.0)
    assert client.post("/api/process", json={"upload_id": uid}).json()["status"] == "completed"
    assert client.post("/api/process", json={"upload_id": uid, "force": True}).json()["status"] == "queued"


def test_clips_empty_until_completed_and_never_served_without_file(client, tmp_media):
    uid = _upload(client, tmp_media, "e.mp4", "gray")
    jid = client.post("/api/process", json={"upload_id": uid}).json()["job_id"]
    assert client.get(f"/api/jobs/{jid}/clips").json() == []
    db = client.app.state.db
    db.insert_clip(id="f" * 32, job_id=jid, idx=0, start_time=0, end_time=1, title="t", hook="h",
                   reason="r", editorial_score=5, transcript="x", source="ai", duration=1.0)
    db.update_job(jid, status="completed")
    assert client.get(f"/api/jobs/{jid}/clips").json() == []  # DB row but no file -> not listed
    assert client.get("/api/clips/" + "f" * 32).status_code == 404


def test_unknown_ids(client):
    assert client.post("/api/process", json={"upload_id": "a" * 32}).status_code == 404
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/jobs/" + "b" * 32 + "/clips").status_code == 404
    assert client.get("/api/clips/../x/download").status_code == 404
