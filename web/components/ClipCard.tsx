import Link from "next/link";
import { formatTimecode, mediaUrl, type Clip } from "@/lib/api";
import { DownloadIcon } from "./icons";

const LAYOUT: Record<Clip["layout"], { label: string; hint: string }> = {
  track: { label: "Speaker tracked", hint: "The 9:16 frame follows the speaker's face." },
  native: { label: "Original vertical", hint: "Your video was already 9:16." },
  fit: { label: "Blurred background", hint: "No steady face found, so the whole frame is shown over a blurred background." },
  original: { label: "Original framing", hint: "Made before vertical reframing existed. Regenerate to update." },
};

export function ClipCard({ clip }: { clip: Clip }) {
  const vertical = clip.layout !== "original";
  const layout = LAYOUT[clip.layout] ?? LAYOUT.original;
  return (
    <article className="flex flex-col overflow-hidden rounded-3xl border border-zinc-100 bg-white shadow-sm">
      <div className="bg-zinc-950">
        <video
          src={mediaUrl(clip.video_url)}
          poster={mediaUrl(clip.thumbnail_url)}
          controls
          preload="none"
          className={`mx-auto w-full object-contain ${vertical ? "aspect-[9/16]" : "aspect-video"}`}
        />
      </div>
      <div className="flex flex-1 flex-col p-4">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-bold leading-snug text-zinc-900">{clip.title}</h3>
          <span title="AI editorial score"
                className="shrink-0 rounded-full bg-violet-100 px-2 py-0.5 text-xs font-bold text-violet-700">
            {clip.editorial_score}/10
          </span>
        </div>
        <p className="mt-1 text-xs text-zinc-500">
          {Math.round(clip.duration)}s · {formatTimecode(clip.start_time)}–{formatTimecode(clip.end_time)}
          {clip.source === "fallback" && " · auto-picked"}
        </p>
        <span title={layout.hint}
              className="mt-2 inline-flex w-fit rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-600">
          {layout.label}
        </span>
        <p className="mt-3 line-clamp-3 border-l-2 border-violet-300 pl-3 text-sm italic text-zinc-700">“{clip.hook}”</p>
        <p className="mt-2 line-clamp-2 text-xs text-zinc-500">{clip.reason}</p>
        {clip.status !== "ready" && (
          <p className={`mt-2 text-xs font-medium ${clip.status === "failed" ? "text-rose-600" : "text-violet-700"}`}>
            {clip.status === "failed" ? `Last edit failed: ${clip.error_message}` : "Rendering your edit…"}
          </p>
        )}
        <div className="mt-auto flex gap-2 pt-4">
          <Link href={`/edit?id=${clip.clip_id}`}
                className="flex flex-1 items-center justify-center rounded-xl border border-violet-200 px-3 py-2.5 text-sm font-semibold text-violet-700 hover:bg-violet-50">
            Edit
          </Link>
          <a href={mediaUrl(clip.download_url)} download aria-label="Download MP4"
             className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-violet-600 px-3 py-2.5 text-sm font-semibold text-white hover:bg-violet-700">
            <DownloadIcon width={18} height={18} /> MP4
          </a>
        </div>
      </div>
    </article>
  );
}
