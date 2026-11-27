"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import { SITE } from "@/lib/site";
import { DownloadIcon, MonitorIcon, Spinner } from "./icons";

/**
 * The web UI is hosted (clips.wondermayank.in) but all processing happens on the visitor's own
 * computer. Show the upload box only when the local Wonder Clips engine answers.
 */
const REPO_URL = SITE.repo;
const INSTALL_CMD = SITE.installCmd;

function CopyCommand({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-2 flex items-stretch overflow-hidden rounded-lg border border-zinc-200 bg-white">
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap px-3 py-2 text-xs text-zinc-800">{text}</code>
      <button type="button" onClick={() => { navigator.clipboard?.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
              className="shrink-0 border-l border-zinc-200 px-3 text-xs font-semibold text-violet-700 hover:bg-violet-50">
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

const SETUP_URL = SITE.installer;

/** First-time install: one download button; the PowerShell one-liner stays available for power users. */
function InstallBox() {
  return (
    <div className="rounded-2xl bg-zinc-50 p-4">
      <div className="text-sm font-semibold text-zinc-900">First time? Install it (free)</div>
      <a href={SETUP_URL} download
         className="mt-3 flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-violet-500 px-4 py-3 font-semibold text-white shadow-lg shadow-violet-500/25 hover:brightness-110">
        <DownloadIcon width={18} height={18} /> Download installer for Windows
      </a>
      <ol className="mt-3 space-y-1 text-xs text-zinc-600">
        <li><b>1.</b> Double-click <b>Install-WonderClips.bat</b> and wait (about 5–15 min, downloads ~4 GB).</li>
        <li><b>2.</b> If Windows says <i>“Windows protected your PC”</i>, click <b>More info → Run anyway</b>.</li>
        <li><b>3.</b> Come back here — this page connects automatically.</li>
      </ol>
      <p className="mt-2 text-xs text-zinc-600">
        🔒 Open source, runs only on your PC, no admin rights needed.{" "}
        <Link href="/faq" className="font-semibold text-violet-700 hover:underline">Is it safe?</Link>
      </p>
      <details className="mt-3 text-xs text-zinc-500">
        <summary className="cursor-pointer hover:text-violet-700">Prefer to paste a command?</summary>
        <CopyCommand text={INSTALL_CMD} />
      </details>
    </div>
  );
}

/**
 * Chrome/Edge (Local Network Access) ask the user before a public site like clips.wondermayank.in may talk to
 * apps on their own computer. Returns "granted" | "prompt" | "denied" | "unsupported".
 */
function useLocalNetworkPermission(): string {
  const [state, setState] = useState("unsupported");
  useEffect(() => {
    let status: PermissionStatus | null = null;
    const update = () => status && setState(status.state);
    (async () => {
      for (const name of ["local-network-access", "loopback-network"]) {
        try {
          status = await navigator.permissions.query({ name: name as PermissionName });
          update();
          status.addEventListener("change", update);
          return;
        } catch { /* not supported by this browser */ }
      }
    })();
    return () => status?.removeEventListener("change", update);
  }, []);
  return state;
}

export function EngineGate({ children }: { children: React.ReactNode }) {
  const sys = useSystemStatus(5_000);
  const lna = useLocalNetworkPermission();
  const hosted = typeof window !== "undefined" && !["localhost", "127.0.0.1"].includes(window.location.hostname);

  if (sys.state === "loading") {
    return (
      <div className="flex min-h-[300px] items-center justify-center gap-3 rounded-3xl border border-violet-100 bg-white/80 text-zinc-500">
        <Spinner /> Looking for Wonder Clips on this computer…
      </div>
    );
  }
  if (sys.state === "offline" && hosted && lna === "denied") {
    return (
      <section className="rounded-3xl border border-amber-200 bg-amber-50/60 p-8">
        <h2 className="text-xl font-bold tracking-tight text-zinc-900">Your browser is blocking Wonder Clips</h2>
        <p className="mt-1.5 max-w-xl text-zinc-700">
          Wonder Clips processes videos on your own computer, so this page needs permission to talk to the
          Wonder Clips engine running there. That permission is currently blocked for this site.
        </p>
        <ol className="mt-5 space-y-2 text-sm text-zinc-700">
          <li><b>1.</b> Click the site settings icon at the left of the address bar.</li>
          <li><b>2.</b> Set <b>Local network access</b> (or “Apps on this device”) to <b>Allow</b>.</li>
          <li><b>3.</b> Reload this page.</li>
        </ol>
        <div className="mt-5 max-w-md">
          <InstallBox />
        </div>
      </section>
    );
  }
  if (sys.state === "offline") {
    return (
      <section className="rounded-3xl border border-violet-100 bg-white/80 p-8 shadow-[0_8px_40px_-12px_rgba(124,58,237,0.15)]">
        <div className="flex items-start gap-4">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-violet-100 text-violet-700">
            <MonitorIcon width={26} height={26} />
          </span>
          <div>
            <h2 className="text-xl font-bold tracking-tight text-zinc-900">Wonder Clips runs on your own computer</h2>
            <p className="mt-1.5 max-w-xl text-zinc-600">
              Your videos never leave your machine: the AI (transcription, highlight finding, face tracking and
              captions) runs locally on your GPU. This page connects to the Wonder Clips engine on this computer,
              and it isn&apos;t running right now.
            </p>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <div className="rounded-2xl bg-violet-50/70 p-4">
                <div className="text-sm font-semibold text-zinc-900">Already installed?</div>
                <p className="mt-1 text-sm text-zinc-600">
                  Double-click <b>Wonder Clips</b> on your Desktop. This page connects by itself — if your browser
                  asks to allow access to apps on this device, choose <b>Allow</b>.
                </p>
              </div>
              <InstallBox />
            </div>
            <p className="mt-5 text-xs text-zinc-400">
              Windows 10/11 · NVIDIA GPU with 6 GB+ recommended (works on CPU, slower) · about 8 GB of disk ·{" "}
              <a href={REPO_URL} target="_blank" rel="noreferrer" className="underline hover:text-violet-700">source &amp; guide</a>
            </p>
          </div>
        </div>
      </section>
    );
  }
  return <>{children}</>;
}
