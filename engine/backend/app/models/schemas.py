from __future__ import annotations

from pydantic import BaseModel


class VideoInfo(BaseModel):
    duration_seconds: float
    width: int
    height: int
    fps: float
    video_codec: str
    has_audio: bool
    container: str


class UploadOut(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    created_at: float
    duplicate: bool = False
    video: VideoInfo


class ComponentStatus(BaseModel):
    ok: bool
    detail: str


class GpuInfo(BaseModel):
    name: str
    vram_total_mb: int
    vram_free_mb: int


class SystemOut(BaseModel):
    gpu: GpuInfo | None
    components: dict[str, ComponentStatus]
    ready_for_processing: bool
    limits: dict[str, float]


class ProcessIn(BaseModel):
    upload_id: str
    force: bool = False  # regenerate even if a completed job exists


class StageOut(BaseModel):
    key: str
    label: str
    state: str  # waiting | active | done | skipped | failed


class JobOut(BaseModel):
    job_id: str
    upload: UploadOut
    status: str
    progress: float
    stage_progress: float
    stages: list[StageOut]
    live_text: str
    error_code: str | None
    error_message: str | None
    attempts: int
    clip_count: int
    created_at: float
    updated_at: float


class ClipOut(BaseModel):
    clip_id: str
    job_id: str
    index: int
    title: str
    hook: str
    reason: str
    editorial_score: int
    start_time: float
    end_time: float
    duration: float
    transcript: str
    source: str
    layout: str            # track | native | fit | original
    caption_style: str | None
    face_coverage: float   # share of sampled frames with a tracked face
    status: str            # ready | queued | rendering | failed
    version: int
    error_message: str | None
    video_url: str
    thumbnail_url: str
    download_url: str


class FetchIn(BaseModel):
    url: str
    confirm_rights: bool = False  # must be True: "I own this video or have permission to use it"


class FetchOut(BaseModel):
    fetch_id: str
    url: str
    status: str            # queued | downloading | completed | failed
    progress: float
    title: str | None
    upload: UploadOut | None
    error_code: str | None
    error_message: str | None


class ClipEditIn(BaseModel):
    start_time: float
    end_time: float
    style: dict = {}                      # CaptionStyle fields; "preset" picks the base
    word_edits: dict[str, str] = {}       # transcript word index -> corrected text ("" hides it)


class EditorWord(BaseModel):
    i: int              # index in the transcript (stable key for edits)
    start: float        # source-video seconds
    end: float
    text: str           # what the caption shows now (after script + edits)
    default: str        # text without any user edit (after script conversion)
    original: str       # what Whisper heard
    edited: bool


class FontOut(BaseModel):
    family: str
    category: str
    devanagari: bool
    has_bold: bool
    regular_url: str
    bold_url: str | None


class EditorOut(BaseModel):
    clip: ClipOut
    source: dict        # upload_id, video_url, duration, width, height, fps
    words: list[EditorWord]
    style: dict
    presets: dict[str, dict]
    fonts: list[FontOut]
    reframe: dict       # layout, crop_w, crop_h, samples [[t, x]] relative to clip start
    limits: dict


class ErrorOut(BaseModel):
    code: str
    message: str
