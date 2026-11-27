from __future__ import annotations

import json
import re
import unicodedata
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from app.config import get_settings
from app.models.db import ACTIVE
from app.models.schemas import (ClipEditIn, ClipOut, EditorOut, EditorWord, ErrorOut, FetchIn, FetchOut, FontOut,
                                JobOut, ProcessIn, StageOut, SystemOut, UploadOut)
from app.services import captions, fonts
from app.services import fetch as fetch_svc
from app.services.highlights import MIN_WORD_PROB
from app.services.media import MediaError, make_thumbnail
from app.services.system import system_status
from app.services.translit import romanize
from app.services.uploads import ingest_upload, to_out, upload_path
from app.workers.pipeline import clip_file, job_dir, stage_states

router = APIRouter(prefix="/api")
_ID = re.compile(r"^[0-9a-f]{32}$")


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=ErrorOut(code=code, message=message).model_dump())


def _not_found(what: str) -> JSONResponse:
    return error(404, "not_found", f"{what} not found.")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/system", response_model=SystemOut)
async def system() -> SystemOut:
    return await run_in_threadpool(system_status)


# ------------------------------------------------------------------ uploads

@router.post("/upload", response_model=UploadOut, responses={400: {"model": ErrorOut}})
async def upload(request: Request, file: UploadFile = File(...)):
    try:
        return await ingest_upload(file, request.app.state.db)
    except MediaError as e:
        status = 413 if e.code in ("file_too_large", "too_long") else 400
        return error(status, e.code, e.message)


def _fetch_out(request: Request, f: dict) -> FetchOut:
    up = _upload_rec(request, f["upload_id"]) if f["upload_id"] else None
    return FetchOut(fetch_id=f["id"], url=f["url"], status=f["status"], progress=f["progress"], title=f["title"],
                    upload=to_out(up) if up else None, error_code=f["error_code"], error_message=f["error_message"])


@router.post("/fetch", response_model=FetchOut, responses={400: {"model": ErrorOut}})
def fetch_link(body: FetchIn, request: Request):
    """Fetch a video from a link. The user must confirm they own it or have permission."""
    if not body.confirm_rights:
        return error(400, "rights_not_confirmed",
                     "Please confirm you own this video or have permission to use it.")
    try:
        url = fetch_svc.validate_url(body.url)
    except fetch_svc.FetchError as e:
        return error(400, e.code, e.message)
    db, fw = request.app.state.db, request.app.state.fetcher
    fid = fetch_svc.new_fetch_id()
    db.create_fetch(fid, url)
    if fw:
        fw.submit(fid)
    return _fetch_out(request, db.get_fetch(fid))


@router.get("/fetch/{fetch_id}", response_model=FetchOut, responses={404: {"model": ErrorOut}})
def get_fetch(fetch_id: str, request: Request):
    f = request.app.state.db.get_fetch(fetch_id) if _ID.match(fetch_id) else None
    return _fetch_out(request, f) if f else _not_found("Fetch")


def _upload_rec(request: Request, upload_id: str) -> dict | None:
    rec = request.app.state.db.get_upload(upload_id) if _ID.match(upload_id) else None
    return rec if rec and upload_path(rec["id"], rec["ext"]).exists() else None


@router.get("/uploads/{upload_id}", response_model=UploadOut, responses={404: {"model": ErrorOut}})
def get_upload(upload_id: str, request: Request):
    rec = _upload_rec(request, upload_id)
    return to_out(rec) if rec else _not_found("Upload")


@router.get("/uploads/{upload_id}/thumbnail", responses={404: {"model": ErrorOut}})
async def upload_thumbnail(upload_id: str, request: Request):
    rec = _upload_rec(request, upload_id)
    if not rec:
        return _not_found("Upload")
    thumb = get_settings().temp_dir / f"{upload_id}_thumb.jpg"
    if not thumb.exists():
        try:
            at = min(rec["video"]["duration_seconds"] * 0.1, 10.0)
            await run_in_threadpool(make_thumbnail, upload_path(rec["id"], rec["ext"]), thumb, at)
        except MediaError as e:
            return error(500, e.code, e.message)
    return FileResponse(thumb, media_type="image/jpeg")


# ------------------------------------------------------------------ jobs

