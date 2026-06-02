"use client";

import type { MarketStatus } from "@/types";
import { t } from "@/lib/i18n";
import { useCountdown } from "@/hooks/useCountdown";

interface Props {
  status: MarketStatus | null;
}

export default function MarketStatusPanel({ status }: Props) {
  const openCountdown = useCountdown(status?.next_open_at ?? null);
  const signalCountdown = useCountdown(status?.next_signal_at ?? null);

  if (!status) return null;

  return (
    <div className={`market-status-panel ${status.is_open ? "open" : "closed"}`}>
      <div className="market-status-header">
        <span className={`market-badge ${status.is_open ? "badge-open" : "badge-closed"}`}>
          {status.is_open ? t.marketOpen : t.marketClosed}
        </span>
        <span className="market-schedule">{status.schedule_ar}</span>
      </div>
      {!status.is_open && status.next_open_at && (
        <div className="countdown-row">
          <span className="countdown-label">{t.opensIn}</span>
          <span className="countdown-value mono">{openCountdown}</span>
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
