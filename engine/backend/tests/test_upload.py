"""Upload endpoint tests. Fixtures are generated with FFmpeg (real files, no mocks)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def make_video(out: Path, seconds: float, audio: bool = True, color: str = "blue") -> Path:
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:r=25:d={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(args, check=True)
    return out


def post(client, path: Path, name: str | None = None):
    with path.open("rb") as fh:
        return client.post("/api/upload", files={"file": (name or path.name, fh, "video/mp4")})


def test_valid_mp4(client, tmp_media):
    r = post(client, make_video(tmp_media / "ok.mp4", 3))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["video"]["width"] == 320 and body["video"]["has_audio"]
    assert 2.9 < body["video"]["duration_seconds"] < 3.2
    assert len(body["upload_id"]) == 32
    assert "\\" not in r.text and "/uploads" not in r.text  # no filesystem paths leaked
    meta = client.get(f"/api/uploads/{body['upload_id']}")
    assert meta.status_code == 200
    thumb = client.get(f"/api/uploads/{body['upload_id']}/thumbnail")
    assert thumb.status_code == 200 and thumb.content[:2] == b"\xff\xd8"


def test_valid_mov(client, tmp_media):
    r = post(client, make_video(tmp_media / "ok.mov", 2, color="red"))
    assert r.status_code == 200, r.text
    assert r.json()["video"]["container"] == "mov"


@pytest.mark.parametrize("rot", ["90", "-90"])
def test_phone_rotation_reports_displayed_size(client, tmp_media, rot):
    """Portrait phone video stored as 320x240 landscape pixels + display rotation -> 240x320."""
    src = make_video(tmp_media / f"side{rot}.mp4", 2, color="olive")
    rotated = tmp_media / f"rot{rot}.mov"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-display_rotation", rot, "-i", str(src), "-c", "copy",
                    str(rotated)], check=True)
    v = post(client, rotated).json()["video"]
    assert (v["width"], v["height"]) == (240, 320)


def test_duplicate_returns_same_upload(client, tmp_media):
    f = make_video(tmp_media / "dup.mp4", 2, color="green")
    a, b = post(client, f).json(), post(client, f).json()
    assert a["upload_id"] == b["upload_id"] and b["duplicate"] is True


def test_rejects_wrong_extension(client, tmp_media):
    p = tmp_media / "x.avi"
    p.write_bytes(b"not a video")
    r = post(client, p)
    assert r.status_code == 400 and r.json()["code"] == "unsupported_format"


def test_rejects_fake_mp4(client, tmp_media):
    p = tmp_media / "fake.mp4"
    p.write_bytes(b"\x00" * 4096)
    r = post(client, p)
    assert r.status_code == 400 and r.json()["code"] == "invalid_video"


def test_rejects_too_long(client, tmp_media):
    r = post(client, make_video(tmp_media / "long.mp4", 14, color="white"))
    assert r.status_code == 413 and r.json()["code"] == "too_long"


def test_rejects_no_audio(client, tmp_media):
    r = post(client, make_video(tmp_media / "silent.mp4", 2, audio=False, color="yellow"))
    assert r.status_code == 400 and r.json()["code"] == "no_audio"


def test_unknown_upload_404(client):
    assert client.get("/api/uploads/../../etc").status_code == 404
    assert client.get("/api/uploads/" + "a" * 32).status_code == 404


def test_no_temp_leftovers(client, tmp_media, tmp_path):
    p = tmp_media / "bad.mp4"
    p.write_bytes(b"garbage")
    post(client, p)
    assert list((tmp_path / "t").glob("*.part")) == []
