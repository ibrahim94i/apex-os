"use client";

import type { TradingSignal } from "@/types";
import { t, translateDirection } from "@/lib/i18n";

interface Props {
  signals: TradingSignal[];
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleString("ar-EG", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export default function SignalHistory({ signals }: Props) {
  if (signals.length === 0) {
    return (
      <div className="card col-4">
        <div className="card-title">{t.signalHistory}</div>
        <div className="empty-state">{t.noSignalsYet}</div>
      </div>
    );
  }

  return (
    <div className="card col-4">
      <div className="card-title">{t.signalHistoryLast20}</div>
      <div className="signal-history">
        <div
          className="signal-row"
          style={{ fontWeight: 600, color: "var(--text-secondary)", fontSize: "0.65rem" }}
        >
          <span>{t.time}</span>
          <span>{t.direction}</span>
          <span>{t.confidence}</span>
          <span>{t.entry}</span>
        </div>
        {signals.map((s, i) => (
          <div key={s.id ?? `${s.timestamp}-${i}`} className="signal-row mono">
            <span>{formatTime(s.timestamp)}</span>
            <span className={`signal-${s.direction}`}>{translateDirection(s.direction)}</span>
            <span>{(s.confidence * 100).toFixed(0)}%</span>
            <span>{s.entry_price.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
