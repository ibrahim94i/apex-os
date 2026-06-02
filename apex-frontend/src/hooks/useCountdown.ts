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
