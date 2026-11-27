"""Speaker tracking with MediaPipe Face Landmarker (CPU) and a smooth 9:16 crop path.

Pipeline per clip:
  FFmpeg decodes the clip range at `track_fps` (small frames) -> Face Landmarker (VIDEO mode)
  -> pick one target face per frame (single-speaker first) -> layout decision
  -> crop centre path: median filter, dead-zone "virtual camera", velocity limit
  -> interpolated to one x-offset per output frame.
"""
from __future__ import annotations

import logging
import re
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.config import get_settings

log = logging.getLogger("clipmitra.face")

TARGET_AR = 9 / 16


@dataclass
class Face:
    cx: float  # normalised 0..1 in source frame
    cy: float
    w: float
    h: float
    mouth: float  # inner-lip gap / face height (speech activity cue)

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass
class Track:
    times: list[float] = field(default_factory=list)           # seconds from clip start
    target: list[float | None] = field(default_factory=list)   # target face centre x (0..1) or None
    faces_per_frame: list[int] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        """Share of samples where the followed person was found (drives the crop path)."""
        return sum(t is not None for t in self.target) / len(self.target) if self.target else 0.0

    @property
    def face_coverage(self) -> float:
        """Share of samples with any usable face (drives the layout: is there someone to frame?)."""
        return sum(n > 0 for n in self.faces_per_frame) / len(self.faces_per_frame) if self.faces_per_frame else 0.0


@dataclass
class Reframe:
    layout: str               # "track" (moving 9:16 crop) | "native" (already 9:16) | "fit" (blurred background)
    crop_w: int = 0
    crop_h: int = 0
    xs: list[int] = field(default_factory=list)  # left edge per output frame (track only)
    coverage: float = 0.0
    max_faces: int = 0


# ------------------------------------------------------------------ detection

class FaceTracker:
    """Owns one Face Landmarker. Create once per job; close() when done."""

    def __init__(self) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision

        s = get_settings()
        model = s.model_dir / "mediapipe" / "face_landmarker.task"
        if not model.exists():
            raise FileNotFoundError("face_landmarker.task missing (see docs/DEPENDENCIES.md)")
        self._mp = mp
        # IMAGE mode: each tile is an independent image (VIDEO mode would track across tiles).
        self._lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=4,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
        ))

    def close(self) -> None:
        self._lm.close()

    def _faces_in(self, tile: np.ndarray) -> list[tuple[float, float, float, float, float]]:
        """Returns (x0, y0, x1, y1, mouth) in tile-normalised coords."""
        res = self._lm.detect(self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                                             data=np.ascontiguousarray(tile)))
        out = []
        for lms in res.face_landmarks or []:
            xs = [p.x for p in lms]
            ys = [p.y for p in lms]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            mouth = abs(lms[14].y - lms[13].y) / max(y1 - y0, 1e-6) if len(lms) > 14 else 0.0
            out.append((x0, y0, x1, y1, mouth))
        return out

    def detect(self, src: Path, start: float, end: float, src_w: int, src_h: int) -> list[tuple[float, list[Face]]]:
        """Detect faces at `track_fps` over [start, end).

        MediaPipe's face detector is a short-range (selfie) model that squashes the whole image to a
        small square input, so a face filling ~8% of a 16:9 frame is missed. We therefore scan
        overlapping square tiles (side = frame height, 50% overlap) and merge the detections.
        """
        s = get_settings()
        ah = 540
        aw = max(ah, int(round(src_w * ah / src_h / 2)) * 2)
        side = min(aw, ah)
        n_tiles = 1 if aw == side else int(np.ceil((aw - side) / (side / 2))) + 1
        tile_xs = [int(round(x)) for x in np.linspace(0, aw - side, n_tiles)]
        proc = subprocess.Popen(
            [s.ffmpeg_bin, "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{end - start:.3f}",
             "-vf", f"fps={s.track_fps},scale={aw}:{ah}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        frame_bytes = aw * ah * 3
        out: list[tuple[float, list[Face]]] = []
        rescan_every = max(1, int(s.track_fps))  # full scan ~1x per second to notice other faces
        i = 0
        misses = 0  # consecutive frames without any face
        known: list[Face] = []  # every face seen last frame; each is followed in its own ROI
        try:
            while True:
                buf = proc.stdout.read(frame_bytes)
                if len(buf) < frame_bytes:
                    break
                # Nothing seen for ~1 s (screen recording, b-roll): scan only every other frame.
                if misses >= rescan_every and i % 2:
                    out.append((i / s.track_fps, []))
                    i += 1
                    continue
                arr = np.frombuffer(buf, np.uint8).reshape(ah, aw, 3)
                boxes = []
                # 1) track: a tight square around EVERY face seen last frame (large enough to detect
                #    reliably). Following only one face biased detection towards it: in Phase 5 the
                #    other person was then found only once per second and the crop drifted away.
                for k in known:
                    r = int(np.clip(3.5 * k.h * ah, 128, ah))
                    rx = int(np.clip(k.cx * aw - r / 2, 0, aw - r))
                    ry = int(np.clip(k.cy * ah - r / 2, 0, ah - r))
                    for x0, y0, x1, y1, m in self._faces_in(arr[ry:ry + r, rx:rx + r]):
                        boxes.append(((rx + x0 * r) / aw, (ry + y0 * r) / ah, (rx + x1 * r) / aw, (ry + y1 * r) / ah, m))
                # 2) scan: overlapping full-height tiles when a known face was lost, or periodically
                if len(merge_boxes(boxes)) < len(known) or not boxes or i % rescan_every == 0:
                    for tx in tile_xs:
                        for x0, y0, x1, y1, m in self._faces_in(arr[:, tx:tx + side]):
                            boxes.append(((tx + x0 * side) / aw, y0, (tx + x1 * side) / aw, y1, m))
                faces = merge_boxes(boxes)
                misses = 0 if faces else misses + 1
                if faces:
                    known = faces[:4]
                out.append((i / s.track_fps, faces))
                i += 1
        finally:
            proc.stdout.close()
            proc.wait(timeout=30)
        return out


def merge_boxes(boxes: list[tuple[float, float, float, float, float]]) -> list[Face]:
    """Same face seen in two overlapping tiles -> keep the larger (more complete) box."""
    faces: list[Face] = []
    for x0, y0, x1, y1, m in sorted(boxes, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1])):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if any(abs(cx - f.cx) < f.w / 2 and abs(cy - f.cy) < f.h / 2 for f in faces):
            continue
        faces.append(Face(cx, cy, x1 - x0, y1 - y0, m))
    return faces


