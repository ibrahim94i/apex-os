"use client";

import type { BacktestResults } from "@/types";
import { t, translateRegime } from "@/lib/i18n";

interface Props {
  results: BacktestResults | null;
  onRefresh?: () => void;
}

export default function BacktestPanel({ results, onRefresh }: Props) {
  if (!results) {
    return (
      <div className="card col-12">
        <div className="card-title">{t.backtestResults}</div>
        <div className="empty-state">{t.awaitingData}</div>
      </div>
    );
  }

  return (
    <div className="card col-12">
      <div className="card-title" style={{ display: "flex", justifyContent: "space-between" }}>
        <span>{t.backtestResults}</span>
        {onRefresh && (
          <button type="button" className="tab-btn" onClick={onRefresh}>
            {t.runBacktest}
          </button>
        )}
      </div>
      <div className="backtest-summary">
        <div className="backtest-stat">
          <div className="label">{t.overallWinRate}</div>
          <div className="metric-value mono">{(results.overall_win_rate * 100).toFixed(1)}%</div>
        </div>
        <div className="backtest-stat">
          <div className="label">{t.avgRR}</div>
          <div className="metric-value mono">{results.overall_avg_rr.toFixed(2)}</div>
        </div>
        <div className="backtest-stat">
          <div className="label">{t.evaluatedSignals}</div>
          <div className="metric-value mono">{results.evaluated}/{results.total_signals}</div>
        </div>
        {results.best_regime && (
          <div className="backtest-stat">
            <div className="label">{t.bestRegime}</div>
            <div className="metric-value">{translateRegime(results.best_regime as never)}</div>
          </div>
        )}
      </div>
      {results.by_regime.length > 0 && (
        <div className="backtest-table">
          <div className="signal-row" style={{ fontWeight: 600, fontSize: "0.65rem", color: "var(--text-secondary)" }}>
            <span>{t.marketRegime}</span>
            <span>{t.overallWinRate}</span>
            <span>{t.avgRR}</span>
            <span>{t.evaluatedSignals}</span>
          </div>
          {results.by_regime.map((r) => (
            <div key={r.regime} className="signal-row mono">
              <span>{translateRegime(r.regime as never)}</span>
              <span>{(r.win_rate * 100).toFixed(0)}%</span>
              <span>{r.avg_rr.toFixed(2)}</span>
              <span>{r.total}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
