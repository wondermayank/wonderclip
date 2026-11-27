"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ClipCard } from "@/components/ClipCard";
import { StageList } from "@/components/StageList";
import {
  ApiError, cancelJob, formatBytes, formatDuration, getClips, getJob, isActive, startProcessing,
  thumbnailUrl, type Clip, type Job,
} from "@/lib/api";
import { AlertIcon, ArrowLeftIcon, ClockIcon, DownloadIcon, MicIcon, RefreshIcon, Spinner, XIcon } from "@/components/icons";

export default function JobView() {
  const id = useSearchParams().get("id") ?? "";
  const [job, setJob] = useState<Job | null>(null);
  const [clips, setClips] = useState<Clip[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [eta, setEta] = useState<string | null>(null);
  const startedAt = useRef<{ t: number; p: number } | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const j = await getJob(id, signal);
      setJob(j);
      setError(null);
      // Rough ETA from observed speed once a few % of progress exist.
      if (isActive(j.status) && j.progress > 0.04) {
        const s = (startedAt.current ??= { t: Date.now(), p: j.progress });
        if (j.progress > s.p + 0.02) {
          const sec = (1 - j.progress) / ((j.progress - s.p) / ((Date.now() - s.t) / 1000));
          setEta(sec < 60 ? "less than a minute" : `~${Math.ceil(sec / 60)} min`);
        }
      } else if (!isActive(j.status)) {
        setEta(null);
      }
      if (j.status === "completed") setClips(await getClips(id));
      return j;
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return null;
      setError(e instanceof ApiError ? e.message : "Can't reach the Wonder Clips server.");
      return null;
    }
  }, [id]);

  // Poll every second while the job is running.
  useEffect(() => {
    const ctl = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const j = await refresh(ctl.signal);
      if (!j || isActive(j.status)) timer = setTimeout(tick, 1000);
    };
    tick();
    return () => { ctl.abort(); clearTimeout(timer); };
  }, [refresh]);

  const restart = async (force: boolean) => {
    if (!job) return;
    setBusy(true);
    setClips(null);
    setEta(null);
    startedAt.current = null;
    try {
      setJob(await startProcessing(job.upload.upload_id, force));
      // re-arm polling
      const poll = async () => { const j = await refresh(); if (j && isActive(j.status)) setTimeout(poll, 1000); };
      poll();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't restart processing.");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    setBusy(true);
    try { setJob(await cancelJob(id)); } finally { setBusy(false); }
  };

  if (!job) {
    return (
      <Shell title="Processing">
        {error ? <ErrorBox message={error} /> : <div className="flex items-center gap-3 text-zinc-500"><Spinner /> Loading…</div>}
      </Shell>
    );
  }

  const active = isActive(job.status);
  const pct = Math.round(job.progress * 100);
  const up = job.upload;

  return (
    <Shell title={job.status === "completed" ? "Your Clips" : "Processing"}>
      {/* Video header */}
      <section className="flex flex-col gap-6 rounded-3xl border border-zinc-100 bg-white p-5 shadow-sm sm:flex-row sm:items-center">
        <div className="relative w-full shrink-0 overflow-hidden rounded-2xl bg-zinc-100 sm:w-72">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={thumbnailUrl(up.upload_id)} alt="" className="aspect-video w-full object-cover" />
          <span className="absolute bottom-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 text-xs font-semibold text-white">
            {formatDuration(up.video.duration_seconds)}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl font-bold tracking-tight">{up.filename}</h1>
          <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-zinc-500">
            <span>{up.video.container.toUpperCase()}</span>
            <span>{formatBytes(up.size_bytes)}</span>
            <span>{up.video.width}×{up.video.height}</span>
          </p>
        </div>
        {active ? (
          <button onClick={cancel} disabled={busy}
                  className="inline-flex items-center gap-2 self-start rounded-xl border border-zinc-200 px-4 py-2.5 font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 sm:self-center">
            <XIcon width={18} height={18} /> Cancel
          </button>
        ) : job.status === "completed" ? (
          <button onClick={() => restart(true)} disabled={busy}
                  title="Ask the AI for a different set of clips (the transcript is reused)"
                  className="inline-flex items-center gap-2 self-start rounded-xl border border-violet-200 px-4 py-2.5 font-medium text-violet-700 hover:bg-violet-50 disabled:opacity-50 sm:self-center">
            <RefreshIcon width={18} height={18} /> Regenerate
          </button>
        ) : null}
      </section>

      {error && <div className="mt-6"><ErrorBox message={error} /></div>}

      {job.status === "completed" ? (
        <Results clips={clips} jobId={job.job_id} />
      ) : (
        <>
          <h2 className="mt-10 text-2xl font-bold tracking-tight">
            {job.status === "failed" ? "Processing stopped" : job.status === "cancelled" ? "Processing cancelled" : "Processing Your Video"}
          </h2>
          <p className="mt-1 text-zinc-500">
            {active ? "AI is analysing your video, finding the best moments, and creating ready-to-post clips." : ""}
          </p>

          {(job.status === "failed" || job.status === "cancelled") && (
            <div className="mt-5 flex flex-wrap items-center gap-4 rounded-2xl border border-rose-100 bg-rose-50 p-4">
              <AlertIcon className="text-rose-600" />
              <p className="flex-1 font-medium text-rose-800">{job.error_message}</p>
              <button onClick={() => restart(false)} disabled={busy}
                      className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2 font-semibold text-white hover:bg-violet-700 disabled:opacity-50">
                <RefreshIcon width={18} height={18} /> Retry
              </button>
            </div>
          )}

          {active && <div className="mt-6 flex items-center gap-4">
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-violet-100">
              <div className="h-full rounded-full bg-gradient-to-r from-violet-600 to-violet-400 transition-[width] duration-700"
                   style={{ width: `${pct}%` }} />
            </div>
            <span className="w-12 text-right text-xl font-bold tabular-nums">{pct}%</span>
            {eta && (
              <span className="hidden items-center gap-1.5 rounded-full bg-violet-50 px-3 py-1.5 text-sm font-medium text-violet-700 sm:inline-flex">
                <ClockIcon width={16} height={16} /> {eta} remaining
              </span>
            )}
          </div>}

          <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_340px]">
            <StageList job={job} />
            <LivePanel job={job} />
          </div>
        </>
      )}
    </Shell>
  );
}

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-10">
      <nav className="mb-6 flex items-center gap-2 text-sm font-medium text-zinc-500">
        <Link href="/" className="inline-flex items-center gap-1.5 hover:text-violet-700">
          <ArrowLeftIcon width={16} height={16} /> Create Clips
        </Link>
        <span>›</span>
        <span className="text-zinc-800">{title}</span>
      </nav>
      {children}
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div role="alert" className="flex items-center gap-3 rounded-2xl border border-rose-100 bg-rose-50 p-4 font-medium text-rose-800">
      <AlertIcon className="text-rose-600" /> {message}
    </div>
  );
}