def _job_out(request: Request, job: dict) -> JobOut:
    db = request.app.state.db
    up = db.get_upload(job["upload_id"])
    return JobOut(
        job_id=job["id"], upload=to_out(up), status=job["status"], progress=job["progress"],
        stage_progress=job["stage_progress"],
        stages=[StageOut(**s) for s in stage_states(job["status"], job["failed_stage"])],
        live_text=job["live_text"], error_code=job["error_code"], error_message=job["error_message"],
        attempts=job["attempts"], clip_count=len(db.list_clips(job["id"])),
        created_at=job["created_at"], updated_at=job["updated_at"],
    )


@router.post("/process", response_model=JobOut, responses={404: {"model": ErrorOut}})
def process(body: ProcessIn, request: Request):
    """Start processing. Idempotent: one job per upload.

    - running/queued job  -> returned as-is (no duplicate work)
    - failed/cancelled    -> retried
    - completed           -> returned, unless force=True (regenerate clips)
    """
    db, worker = request.app.state.db, request.app.state.worker
    if not _upload_rec(request, body.upload_id):
        return _not_found("Upload")
    job = db.get_job_by_upload(body.upload_id)
    if job is None:
        job_id = uuid.uuid4().hex
        db.create_job(job_id, body.upload_id)
    elif job["status"] in ACTIVE or (job["status"] == "completed" and not body.force):
        return _job_out(request, job)
    elif any(c["status"] in ("queued", "rendering") for c in db.list_clips(job["id"])):
        return error(409, "clip_busy", "A clip is still rendering. Try again when it's done.")
    else:
        job_id = job["id"]
        db.reset_job(job_id)
    if worker:
        worker.submit(job_id)
    return _job_out(request, db.get_job(job_id))


def _job(request: Request, job_id: str) -> dict | None:
    return request.app.state.db.get_job(job_id) if _ID.match(job_id) else None


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(request: Request):
    db = request.app.state.db
    return [_job_out(request, j) for j in db.list_jobs() if db.get_upload(j["upload_id"])]


@router.get("/jobs/{job_id}", response_model=JobOut, responses={404: {"model": ErrorOut}})
def get_job(job_id: str, request: Request):
    job = _job(request, job_id)
    return _job_out(request, job) if job else _not_found("Job")


@router.post("/jobs/{job_id}/cancel", response_model=JobOut, responses={404: {"model": ErrorOut}})
def cancel_job(job_id: str, request: Request):
    db = request.app.state.db
    job = _job(request, job_id)
    if not job:
        return _not_found("Job")
    if job["status"] == "queued":
        db.update_job(job_id, status="cancelled", error_code="cancelled",
                      error_message="Processing was cancelled.")
    elif job["status"] in ACTIVE:
        db.update_job(job_id, cancel=1)  # the worker stops at the next checkpoint
    return _job_out(request, db.get_job(job_id))


# ------------------------------------------------------------------ clips

def _clip_out(c: dict) -> ClipOut:
    base = f"/api/clips/{c['id']}"
    v = f"?v={c['version']}"  # cache-busting: the file is replaced in place after an edit
    return ClipOut(
        clip_id=c["id"], job_id=c["job_id"], index=c["idx"], title=c["title"], hook=c["hook"],
        reason=c["reason"], editorial_score=c["editorial_score"], start_time=c["start_time"],
        end_time=c["end_time"], duration=c["duration"], transcript=c["transcript"], source=c["source"],
        layout=c["layout"], caption_style=c["caption_style"], face_coverage=c["face_coverage"],
        status=c["status"], version=c["version"], error_message=c["error_message"],
        video_url=f"{base}/video{v}", thumbnail_url=f"{base}/thumbnail{v}", download_url=f"{base}/download",
    )


@router.get("/jobs/{job_id}/clips", response_model=list[ClipOut], responses={404: {"model": ErrorOut}})
def job_clips(job_id: str, request: Request):
    job = _job(request, job_id)
    if not job:
        return _not_found("Job")
    if job["status"] != "completed":
        return []
    return [_clip_out(c) for c in request.app.state.db.list_clips(job_id)
            if clip_file(job_id, c["idx"]).exists()]


def _clip(request: Request, clip_id: str) -> dict | None:
    c = request.app.state.db.get_clip(clip_id) if _ID.match(clip_id) else None
    return c if c and clip_file(c["job_id"], c["idx"]).exists() else None


