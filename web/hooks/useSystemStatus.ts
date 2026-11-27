"use client";

import { useEffect, useState } from "react";
import { getSystem, type SystemStatus } from "@/lib/api";

export type SystemState =
  | { state: "loading" }
  | { state: "offline" }
  | { state: "ok"; data: SystemStatus };

/** Polls /api/system every `intervalMs` (default 30 s). */
export function useSystemStatus(intervalMs = 30_000): SystemState {
  const [s, setS] = useState<SystemState>({ state: "loading" });
  useEffect(() => {
    let ctl = new AbortController();
    const load = () => {
      ctl.abort();
      ctl = new AbortController();
      getSystem(ctl.signal)
        .then((data) => setS({ state: "ok", data }))
        .catch((e) => e?.name !== "AbortError" && setS({ state: "offline" }));
    };
    load();
    const t = setInterval(load, intervalMs);
    return () => {
      clearInterval(t);
      ctl.abort();
    };
  }, [intervalMs]);
  return s;
}
