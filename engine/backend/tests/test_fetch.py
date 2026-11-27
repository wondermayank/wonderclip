"""Paste-a-link: rights check, URL validation, real yt-dlp downloads from a local web server."""
from __future__ import annotations

import functools
import http.server
import threading

import pytest

from app.services import fetch as f
from app.services.media import MediaError
from tests.test_upload import make_video


@pytest.fixture()
def web(tmp_path):
    """Tiny HTTP server serving tmp_path — a 'direct video link' without needing the internet."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield tmp_path, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_rights_must_be_confirmed(client):
    r = client.post("/api/fetch", json={"url": "https://www.youtube.com/watch?v=x"})
    assert r.status_code == 400 and r.json()["code"] == "rights_not_confirmed"


@pytest.mark.parametrize("url", ["file:///C:/Windows/win.ini", "youtube.com/watch?v=x", "", "ftp://x/y.mp4"])
def test_bad_urls_rejected(client, url):
    r = client.post("/api/fetch", json={"url": url, "confirm_rights": True})
    assert r.status_code == 400 and r.json()["code"] == "bad_url"


def test_fetch_is_queued_and_tracked(client):
    r = client.post("/api/fetch", json={"url": "https://example.com/v.mp4", "confirm_rights": True})
    assert r.status_code == 200 and r.json()["status"] == "queued"
    fid = r.json()["fetch_id"]
    assert client.get(f"/api/fetch/{fid}").json()["url"] == "https://example.com/v.mp4"
    assert client.app.state.db.get_fetch(fid)["rights_confirmed_at"] > 0
    assert client.get("/api/fetch/" + "0" * 32).status_code == 404


def test_direct_link_download_becomes_upload(client, web):
    root, base = web
    make_video(root / "talk.mp4", 3, color="navy")
    seen = []
    up = f.fetch_to_upload(f"{base}/talk.mp4", "a" * 32, client.app.state.db, seen.append)
    assert up["video"]["has_audio"] and 2.9 < up["video"]["duration_seconds"] < 3.2
    assert up["filename"].endswith(".mp4") and seen and seen[-1] == 1.0
    assert client.get(f"/api/uploads/{up['upload_id']}").status_code == 200
    again = f.fetch_to_upload(f"{base}/talk.mp4", "b" * 32, client.app.state.db, lambda p: None)
    assert again["duplicate"] and again["upload_id"] == up["upload_id"]   # dedupe like uploads


def test_direct_link_too_long_rejected(client, web):
    root, base = web
    make_video(root / "long.mp4", 14, color="maroon")  # test limit is 10 s
    with pytest.raises(MediaError) as e:
        f.fetch_to_upload(f"{base}/long.mp4", "c" * 32, client.app.state.db, lambda p: None)
    assert e.value.code == "too_long"


def test_missing_page_gives_friendly_error(client, web):
    _, base = web
    with pytest.raises(f.FetchError) as e:
        f.fetch_to_upload(f"{base}/nope.mp4", "d" * 32, client.app.state.db, lambda p: None)
    assert e.value.code in ("unavailable", "fetch_failed", "unsupported_link")
    assert "\\" not in e.value.message and "Traceback" not in e.value.message  # user-facing text only


@pytest.mark.parametrize("raw,code", [
    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "login_required"),
    ("ERROR: Unsupported URL: https://example.com/page", "unsupported_link"),
    ("ERROR: [youtube] abc: Video unavailable. This video has been removed", "unavailable"),
    ("ERROR: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>", "network"),
    ("something odd happened", "fetch_failed"),
])
def test_friendly_messages(raw, code):
    assert f.friendly(Exception(raw)).code == code
