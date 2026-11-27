"""Single-threaded job worker: GPU stages never overlap (6 GB VRAM)."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
import queue
import shutil
import threading
import time
import uuid
from pathlib import Path

from app.config import get_settings
from app.models.db import Database
from app.services import captions, face, highlights, llm, render
from app.services.audio import extract_audio
from app.services.media import probe_video
from app.services.translit import romanize
from app.services.transcribe import Cancelled, PipelineError, transcribe
from app.services.uploads import upload_path

log = logging.getLogger("clipmitra.worker")

# (key, label, weight in overall progress, implemented?)
STAGES: list[tuple[str, str, float, bool]] = [
    ("extracting_audio", "Extracting audio", 0.05, True),
    ("transcribing", "Transcribing audio", 0.40, True),
    ("finding_highlights", "Finding highlights", 0.15, True),
    ("tracking_speakers", "Tracking speakers", 0.15, True),
    ("creating_captions", "Creating captions", 0.02, True),
    ("rendering_clips", "Rendering clips", 0.23, True),
]
_KEYS = [k for k, *_ in STAGES]


def job_dir(job_id: str) -> Path:
    return get_settings().output_dir / job_id


def clip_file(job_id: str, idx: int, ext: str = "mp4") -> Path:
    return job_dir(job_id) / f"clip_{idx + 1}.{ext}"


def stage_states(status: str, failed_stage: str | None = None) -> list[dict]:
    """Derive per-stage UI state from the job status."""
    cur = _KEYS.index(status) if status in _KEYS else None
    out = []
    for i, (key, label, _, implemented) in enumerate(STAGES):
        if not implemented:
            state = "skipped"
        elif status == "completed":
            state = "done"
        elif cur is not None:
            state = "done" if i < cur else "active" if i == cur else "waiting"
        elif status in ("failed", "cancelled") and failed_stage:
            fi = _KEYS.index(failed_stage) if failed_stage in _KEYS else -1
            state = "done" if i < fi else "failed" if i == fi else "waiting"
        else:
            state = "waiting"
        out.append({"key": key, "label": label, "state": state})
    return out


class Worker:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.q: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="clipmitra-worker", daemon=True)
        self._stop = threading.Event()

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        for job in self.db.active_jobs():  # resume after a restart
            self.db.update_job(job["id"], status="queued", stage_progress=0.0)
            self.q.put(job["id"])
        for clip in self.db.pending_clip_renders():
            self.db.update_clip(clip["id"], status="queued")
            self.q.put("clip:" + clip["id"])
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.q.put("")

    def submit(self, job_id: str) -> None:
        self.q.put(job_id)

    def submit_clip(self, clip_id: str) -> None:
        """Re-render one edited clip. Shares the queue so GPU/CPU-heavy work never overlaps."""
        self.q.put("clip:" + clip_id)

    def _loop(self) -> None:
        while not self._stop.is_set():
            item = self.q.get()
            if not item:
                continue
            if item.startswith("clip:"):
                self._render_clip(item[5:])
                continue
            job = self.db.get_job(item)
            if not job or job["status"] != "queued":
                continue
            self._run(item)

    # ------------------------------------------------------------ helpers
    def _cancelled(self, job_id: str) -> bool:
        j = self.db.get_job(job_id)
        return bool(j and j["cancel"])

    def _stage(self, job_id: str, key: str, frac: float = 0.0, live_text: str | None = None) -> None:
        if self._cancelled(job_id):
            raise Cancelled()
        done = 0.0
        for k, _, w, _ in STAGES:
            if k == key:
                done += w * frac
                break
            done += w
        fields = dict(status=key, stage_progress=round(frac, 4), progress=round(min(done, 0.99), 4))
        if live_text is not None:
            fields["live_text"] = live_text[:300]
        self.db.update_job(job_id, **fields)

    # ------------------------------------------------------------ pipeline
    def _run(self, job_id: str) -> None:
        job = self.db.get_job(job_id)
        attempts = job["attempts"] + 1
        self.db.update_job(job_id, attempts=attempts)
        current = "extracting_audio"
        t0 = time.time()
        try:
            up = self.db.get_upload(job["upload_id"])
            src = upload_path(up["id"], up["ext"]) if up else None
            if not src or not src.exists():
                raise PipelineError("upload_missing", "The original video is no longer available. Please upload it again.")
            out = job_dir(job_id)
            out.mkdir(parents=True, exist_ok=True)
            tjson = out / "transcript.json"

            # 1. audio + 2. transcript (cached across retries / regenerations)
            if tjson.exists():
                transcript = json.loads(tjson.read_text("utf-8"))
                self._stage(job_id, "transcribing", 1.0)
            else:
                self._stage(job_id, current)
                wav = get_settings().temp_dir / f"{job_id}.wav"
                try:
                    extract_audio(src, wav)
                except RuntimeError as e:
                    raise PipelineError("audio_failed", "Couldn't read the audio from this video.") from e
                current = "transcribing"
                self._stage(job_id, current)
                llm.unload_all()  # free the GPU before Whisper loads
                try:
                    transcript = transcribe(
                        wav,
                        on_progress=lambda f, text: self._stage(job_id, "transcribing", f, text),
                        should_cancel=lambda: self._cancelled(job_id),
                    )
                finally:
                    wav.unlink(missing_ok=True)
                tjson.write_text(json.dumps(transcript, ensure_ascii=False), "utf-8")
            log.info("job %s transcript: %d words, lang=%s", job_id, len(transcript["words"]), transcript["language"])

            # 3. highlights (higher temperature on regenerate for variety)
            current = "finding_highlights"
            self._stage(job_id, current, live_text="")
            picks = highlights.select_highlights(
                transcript, temperature=0.3 if attempts == 1 else 0.6,
                on_progress=lambda f: self._stage(job_id, "finding_highlights", f))
            if not picks:
                raise PipelineError("no_highlights",
                                    "There isn't enough continuous speech to make a 20-second clip.")
            # 4. speaker tracking -> 9:16 layout per clip (MediaPipe on CPU; GPU is idle here)
            current = "tracking_speakers"
            vid = fresh_video_info(src, up)
            fps = vid["fps"] or 30.0
            reframes = []
            with _Tracker(vid) as tr:
                for i, h in enumerate(picks):
                    self._stage(job_id, current, i / len(picks), live_text=h.title)
                    reframes.append(tr.reframe(src, h.start_time, h.end_time, fps))

            # 5. captions from the real word timestamps
            current = "creating_captions"
            self._stage(job_id, current)
            cfg = get_settings()
            style_name, script = cfg.caption_style, cfg.caption_script
            style = captions.get_style(style_name)
            ass = [captions.build_ass(captions.clip_words(transcript["words"], h.start_time, h.end_time, script),
                                      h.duration, style) for h in picks]
            if script == "roman":  # show the same Hinglish spelling in the app as in the captions
                for h in picks:
                    h.title, h.hook, h.transcript = romanize(h.title), romanize(h.hook), romanize(h.transcript)

            (out / "highlights.json").write_text(json.dumps(
                [{**h.__dict__, "duration": h.duration, "layout": rf.layout, "face_coverage": rf.coverage,
                  "max_faces": rf.max_faces} for h, rf in zip(picks, reframes)],
                ensure_ascii=False, indent=2), "utf-8")

            # 6. render + verify each clip
            current = "rendering_clips"
            for old in out.glob("clip_*"):
                old.unlink()
            for i, (h, rf) in enumerate(zip(picks, reframes)):
                self._stage(job_id, current, i / len(picks), live_text=h.title)
                mp4 = clip_file(job_id, i)
                dur = render.render_clip(src, h.start_time, h.end_time, mp4, rf, fps, ass[i])
                render.clip_thumbnail(mp4, clip_file(job_id, i, "jpg"), dur)
                save_reframe(job_id, i, rf, fps)
                self.db.insert_clip(
                    id=uuid.uuid4().hex, job_id=job_id, idx=i, start_time=h.start_time, end_time=h.end_time,
                    title=h.title, hook=h.hook, reason=h.reason, editorial_score=h.editorial_score,
                    transcript=h.transcript, source=h.source, duration=dur, layout=rf.layout,
                    caption_style=style_name, face_coverage=rf.coverage,
                    style_json=json.dumps(asdict(style)))

            self.db.update_job(job_id, status="completed", progress=1.0, stage_progress=1.0, live_text="",
                               error_code=None, error_message=None)
            log.info("job %s completed: %d clips in %.0fs", job_id, len(picks), time.time() - t0)
        except Cancelled:
            self._fail(job_id, "cancelled", "cancelled", "Processing was cancelled.", current)
        except PipelineError as e:
            log.warning("job %s failed at %s: %s", job_id, current, e.code)
            self._fail(job_id, "failed", e.code, e.message, current)
        except Exception:
            log.exception("job %s crashed at %s", job_id, current)
            self._fail(job_id, "failed", "internal_error", "Something went wrong while processing. Please retry.", current)
        finally:
            llm.unload_all()

    # ------------------------------------------------------------ single-clip re-render (editor)
    def _render_clip(self, clip_id: str) -> None:
        c = self.db.get_clip(clip_id)
        if not c or c["status"] != "queued":
            return
        job = self.db.get_job(c["job_id"])
        up = self.db.get_upload(job["upload_id"]) if job else None
        self.db.update_clip(clip_id, status="rendering", error_message=None)
        i, jid = c["idx"], c["job_id"]
        tmp = job_dir(jid) / f"clip_{i + 1}_edit.mp4"
        try:
            src = upload_path(up["id"], up["ext"]) if up else None
            tjson = job_dir(jid) / "transcript.json"
            if not src or not src.exists() or not tjson.exists():
                raise PipelineError("upload_missing", "The original video is no longer available.")
            transcript = json.loads(tjson.read_text("utf-8"))
            cfg = get_settings()
            words = apply_word_edits(transcript["words"], json.loads(c["word_edits_json"] or "{}"))
            saved = json.loads(c["style_json"] or "{}")
            style = captions.get_style(saved.get("preset"), saved)
            start, end = c["start_time"], c["end_time"]
            vid = fresh_video_info(src, up)
            fps = vid["fps"] or 30.0
            with _Tracker(vid) as tr:
                rf = tr.reframe(src, start, end, fps)
            ass = captions.build_ass(captions.clip_words(words, start, end, cfg.caption_script), end - start, style)
            dur = render.render_clip(src, start, end, tmp, rf, fps, ass)
            # Swap in only after verification: a failed edit never destroys the previous clip.
            tmp.replace(clip_file(jid, i))
            ass_tmp = tmp.with_suffix(".ass")
            if ass_tmp.exists():
                ass_tmp.replace(clip_file(jid, i, "ass"))
            render.clip_thumbnail(clip_file(jid, i), clip_file(jid, i, "jpg"), dur)
            save_reframe(jid, i, rf, fps)
            text = " ".join(w.text for w in captions.clip_words(words, start, end, cfg.caption_script))
            self.db.update_clip(clip_id, status="ready", duration=dur, layout=rf.layout, face_coverage=rf.coverage,
                                caption_style=style.preset, style_json=json.dumps(asdict(style)),
                                transcript=text, version=c["version"] + 1, error_message=None)
            log.info("clip %s re-rendered (v%d, %.1fs, %s)", clip_id, c["version"] + 1, dur, rf.layout)
        except PipelineError as e:
            self.db.update_clip(clip_id, status="failed", error_message=e.message)
        except Exception:
            log.exception("clip %s render crashed", clip_id)
            self.db.update_clip(clip_id, status="failed", error_message="Rendering failed. Please try again.")
        finally:
            for p in job_dir(jid).glob(f"clip_{i + 1}_edit.*"):
                p.unlink(missing_ok=True)

    def _fail(self, job_id: str, status: str, code: str, message: str, stage: str) -> None:
        # Remove partial clips so nothing half-finished is ever served.
        self.db.reset_job(job_id)
        for p in job_dir(job_id).glob("clip_*"):
            p.unlink(missing_ok=True)
        self.db.update_job(job_id, status=status, error_code=code, error_message=message,
                           failed_stage=stage)


class _Tracker:
    """Context manager: one FaceTracker for several clips, only when the source needs a moving crop."""

    def __init__(self, video: dict) -> None:
        self.w, self.h = video["width"], video["height"]
        self.ft = None

    def __enter__(self) -> "_Tracker":
        if face.needs_tracking(self.w, self.h):
            try:
                self.ft = face.FaceTracker()
            except Exception:  # model missing/broken: degrade to blurred-background layout
                log.exception("face tracker unavailable; using fit layout")
        return self

    def __exit__(self, *exc) -> None:
        if self.ft:
            self.ft.close()

    def reframe(self, src: Path, start: float, end: float, fps: float) -> face.Reframe:
        if self.ft:
            frames = self.ft.detect(src, start, end, self.w, self.h)
            cuts = face.detect_cuts(src, start, end)  # multi-camera videos: reset framing at each cut
            return face.compute_reframe(frames, self.w, self.h, end - start, fps, cuts)
        return face.Reframe(face.choose_layout(self.w, self.h, 0.0 if face.needs_tracking(self.w, self.h) else 1.0))


def fresh_video_info(src: Path, up: dict) -> dict:
    """Probe the source again instead of trusting metadata stored at upload time
    (keeps old uploads correct when probing improves, e.g. phone rotation handling)."""
    try:
        return probe_video(src, up["ext"]).model_dump()
    except Exception:
        return up["video"]


def save_reframe(job_id: str, idx: int, rf: face.Reframe, fps: float) -> None:
    """Crop path at ~10 samples/s for the editor's live preview (the render uses every frame)."""
    step = max(1, int(round(fps / 10)))
    data = {"layout": rf.layout, "crop_w": rf.crop_w, "crop_h": rf.crop_h,
            "samples": [[round(k / fps, 3), x] for k, x in enumerate(rf.xs) if k % step == 0]}
    clip_file(job_id, idx, "reframe.json").write_text(json.dumps(data), "utf-8")


def apply_word_edits(words: list[dict], edits: dict[str, str]) -> list[dict]:
    """User corrections replace word text only; timing is never changed. Empty text hides a word."""
    if not edits:
        return words
    return [dict(w, text=edits[str(i)]) if str(i) in edits else w for i, w in enumerate(words)]


def sweep_jobs(db: Database) -> int:
    """Retention: delete finished jobs (and their clips/transcripts) older than the window."""
    cutoff = time.time() - get_settings().retention_hours * 3600
    old = db.jobs_older_than(cutoff)
    for j in old:
        shutil.rmtree(job_dir(j["id"]), ignore_errors=True)
        db.delete_job(j["id"])
    return len(old)