@router.get("/clips/{clip_id}", response_model=ClipOut, responses={404: {"model": ErrorOut}})
def get_clip(clip_id: str, request: Request):
    c = _clip(request, clip_id)
    return _clip_out(c) if c else _not_found("Clip")


@router.get("/clips/{clip_id}/video", responses={404: {"model": ErrorOut}})
def clip_video(clip_id: str, request: Request):
    c = _clip(request, clip_id)
    if not c:
        return _not_found("Clip")
    return FileResponse(clip_file(c["job_id"], c["idx"]), media_type="video/mp4")


@router.get("/clips/{clip_id}/thumbnail", responses={404: {"model": ErrorOut}})
def clip_thumbnail(clip_id: str, request: Request):
    c = _clip(request, clip_id)
    p = clip_file(c["job_id"], c["idx"], "jpg") if c else None
    if not p or not p.exists():
        return _not_found("Thumbnail")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/clips/{clip_id}/download", responses={404: {"model": ErrorOut}})
def clip_download(clip_id: str, request: Request):
    c = _clip(request, clip_id)
    if not c:
        return _not_found("Clip")
    return FileResponse(clip_file(c["job_id"], c["idx"]), media_type="video/mp4", filename=_clip_filename(c))


def _clip_filename(c: dict) -> str:
    # Keep letters, digits and combining marks (Devanagari vowel signs) so Hindi titles survive.
    slug = "".join(ch if ch.isalnum() or unicodedata.category(ch)[0] == "M" else "-" for ch in c["title"].lower())
    slug = re.sub(r"-+", "-", slug).strip("-")[:50] or "clip"
    return f"clipmitra-{c['idx'] + 1}-{slug}.mp4"


# ------------------------------------------------------------------ editor

MIN_CLIP, MAX_CLIP = 3.0, 90.0


def _editor_words(transcript: dict, edits: dict[str, str]) -> list[EditorWord]:
    roman = get_settings().caption_script == "roman"
    out = []
    for i, w in enumerate(transcript["words"]):
        if w.get("prob", 1.0) < MIN_WORD_PROB:
            continue
        default = romanize(w["text"]) if roman else w["text"]
        key = str(i)
        out.append(EditorWord(i=i, start=w["start"], end=w["end"], text=edits.get(key, default),
                              default=default, original=w["text"], edited=key in edits))
    return out


@router.get("/clips/{clip_id}/editor", response_model=EditorOut, responses={404: {"model": ErrorOut}})
def clip_editor(clip_id: str, request: Request):
    db = request.app.state.db
    c = _clip(request, clip_id)
    if not c:
        return _not_found("Clip")
    job = db.get_job(c["job_id"])
    up = db.get_upload(job["upload_id"]) if job else None
    tjson = job_dir(c["job_id"]) / "transcript.json"
    if not up or not upload_path(up["id"], up["ext"]).exists() or not tjson.exists():
        return error(410, "source_missing", "The original video for this clip is no longer available.")
    transcript = json.loads(tjson.read_text("utf-8"))
    saved = json.loads(c["style_json"] or "{}")
    style = captions.get_style(saved.get("preset") or c["caption_style"], saved)
    rpath = clip_file(c["job_id"], c["idx"], "reframe.json")
    reframe = json.loads(rpath.read_text("utf-8")) if rpath.exists() else {"layout": c["layout"], "samples": []}
    v = up["video"]
    return EditorOut(
        clip=_clip_out(c),
        source={"upload_id": up["id"], "video_url": f"/api/uploads/{up['id']}/video",
                "duration": v["duration_seconds"], "width": v["width"], "height": v["height"], "fps": v["fps"]},
        words=_editor_words(transcript, json.loads(c["word_edits_json"] or "{}")),
        style=asdict(style),
        presets={k: asdict(p) for k, p in captions.PRESETS.items()},
        fonts=[FontOut(family=f.family, category=f.category, devanagari=f.devanagari, has_bold=bool(f.bold),
                       regular_url=f"/api/fonts/{f.regular}", bold_url=f"/api/fonts/{f.bold}" if f.bold else None)
               for f in fonts.available()],
        reframe={**reframe, "src_w": v["width"], "src_h": v["height"]},
        limits={"min_duration": MIN_CLIP, "max_duration": MAX_CLIP, "output_width": get_settings().output_width,
                "output_height": get_settings().output_height},
    )


