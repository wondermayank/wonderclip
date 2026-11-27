"use client";

import { useEffect, useState } from "react";

const LINE = "Long video in. Viral clips out.";

/** Short animated welcome shown once per browser session. Skippable, respects reduced motion. */
export function Intro() {
  const [open, setOpen] = useState(true);
  const [typed, setTyped] = useState("");
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const seen = document.documentElement.classList.contains("seen-intro");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (seen || reduce) { setOpen(false); return; }
    try { sessionStorage.setItem("wc-intro", "1"); } catch { /* ignore */ }
    document.body.style.overflow = "hidden";
    let i = 0;
    const type = setInterval(() => { i++; setTyped(LINE.slice(0, i)); if (i >= LINE.length) clearInterval(type); }, 38);
    const leave = setTimeout(() => setLeaving(true), 2100);
    const done = setTimeout(() => setOpen(false), 2700);
    return () => { clearInterval(type); clearTimeout(leave); clearTimeout(done); document.body.style.overflow = ""; };
  }, []);

  useEffect(() => { if (!open) document.body.style.overflow = ""; }, [open]);
  if (!open) return null;

  const skip = () => { setLeaving(true); setTimeout(() => setOpen(false), 350); };
  return (
    <div className={`wc-intro fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-[#f6f3ff] px-6 text-center transition-opacity duration-500 ${leaving ? "opacity-0" : "opacity-100"}`} role="dialog" aria-label="Welcome to Wonder Clips">
      <style>{`@keyframes wcPop{0%{transform:scale(.4) rotate(-12deg);opacity:0}70%{transform:scale(1.08) rotate(3deg);opacity:1}100%{transform:scale(1) rotate(0)}}@keyframes wcBar{from{width:0}to{width:100%}}@keyframes wcCaret{50%{opacity:0}}`}</style>
      <img src="/favicon.svg" alt="" width={88} height={88} className="rounded-[26px] shadow-[0_18px_50px_-12px_rgba(87,58,252,.55)]" style={{ animation: "wcPop .8s cubic-bezier(.2,.9,.3,1.2) both" }} />
      <div className="mt-6 text-3xl font-extrabold tracking-tight text-zinc-900">Wonder<span className="text-[#573AFC]"> Clips</span></div>
      <p className="mt-3 h-7 text-lg font-medium text-zinc-600">{typed}<span className="ml-0.5 inline-block w-[2px] bg-[#573AFC] align-middle" style={{ height: "1.1em", animation: "wcCaret 1s steps(1) infinite" }} /></p>
      <div className="mt-8 h-1.5 w-56 overflow-hidden rounded-full bg-violet-200/70"><div className="h-full rounded-full bg-[#573AFC]" style={{ animation: "wcBar 2.1s ease-out forwards" }} /></div>
      <button type="button" onClick={skip} className="mt-8 rounded-full px-4 py-2 text-sm font-semibold text-zinc-500 hover:text-[#573AFC]">Skip</button>
    </div>
  );
}
