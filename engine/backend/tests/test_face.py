"""Crop-path logic with synthetic face tracks (no model needed)."""
from __future__ import annotations

import random
import subprocess

import pytest

from app.services import face
from app.services.face import Face


@pytest.fixture(autouse=True)
def _env(settings_env):
    yield


def frames_from(centres, fps=5.0):
    return [(i / fps, [] if c is None else [Face(c, 0.4, 0.08, 0.15, 0.02)]) for i, c in enumerate(centres)]


def test_layout_decisions():
    assert face.choose_layout(1080, 1920, 0.0) == "native"
    assert face.choose_layout(1920, 1080, 0.9) == "track"
    assert face.choose_layout(1920, 1080, 0.1) == "fit"      # screen recording / no face
    assert face.choose_layout(1080, 2400, 1.0) == "fit"      # narrower than 9:16
    assert face.needs_tracking(1920, 1080) and not face.needs_tracking(1080, 1920)


def test_jitter_inside_dead_zone_keeps_camera_still():
    random.seed(1)
    c = [0.5 + random.uniform(-0.01, 0.01) for _ in range(50)]
    rf = face.compute_reframe(frames_from(c), 1920, 1080, 10.0, 30)
    assert rf.layout == "track" and len(set(rf.xs)) <= 3


def test_camera_follows_move_smoothly_and_stays_in_bounds():
    c = [0.4] * 10 + [0.6] * 40   # same person shifting 384 px (less than a crop width)
    rf = face.compute_reframe(frames_from(c), 1920, 1080, 10.0, 30)
    assert rf.crop_w == 608 and rf.crop_h == 1080 and len(rf.xs) == 300
    assert all(0 <= x <= 1920 - 608 for x in rf.xs)
    assert max(abs(a - b) for a, b in zip(rf.xs, rf.xs[1:])) <= 15   # smooth pan, no jumps
    final_centre = rf.xs[-1] + 304
    assert abs(final_centre - 0.6 * 1920) < 0.15 * 608              # converged near the face
    # edges stay in bounds even for a face at the very edge
    edge = face.compute_reframe(frames_from([0.02] * 20), 1920, 1080, 4.0, 30)
    assert min(edge.xs) == 0


def test_missing_detections_hold_last_position():
    c = [0.7] * 10 + [None] * 20 + [0.7] * 5
    rf = face.compute_reframe(frames_from(c), 1920, 1080, 7.0, 30)
    assert len(set(rf.xs[60:180])) == 1


def test_low_coverage_falls_back_to_fit():
    rf = face.compute_reframe(frames_from([None] * 40 + [0.5] * 5), 1920, 1080, 9.0, 30)
    assert rf.layout == "fit" and rf.xs == []


def test_merge_boxes_dedupes_overlapping_tiles():
    boxes = [(0.40, 0.2, 0.50, 0.4, 0.0), (0.41, 0.21, 0.49, 0.39, 0.0), (0.8, 0.2, 0.85, 0.3, 0.0)]
    faces = face.merge_boxes(boxes)
    assert len(faces) == 2 and abs(faces[0].w - 0.10) < 1e-9


def test_brief_dropout_does_not_switch_to_other_person():
    """Two people (x=0.27 and x=0.72). The target disappears for 1 s while the other stays visible."""
    a = lambda: Face(0.27, 0.4, 0.1, 0.18, 0.05)
    b = lambda: Face(0.72, 0.4, 0.1, 0.18, 0.0)
    frames = [(i / 5, [a(), b()]) for i in range(10)]
    frames += [(i / 5, [b()]) for i in range(10, 15)]          # 1 s: only the other person detected
    frames += [(i / 5, [a(), b()]) for i in range(15, 25)]
    tr = face.pick_target(frames)
    assert all(t is None or abs(t - 0.27) < 0.01 for t in tr.target)
    rf = face.compute_reframe(frames, 1920, 1080, 5.0, 30)
    assert max(rf.xs) - min(rf.xs) < 40  # camera never travelled to the other person


def test_cutaway_without_faces_does_not_cause_switch():
    """Real Phase 5 trace: target, 2.6 s of graphics (no faces), 1 s with only the other person, then both."""
    a = lambda: Face(0.27, 0.4, 0.1, 0.18, 0.05)
    b = lambda: Face(0.74, 0.4, 0.1, 0.18, 0.0)
    frames = [(i / 5, [a(), b()] if i % 5 == 0 else [a()]) for i in range(18)]
    frames += [(i / 5, []) for i in range(18, 31)]
    frames += [(i / 5, [b()]) for i in range(31, 36)]
    frames += [(i / 5, [a(), b()]) for i in range(36, 50)]
    tr = face.pick_target(frames)
    assert all(t is None or abs(t - 0.27) < 0.01 for t in tr.target)


