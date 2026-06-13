"use client";

import type { MarketStatus } from "@/types";
import { t } from "@/lib/i18n";
import { formatBaghdadDateTime, useCountdown, useCountdownParts } from "@/hooks/useCountdown";

interface Props {
  status: MarketStatus | null;
}

export default function MarketStatusPanel({ status }: Props) {
  const openTarget = status?.is_open ? status.next_close_at : status?.next_open_at;
  const { label: sessionCountdown, totalSeconds } = useCountdownParts(openTarget);
  const signalCountdown = useCountdown(status?.next_signal_at ?? null);

  if (!status) return null;

  const sessionLabel = status.is_open ? t.closesIn : t.opensIn;
  const sessionAtLabel = status.is_open ? t.marketClosesAt : t.marketOpensAt;
  const sessionAtIso = status.is_open ? status.next_close_at : status.next_open_at;

  return (
    <div className={`market-status-panel mt-session-panel ${status.is_open ? "open" : "closed"}`}>
      <div className="market-status-header">
        <span className={`market-badge ${status.is_open ? "badge-open" : "badge-closed"}`}>
          {status.is_open ? t.marketOpen : t.marketClosed}
        </span>
        <span className="market-schedule">{status.schedule_ar}</span>
      </div>

      {sessionAtIso && (
        <div className="mt-countdown-block">
          <div className="mt-countdown-label">{sessionLabel}</div>
          <div className="mt-countdown-value mono">{sessionCountdown}</div>
          <div className="mt-countdown-meta">
            <span>{sessionAtLabel}:</span>
            <span className="mono">{formatBaghdadDateTime(sessionAtIso)}</span>
            <span className="mt-countdown-tz">({t.iraqTime})</span>
          </div>
          {totalSeconds > 0 && totalSeconds <= 3600 && (
            <div className="mt-countdown-soon">
              {status.is_open ? "اقترب وقت إغلاق السوق" : "اقترب وقت فتح السوق"}
            </div>
          )}
        </div>
      )}

      {status.is_open && status.next_signal_at && (
        <div className="countdown-row">
          <span className="countdown-label">{t.nextSignalIn}</span>
          <span className="countdown-value mono">{signalCountdown}</span>
        </div>
      )}
    </div>
  );
}
