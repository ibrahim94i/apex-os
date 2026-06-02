"use client";

import type { Alert } from "@/types";

interface Props {
  alerts: Alert[];
  onDismiss: (id: string) => void;
}

export default function AlertBanner({ alerts, onDismiss }: Props) {
  const banners = alerts.filter(
    (a) => !a.fullscreen && (a.severity === "warning" || a.severity === "critical")
  );

  if (banners.length === 0) return null;

  return (
    <div className="alert-banners">
      {banners.map((alert) => (
        <div
          key={alert.id}
          className={`alert-banner alert-${alert.severity}`}
          role="alert"
        >
          <strong>{alert.title_ar}</strong>
          <span>{alert.message_ar}</span>
          <button type="button" className="alert-dismiss" onClick={() => onDismiss(alert.id)}>
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
