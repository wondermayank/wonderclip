"""Editor API: validation, queuing, word edits, fonts, export. Worker disabled; renders tested in test_render."""
from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest

from app.workers.pipeline import apply_word_edits, clip_file, job_dir
from tests.test_upload import make_video, post


@pytest.fixture()
def ready_clip(client, tmp_media):
    """A completed job with one clip file + transcript, as the pipeline would leave it."""
    uid = post(client, make_video(tmp_media / "ed.mp4", 8, color="teal")).json()["upload_id"]
    jid = client.post("/api/process", json={"upload_id": uid}).json()["job_id"]
    db = client.app.state.db
    d = job_dir(jid)
    d.mkdir(parents=True, exist_ok=True)
    words = [{"start": 0.5 + i, "end": 0.9 + i, "text": t, "prob": 0.9} for i, t in enumerate(["इतना", "आसान", "नहीं", "tool"])]
    (d / "transcript.json").write_text(json.dumps({"words": words, "segments": [], "duration": 8}), "utf-8")
    clip_file(jid, 0).write_bytes(b"\x00" * 2048)
    db.insert_clip(id="c" * 32, job_id=jid, idx=0, start_time=0.0, end_time=6.0, title="T", hook="h", reason="r",
                   editorial_score=7, transcript="x", source="ai", duration=6.0, layout="fit", caption_style="bold")
    db.update_job(jid, status="completed")
    return client, "c" * 32, jid


def test_editor_payload(ready_clip):
    client, cid, _ = ready_clip
    r = client.get(f"/api/clips/{cid}/editor")
    assert r.status_code == 200, r.text
    e = r.json()
    assert [w["text"] for w in e["words"]] == ["itna", "aasan", "nahi", "tool"]  # Roman Hinglish default
    assert e["words"][0]["original"] == "इतना" and e["words"][0]["i"] == 0
    assert set(e["presets"]) >= {"bold", "karaoke", "minimal", "headline"}
    fams = {f["family"]: f for f in e["fonts"]}
    assert fams["Poppins"]["has_bold"] and not fams["Anton"]["has_bold"]
    assert e["source"]["video_url"].startswith("/api/uploads/") and "\\" not in r.text
    assert client.get(fams["Poppins"]["regular_url"]).status_code == 200


def test_edit_queues_render_and_stores_settings(ready_clip):
    client, cid, _ = ready_clip
    r = client.put(f"/api/clips/{cid}", json={"start_time": 1.0, "end_time": 5.5,
                                               "style": {"preset": "minimal", "font": "Mukta", "size": 64},
                                               "word_edits": {"3": "  tool  bhi "}})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"
    c = client.app.state.db.get_clip(cid)
    assert (c["start_time"], c["end_time"]) == (1.0, 5.5)
    st = json.loads(c["style_json"])
    assert st["preset"] == "minimal" and st["font"] == "Mukta" and st["box"] is True
    assert json.loads(c["word_edits_json"]) == {"3": "tool bhi"}
    # busy while queued
    again = client.put(f"/api/clips/{cid}", json={"start_time": 1.0, "end_time": 5.0})
    assert again.status_code == 409


@pytest.mark.parametrize("body,code", [
    ({"start_time": 5, "end_time": 4}, "bad_range"),
    ({"start_time": -1, "end_time": 4}, "bad_range"),
    ({"start_time": 0, "end_time": 99}, "bad_range"),
    ({"start_time": 0, "end_time": 2}, "bad_length"),
    ({"start_time": 0, "end_time": 5, "style": {"font": "Comic Sans"}}, "bad_style"),
    ({"start_time": 0, "end_time": 5, "style": {"text_color": "blue"}}, "bad_style"),
    ({"start_time": 0, "end_time": 5, "word_edits": {"99": "x"}}, "bad_word_edit"),
    ({"start_time": 0, "end_time": 5, "word_edits": {"../1": "x"}}, "bad_word_edit"),
])
def test_edit_validation(ready_clip, body, code):
    client, cid, _ = ready_clip
    r = client.put(f"/api/clips/{cid}", json=body)
    assert r.status_code == 400 and r.json()["code"] == code


def test_word_edits_change_text_never_timing():
    words = [{"start": 1, "end": 2, "text": "toobhi"}, {"start": 2, "end": 3, "text": "banana"}]
    out = apply_word_edits(words, {"0": "tool bhi"})
    assert out[0] == {"start": 1, "end": 2, "text": "tool bhi"} and out[1] is words[1]


def test_fonts_whitelist(client):
    assert client.get("/api/fonts/Poppins-Bold.ttf").status_code == 200
    assert client.get("/api/fonts/..%2Fconfig.py").status_code == 404
    assert client.get("/api/fonts/wonderclip.db").status_code == 404


def test_export_zip(ready_clip):
    client, _, jid = ready_clip
    r = client.get(f"/api/jobs/{jid}/export.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(BytesIO(r.content)).namelist()
    assert names == ["wonderclip-1-t.mp4"]


def test_cors_preflight_allows_put_from_frontend(client):
    r = client.options("/api/clips/" + "a" * 32, headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 200 and "PUT" in r.headers["access-control-allow-methods"]


def test_hosted_ui_allowed_including_private_network_preflight(client):
    r = client.options("/api/upload", headers={
        "Origin": "https://clips.wondermayank.in", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Private-Network": "true"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://clips.wondermayank.in"
    assert r.headers.get("access-control-allow-private-network") == "true"
    assert client.get("/api/health", headers={"Origin": "https://clips.wondermayank.in"}).status_code == 200


def test_other_websites_are_rejected(client, tmp_media):
    from tests.test_upload import make_video
    vid = make_video(tmp_media / "evil.mp4", 2, color="black")
    with vid.open("rb") as fh:  # a "simple" cross-site POST browsers send without preflight
        r = client.post("/api/upload", files={"file": ("x.mp4", fh, "video/mp4")},
                        headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "forbidden_origin"
    assert client.get("/api/health").status_code == 200  # no Origin (local scripts) still fine


def test_regenerate_blocked_while_clip_renders(ready_clip):
    client, cid, jid = ready_clip
    client.app.state.db.update_clip(cid, status="rendering")
    uid = client.app.state.db.get_job(jid)["upload_id"]
    assert client.post("/api/process", json={"upload_id": uid, "force": True}).status_code == 409
