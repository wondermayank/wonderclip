export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type VideoInfo = {
  duration_seconds: number;
  width: number;
  height: number;
  fps: number;
  video_codec: string;
  has_audio: boolean;
  container: string;
};

export type UploadResult = {
  upload_id: string;
  filename: string;
  size_bytes: number;
  created_at: number;
  duplicate: boolean;
  video: VideoInfo;
};

export type ComponentStatus = { ok: boolean; detail: string };

export type SystemStatus = {
  gpu: { name: string; vram_total_mb: number; vram_free_mb: number } | null;
  components: Record<string, ComponentStatus>;
  ready_for_processing: boolean;
  limits: { max_duration_seconds: number; max_upload_mb: number };
};

export class ApiError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

export type FetchResult = {
  fetch_id: string;
  url: string;
  status: "queued" | "downloading" | "completed" | "failed";
  progress: number;
  title: string | null;
  upload: UploadResult | null;
  error_code: string | null;
  error_message: string | null;
};

export const startFetch = (url: string) =>
  fetch(`${API_URL}/api/fetch`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url, confirm_rights: true }),
  }).then(async (r) => {
    const body = await r.json().catch(() => null);
    if (!r.ok) throw new ApiError(body?.code ?? "error", body?.message ?? "Couldn't fetch this link.");
    return body as FetchResult;
  });

export const getFetch = (id: string) =>
  fetch(`${API_URL}/api/fetch/${id}`, { cache: "no-store" }).then(async (r) => {
    const body = await r.json().catch(() => null);
    if (!r.ok) throw new ApiError(body?.code ?? "error", body?.message ?? "Couldn't check the download.");
    return body as FetchResult;
  });

export async function getSystem(signal?: AbortSignal): Promise<SystemStatus> {
  const r = await fetch(`${API_URL}/api/system`, { signal, cache: "no-store" });
  if (!r.ok) throw new ApiError("system_error", "Could not read system status.");
  return r.json();
}

export const thumbnailUrl = (id: string) => `${API_URL}/api/uploads/${id}/thumbnail`;

/** XHR (not fetch) so we get real upload progress events. */
export function uploadVideo(
  file: File,
  onProgress: (fraction: number) => void,
): { promise: Promise<UploadResult>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<UploadResult>((resolve, reject) => {
    xhr.open("POST", `${API_URL}/api/upload`);
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      const body = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as UploadResult);
      else reject(new ApiError(body?.code ?? "upload_failed", body?.message ?? "Upload failed."));
    };
    xhr.onerror = () =>
      reject(new ApiError("network", "Can't reach the Wonder Clips server. Is the backend running?"));
    xhr.onabort = () => reject(new ApiError("aborted", "Upload cancelled."));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}

// ------------------------------------------------------------------ jobs & clips

export type StageState = "waiting" | "active" | "done" | "skipped" | "failed";
export type Stage = { key: string; label: string; state: StageState };

export type Job = {
  job_id: string;
  upload: UploadResult;
  status: string; // queued | <stage key> | completed | failed | cancelled
  progress: number;
  stage_progress: number;
  stages: Stage[];
  live_text: string;
  error_code: string | null;
  error_message: string | null;
  attempts: number;
  clip_count: number;
  created_at: number;
  updated_at: number;
};

export type Clip = {
  clip_id: string;
  job_id: string;
  index: number;
  title: string;
  hook: string;
  reason: string;
  editorial_score: number;
  start_time: number;
  end_time: number;
  duration: number;
  transcript: string;
  source: "ai" | "fallback";
  layout: "track" | "native" | "fit" | "original";
  caption_style: string | null;
  face_coverage: number;
  status: "ready" | "queued" | "rendering" | "failed";
  version: number;
  error_message: string | null;
  video_url: string;
  thumbnail_url: string;
  download_url: string;
};

export const isActive = (status: string) =>
  !["completed", "failed", "cancelled"].includes(status);

export const mediaUrl = (path: string) => `${API_URL}${path}`;

async function json<T>(r: Response): Promise<T> {
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new ApiError(body?.code ?? "error", body?.message ?? "Request failed.");
  return body as T;
}

export const startProcessing = (upload_id: string, force = false) =>
  fetch(`${API_URL}/api/process`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ upload_id, force }),
  }).then(json<Job>);

export const getJob = (id: string, signal?: AbortSignal) =>
  fetch(`${API_URL}/api/jobs/${id}`, { cache: "no-store", signal }).then(json<Job>);

export const listJobs = () => fetch(`${API_URL}/api/jobs`, { cache: "no-store" }).then(json<Job[]>);

export const cancelJob = (id: string) =>
  fetch(`${API_URL}/api/jobs/${id}/cancel`, { method: "POST" }).then(json<Job>);

export const getClips = (id: string) =>
  fetch(`${API_URL}/api/jobs/${id}/clips`, { cache: "no-store" }).then(json<Clip[]>);

// ------------------------------------------------------------------ editor

export type CaptionStyle = {
  preset: string;
  animation: "highlight" | "karaoke" | "none";
  font: string;
  bold: boolean;
  size: number;
  uppercase: boolean;
  text_color: string;
  highlight_color: string;
  outline_color: string;
  outline: number;
  shadow: number;
  box: boolean;
  box_color: string;
  box_opacity: number;
  position: "lower" | "middle" | "upper";
  max_words: number;
  max_chars: number;
  highlight_scale: number;
};

export type EditorWord = {
  i: number; start: number; end: number; text: string; default: string; original: string; edited: boolean;
};
export type FontInfo = {
  family: string; category: string; devanagari: boolean; has_bold: boolean; regular_url: string; bold_url: string | null;
};
export type EditorData = {
  clip: Clip;
  source: { upload_id: string; video_url: string; duration: number; width: number; height: number; fps: number };
  words: EditorWord[];
  style: CaptionStyle;
  presets: Record<string, CaptionStyle>;
  fonts: FontInfo[];
  reframe: { layout: Clip["layout"]; crop_w?: number; crop_h?: number; samples: [number, number][]; src_w: number; src_h: number };
  limits: { min_duration: number; max_duration: number; output_width: number; output_height: number };
};

export const getEditor = (clipId: string) =>
  fetch(`${API_URL}/api/clips/${clipId}/editor`, { cache: "no-store" }).then(json<EditorData>);

export const getClip = (clipId: string) =>
  fetch(`${API_URL}/api/clips/${clipId}`, { cache: "no-store" }).then(json<Clip>);

export const saveClip = (
  clipId: string,
  body: { start_time: number; end_time: number; style: CaptionStyle; word_edits: Record<string, string> },
) =>
  fetch(`${API_URL}/api/clips/${clipId}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then(json<Clip>);

export const exportZipUrl = (jobId: string) => `${API_URL}/api/jobs/${jobId}/export.zip`;

export function formatTimecode(sec: number): string {
  const m = Math.floor(sec / 60);
  return `${m}:${(sec % 60).toFixed(1).padStart(4, "0")}`;
}

export function formatBytes(n: number): string {
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function formatDuration(sec: number): string {
  const s = Math.round(sec);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}
