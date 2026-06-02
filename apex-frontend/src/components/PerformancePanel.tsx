"use client";

import type { PerformanceSummary } from "@/types";
import { t, translateRegime } from "@/lib/i18n";

interface Props {
  performance: PerformanceSummary | null;
  onRefresh?: () => void;
}

const STATUS_CLASS: Record<string, string> = {
  green: "calibration-go",
  yellow: "calibration-adjust",
  red: "calibration-stop",
};

export default function PerformancePanel({ performance, onRefresh }: Props) {
  if (!performance) {
    return (
      <div className="card col-12">
        <div className="card-title">{t.performanceTab}</div>
        <div className="empty-state">{t.awaitingData}</div>
      </div>
    );
  }

  const statusClass = STATUS_CLASS[performance.calibration_color] ?? "calibration-adjust";

  return (
    <div className="card col-12">
      <div className="card-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>{t.performanceTab}</span>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <span className={`calibration-badge ${statusClass}`}>
            {performance.calibration_status_ar}
          </span>
          {onRefresh && (
            <button type="button" className="tab-btn" onClick={onRefresh}>
              {t.refreshPerformance}
            </button>
          )}
        </div>
      </div>

      <div className="backtest-summary">
        <div className="backtest-stat">
          <div className="label">{t.dailyWinRate}</div>
          <div className="metric-value mono">{(performance.daily_win_rate * 100).toFixed(1)}%</div>
        </div>
        <div className="backtest-stat">
          <div className="label">{t.overallWinRate}</div>
          <div className="metric-value mono">{(performance.overall_win_rate * 100).toFixed(1)}%</div>
        </div>
        <div className="backtest-stat">
          <div className="label">{t.profitFactor}</div>
          <div className="metric-value mono">
            {performance.profit_factor >= 999 ? "∞" : performance.profit_factor.toFixed(2)}
          </div>
        </div>
        <div className="backtest-stat">
          <div className="label">{t.maxDrawdown}</div>
          <div className="metric-value mono">{performance.max_drawdown_pct.toFixed(2)}%</div>
        </div>
        <div className="backtest-stat">
          <div className="label">{t.expectancyPerTrade}</div>
          <div className="metric-value mono">{performance.expectancy_per_trade.toFixed(2)}</div>
        </div>
        <div className="backtest-stat">
          <div className="label">{t.evaluatedSignals}</div>
          <div className="metric-value mono">
            {performance.evaluated_signals}/{performance.total_signals}
          </div>
        </div>
      </div>

      {(performance.best_regime_ar || performance.worst_regime_ar) && (
        <div className="backtest-summary" style={{ marginTop: "0.75rem" }}>
          {performance.best_regime_ar && (
            <div className="backtest-stat">
              <div className="label">{t.bestMarketCondition}</div>
              <div className="metric-value">{performance.best_regime_ar}</div>
            </div>
          )}
          {performance.worst_regime_ar && (
            <div className="backtest-stat">
              <div className="label">{t.worstMarketCondition}</div>
              <div className="metric-value">{performance.worst_regime_ar}</div>
            </div>
          )}
        </div>
      )}

      {performance.by_regime.length > 0 && (
        <div className="backtest-table" style={{ marginTop: "1rem" }}>
          <div className="card-subtitle">{t.regimePerformance}</div>
          <div className="signal-row" style={{ fontWeight: 600, fontSize: "0.65rem", color: "var(--text-secondary)" }}>
            <span>{t.marketRegime}</span>
            <span>{t.overallWinRate}</span>
            <span>{t.profitFactor}</span>
            <span>{t.expectancyPerTrade}</span>
            <span>{t.evaluatedSignals}</span>
          </div>
          {performance.by_regime.map((r) => (
            <div key={r.regime} className="signal-row mono">
              <span>{r.regime_ar || translateRegime(r.regime as never)}</span>
              <span>{(r.win_rate * 100).toFixed(0)}%</span>
              <span>{r.profit_factor >= 999 ? "∞" : r.profit_factor.toFixed(2)}</span>
              <span>{r.expectancy.toFixed(2)}</span>
              <span>{r.total}</span>
            </div>
          ))}
        </div>
      )}

      {performance.confidence_vs_accuracy.length > 0 && (
        <div className="backtest-table" style={{ marginTop: "1rem" }}>
          <div className="card-subtitle">{t.confidenceVsAccuracy}</div>
          <div className="signal-row" style={{ fontWeight: 600, fontSize: "0.65rem", color: "var(--text-secondary)" }}>
            <span>{t.confidence}</span>
            <span>{t.evaluatedSignals}</span>
            <span>{t.accuracy}</span>
          </div>
          {performance.confidence_vs_accuracy.map((c) => (
            <div key={c.bucket} className="signal-row mono">
              <span>{c.bucket}</span>
              <span>{c.total}</span>
              <span>{(c.accuracy * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
