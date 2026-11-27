"""ffprobe / ffmpeg helpers. Never leak file paths or raw stderr to API callers."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.config import get_settings
from app.models.schemas import VideoInfo

# ffprobe format_name for MP4/MOV is "mov,mp4,m4a,3gp,3g2,mj2"
_ALLOWED_FORMATS = {"mov", "mp4"}


class MediaError(Exception):
    """User-facing media validation error (message is safe to show)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _fps(rate: str | None) -> float:
    try:
        num, den = (rate or "0/1").split("/")
        return round(float(num) / float(den), 3) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def _rotation(stream: dict) -> int:
    """Display rotation in degrees (0/90/180/270) from the display matrix or the legacy rotate tag."""
    for sd in stream.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                return int(round(float(sd["rotation"]))) % 360
            except (TypeError, ValueError):
                pass
    try:
        return int((stream.get("tags") or {}).get("rotate", 0)) % 360
    except (TypeError, ValueError):
        return 0


def probe_video(path: Path, ext: str | None = None) -> VideoInfo:
    """ext: the original file extension (path may be a temp file)."""
    ext = (ext or path.suffix).lower()
    s = get_settings()
    try:
        proc = subprocess.run(
            [s.ffprobe_bin, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise MediaError("probe_failed", "Could not read the video file.") from e
    if proc.returncode != 0:
        raise MediaError("invalid_video", "This file is not a readable video.")

    data = json.loads(proc.stdout or "{}")
    fmt = data.get("format", {})
    formats = set((fmt.get("format_name") or "").split(","))
    if not formats & _ALLOWED_FORMATS:
        raise MediaError("unsupported_format", "Only MP4 and MOV videos are supported.")

    streams = data.get("streams", [])
    video = next((st for st in streams if st.get("codec_type") == "video"
                  and not st.get("disposition", {}).get("attached_pic")), None)
    if video is None:
        raise MediaError("no_video_stream", "The file has no video track.")

    try:
        duration = float(fmt.get("duration") or video.get("duration") or 0)
    except ValueError:
        duration = 0.0
    if duration <= 0:
        raise MediaError("invalid_duration", "Could not determine the video length.")

    # Phones often store portrait video as landscape pixels plus a "display rotation" flag.
    # FFmpeg auto-rotates when decoding (tracking, rendering, thumbnails), so report the
    # dimensions as displayed — otherwise a vertical phone video is treated as landscape.
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if _rotation(video) % 180 == 90:
        width, height = height, width

    return VideoInfo(
        duration_seconds=round(duration, 3),
        width=width,
        height=height,
        fps=_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        video_codec=video.get("codec_name") or "unknown",
        has_audio=any(st.get("codec_type") == "audio" for st in streams),
        container="mov" if ext == ".mov" else "mp4",
    )


def make_thumbnail(video: Path, out: Path, at_seconds: float, width: int = 640) -> None:
    s = get_settings()
    proc = subprocess.run(
        [s.ffmpeg_bin, "-y", "-v", "error", "-ss", f"{at_seconds:.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(out)],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0 or not out.exists():
        raise MediaError("thumbnail_failed", "Could not create a thumbnail.")