def needs_tracking(src_w: int, src_h: int) -> bool:
    """Only frames wider than 9:16 need a moving crop; vertical videos are used as they are."""
    return src_w / src_h > TARGET_AR + 0.02


# ------------------------------------------------------------------ target selection

def pick_target(frames: list[tuple[float, list[Face]]], min_area: float = 0.004,
                switch_after: int = 15, same_person: float = 0.25,
                shots: list[int] | None = None) -> Track:
    """Follow one face: start with the most prominent, then stay with that person.

    Prominence = size, plus mouth movement (the speaker usually moves their lips).
    If only *other* faces are visible (target turned away / covered), the target counts as missing
    and the camera holds; it switches to someone else only after `switch_after` samples (3 s at 5 fps)
    with another person visible and the target not. Without this, a one-frame detection dropout or a
    cutaway made the crop pan to the other person (found in Phase 5 with a two-person video).
    """
    tr = Track()
    prev: Face | None = None
    lost = 0
    for t, faces in frames:
        faces = [f for f in faces if f.area >= min_area]  # ignore tiny background faces
        if shots is not None and len(tr.times) and shots[len(tr.times)] != shots[len(tr.times) - 1]:
            prev, lost = None, 0  # camera cut: the new shot shows a different view; pick its main face afresh
        tr.times.append(t)
        tr.faces_per_frame.append(len(faces))
        cur: Face | None = None
        if faces:
            if prev is None:
                cur = max(faces, key=lambda f: f.area * (1 + 4 * f.mouth))
            else:
                near = min(faces, key=lambda f: abs(f.cx - prev.cx) + abs(f.cy - prev.cy))
                if abs(near.cx - prev.cx) < same_person:
                    cur = near
                elif lost + 1 >= switch_after:  # target gone for a while: follow the most prominent face
                    cur = max(faces, key=lambda f: f.area * (1 + 4 * f.mouth))
        if cur is None:
            # Only time where *someone else* is on screen counts towards switching; a cutaway with no
            # faces at all (b-roll, graphics) says nothing about whether the speaker left.
            if faces:
                lost += 1
            tr.target.append(None)
            continue
        lost = 0
        prev = cur
        tr.target.append(cur.cx)
    return tr


# ------------------------------------------------------------------ layout + crop path

def choose_layout(src_w: int, src_h: int, coverage: float, min_coverage: float = 0.3) -> str:
    ar = src_w / src_h
    if abs(ar - TARGET_AR) < 0.02:
        return "native"
    if ar < TARGET_AR or coverage < min_coverage:
        return "fit"
    return "track"


