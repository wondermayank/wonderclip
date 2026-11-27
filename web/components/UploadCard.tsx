"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError, formatBytes, formatDuration, getFetch, getSystem, startFetch, startProcessing, thumbnailUrl, uploadVideo,
  type FetchResult, type UploadResult,
} from "@/lib/api";
import { CheckIcon, CloudUpIcon, DownloadIcon, LinkIcon, SparkIcon, UploadIcon, XIcon } from "./icons";

const ACCEPT = [".mp4", ".mov"];
// Defaults until the engine reports its own limits (older engines allow 5 min / 2 GB).
const DEFAULT_LIMITS = { minutes: 30, bytes: 8 * 1024 ** 3 };

/** The limits come from the engine on this computer, so the page always matches the installed version. */
function useEngineLimits() {
  const [limits, setLimits] = useState(DEFAULT_LIMITS);
  useEffect(() => {
    getSystem()
      .then((d) => setLimits({ minutes: Math.round(d.limits.max_duration_seconds / 60), bytes: d.limits.max_upload_mb * 1024 ** 2 }))
      .catch(() => { /* keep defaults; the engine reports errors on upload anyway */ });
  }, []);
  return limits;
}

type State =
  | { kind: "idle"; error?: string }
  | { kind: "uploading"; file: File; duration: number | null; progress: number; abort: () => void }
  | { kind: "verifying"; file: File; duration: number | null }
  | { kind: "done"; result: UploadResult };

/** Read duration locally (before upload) so the user sees it immediately. */
function readDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    v.preload = "metadata";
    const done = (d: number | null) => { URL.revokeObjectURL(url); resolve(d); };
    v.onloadedmetadata = () => done(Number.isFinite(v.duration) ? v.duration : null);
    v.onerror = () => done(null);
    setTimeout(() => done(null), 5000);
    v.src = url;
  });
}

export function UploadCard() {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const limits = useEngineLimits();

  const start = useCallback(async (file: File) => {
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPT.includes(ext)) return setState({ kind: "idle", error: "Only MP4 and MOV videos are supported." });
    if (file.size > limits.bytes)
      return setState({ kind: "idle", error: `File is larger than ${formatBytes(limits.bytes)}.` });

    const duration = await readDuration(file);
    if (duration && duration > limits.minutes * 60 + 1)
      return setState({ kind: "idle", error: `This video is ${formatDuration(duration)} long. The limit is ${limits.minutes} minutes.` });

    const { promise, abort } = uploadVideo(file, (p) =>
      setState((s) =>
        s.kind === "uploading" ? (p >= 1 ? { kind: "verifying", file, duration } : { ...s, progress: p }) : s,
      ),
    );
    setState({ kind: "uploading", file, duration, progress: 0, abort });
    try {
      setState({ kind: "done", result: await promise });
    } catch (e) {
      setState({ kind: "idle", error: e instanceof ApiError ? e.message : "Upload failed." });
    }
  }, [limits]);

  const onFiles = (files: FileList | null) => files?.[0] && start(files[0]);
  const reset = () => { setState({ kind: "idle" }); if (input.current) input.current.value = ""; };

  return (
    <section className="rounded-3xl border border-violet-100 bg-white/80 p-3 shadow-[0_8px_40px_-12px_rgba(124,58,237,0.15)]">
      {state.kind === "done" ? (
        <UploadedFile result={state.result} onReset={reset} />
      ) : (
        <div className="grid items-stretch gap-3 lg:grid-cols-[1fr_auto_1fr]">
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); if (state.kind === "idle") onFiles(e.dataTransfer.files); }}
          onClick={() => state.kind === "idle" && input.current?.click()}
          className={`flex min-h-[300px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
            drag ? "border-violet-500 bg-violet-50" : "border-violet-200 bg-violet-50/30 hover:border-violet-300"
          } ${state.kind !== "idle" ? "cursor-default" : ""}`}
        >
          <input ref={input} type="file" accept=".mp4,.mov,video/mp4,video/quicktime" hidden
                 onChange={(e) => onFiles(e.target.files)} />

          {state.kind === "idle" ? (
            <>
              <CloudUpIcon width={52} height={52} className="text-violet-600" strokeWidth={1.6} />
              <h2 className="mt-4 text-2xl font-bold tracking-tight text-zinc-900">Upload a Video</h2>
              <p className="mt-1.5 text-zinc-500">Drag &amp; drop or click to choose a file</p>
              <button type="button"
                      className="mt-6 inline-flex items-center gap-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-violet-500 px-7 py-3 font-semibold text-white shadow-lg shadow-violet-500/25 transition hover:brightness-110">
                <UploadIcon /> Choose Video
              </button>
              <p className="mt-4 text-sm text-zinc-500">MP4, MOV • Up to {limits.minutes} minutes</p>
              {state.error && (
                <p role="alert" className="mt-4 rounded-lg bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700">{state.error}</p>
              )}
            </>
          ) : (
            <Progress
              file={state.file}
              duration={state.duration}
              progress={state.kind === "uploading" ? state.progress : 1}
              verifying={state.kind === "verifying"}
              onCancel={state.kind === "uploading" ? state.abort : undefined}
            />
          )}
        </div>
        <div className="flex items-center justify-center">
          <span className="grid h-10 w-10 place-items-center rounded-full border border-zinc-200 bg-white text-xs font-semibold text-zinc-500">OR</span>
        </div>
        <LinkPanel disabled={state.kind !== "idle"} onDone={(result) => setState({ kind: "done", result })} />
        </div>
      )}
    </section>
  );
}

