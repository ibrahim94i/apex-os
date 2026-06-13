"use client";

import { useEffect, useState } from "react";

function formatRemaining(totalSeconds: number): string {
  if (totalSeconds <= 0) return "0:00";
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function useCountdown(targetIso: string | null | undefined): string {
  const [label, setLabel] = useState("—");

  useEffect(() => {
    if (!targetIso) {
      setLabel("—");
      return;
    }

    const tick = () => {
      const diffMs = new Date(targetIso).getTime() - Date.now();
      const secs = Math.max(0, Math.floor(diffMs / 1000));
      setLabel(formatRemaining(secs));
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetIso]);

  return label;
}

export function minutesFromSeconds(seconds: number | null | undefined): number {
  if (seconds == null) return 0;
  return Math.ceil(seconds / 60);
}

const BAGHDAD_TZ = "Asia/Baghdad";

export function formatBaghdadDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("ar-IQ", {
      timeZone: BAGHDAD_TZ,
      weekday: "long",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(iso));
  } catch {
    return "—";
  }
}

export function useCountdownParts(
  targetIso: string | null | undefined,
): { label: string; totalSeconds: number } {
  const [state, setState] = useState({ label: "—", totalSeconds: 0 });

  useEffect(() => {
    if (!targetIso) {
      setState({ label: "—", totalSeconds: 0 });
      return;
    }

    const tick = () => {
      const diffMs = new Date(targetIso).getTime() - Date.now();
      const secs = Math.max(0, Math.floor(diffMs / 1000));
      setState({ label: formatRemaining(secs), totalSeconds: secs });
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetIso]);

  return state;
}