function LivePanel({ job }: { job: Job }) {
  const transcribing = job.status === "transcribing";
  const label =
    job.status === "queued" ? "Waiting for the GPU…"
      : job.status === "failed" ? "Stopped — see the message above"
      : job.status === "cancelled" ? "Cancelled"
      : job.stages.find((s) => s.state === "active")?.label ?? "Working…";
  return (
    <aside className="rounded-2xl border border-zinc-100 bg-white p-5 shadow-sm">
      <h3 className="font-semibold">What&apos;s happening now?</h3>
      <div className="my-5 flex h-14 items-center justify-center gap-[3px]" aria-hidden>
        {Array.from({ length: 36 }, (_, i) => (
          <span key={i}
                className={`w-[3px] rounded-full bg-violet-400 ${isActive(job.status) ? "animate-pulse" : ""}`}
                style={{ height: `${20 + 70 * Math.abs(Math.sin(i * 1.7))}%`, animationDelay: `${(i % 6) * 120}ms` }} />
        ))}
      </div>
      {job.live_text ? (
        <blockquote className="rounded-xl bg-violet-50 p-4 text-[15px] leading-relaxed text-zinc-700">
          {transcribing ? `“… ${job.live_text} …”` : job.live_text}
        </blockquote>
      ) : null}
      <div className="mt-4 inline-flex items-center gap-2 rounded-full bg-zinc-50 px-3 py-1.5 text-sm font-medium text-zinc-600">
        {isActive(job.status) ? <Spinner width={16} height={16} /> : null}
        {transcribing ? <><MicIcon width={16} height={16} /> Transcribing speech</> : label}
      </div>
    </aside>
  );
}

function Results({ clips, jobId }: { clips: Clip[] | null; jobId: string }) {
  if (!clips) return <div className="mt-10 flex items-center gap-3 text-zinc-500"><Spinner /> Loading clips…</div>;
  return (
    <>
      <div className="mt-10 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{clips.length} clips ready</h2>
          <p className="mt-1 text-zinc-500">Vertical 9:16 with word-by-word captions. Edit any clip to trim it or restyle captions.</p>
        </div>
        <Link href={`/job/export?id=${jobId}`}
              className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 font-semibold text-white hover:bg-violet-700">
          <DownloadIcon width={18} height={18} /> Export
        </Link>
      </div>
      <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {clips.map((c) => <ClipCard key={c.clip_id} clip={c} />)}
      </div>
    </>
  );
}
