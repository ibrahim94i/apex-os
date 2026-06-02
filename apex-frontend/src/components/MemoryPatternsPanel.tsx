"use client";

import type { MemoryPattern, MemorySummary } from "@/types";
import { t, translateRegime } from "@/lib/i18n";
import { ASSET_LABELS } from "@/types";

interface Props {
  patterns: Record<string, MemoryPattern[]>;
  summaries?: Record<string, MemorySummary>;
}

const TIME_AR: Record<string, string> = {
  morning: "صباحاً",
  afternoon: "ظهراً",
  evening: "مساءً",
  night: "ليلاً",
};

export default function MemoryPatternsPanel({ patterns, summaries = {} }: Props) {
  const hasData = Object.values(patterns).some((p) => p.length > 0);
  const hasSummary = Object.values(summaries).some((s) => s.total_samples > 0);

  if (!hasData && !hasSummary) {
    return (
      <div className="card col-12">
        <div className="card-title">{t.bestPatterns}</div>
        <div className="empty-state">{t.noPatternsYet}</div>
      </div>
    );
  }

  return (
    <div className="card col-12 memory-patterns-panel">
      <div className="card-title">{t.bestPatterns}</div>

      {Object.entries(summaries).map(([sym, summary]) =>
        summary.total_samples > 0 ? (
          <div key={`sum-${sym}`} className="memory-summary">
            <h3 className="memory-symbol">{ASSET_LABELS[sym] || sym}</h3>
            <div className="memory-summary-grid">
              <div className="memory-summary-item">
                <span className="memory-summary-label">{t.bestRegime}</span>
                <strong>{summary.best_regime_ar || "—"}</strong>
              </div>
              <div className="memory-summary-item">
                <span className="memory-summary-label">{t.bestTimeOfDay}</span>
                <strong>{summary.best_time_of_day_ar || "—"}</strong>
              </div>
              <div className="memory-summary-item">
                <span className="memory-summary-label">{t.overallWinRate}</span>
                <strong className="mono">{(summary.overall_win_rate * 100).toFixed(0)}%</strong>
              </div>
              <div className="memory-summary-item">
                <span className="memory-summary-label">{t.sampleCount}</span>
                <strong className="mono">{summary.total_samples}</strong>
              </div>
            </div>
          </div>
        ) : null
      )}

      {Object.entries(patterns).map(([sym, items]) =>
        items.length > 0 ? (
          <div key={sym} className="memory-section">
            <h3 className="memory-symbol">{ASSET_LABELS[sym] || sym} — {t.topPatterns}</h3>
            {items.map((p, i) => (
              <div key={i} className="memory-row">
                <span>{translateRegime(p.regime as never)}</span>
                <span>{TIME_AR[p.time_of_day] || p.time_of_day}</span>
                <span className="mono">{(p.win_rate * 100).toFixed(0)}%</span>
                <span className="mono">RR {p.avg_rr.toFixed(1)}</span>
                <span className="mono">n={p.sample_count}</span>
              </div>
            ))}
          </div>
        ) : null
      )}
    </div>
  );
}
