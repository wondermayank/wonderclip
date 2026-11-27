/**
 * Caption layout for the live preview — a direct port of backend/app/services/captions.py
 * (paginate + page timing + text cleanup) so the preview breaks lines exactly like the render.
 */
import type { CaptionStyle, EditorWord } from "./api";

export type Page = { words: EditorWord[]; start: number; end: number };

const NO_SPACE_BEFORE = /^(?:[,.;:!?%)\]}'’…]|-(?=\w)|n't\b)/;

/** Words in [start, end) with punctuation glued to the previous word (same as clip_words). */
export function wordsInRange(words: EditorWord[], start: number, end: number): EditorWord[] {
  const out: EditorWord[] = [];
  for (const w of words) {
    if (w.end <= start || w.start >= end) continue;
    const text = w.text.trim();
    if (!text) continue; // hidden in the editor
    const last = out[out.length - 1];
    if (last && NO_SPACE_BEFORE.test(text)) {
      out[out.length - 1] = { ...last, text: last.text + text, end: w.end };
    } else {
      out.push({ ...w, text, start: Math.max(start, w.start), end: Math.min(end, w.end) });
    }
  }
  return out;
}

export function paginate(words: EditorWord[], maxWords: number, maxChars: number, gap = 0.6): EditorWord[][] {
  const pages: EditorWord[][] = [];
  let cur: EditorWord[] = [];
  for (const w of words) {
    const chars = cur.reduce((n, x) => n + x.text.length + 1, 0) + w.text.length;
    if (cur.length && (cur.length >= maxWords || chars > maxChars || w.start - cur[cur.length - 1].end > gap)) {
      pages.push(cur);
      cur = [];
    }
    cur.push(w);
    if (/[.?!।]$/.test(w.text)) {
      pages.push(cur);
      cur = [];
    }
  }
  if (cur.length) pages.push(cur);
  return pages;
}

export function timedPages(words: EditorWord[], st: CaptionStyle, clipEnd: number): Page[] {
  const pages = paginate(words, st.max_words, st.max_chars);
  return pages.map((p, i) => {
    const next = i + 1 < pages.length ? pages[i + 1][0].start : clipEnd;
    return { words: p, start: p[0].start, end: Math.min(p[p.length - 1].end + 0.35, next, clipEnd) };
  });
}

export function cleanText(text: string, st: CaptionStyle): string {
  let t = text.replace(/[\\{}]/g, "");
  if (st.preset === "bold") t = t.replace(/[.,;:]+$/, "");
  return st.uppercase ? t.toUpperCase() : t;
}

/** Interpolated crop left-edge (source px) at clip-relative time t. */
export function cropXAt(samples: [number, number][], t: number): number {
  if (!samples.length) return 0;
  if (t <= samples[0][0]) return samples[0][1];
  for (let i = 1; i < samples.length; i++) {
    const [t1, x1] = samples[i];
    if (t <= t1) {
      const [t0, x0] = samples[i - 1];
      return x0 + ((x1 - x0) * (t - t0)) / Math.max(t1 - t0, 1e-6);
    }
  }
  return samples[samples.length - 1][1];
}

export function hexToRgba(hex: string, opacity: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${opacity})`;
}
