"use client";

import type { FeedStatus } from "@/types";
import { ASSET_LABELS } from "@/types";
import { t } from "@/lib/i18n";

interface Props {
  feedStatus: Record<string, FeedStatus>;
  symbols: string[];
}

function statusClass(status: FeedStatus["status"]): string {
  if (status === "connected") return "feed-connected";
  if (status === "reconnecting") return "feed-reconnecting";
  return "feed-disconnected";
}

function formatAge(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const age = Math.max(0, Math.floor(seconds));
  if (age < 60) return `${age}${t.secondsShort}`;
  const mins = Math.floor(age / 60);
  return `${mins}${t.minutesShort}`;
}

export default function FeedStatusPanel({ feedStatus, symbols }: Props) {
  if (!symbols.length) return null;

  return (
    <div className="card feed-status-panel">
      <h2>{t.feedStatusTitle}</h2>
      <div className="feed-status-grid">
        {symbols.map((sym) => {
          const feed = feedStatus[sym];
          const status = feed?.status ?? "disconnected";
          const label = feed?.status_ar ?? t.feedDisconnected;

          return (
            <div key={sym} className={`feed-status-item ${statusClass(status)}`}>
              <div className="feed-status-row">
                <span className="feed-symbol">{ASSET_LABELS[sym] ?? sym}</span>
                <span className={`feed-badge ${statusClass(status)}`}>{label}</span>
              </div>
              <div className="feed-meta">
                <span>{t.lastUpdate}: {formatAge(feed?.age_seconds)}</span>
                {(feed?.consecutive_failures ?? 0) > 0 && (
                  <span className="feed-failures">
                    {t.recoveryAttempts}: {feed?.consecutive_failures}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
