"""Real FFmpeg renders of every layout with burned captions (small synthetic inputs)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.services import captions as cap
from app.services.face import Reframe
from app.services.media import probe_video
from app.services.render import render_clip, write_crop_commands


@pytest.fixture(autouse=True)
def _env(settings_env):
    yield


def src_video(path: Path, w: int, h: int, secs: float = 3) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=30:d={secs}",
                    "-f", "lavfi", "-i", f"sine=f=300:d={secs}", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


ASS = cap.build_ass([cap.Word(0.1, 0.6, "नमस्ते"), cap.Word(0.7, 1.2, "creators")], 2.0, cap.get_style("bold"))


@pytest.mark.parametrize("layout,size", [("track", (1280, 720)), ("native", (540, 960)), ("fit", (1280, 720))])
def test_render_layouts_produce_verified_vertical_clip(tmp_path, layout, size):
    src = src_video(tmp_path / "in.mp4", *size)
    rf = Reframe(layout)
    if layout == "track":
        rf.crop_w, rf.crop_h = 404, 720
        rf.xs = [min(876, 10 * k) for k in range(60)]  # pan right
    out = tmp_path / "clip_1.mp4"
    dur = render_clip(src, 0.5, 2.5, out, rf, 30, ASS)
    info = probe_video(out)
    assert (info.width, info.height) == (1080, 1920) and abs(dur - 2.0) < 0.2 and info.has_audio
    assert (tmp_path / "clip_1.ass").exists()


def test_crop_commands_only_on_change(tmp_path):
    rf = Reframe("track", 404, 720, [5, 5, 5, 9, 9, 12])
    p = tmp_path / "c.cmd"
    write_crop_commands(rf, 30, p)
    assert p.read_text().splitlines() == ["0.0000 crop@cam x 5;", "0.1000 crop@cam x 9;", "0.1667 crop@cam x 12;"]
