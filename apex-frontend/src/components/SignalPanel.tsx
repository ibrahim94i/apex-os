"use client";

import type { TradingSignal } from "@/types";
import { t, translateDirection } from "@/lib/i18n";

interface Props {
  signal: TradingSignal | null;
  currentPrice: number | null;
}

function formatPrice(price: number): string {
  return price.toLocaleString("ar-EG", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function SignalPanel({ signal, currentPrice }: Props) {
  if (!signal) {
    return (
      <div className="card col-6">
        <div className="card-title">{t.latestSignal}</div>
        <div className="empty-state">
          {t.noActiveSignal}
          {currentPrice != null && (
            <div style={{ marginTop: "0.5rem" }}>
              <span className="card-title">{t.price} </span>
              <span className="mono metric-value">${formatPrice(currentPrice)}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="card col-6">
      <div className="card-title">{t.latestSignal}</div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <span className={`signal-direction signal-${signal.direction}`}>
          {translateDirection(signal.direction)}
        </span>
        {signal.degraded && <span className="degraded-tag">{t.degraded}</span>}
      </div>
      <div style={{ marginTop: "0.5rem" }}>
        <span className="card-title">{t.confidence} </span>
        <span className="mono metric-value">{(signal.confidence * 100).toFixed(1)}%</span>
        <div className="confidence-bar">
          <div
            className="confidence-fill"
            style={{ width: `${signal.confidence * 100}%` }}
          />
        </div>
      </div>
      <div className="price-levels">
        <div className="price-level entry">
          <div className="label">{t.entry}</div>
          <div className="value">${formatPrice(signal.entry_price)}</div>
        </div>
        <div className="price-level sl">
          <div className="label">{t.stopLoss}</div>
          <div className="value">${formatPrice(signal.stop_loss)}</div>
        </div>
        <div className="price-level tp">
          <div className="label">{t.takeProfit}</div>
          <div className="value">${formatPrice(signal.take_profit)}</div>
        </div>
      </div>
      {currentPrice != null && (
        <div style={{ marginTop: "0.75rem" }}>
          <span className="card-title">{t.livePrice} </span>
          <span className="mono metric-value">${formatPrice(currentPrice)}</span>
        </div>
      )}
      {signal.degradation_reason && (
        <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--gold)" }}>
          {signal.degradation_reason}
        </div>
      )}
    </div>
  );
}
