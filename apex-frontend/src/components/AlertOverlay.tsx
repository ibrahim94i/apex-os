"use client";

import type { Alert } from "@/types";

interface Props {
  alerts: Alert[];
  onDismiss: (id: string) => void;
}

export default function AlertOverlay({ alerts, onDismiss }: Props) {
  const overlay = alerts.find(
    (a) =>
      a.fullscreen &&
      (a.type === "kill_switch" ||
        a.type === "high_confidence" ||
        a.type === "consecutive_losses" ||
        a.type === "new_signal")
  );

  if (!overlay) return null;

  const variant =
    overlay.overlay_variant ||
    (overlay.type === "consecutive_losses" ? "yellow" : "red");

  return (
    <div className={`alert-overlay alert-overlay-${variant}`}>
      <div className={`alert-overlay-content alert-overlay-${variant}`}>
        <div className="alert-overlay-icon">
          {variant === "yellow" ? "⚠️" : "🚨"}
        </div>
        <h2>{overlay.title_ar}</h2>
        <p>{overlay.message_ar}</p>
        <button type="button" className="tab-btn" onClick={() => onDismiss(overlay.id)}>
          إغلاق
        </button>
      </div>
    </div>
  );
}