type LinkState =
  | { kind: "idle"; error?: string }
  | { kind: "fetching"; fetch: FetchResult };

/** Paste a link (YouTube, Instagram, X, Vimeo, direct file…). The engine downloads it with yt-dlp. */
function LinkPanel({ disabled, onDone }: { disabled: boolean; onDone: (r: UploadResult) => void }) {
  const [url, setUrl] = useState("");
  const [rights, setRights] = useState(false);
  const [st, setSt] = useState<LinkState>({ kind: "idle" });

  const go = async () => {
    try {
      let f = await startFetch(url.trim());
      setSt({ kind: "fetching", fetch: f });
      while (f.status === "queued" || f.status === "downloading") {
        await new Promise((r) => setTimeout(r, 1000));
        f = await getFetch(f.fetch_id);
        setSt({ kind: "fetching", fetch: f });
      }
      if (f.status === "completed" && f.upload) onDone(f.upload);
      else setSt({ kind: "idle", error: f.error_message ?? "Couldn't fetch this video." });
    } catch (e) {
      setSt({ kind: "idle", error: e instanceof ApiError ? e.message : "Couldn't fetch this video." });
    }
  };

  const canGo = !disabled && st.kind === "idle" && rights && /^https?:\/\/\S+\.\S+/.test(url.trim());

  return (
    <div className="flex min-h-[300px] flex-col items-center justify-center rounded-2xl border border-zinc-200 bg-white px-6 py-8 text-center">
      <LinkIcon width={44} height={44} className="text-violet-600" />
      <h2 className="mt-3 flex items-center gap-2 text-2xl font-bold tracking-tight text-zinc-900">
        Paste a Video Link
        <span className="rounded-full bg-violet-600 px-2 py-0.5 text-xs font-semibold text-white">New</span>
      </h2>
      <p className="mt-1.5 text-sm text-zinc-500">YouTube, Instagram, Facebook, X, Vimeo and more</p>

      {st.kind === "fetching" ? (
        <div className="mt-6 w-full max-w-sm text-left">
          <div className="truncate text-sm font-semibold text-zinc-800">{st.fetch.title ?? st.fetch.url}</div>
          <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-violet-100">
            <div className={`h-full rounded-full bg-gradient-to-r from-violet-600 to-violet-400 transition-[width] duration-500 ${st.fetch.status === "queued" ? "animate-pulse" : ""}`}
                 style={{ width: `${Math.max(4, Math.round(st.fetch.progress * 100))}%` }} />
          </div>
          <div className="mt-2 flex justify-between text-sm text-zinc-500">
            <span>{st.fetch.status === "queued" ? "Checking the link…" : st.fetch.progress >= 1 ? "Checking video…" : "Downloading…"}</span>
            <span className="tabular-nums">{Math.round(st.fetch.progress * 100)}%</span>
          </div>
        </div>
      ) : (
        <form className="mt-5 w-full max-w-sm" onSubmit={(e) => { e.preventDefault(); if (canGo) go(); }}>
          <input value={url} onChange={(e) => setUrl(e.target.value)} disabled={disabled} type="url" inputMode="url"
                 placeholder="https://www.youtube.com/watch?v=…" aria-label="Video link"
                 className="w-full rounded-xl border border-zinc-200 px-4 py-3 text-[15px] outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100" />
          <label className="mt-3 flex items-start gap-2 text-left text-xs text-zinc-600">
            <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} className="mt-0.5 accent-violet-600" />
            I own this video or have permission to use it.
          </label>
          <button type="submit" disabled={!canGo}
                  className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-violet-100 px-5 py-3 font-semibold text-violet-800 transition hover:bg-violet-200 disabled:cursor-not-allowed disabled:opacity-50">
            <DownloadIcon width={18} height={18} /> Fetch Video
          </button>
          {st.kind === "idle" && st.error && (
            <p role="alert" className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700">{st.error}</p>
          )}
        </form>
      )}
    </div>
  );
}

