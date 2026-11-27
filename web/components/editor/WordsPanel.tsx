"use client";

import type { EditorWord } from "@/lib/api";
import { formatTimecode } from "@/lib/api";

type Props = {
  words: EditorWord[];      // words inside the current trim
  playhead: number;
  onEdit: (i: number, text: string) => void;
  onReset: (i: number) => void;
  onSeek: (t: number) => void;
};

/** Fix what Whisper misheard. Only the text changes — word timing stays exactly as transcribed. */
export function WordsPanel({ words, playhead, onEdit, onReset, onSeek }: Props) {
  if (!words.length) return <p className="text-sm text-zinc-500">No speech in this range.</p>;
  return (
    <div>
      <p className="mb-3 text-sm text-zinc-500">
        Click a word&apos;s time to jump there. Edit the text to fix a mistake; clear it to hide the word.
      </p>
      <ul className="max-h-[560px] space-y-1 overflow-y-auto pr-1">
        {words.map((w) => {
          const now = playhead >= w.start && playhead < w.end;
          const hidden = !w.text.trim();
          return (
            <li key={w.i} className={`flex items-center gap-2 rounded-lg px-2 py-1 ${now ? "bg-violet-50" : ""}`}>
              <button onClick={() => onSeek(w.start)} className="w-14 shrink-0 text-left text-xs tabular-nums text-zinc-400 hover:text-violet-700">
                {formatTimecode(w.start)}
              </button>
              <input value={w.text} onChange={(e) => onEdit(w.i, e.target.value)} placeholder="(hidden)" maxLength={60}
                     className={`min-w-0 flex-1 rounded-md border px-2 py-1 text-sm ${w.edited ? "border-amber-300 bg-amber-50" : "border-transparent hover:border-zinc-200"} ${hidden ? "italic text-zinc-400" : ""}`} />
              {w.edited && (
                <button onClick={() => onReset(w.i)} title={`Undo (Whisper heard: ${w.original})`}
                        className="shrink-0 text-xs text-zinc-400 hover:text-zinc-700">↺</button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
