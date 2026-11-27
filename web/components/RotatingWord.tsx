"use client";

import { useEffect, useState } from "react";

/** Cycles through short words inside a headline. */
export function RotatingWord({ words }: { words: string[] }) {
  const [i, setI] = useState(0);
  const [out, setOut] = useState(false);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => { setOut(true); setTimeout(() => { setI((n) => (n + 1) % words.length); setOut(false); }, 300); }, 2600);
    return () => clearInterval(t);
  }, [words.length]);
  return (
    <span className={`inline-block text-[#573AFC] transition-all duration-300 ${out ? "-translate-y-2 opacity-0" : "translate-y-0 opacity-100"}`}>
      {words[i]}
    </span>
  );
}
