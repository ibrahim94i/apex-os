"use client";

import type { RegimeSnapshot } from "@/types";
import { t, translateRegime } from "@/lib/i18n";

interface Props {
  regime: RegimeSnapshot | null;
}

export default function RegimePanel({ regime }: Props) {
  if (!regime) {
    return (
      <div className="card col-3">
        <div className="card-title">{t.marketRegime}</div>
        <div className="empty-state">{t.awaitingData}</div>
      </div>
    );
  }

  return (
    <div className="card col-3">
      <div className="card-title">{t.marketRegime}</div>
      <div className={`regime-badge regime-${regime.regime}`}>
        {translateRegime(regime.regime)}
      </div>
      <div style={{ marginTop: "1rem" }}>
        <div className="card-title">{t.confidence}</div>
        <div className="metric-value mono">{(regime.confidence * 100).toFixed(1)}%</div>
        <div className="confidence-bar">
          <div
            className="confidence-fill"
            style={{ width: `${regime.confidence * 100}%` }}
          />
        </div>
      </div>
      {regime.adx_value != null && (
        <div style={{ marginTop: "0.75rem" }}>
          <span className="card-title">ADX </span>
          <span className="mono">{regime.adx_value.toFixed(2)}</span>
        </div>
      )}
      {regime.volatility_pct != null && (
        <div style={{ marginTop: "0.25rem" }}>
          <span className="card-title">{t.volatility} </span>
          <span className="mono">{regime.volatility_pct.toFixed(2)}%</span>
        </div>
      )}
    </div>
  );
}
