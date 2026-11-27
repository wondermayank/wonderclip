"""Vertical 9:16 clip rendering with FFmpeg: reframe + burned-in captions in one pass."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.config import get_settings
from app.services.face import Reframe
from app.services.media import MediaError, make_thumbnail, probe_video
from app.services.transcribe import PipelineError

log = logging.getLogger("clipmitra.render")

NVENC = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0"]
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def _escape_filter_path(p: str) -> str:
    """Path as a filter option value: forward slashes, ':' escaped, quoted."""
    return "'" + p.replace("\\", "/").replace(":", "\\:").replace("'", "") + "'"


def write_crop_commands(rf: Reframe, fps: float, path: Path) -> None:
    """sendcmd script: move the crop window only on frames where x changes."""
    lines, prev = [], None
    for k, x in enumerate(rf.xs):
        if x != prev:
            lines.append(f"{k / fps:.4f} crop@cam x {x};")
            prev = x
    path.write_text("\n".join(lines) + "\n", "ascii")


def build_filter(rf: Reframe, ass_name: str | None, cmd_name: str | None) -> tuple[str, bool]:
    """Returns (filtergraph, is_complex)."""
    s = get_settings()
    W, H = s.output_width, s.output_height
    subs = f",subtitles=filename={ass_name}:fontsdir={_escape_filter_path(s.fonts_dir)}" if ass_name else ""
    if rf.layout == "track":
        x0 = rf.xs[0] if rf.xs else 0
        return (f"sendcmd=f={cmd_name},crop@cam=w={rf.crop_w}:h={rf.crop_h}:x={x0}:y=0,"
                f"scale={W}:{H}:flags=lanczos,setsar=1{subs}", False)
    if rf.layout == "native":
        return f"scale={W}:{H}:flags=lanczos,setsar=1{subs}", False
    # fit: whole frame centred over a blurred, darkened copy of itself.
    # Blur at quarter resolution then upscale: same look, ~10x cheaper than blurring 1080x1920.
    return (f"[0:v]split=2[a][b];[a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,"
            f"crop={W // 4}:{H // 4},boxblur=luma_radius=10:luma_power=2,eq=brightness=-0.08,"
            f"scale={W}:{H}:flags=bicubic[bg];"
            f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1{subs}[v]", True)


def render_clip(src: Path, start: float, end: float, out: Path, rf: Reframe, fps: float,
                ass_text: str | None) -> float:
    """Render [start, end) as a 1080x1920 MP4. Returns the ffprobe-verified duration."""
    s = get_settings()
    src, out = src.resolve(), out.resolve()  # ffmpeg runs with cwd = clip folder
    work = out.parent
    stem = out.stem
    ass_name = cmd_name = None
    if ass_text:
        ass_name = f"{stem}.ass"
        (work / ass_name).write_text(ass_text, "utf-8")
    if rf.layout == "track":
        cmd_name = f"{stem}.cmd"
        write_crop_commands(rf, fps, work / cmd_name)
    graph, complex_ = build_filter(rf, ass_name, cmd_name)
    vf = ["-filter_complex", graph, "-map", "[v]", "-map", "0:a:0"] if complex_ else \
         ["-vf", graph, "-map", "0:v:0", "-map", "0:a:0"]

    def run(enc: list[str]) -> bool:
        cmd = [s.ffmpeg_bin, "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src),
               "-t", f"{end - start:.3f}", *vf, *enc, "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out.name]
        # cwd = job folder so .ass/.cmd are referenced by bare names (no Windows path escaping)
        p = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=1800)
        if p.returncode != 0:
            log.warning("render failed (%s): %s", enc[1], p.stderr[-600:])
        return p.returncode == 0 and out.exists()

    if not (run(NVENC) or run(X264)):
        raise PipelineError("render_failed", "Couldn't render a clip from this video.")
    return verify_clip(out, end - start)


def verify_clip(path: Path, expected: float, tolerance: float = 0.5) -> float:
    """Never report a clip as done unless the file exists and ffprobe agrees on size and length."""
    s = get_settings()
    if not path.exists() or path.stat().st_size == 0:
        raise PipelineError("render_failed", "A rendered clip is missing.")
    try:
        info = probe_video(path)
    except MediaError as e:
        raise PipelineError("render_failed", "A rendered clip is unreadable.") from e
    if (info.width, info.height) != (s.output_width, s.output_height):
        raise PipelineError("render_failed", "A rendered clip has the wrong size.")
    if not info.has_audio or abs(info.duration_seconds - expected) > tolerance:
        raise PipelineError("render_failed", "A rendered clip came out the wrong length.")
    return info.duration_seconds


def clip_thumbnail(clip: Path, out: Path, duration: float) -> None:
    make_thumbnail(clip, out, min(1.0, duration / 2), width=480)
