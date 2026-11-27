"use client";

import { useMemo, useState } from "react";
import type { EditorWord } from "@/lib/api";
import { formatTimecode } from "@/lib/api";

type Props = {
  start: number;
  end: number;
  duration: number; // whole source video
  words: EditorWord[];
  min: number;
  max: number;
  playhead: number;
  onChange: (start: number, end: number) => void;
};

const PAD = 20; // seconds of context shown around the original clip

/** Snap a start to just before a word begins / an end to just after a word ends. */
function snap(t: number, words: EditorWord[], edge: "start" | "end"): number {
  let best = t, bestD = 0.6;
  for (const w of words) {
    const c = edge === "start" ? w.start - 0.15 : w.end + 0.25;
    const d = Math.abs(c - t);
    if (d < bestD) { best = c; bestD = d; }
  }
  return Math.max(0, best);
}

export function Trim({ start, end, duration, words, min, max, playhead, onChange }: Props) {
  // Fixed window (computed once) so the scale doesn't shift while dragging.
  const [win] = useState(() => [Math.max(0, start - PAD), Math.min(duration, end + PAD)] as const);
  const [snapOn, setSnapOn] = useState(true);
  const span = win[1] - win[0];
  const pct = (t: number) => `${((t - win[0]) / span) * 100}%`;
  const len = end - start;
  const bad = len < min || len > max;

  const set = (s: number, e: number) => {
    s = Math.max(win[0], Math.min(s, duration));
    e = Math.max(win[0], Math.min(e, win[1]));
    if (e - s < 0.5) return;
    onChange(+s.toFixed(2), +e.toFixed(2));
  };
  const setStart = (s: number) => set(snapOn ? snap(s, words, "start") : s, end);
  const setEnd = (e: number) => set(start, snapOn ? snap(e, words, "end") : e);
  const ticks = useMemo(() => words.filter((w) => w.start >= win[0] && w.end <= win[1]), [words, win]);

  return (
    <div>
      <div className="relative h-14 rounded-xl bg-zinc-100">
        {ticks.map((w) => (
          <span key={w.i} className="absolute top-4 h-6 w-px bg-zinc-300" style={{ left: pct(w.start) }} />
        ))}
        <div className="absolute inset-y-0 rounded-xl border-2 border-violet-500 bg-violet-500/15"
             style={{ left: pct(start), width: `${(len / span) * 100}%` }} />
        <span className="absolute inset-y-0 w-0.5 bg-rose-500" style={{ left: pct(Math.min(Math.max(playhead, win[0]), win[1])) }} />
        {/* Two overlaid range inputs = two draggable handles */}
        <input type="range" aria-label="Clip start" min={win[0]} max={win[1]} step={0.05} value={start}
               onChange={(e) => setStart(+e.target.value)} className="trim-range" />
        <input type="range" aria-label="Clip end" min={win[0]} max={win[1]} step={0.05} value={end}
               onChange={(e) => setEnd(+e.target.value)} className="trim-range" />
      </div>
      <div className="mt-1 flex justify-between text-xs text-zinc-400">
        <span>{formatTimecode(win[0])}</span><span>{formatTimecode(win[1])}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-3 text-sm">
        <Field label="Start" value={start} onNudge={(d) => set(start + d, end)} onPlayhead={() => setStart(playhead)} />
        <Field label="End" value={end} onNudge={(d) => set(start, end + d)} onPlayhead={() => setEnd(playhead)} />
        <span className={`font-semibold tabular-nums ${bad ? "text-rose-600" : "text-zinc-700"}`}>
          {len.toFixed(1)}s {bad && `(must be ${min}–${max}s)`}
        </span>
        <label className="ml-auto inline-flex items-center gap-2 text-zinc-600">
          <input type="checkbox" checked={snapOn} onChange={(e) => setSnapOn(e.target.checked)} className="accent-violet-600" />
          Snap to words
        </label>
      </div>
    </div>
  );
}

function Field({ label, value, onNudge, onPlayhead }: {
  label: string; value: number; onNudge: (d: number) => void; onPlayhead: () => void;
}) {
  const btn = "rounded-md px-1.5 py-0.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800";
  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-zinc-500">{label}</span>
      <button className={btn} onClick={() => onNudge(-0.1)} aria-label={`${label} earlier`}>−</button>
      <span className="w-14 text-center font-semibold tabular-nums text-zinc-800">{formatTimecode(value)}</span>
      <button className={btn} onClick={() => onNudge(0.1)} aria-label={`${label} later`}>+</button>
      <button className={`${btn} text-xs`} onClick={onPlayhead} title="Set to the current preview position">⇤ playhead</button>
    </span>
  );
}
