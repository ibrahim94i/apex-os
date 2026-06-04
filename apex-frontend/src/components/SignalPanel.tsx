"use client";

import type { AgentConsensus, TradingSignal } from "@/types";
import { t, translateDirection } from "@/lib/i18n";

interface Props {
  signal: TradingSignal | null;
  currentPrice: number | null;
  symbol: string;
  consensus?: AgentConsensus | null;
}

function formatPrice(price: number, symbol: string): string {
  const decimals = symbol === "EURUSD" ? 5 : 2;
  return price.toLocaleString("ar-EG", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export default function SignalPanel({ signal, currentPrice, symbol, consensus }: Props) {
  const prefix = symbol === "XAUUSD" || symbol === "BTCUSDT" ? "$" : "";

  if (!signal) {
    return (
      <div className="card col-6">
        <div className="card-title">{t.latestSignal}</div>
        <div className="empty-state">
          {consensus?.rejection_reason_ar ? (
            <div className="signal-rejection-inline">{consensus.rejection_reason_ar}</div>
          ) : (
            t.noActiveSignal
          )}
          {consensus?.proposed_direction &&
            consensus.proposed_direction !== "NEUTRAL" &&
            consensus.signal_decision === "blocked" && (
              <div style={{ marginTop: "0.75rem" }}>
                <span className="card-title">{t.proposedDirection}: </span>
                <span className={`signal-direction signal-${consensus.proposed_direction}`}>
                  {translateDirection(consensus.proposed_direction)}
                </span>
                {consensus.proposed_confidence != null && (
                  <span className="mono" style={{ marginRight: "0.5rem" }}>
                    {" "}
                    {(consensus.proposed_confidence * 100).toFixed(1)}%
                  </span>
                )}
              </div>
            )}
          {currentPrice != null && (
            <div style={{ marginTop: "0.5rem" }}>
              <span className="card-title">{t.price} </span>
              <span className="mono metric-value">
                {prefix}
                {formatPrice(currentPrice, symbol)}
              </span>
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
          <div className="value">
            {prefix}
            {formatPrice(signal.entry_price, symbol)}
          </div>
        </div>
        <div className="price-level sl">
          <div className="label">{t.stopLoss}</div>
          <div className="value">
            {prefix}
            {formatPrice(signal.stop_loss, symbol)}
          </div>
        </div>
        <div className="price-level tp">
          <div className="label">{t.takeProfit}</div>
          <div className="value">
            {prefix}
            {formatPrice(signal.take_profit, symbol)}
          </div>
        </div>
      </div>
      {currentPrice != null && (
        <div style={{ marginTop: "0.75rem" }}>
          <span className="card-title">{t.livePrice} </span>
          <span className="mono metric-value">
            {prefix}
            {formatPrice(currentPrice, symbol)}
          </span>
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
