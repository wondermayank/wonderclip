"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertIcon, ArrowLeftIcon, CheckIcon, DownloadIcon, Spinner } from "@/components/icons";
import { exportZipUrl, getClips, getJob, mediaUrl, type Clip, type Job } from "@/lib/api";

export default function ExportView() {
  const id = useSearchParams().get("id") ?? "";
  const [job, setJob] = useState<Job | null>(null);
  const [clips, setClips] = useState<Clip[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getJob(id), getClips(id)])
      .then(([j, c]) => { setJob(j); setClips(c); })
      .catch(() => setError("Couldn't load this project."));
  }, [id]);

  const busy = clips?.some((c) => c.status === "queued" || c.status === "rendering");

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-8 lg:px-10">
      <nav className="mb-6 flex items-center gap-2 text-sm font-medium text-zinc-500">
        <Link href={`/job?id=${id}`} className="inline-flex items-center gap-1.5 hover:text-violet-700">
          <ArrowLeftIcon width={16} height={16} /> Your clips
        </Link>
        <span>›</span><span className="text-zinc-800">Export</span>
      </nav>
      <h1 className="text-3xl font-bold tracking-tight">Export</h1>
      {error && <p className="mt-6 flex items-center gap-2 text-rose-700"><AlertIcon /> {error}</p>}
      {!clips || !job ? (
        !error && <div className="mt-8 flex items-center gap-3 text-zinc-500"><Spinner /> Loading…</div>
      ) : (
        <>
          <p className="mt-2 text-zinc-500">
            {clips.length} vertical clips from <span className="font-medium text-zinc-700">{job.upload.filename}</span> ·
            MP4 (H.264 + AAC) · 1080×1920 · ready for Reels, Shorts and TikTok.
          </p>

          <div className="mt-6 flex items-center gap-4 rounded-2xl border border-violet-100 bg-violet-50/60 p-5">
            <div className="flex-1">
              <div className="font-semibold">Download all clips</div>
              <div className="text-sm text-zinc-500">One ZIP with every clip, named by number and title.</div>
            </div>
            <a href={busy ? undefined : exportZipUrl(id)} aria-disabled={busy}
               className={`inline-flex items-center gap-2 rounded-xl bg-violet-600 px-5 py-2.5 font-semibold text-white hover:bg-violet-700 ${busy ? "pointer-events-none opacity-50" : ""}`}>
              <DownloadIcon width={18} height={18} /> Download ZIP
            </a>
          </div>
          {busy && <p className="mt-2 text-sm text-violet-700">A clip is still rendering — the ZIP will be ready when it finishes.</p>}

          <ul className="mt-6 divide-y divide-zinc-100 rounded-2xl border border-zinc-100 bg-white shadow-sm">
            {clips.map((c) => (
              <li key={c.clip_id} className="flex items-center gap-4 p-4">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={mediaUrl(c.thumbnail_url)} alt="" className="h-20 w-[45px] rounded-md bg-zinc-100 object-cover" />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold">{c.index + 1}. {c.title}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-sm text-zinc-500">
                    {Math.round(c.duration)}s
                    {c.version > 1 && <span className="inline-flex items-center gap-1 text-emerald-700"><CheckIcon width={14} height={14} /> edited</span>}
                    {c.status !== "ready" && <span className="text-violet-700">{c.status}</span>}
                  </div>
                </div>
                <Link href={`/edit?id=${c.clip_id}`} className="rounded-lg px-3 py-2 text-sm font-medium text-violet-700 hover:bg-violet-50">Edit</Link>
                <a href={mediaUrl(c.download_url)} download
                   className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50">
                  <DownloadIcon width={16} height={16} /> MP4
                </a>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-xs text-zinc-400">Files stay on this computer. Uploads and clips are deleted automatically after the retention period (72 h by default).</p>
        </>
      )}
    </div>
  );
}
