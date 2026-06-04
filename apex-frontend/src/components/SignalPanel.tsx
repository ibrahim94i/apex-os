"use client";

import type { AgentConsensus, TradingSignal } from "@/types";
import { formatAssetPrice, pricePrefix } from "@/lib/formatPrice";
import { t, translateDirection } from "@/lib/i18n";

interface Props {
  signal: TradingSignal | null;
  currentPrice: number | null;
  symbol: string;
  consensus?: AgentConsensus | null;
}

export default function SignalPanel({ signal, currentPrice, symbol, consensus }: Props) {
  const prefix = pricePrefix(symbol);

  const rejectionHeadline =
    !signal && consensus?.signal_decision && consensus.signal_decision !== "none"
      ? consensus.rejection_reason === "ranging_market_wait"
        ? t.signalRejectedRanging
        : consensus.rejection_reason_ar
          ? `🚫 ${consensus.rejection_reason_ar}`
          : null
      : null;

  if (!signal) {
    return (
      <div className="card col-6">
        <div className="card-title">{t.latestSignal}</div>
        <div className="empty-state">
          {rejectionHeadline ? (
            <div className="signal-rejection-inline">{rejectionHeadline}</div>
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
                {formatAssetPrice(currentPrice, symbol)}
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
            {formatAssetPrice(signal.entry_price, symbol)}
          </div>
        </div>
        <div className="price-level sl">
          <div className="label">{t.stopLoss}</div>
          <div className="value">
            {prefix}
            {formatAssetPrice(signal.stop_loss, symbol)}
          </div>
        </div>
        <div className="price-level tp">
          <div className="label">{t.takeProfit}</div>
          <div className="value">
            {prefix}
            {formatAssetPrice(signal.take_profit, symbol)}
          </div>
        </div>
      </div>
      {currentPrice != null && (
        <div style={{ marginTop: "0.75rem" }}>
          <span className="card-title">{t.livePrice} </span>
          <span className="mono metric-value">
            {prefix}
            {formatAssetPrice(currentPrice, symbol)}
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
