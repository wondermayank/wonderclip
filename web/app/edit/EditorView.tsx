"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Preview, type PreviewHandle } from "@/components/editor/Preview";
import { StylePanel } from "@/components/editor/StylePanel";
import { Trim } from "@/components/editor/Trim";
import { WordsPanel } from "@/components/editor/WordsPanel";
import { AlertIcon, ArrowLeftIcon, CheckIcon, DownloadIcon, Spinner } from "@/components/icons";
import {
  API_URL, ApiError, getClip, getEditor, mediaUrl, saveClip,
  type CaptionStyle, type Clip, type EditorData, type EditorWord,
} from "@/lib/api";

type Draft = { start: number; end: number; style: CaptionStyle; texts: Record<number, string> };

function draftFrom(d: EditorData): Draft {
  const texts: Record<number, string> = {};
  for (const w of d.words) texts[w.i] = w.text;
  return { start: d.clip.start_time, end: d.clip.end_time, style: d.style, texts };
}

function useFontFaces(data: EditorData | null) {
  useEffect(() => {
    if (!data) return;
    const css = data.fonts.flatMap((f) => [
      `@font-face{font-family:"${f.family}";src:url(${API_URL}${f.regular_url});font-weight:400;font-display:swap}`,
      f.bold_url ? `@font-face{font-family:"${f.family}";src:url(${API_URL}${f.bold_url});font-weight:700;font-display:swap}` : "",
    ]).join("\n");
    const el = document.createElement("style");
    el.textContent = css;
    document.head.appendChild(el);
    return () => el.remove();
  }, [data]);
}

