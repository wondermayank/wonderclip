"use client";

import { useSystemStatus } from "@/hooks/useSystemStatus";

const LABELS: Record<string, string> = {
  gpu: "GPU",
  ffmpeg: "FFmpeg (video engine)",
  whisper: "Faster-Whisper (transcription)",
  ollama: "Ollama + Qwen3 (highlight finder)",
};

export default function SettingsPage() {
  const sys = useSystemStatus(10_000);
  return (
    <div className="mx-auto max-w-3xl px-6 py-10 lg:px-10">
      <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
      <h2 className="mt-8 text-lg font-semibold">Local AI engine</h2>
      <p className="mt-1 text-sm text-zinc-500">Everything runs on this computer. Nothing is sent to paid AI services.</p>

      <div className="mt-5 divide-y divide-zinc-100 rounded-2xl border border-zinc-100 bg-white shadow-sm">
        {sys.state === "loading" && <p className="p-5 text-zinc-500">Checking your system…</p>}
        {sys.state === "offline" && (
          <p className="p-5 text-rose-600">Can&apos;t reach the Wonder Clips backend on this computer. Start it with <code>scripts/dev-backend.ps1</code>.</p>
        )}
        {sys.state === "ok" &&
          Object.entries(LABELS).map(([key, label]) => {
            const c = sys.data.components[key];
            return (
              <div key={key} className="flex items-center justify-between gap-4 p-5">
                <div>
                  <div className="font-medium text-zinc-800">{label}</div>
                  <div className="text-sm text-zinc-500">{c?.detail ?? "—"}</div>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${c?.ok ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                  {c?.ok ? "Ready" : "Needs setup"}
                </span>
              </div>
            );
          })}
      </div>
    </div>
  );
}