function Progress({ file, duration, progress, verifying, onCancel }: {
  file: File; duration: number | null; progress: number; verifying: boolean; onCancel?: () => void;
}) {
  const pct = Math.round(progress * 100);
  return (
    <div className="w-full max-w-md text-left">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="truncate font-semibold text-zinc-900">{file.name}</div>
          <div className="mt-0.5 text-sm text-zinc-500">
            {formatBytes(file.size)}{duration ? ` • ${formatDuration(duration)}` : ""}
          </div>
        </div>
        {onCancel && (
          <button onClick={onCancel} className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700" aria-label="Cancel upload">
            <XIcon />
          </button>
        )}
      </div>
      <div className="mt-5 h-2.5 overflow-hidden rounded-full bg-violet-100">
        <div className={`h-full rounded-full bg-gradient-to-r from-violet-600 to-violet-400 transition-[width] duration-200 ${verifying ? "animate-pulse" : ""}`}
             style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-2.5 flex justify-between text-sm">
        <span className="font-medium text-zinc-600">{verifying ? "Checking video…" : "Uploading…"}</span>
        <span className="tabular-nums text-zinc-500">{pct}%</span>
      </div>
    </div>
  );
}

function UploadedFile({ result, onReset }: { result: UploadResult; onReset: () => void }) {
  const v = result.video;
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generate = async () => {
    setStarting(true);
    setError(null);
    try {
      const job = await startProcessing(result.upload_id);
      router.push(`/job?id=${job.job_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't start processing.");
      setStarting(false);
    }
  };
  return (
    <div className="flex flex-col gap-6 p-4 sm:flex-row sm:items-center">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={thumbnailUrl(result.upload_id)} alt="" className="aspect-video w-full rounded-xl bg-zinc-100 object-cover sm:w-72" />
      <div className="min-w-0 flex-1">
        <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
          <CheckIcon width={14} height={14} /> {result.duplicate ? "Already uploaded" : "Uploaded & verified"}
        </div>
        <h3 className="mt-2 truncate text-xl font-bold text-zinc-900">{result.filename}</h3>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-4">
          {[
            ["Duration", formatDuration(v.duration_seconds)],
            ["Size", formatBytes(result.size_bytes)],
            ["Resolution", `${v.width}×${v.height}`],
            ["Frame rate", `${Math.round(v.fps)} fps`],
          ].map(([k, val]) => (
            <div key={k}><dt className="text-zinc-500">{k}</dt><dd className="font-semibold text-zinc-800">{val}</dd></div>
          ))}
        </dl>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button onClick={generate} disabled={starting}
                  className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-violet-500 px-5 py-2.5 font-semibold text-white shadow-lg shadow-violet-500/25 transition hover:brightness-110 disabled:opacity-60">
            <SparkIcon width={18} height={18} /> {starting ? "Starting…" : "Generate Clips"}
          </button>
          <button onClick={onReset} className="rounded-xl px-4 py-2.5 font-medium text-zinc-600 hover:bg-zinc-100">
            Upload another
          </button>
        </div>
        {error && <p role="alert" className="mt-3 text-sm font-medium text-rose-700">{error}</p>}
      </div>
    </div>
  );
}
