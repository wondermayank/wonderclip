"""Fetch a video from a link (YouTube, Instagram, X, Vimeo, direct .mp4 …) with yt-dlp.

Runs on its own single thread (network-bound) so a download can overlap GPU processing.
Flow: rights confirmed by the user -> read metadata (reject live / too long BEFORE downloading)
-> download <=1080p MP4 -> the same validation as a normal upload (ffprobe, dedupe, audio).
"""
from __future__ import annotations

import logging
import os
import queue
import re
import shutil
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings
from app.models.db import Database
from app.services.media import MediaError
from app.services.uploads import finalize_file, safe_display_name, sha256_file

log = logging.getLogger("clipmitra.fetch")

# <=1080p; prefer H.264 + AAC so no re-encode is needed; any format as last resort (merged to MP4)
FORMAT = ("bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/"
          "b[height<=1080]/bv*+ba/b")


class FetchError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def validate_url(url: str) -> str:
    url = (url or "").strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc or len(url) > 2000:
        raise FetchError("bad_url", "Paste a full link that starts with https://")
    return url


def js_runtimes() -> dict:
    """yt-dlp needs a JavaScript runtime for YouTube. Prefer Deno (installer default), then Node, Bun."""
    found = {}
    for name, extra in (("deno", [Path.home() / ".deno" / "bin" / "deno.exe"]), ("node", []), ("bun", [])):
        path = shutil.which(name) or next((str(p) for p in extra if p.exists()), None)
        if path:
            found[name] = {"path": path}
    return found


_FRIENDLY = [
    (r"private video|sign in|log in|login|members-only|age-restricted|confirm your age|cookies",
     "login_required", "This video is private or needs a login, so Wonder Clips can't fetch it. "
                       "Download it yourself and upload the file instead."),
    (r"unsupported url|no video formats|is not a valid url",
     "unsupported_link", "This link isn't supported. Paste a link to a video page or a direct video file."),
    (r"not available in your country|geo|unavailable|removed|does not exist|404",
     "unavailable", "This video is unavailable (removed, region-locked or the link is wrong)."),
    (r"timed out|connection|getaddrinfo|network|resolve",
     "network", "Couldn't reach that website. Check your internet connection and try again."),
    (r"max_filesize|larger than", "file_too_large", "This video file is too large."),
]


def friendly(err: Exception) -> FetchError:
    msg = str(err).lower()
    for pattern, code, text in _FRIENDLY:
        if re.search(pattern, msg):
            return FetchError(code, text)
    return FetchError("fetch_failed", "Couldn't fetch this video. Try another link or upload the file.")


class _YtLogger:
    """Route yt-dlp's console output into our log (it prints raw ERROR lines otherwise)."""
    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.info("yt-dlp: %s", msg)


def fetch_to_upload(url: str, fetch_id: str, db: Database, on_progress) -> dict:
    """Returns the upload record (dict from UploadOut). Raises FetchError / MediaError."""
    import yt_dlp

    s = get_settings()
    base = {
        "quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 30, "logger": _YtLogger(),
        "ffmpeg_location": str(Path(s.ffmpeg_bin).parent) if os.path.isabs(s.ffmpeg_bin) else None,
        "js_runtimes": js_runtimes(),
    }
    base = {k: v for k, v in base.items() if v is not None}
    # 1. metadata only — reject live streams and long videos without downloading anything
    try:
        with yt_dlp.YoutubeDL({**base, "skip_download": True}) as y:
            info = y.extract_info(url, download=False)
    except Exception as e:  # yt-dlp raises DownloadError/ExtractorError with readable text
        log.info("metadata failed for %s: %s", url, e)
        raise friendly(e) from e
    if info.get("_type") == "playlist":
        raise FetchError("playlist", "That's a playlist. Paste the link of a single video.")
    if info.get("is_live"):
        raise FetchError("live", "Live streams can't be fetched. Try again after the stream has ended.")
    limit = s.max_duration_seconds + s.duration_tolerance_seconds
    dur = info.get("duration")
    if dur and dur > limit:
        raise MediaError("too_long", f"This video is {int(dur // 60)}:{int(dur % 60):02d} long. "
                                     f"For now the limit is {s.max_duration_seconds / 60:g} minutes.")
    title = safe_display_name(f"{info.get('title') or 'video'}")
    title = re.sub(r"\.(mp4|mov|webm|mkv)$", "", title, flags=re.I)[:90] + ".mp4"

    # 2. download (merged to MP4)
    out_tmpl = str(s.temp_dir / f"fetch_{fetch_id}.%(ext)s")

    def hook(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                on_progress(min(d.get("downloaded_bytes", 0) / total, 0.99))

    opts = {**base, "format": FORMAT, "merge_output_format": "mp4", "outtmpl": out_tmpl,
            "max_filesize": s.max_upload_bytes, "progress_hooks": [hook], "overwrites": True,
            "postprocessor_args": {"merger": ["-movflags", "+faststart"]}}
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([info.get("webpage_url") or url])
    except Exception as e:
        raise friendly(e) from e
    files = sorted(s.temp_dir.glob(f"fetch_{fetch_id}.*"), key=lambda p: p.stat().st_size, reverse=True)
    media = next((p for p in files if p.suffix.lower() in (".mp4", ".mov")), None)
    if not media:
        raise FetchError("fetch_failed", "The download didn't produce a playable MP4.")
    on_progress(1.0)

    # 3. exactly the same checks as a normal upload
    digest, size = sha256_file(media)
    if size > s.max_upload_bytes:
        raise MediaError("file_too_large", f"This video file is larger than {s.max_upload_bytes // 1024**3} GB.")
    tmp = s.temp_dir / f"{uuid.uuid4().hex}.part"
    media.replace(tmp)
    try:
        return finalize_file(tmp, title, ".mp4", size, digest, db).model_dump()
    finally:
        tmp.unlink(missing_ok=True)


class FetchWorker:
    """One download at a time on its own thread."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.q: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="clipmitra-fetch", daemon=True)

    def start(self) -> None:
        for f in self.db.pending_fetches():  # interrupted by a restart: start again
            self.db.update_fetch(f["id"], status="queued", progress=0.0)
            self.q.put(f["id"])
        self._thread.start()

    def stop(self) -> None:
        self.q.put("")

    def submit(self, fetch_id: str) -> None:
        self.q.put(fetch_id)

    def _loop(self) -> None:
        while True:
            fid = self.q.get()
            if not fid:
                return
            f = self.db.get_fetch(fid)
            if not f or f["status"] != "queued":
                continue
            self.db.update_fetch(fid, status="downloading")
            last = [0.0]

            def progress(p: float) -> None:
                if p - last[0] >= 0.01 or p >= 1:
                    last[0] = p
                    self.db.update_fetch(fid, progress=round(p, 3))

            try:
                up = fetch_to_upload(f["url"], fid, self.db, progress)
                self.db.update_fetch(fid, status="completed", progress=1.0, upload_id=up["upload_id"],
                                     title=up["filename"])
            except (FetchError, MediaError) as e:
                self.db.update_fetch(fid, status="failed", error_code=e.code, error_message=e.message)
            except Exception:
                log.exception("fetch %s crashed", fid)
                self.db.update_fetch(fid, status="failed", error_code="fetch_failed",
                                     error_message="Couldn't fetch this video. Try another link or upload the file.")
            finally:
                for p in get_settings().temp_dir.glob(f"fetch_{fid}.*"):
                    p.unlink(missing_ok=True)


def new_fetch_id() -> str:
    return uuid.uuid4().hex