export default function EditorView() {
  const id = useSearchParams().get("id") ?? "";
  const [data, setData] = useState<EditorData | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saved, setSaved] = useState<Draft | null>(null);
  const [clip, setClip] = useState<Clip | null>(null);
  const [tab, setTab] = useState<"style" | "words">("style");
  const [view, setView] = useState<"live" | "render">("live");
  const [playhead, setPlayhead] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const preview = useRef<PreviewHandle>(null);
  useFontFaces(data);

  const apply = useCallback((d: EditorData) => {
    setData(d);
    setClip(d.clip);
    const dr = draftFrom(d);
    setDraft(dr);
    setSaved(dr);
    setPlayhead(d.clip.start_time);
  }, []);
  const fail = useCallback((e: unknown) => setError(e instanceof ApiError ? e.message : "Couldn't open the editor."), []);
  const load = useCallback(() => getEditor(id).then(apply, fail), [id, apply, fail]);
  useEffect(() => {
    getEditor(id).then(apply, fail);
  }, [id, apply, fail]);

  // While a render is queued/running, poll until it finishes, then reload the editor state.
  useEffect(() => {
    if (!clip || (clip.status !== "queued" && clip.status !== "rendering")) return;
    const t = setInterval(async () => {
      const c = await getClip(id).catch(() => null);
      if (!c) return;
      setClip(c);
      if (c.status === "ready") { clearInterval(t); await load(); setView("render"); }
      if (c.status === "failed") clearInterval(t);
    }, 1000);
    return () => clearInterval(t);
  }, [clip, id, load]);

  const words: EditorWord[] = useMemo(
    () => (data && draft ? data.words.map((w) => ({ ...w, text: draft.texts[w.i] ?? w.text })) : []),
    [data, draft],
  );
  const onTime = useCallback((t: number) => setPlayhead(t), []);

  if (error && !data) return <Shell><Err msg={error} /></Shell>;
  if (!data || !draft || !saved || !clip) return <Shell><div className="flex items-center gap-3 text-zinc-500"><Spinner /> Loading editor…</div></Shell>;

  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  const busy = clip.status === "queued" || clip.status === "rendering";
  const len = draft.end - draft.start;
  const lenOk = len >= data.limits.min_duration && len <= data.limits.max_duration;
  const inRange = words.filter((w) => w.end > draft.start && w.start < draft.end);
  const editedCount = data.words.filter((w) => (draft.texts[w.i] ?? w.text) !== w.default).length;

  const save = async () => {
    setError(null);
    const word_edits: Record<string, string> = {};
    for (const w of data.words) {
      const t = draft.texts[w.i] ?? w.text;
      if (t !== w.default) word_edits[String(w.i)] = t;
    }
    try {
      setClip(await saveClip(id, { start_time: draft.start, end_time: draft.end, style: draft.style, word_edits }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save.");
    }
  };

  return (
    <Shell jobId={clip.job_id} title={clip.title}>
      <div className="grid gap-8 lg:grid-cols-[auto_1fr]">
        {/* Left: preview */}
        <div className="mx-auto lg:mx-0">
          <div className="mb-3 flex gap-1 rounded-xl bg-zinc-100 p-1 text-sm font-medium">
            <button onClick={() => setView("live")}
                    className={`flex-1 rounded-lg px-3 py-1.5 ${view === "live" ? "bg-white shadow-sm" : "text-zinc-500"}`}>
              Live preview
            </button>
            <button onClick={() => setView("render")}
                    className={`flex-1 rounded-lg px-3 py-1.5 ${view === "render" ? "bg-white shadow-sm" : "text-zinc-500"}`}>
              Saved render v{clip.version}
            </button>
          </div>
          {view === "live" ? (
            <Preview ref={preview} data={data} start={draft.start} end={draft.end} style={draft.style}
                     words={words} renderedStart={data.clip.start_time} onTime={onTime} />
          ) : (
            <div>
              <video key={clip.video_url} src={mediaUrl(clip.video_url)} controls playsInline
                     className="aspect-[9/16] w-[340px] rounded-2xl bg-black" />
              <p className="mt-2 text-center text-xs text-zinc-400">Exact output file · 1080×1920</p>
            </div>
          )}
        </div>

        {/* Right: controls */}
        <div className="min-w-0 space-y-6">
          <section className="rounded-2xl border border-zinc-100 bg-white p-5 shadow-sm">
            <h2 className="mb-3 font-semibold">Trim</h2>
            <Trim start={draft.start} end={draft.end} duration={data.source.duration} words={data.words}
                  min={data.limits.min_duration} max={data.limits.max_duration} playhead={playhead}
                  onChange={(start, end) => { setDraft({ ...draft, start, end }); preview.current?.seek(start); setView("live"); }} />
          </section>

          <section className="rounded-2xl border border-zinc-100 bg-white shadow-sm">
            <div className="flex border-b border-zinc-100 text-sm font-medium">
              {(["style", "words"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)}
                        className={`-mb-px border-b-2 px-5 py-3 ${tab === t ? "border-violet-600 text-violet-700" : "border-transparent text-zinc-500 hover:text-zinc-800"}`}>
                  {t === "style" ? "Caption style" : `Words${editedCount ? ` (${editedCount} fixed)` : ""}`}
                </button>
              ))}
            </div>
            <div className="p-5">
              {tab === "style" ? (
                <StylePanel style={draft.style} presets={data.presets} fonts={data.fonts}
                            onChange={(style) => { setDraft({ ...draft, style }); setView("live"); }} />
              ) : (
                <WordsPanel words={inRange.map((w) => ({ ...w, edited: w.text !== w.default }))} playhead={playhead}
                            onEdit={(i, text) => { setDraft({ ...draft, texts: { ...draft.texts, [i]: text } }); setView("live"); }}
                            onReset={(i) => {
                              const w = data.words.find((x) => x.i === i);
                              if (w) setDraft({ ...draft, texts: { ...draft.texts, [i]: w.default } });
                            }}
                            onSeek={(t) => { setView("live"); preview.current?.seek(t); }} />
              )}
            </div>
          </section>
        </div>
      </div>

      {/* Sticky action bar */}
      <div className="sticky bottom-0 -mx-6 mt-8 border-t border-zinc-100 bg-white/90 px-6 py-4 backdrop-blur lg:-mx-10 lg:px-10">
        <div className="flex flex-wrap items-center gap-3">
          {busy ? (
            <span className="inline-flex items-center gap-2 font-medium text-violet-700">
              <Spinner /> {clip.status === "queued" ? "Waiting to render…" : "Rendering your clip…"}
            </span>
          ) : clip.status === "failed" ? (
            <span className="inline-flex items-center gap-2 font-medium text-rose-700"><AlertIcon /> {clip.error_message}</span>
          ) : dirty ? (
            <span className="text-sm text-zinc-500">Unsaved changes — the preview shows them already.</span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-sm text-emerald-700"><CheckIcon width={16} height={16} /> Saved</span>
          )}
          {error && <span className="text-sm font-medium text-rose-700">{error}</span>}
          <div className="ml-auto flex gap-3">
            {dirty && !busy && (
              <button onClick={() => setDraft(saved)} className="rounded-xl px-4 py-2.5 font-medium text-zinc-600 hover:bg-zinc-100">
                Discard
              </button>
            )}
            <a href={mediaUrl(clip.download_url)} download
               className={`inline-flex items-center gap-2 rounded-xl border border-zinc-200 px-4 py-2.5 font-medium text-zinc-700 hover:bg-zinc-50 ${busy ? "pointer-events-none opacity-50" : ""}`}>
              <DownloadIcon width={18} height={18} /> Download
            </a>
            <button onClick={save} disabled={!dirty || busy || !lenOk}
                    className="rounded-xl bg-violet-600 px-5 py-2.5 font-semibold text-white shadow-lg shadow-violet-500/25 hover:bg-violet-700 disabled:opacity-40 disabled:shadow-none">
              Save &amp; render
            </button>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function Shell({ jobId, title, children }: { jobId?: string; title?: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-6xl px-6 pt-8 lg:px-10">
      <nav className="mb-6 flex items-center gap-2 text-sm font-medium text-zinc-500">
        <Link href={jobId ? `/job?id=${jobId}` : "/projects"} className="inline-flex items-center gap-1.5 hover:text-violet-700">
          <ArrowLeftIcon width={16} height={16} /> Your clips
        </Link>
        <span>›</span>
        <span className="truncate text-zinc-800">Edit{title ? `: ${title}` : ""}</span>
      </nav>
      {children}
    </div>
  );
}

function Err({ msg }: { msg: string }) {
  return <div role="alert" className="flex items-center gap-3 rounded-2xl bg-rose-50 p-4 font-medium text-rose-800"><AlertIcon /> {msg}</div>;
}