def _fill_gaps(vals: list[float | None]) -> list[float]:
    known = [v for v in vals if v is not None]
    if not known:
        return [0.5] * len(vals)
    out, last = [], known[0]
    for v in vals:
        last = v if v is not None else last
        out.append(last)
    return out


def smooth_path(
    centres: list[float], dt: float, crop_frac: float,
    deadzone: float = 0.10, alpha: float = 0.35, max_speed: float = 0.55,
) -> list[float]:
    """Virtual camera over normalised centre positions (0..1 of source width).

    - median over ~1 s removes landmark jitter and one-frame glitches
    - dead zone: camera stays still while the face moves within `deadzone` x crop width
    - eased follow (alpha) with a speed limit (`max_speed` crop widths per second)
    """
    if not centres:
        return []
    k = 1  # 3-sample median (~0.6 s at 5 fps)
    med =[statistics.median(centres[max(0, i - k): i + k + 1]) for i in range(len(centres))]
    dz = deadzone * crop_frac
    vmax = max_speed * crop_frac * dt
    cam = med[0]
    out = []
    for c in med:
        err = c - cam
        if abs(err) > crop_frac:
            cam = c  # a different person (more than a frame-width away): hard cut, like an editor would
        elif abs(err) > dz:
            step = alpha * (err - np.sign(err) * dz)
            cam += float(np.clip(step, -vmax, vmax))
        out.append(cam)
    return out


def detect_cuts(src: Path, start: float, end: float, threshold: float = 0.15) -> list[float]:
    """Camera cuts (seconds from `start`) via FFmpeg scene detection on a small preview.

    Measured on a multi-camera podcast: normal frames score <= 0.003, cuts ~0.43.
    """
    s = get_settings()
    try:
        p = subprocess.run(
            [s.ffmpeg_bin, "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{end - start:.3f}", "-an",
             "-vf", f"scale=192:-2,select='gt(scene,{threshold})',metadata=print:file=-", "-f", "null", "-"],
            capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return sorted(float(m) for m in re.findall(r"pts_time:([0-9.]+)", p.stdout) if float(m) > 0.05)


def compute_reframe(frames: list[tuple[float, list[Face]]], src_w: int, src_h: int,
                    duration: float, out_fps: float, cuts: list[float] | tuple = ()) -> Reframe:
    """Crop path per output frame. `cuts` (camera cuts, seconds) split the clip into shots: the target is
    re-picked at each cut and the frame jumps on the exact cut frame (no pan, no lag)."""
    s = get_settings()
    cuts = sorted(cuts)
    times = np.array([t for t, _ in frames])
    shots = list(np.searchsorted(cuts, times, side="right")) if cuts else None
    tr = pick_target(frames, shots=shots)
    layout = choose_layout(src_w, src_h, tr.face_coverage)
    rf = Reframe(layout=layout, coverage=round(tr.face_coverage, 3), max_faces=max(tr.faces_per_frame, default=0))
    if layout != "track":
        return rf
    crop_w = int(round(src_h * TARGET_AR / 2)) * 2
    rf.crop_w, rf.crop_h = crop_w, src_h
    frac = crop_w / src_w
    shot_of = np.array(shots if shots is not None else [0] * len(times))
    # smooth each shot on its own (no median/easing across a cut)
    p = np.zeros(len(times))
    for sid in np.unique(shot_of):
        idx = np.nonzero(shot_of == sid)[0]
        p[idx] = smooth_path(_fill_gaps([tr.target[i] for i in idx]), 1 / s.track_fps, frac)
    # one x per output frame: linear between samples of the same shot; a jump bigger than the frame
    # (switch of person) lands on a single frame instead of being smeared into a fast pan
    n = max(1, int(round(duration * out_fps)))
    t_out = np.arange(n) / out_fps
    out_shot = np.searchsorted(cuts, t_out, side="right") if cuts else np.zeros(n, int)
    centre = np.empty(n)
    for sid in np.unique(out_shot):
        m = out_shot == sid
        idx = np.nonzero(shot_of == sid)[0]
        if len(idx) == 0:  # shot shorter than one sample: use the nearest sample in time
            centre[m] = p[np.argmin(np.abs(times - t_out[m][0]))]
            continue
        ts, ps = times[idx], p[idx]
        c = np.interp(t_out[m], ts, ps)
        tm = t_out[m]
        for k in np.nonzero(np.abs(np.diff(ps)) > frac)[0]:
            c[(tm >= ts[k]) & (tm < ts[k + 1])] = ps[k]
        centre[m] = c
    centre = centre * src_w
    left = np.clip(np.round(centre - crop_w / 2), 0, src_w - crop_w)
    rf.xs = [int(x) for x in left]
    return rf