def test_layout_uses_any_face_not_just_the_followed_one():
    """Followed person visible 30%, someone else visible another 30%: there IS a person to frame."""
    a = Face(0.27, 0.4, 0.1, 0.18, 0.05)
    b = Face(0.74, 0.4, 0.1, 0.18, 0.0)
    frames = [(i / 5, [a]) for i in range(6)] + [(i / 5, [b]) for i in range(6, 9)] + \
             [(i / 5, []) for i in range(9, 14)] + [(i / 5, [b]) for i in range(14, 17)] + [(i / 5, []) for i in range(17, 20)]
    rf = face.compute_reframe(frames, 1920, 1080, 4.0, 30)
    assert rf.layout == "track" and rf.coverage == 0.6


def test_camera_cut_reframes_on_the_exact_cut_frame():
    """Multi-camera podcast: wide shot (speaker at x=0.21) cuts to a close-up (face at x=0.5) at t=3.1 s.
    Without cut awareness the crop held the old spot for ~3 s (showing a lamp)."""
    wide = lambda: Face(0.21, 0.4, 0.05, 0.09, 0.02)
    close = lambda: Face(0.50, 0.4, 0.15, 0.30, 0.02)
    frames = [(i / 5, [wide()]) for i in range(16)] + [(i / 5, [close()]) for i in range(16, 40)]
    rf = face.compute_reframe(frames, 1920, 1080, 8.0, 30, cuts=[3.1])
    centre = lambda k: rf.xs[k] + rf.crop_w / 2
    cut_frame = int(3.1 * 30) + 1
    assert abs(centre(cut_frame - 2) - 0.21 * 1920) < 0.12 * 608   # on the wide-shot speaker until the cut
    assert abs(centre(cut_frame + 1) - 0.50 * 1920) < 0.12 * 608   # on the close-up face right after it
    jumps = [k for k in range(1, len(rf.xs)) if abs(rf.xs[k] - rf.xs[k - 1]) > 100]
    assert len(jumps) == 1 and abs(jumps[0] - cut_frame) <= 1


def test_shot_without_faces_is_centred_and_next_shot_recovers():
    a = lambda: Face(0.25, 0.4, 0.1, 0.18, 0.02)
    frames = [(i / 5, [a()]) for i in range(10)] + [(i / 5, []) for i in range(10, 20)] + \
             [(i / 5, [a()]) for i in range(20, 30)]
    rf = face.compute_reframe(frames, 1920, 1080, 6.0, 30, cuts=[2.0, 4.0])
    assert abs(rf.xs[90] + 304 - 960) < 5          # faceless shot: centred
    assert abs(rf.xs[150] + 304 - 0.25 * 1920) < 80  # back on the speaker in the next shot


def test_detect_cuts_on_real_video(tmp_path):
    from app.services.face import detect_cuts
    from tests.test_upload import make_video
    a = make_video(tmp_path / "a.mp4", 2, color="red")
    b = make_video(tmp_path / "b.mp4", 2, color="blue")
    lst = tmp_path / "l.txt"
    lst.write_text(f"file '{a.as_posix()}'\nfile '{b.as_posix()}'\n")
    out = tmp_path / "cut.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)],
                   check=True)
    cuts = detect_cuts(out, 0, 4)
    assert len(cuts) == 1 and abs(cuts[0] - 2.0) < 0.1


def test_switches_after_target_gone_for_long():
    a = Face(0.27, 0.4, 0.1, 0.18, 0.05)
    b = Face(0.72, 0.4, 0.1, 0.18, 0.0)
    frames = [(0.0, [a, b])] + [(i / 5, [b]) for i in range(1, 20)]
    tr = face.pick_target(frames)
    assert tr.target[0] == 0.27 and tr.target[-1] == 0.72 and tr.target[5] is None


def test_switching_person_is_a_cut_not_a_pan():
    a = Face(0.27, 0.4, 0.1, 0.18, 0.05)
    b = Face(0.72, 0.4, 0.1, 0.18, 0.0)
    frames = [(i / 5, [a, b]) for i in range(10)] + [(i / 5, [b]) for i in range(10, 40)]
    rf = face.compute_reframe(frames, 1920, 1080, 8.0, 30)
    steps = sorted(abs(p - q) for p, q in zip(rf.xs, rf.xs[1:]))
    assert steps[-1] > 600                 # one hard cut across to the other person...
    assert steps[-2] <= 20                 # ...and no slow sweep across the room


def test_target_prefers_large_speaking_face_then_sticks():
    big = Face(0.3, 0.4, 0.12, 0.2, 0.05)
    small = Face(0.8, 0.4, 0.05, 0.08, 0.0)
    tr = face.pick_target([(0.0, [small, big]), (0.2, [Face(0.32, 0.4, 0.12, 0.2, 0.0), small])])
    assert tr.target == [0.3, 0.32]
