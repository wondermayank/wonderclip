"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FolderIcon } from "@/components/icons";
import { formatDuration, isActive, listJobs, thumbnailUrl, type Job } from "@/lib/api";

const STATUS: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-700",
  failed: "bg-rose-50 text-rose-700",
  cancelled: "bg-zinc-100 text-zinc-600",
};

export default function ProjectsPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => { listJobs().then(setJobs).catch(() => setOffline(true)); }, []);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 lg:px-10">
      <h1 className="text-3xl font-bold tracking-tight">My Projects</h1>
      {offline && <p className="mt-6 text-rose-600">Can&apos;t reach the Wonder Clips backend.</p>}
      {jobs && jobs.length === 0 && (
        <div className="mt-8 flex flex-col items-center rounded-3xl border border-dashed border-zinc-200 py-16 text-center">
          <FolderIcon width={40} height={40} className="text-zinc-300" />
          <p className="mt-4 font-medium text-zinc-700">No projects yet</p>
          <p className="mt-1 text-sm text-zinc-500">Processed videos and their clips will show up here.</p>
          <Link href="/" className="mt-5 rounded-xl bg-violet-600 px-5 py-2.5 font-semibold text-white hover:bg-violet-700">
            Create clips
          </Link>
        </div>
      )}
      {jobs && jobs.length > 0 && (
        <ul className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {jobs.map((j) => (
            <li key={j.job_id}>
              <Link href={`/job?id=${j.job_id}`} className="block overflow-hidden rounded-2xl border border-zinc-100 bg-white shadow-sm transition hover:shadow-md">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={thumbnailUrl(j.upload.upload_id)} alt="" className="aspect-video w-full bg-zinc-100 object-cover" />
                <div className="p-4">
                  <div className="truncate font-semibold">{j.upload.filename}</div>
                  <div className="mt-2 flex items-center justify-between text-sm">
                    <span className="text-zinc-500">{formatDuration(j.upload.video.duration_seconds)}</span>
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS[j.status] ?? "bg-violet-50 text-violet-700"}`}>
                      {j.status === "completed" ? `${j.clip_count} clips` : isActive(j.status) ? "Processing" : j.status}
                    </span>
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
