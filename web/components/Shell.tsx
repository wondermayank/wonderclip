"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Create Clips", d: <><rect x="3" y="5" width="18" height="14" rx="3" /><polygon points="10 9 16 12 10 15" fill="currentColor" stroke="none" /></> },
  { href: "/projects/", label: "Projects", d: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /> },
  { href: "/settings/", label: "Settings", d: <><path d="M4 7h9M19 7h1M4 17h1M11 17h9" /><circle cx="16" cy="7" r="2.2" /><circle cx="8" cy="17" r="2.2" /></> },
  { href: "/faq/", label: "FAQ", d: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17h.01" /></> },
];

/** Theme toggle for the header + the floating dock (replaces the old sidebar). */
export function Shell() {
  const path = usePathname() || "/";
  const bar = useRef<HTMLDivElement>(null);
  const dock = useRef<HTMLElement>(null);
  const norm = path.endsWith("/") ? path : path + "/";
  let active = ITEMS.findIndex((i) => (i.href === "/" ? norm === "/" : norm.startsWith(i.href)));
  if (norm.startsWith("/job/") || norm.startsWith("/edit/")) active = 1;
  if (active < 0) active = 0;

  useEffect(() => {
    const btn = document.getElementById("themeBtn");
    const toggle = () => {
      const d = document.documentElement;
      const next = d.getAttribute("data-theme") === "dark" ? "light" : "dark";
      d.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch { /* storage blocked */ }
    };
    btn?.addEventListener("click", toggle);
    return () => btn?.removeEventListener("click", toggle);
  }, []);

  useEffect(() => {
    const place = () => {
      const el = bar.current?.querySelectorAll<HTMLElement>(".dock-btn")[active];
      const ind = bar.current?.querySelector<HTMLElement>(".dock-indicator");
      if (el && ind) ind.style.setProperty("--dx", `${el.offsetLeft + (el.offsetWidth - ind.offsetWidth) / 2}px`);
    };
    place();
    const r = requestAnimationFrame(() => requestAnimationFrame(place));
    window.addEventListener("resize", place);
    let last = window.scrollY;
    const onScroll = () => {
      const y = window.scrollY, dy = y - last;
      if (Math.abs(dy) > 8) { dock.current?.classList.toggle("hide", dy > 0 && y > 160); last = y; }
      if (window.innerHeight + y >= document.documentElement.scrollHeight - 4) dock.current?.classList.remove("hide");
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { cancelAnimationFrame(r); window.removeEventListener("resize", place); window.removeEventListener("scroll", onScroll); };
  }, [active]);

  return (
    <nav className="dock" aria-label="Quick tools" ref={dock}>
      <div className="dock-bar" ref={bar}>
        <span className="dock-indicator" aria-hidden="true" />
        {ITEMS.map((it, i) => (
          <a key={it.href} className="dock-btn" href={it.href} data-label={it.label} aria-label={it.label} aria-current={i === active ? "page" : undefined}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{it.d}</svg>
          </a>
        ))}
      </div>
    </nav>
  );
}