@router.put("/clips/{clip_id}", response_model=ClipOut,
            responses={400: {"model": ErrorOut}, 404: {"model": ErrorOut}, 409: {"model": ErrorOut}})
def edit_clip(clip_id: str, body: ClipEditIn, request: Request):
    """Save trim / caption style / word corrections and queue a re-render of this clip."""
    db, worker = request.app.state.db, request.app.state.worker
    c = _clip(request, clip_id)
    if not c:
        return _not_found("Clip")
    job = db.get_job(c["job_id"])
    if not job or job["status"] != "completed":
        return error(409, "job_busy", "This video is still being processed.")
    if c["status"] in ("queued", "rendering"):
        return error(409, "clip_busy", "This clip is already being rendered. Please wait.")
    up = db.get_upload(job["upload_id"])
    total = up["video"]["duration_seconds"] if up else 0.0
    start, end = round(body.start_time, 3), round(body.end_time, 3)
    if not (0 <= start < end <= total + 0.01):
        return error(400, "bad_range", "Start and end must be inside the video.")
    if not MIN_CLIP <= end - start <= MAX_CLIP:
        return error(400, "bad_length", f"Clips must be {MIN_CLIP:g}–{MAX_CLIP:g} seconds long.")
    try:
        style = captions.get_style(body.style.get("preset"), body.style)
    except captions.StyleError as e:
        return error(400, "bad_style", str(e))
    tjson = job_dir(c["job_id"]) / "transcript.json"
    n_words = len(json.loads(tjson.read_text("utf-8"))["words"]) if tjson.exists() else 0
    edits: dict[str, str] = {}
    for k, t in body.word_edits.items():
        if not k.isdigit() or int(k) >= n_words or not isinstance(t, str) or len(t) > 60:
            return error(400, "bad_word_edit", "A corrected word is invalid (max 60 characters).")
        edits[k] = re.sub(r"\s+", " ", t).strip()
    db.update_clip(clip_id, start_time=start, end_time=end, style_json=json.dumps(asdict(style)),
                   word_edits_json=json.dumps(edits, ensure_ascii=False), status="queued", error_message=None)
    if worker:
        worker.submit_clip(clip_id)
    return _clip_out(db.get_clip(clip_id))


@router.get("/uploads/{upload_id}/video", responses={404: {"model": ErrorOut}})
def upload_video(upload_id: str, request: Request):
    """Original video for the editor's live preview (range requests supported)."""
    rec = _upload_rec(request, upload_id)
    if not rec:
        return _not_found("Upload")
    return FileResponse(upload_path(rec["id"], rec["ext"]),
                        media_type="video/quicktime" if rec["ext"] == ".mov" else "video/mp4")


@router.get("/fonts/{name}", responses={404: {"model": ErrorOut}})
def font_file(name: str):
    if name not in fonts.font_files():  # whitelist: no path traversal possible
        return _not_found("Font")
    p = Path(get_settings().fonts_dir) / name
    if not p.exists():
        return _not_found("Font")
    return FileResponse(p, media_type="font/ttf", headers={"Cache-Control": "public, max-age=604800"})


# ------------------------------------------------------------------ export

@router.get("/jobs/{job_id}/export.zip", responses={404: {"model": ErrorOut}})
def export_zip(job_id: str, request: Request):
    db = request.app.state.db
    job = _job(request, job_id)
    if not job or job["status"] != "completed":
        return _not_found("Job")
    clips = [c for c in db.list_clips(job_id) if c["status"] != "failed" and clip_file(job_id, c["idx"]).exists()]
    if not clips:
        return _not_found("Clips")
    tmp = get_settings().temp_dir / f"export_{job_id}_{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as z:  # MP4 is already compressed
        for c in clips:
            z.write(clip_file(job_id, c["idx"]), arcname=_clip_filename(c))
    up = db.get_upload(job["upload_id"])
    base = re.sub(r"[^\w\-]+", "-", Path(up["filename"]).stem if up else "clips").strip("-")[:40] or "clips"
    return FileResponse(tmp, media_type="application/zip", filename=f"{base}-clipmitra.zip",
                        background=BackgroundTask(tmp.unlink, missing_ok=True))
