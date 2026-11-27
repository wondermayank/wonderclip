import type { Job, StageState } from "@/lib/api";
import { CcIcon, CheckIcon, FrameIcon, LayersIcon, MicIcon, SparkIcon, Spinner, UploadIcon, XIcon } from "./icons";

const META: Record<string, { Icon: typeof MicIcon; desc: string }> = {
  uploaded: { Icon: UploadIcon, desc: "Your video is ready for processing." },
  extracting_audio: { Icon: MicIcon, desc: "Pulling the audio track out of your video." },
  transcribing: { Icon: MicIcon, desc: "Converting speech to text with word timestamps." },
  finding_highlights: { Icon: SparkIcon, desc: "AI is picking the most interesting moments." },
  tracking_speakers: { Icon: FrameIcon, desc: "Detecting and tracking the speaker." },
  creating_captions: { Icon: CcIcon, desc: "Generating stylish, timed captions." },
  rendering_clips: { Icon: LayersIcon, desc: "Cutting and checking each clip." },
};

export function StageList({ job }: { job: Job }) {
  const rows: { key: string; label: string; state: StageState }[] = [
    { key: "uploaded", label: "Video Uploaded", state: "done" },
    ...job.stages,
  ];
  return (
    <ol className="divide-y divide-zinc-100 rounded-2xl border border-zinc-100 bg-white shadow-sm">
      {rows.map(({ key, label, state }) => {
        const { Icon, desc } = META[key] ?? { Icon: SparkIcon, desc: "" };
        const activeRow = state === "active";
        return (
          <li key={key} className={`flex items-center gap-4 px-5 py-4 ${activeRow ? "bg-violet-50/60" : ""} ${state === "skipped" ? "opacity-50" : ""}`}>
            <StateDot state={state} />
            <Icon className={state === "done" ? "text-emerald-600" : state === "failed" ? "text-rose-600" : "text-violet-600"} />
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-zinc-900">{label}</div>
              <div className="truncate text-sm text-zinc-500">{desc}</div>
            </div>
            <span className="shrink-0 text-sm font-medium">
              {state === "done" && <span className="inline-flex items-center gap-1 text-emerald-600"><CheckIcon width={16} height={16} /> Completed</span>}
              {state === "active" && (
                <span className="tabular-nums text-violet-700">
                  {key === "transcribing" || key === "rendering_clips" ? `${Math.round(job.stage_progress * 100)}%` : "Working…"}
                </span>
              )}
              {state === "waiting" && <span className="text-zinc-400">Waiting…</span>}
              {state === "skipped" && <span className="text-zinc-400">Coming soon</span>}
              {state === "failed" && <span className="text-rose-600">Stopped</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function StateDot({ state }: { state: StageState }) {
  if (state === "done")
    return <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-emerald-500 text-white"><CheckIcon width={14} height={14} strokeWidth={3} /></span>;
  if (state === "active") return <Spinner className="shrink-0 text-violet-600" width={24} height={24} />;
  if (state === "failed")
    return <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-rose-500 text-white"><XIcon width={14} height={14} strokeWidth={3} /></span>;
  return <span className="h-6 w-6 shrink-0 rounded-full border-2 border-zinc-200" />;
}
