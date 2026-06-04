"use client";

import type { HourlyReport } from "@/types";
import { t } from "@/lib/i18n";

interface Props {
  report: HourlyReport | null;
}

export default function HourlyReportPanel({ report }: Props) {
  if (!report) {
    return (
      <div className="card col-12">
        <div className="card-title">{t.hourlyReport}</div>
        <div className="empty-state">{t.awaitingData}</div>
      </div>
    );
  }

  const time = new Date(report.timestamp).toLocaleString("ar-IQ", {
    hour: "2-digit",
    minute: "2-digit",
    day: "numeric",
    month: "short",
  });

  return (
    <div className="card col-12 hourly-report-panel">
      <div className="card-title">
        {t.hourlyReport} <span className="report-time mono">{time}</span>
      </div>
      <div className="hourly-report-list">
        {report.assets?.map((asset) => (
          <div key={asset.symbol} className="hourly-report-item">
            <div className="hourly-report-item-header">
              <strong>{asset.display_name_ar}</strong>
              <span className={`market-badge ${asset.is_market_open ? "badge-open" : "badge-closed"}`}>
                {asset.is_market_open ? t.marketOpen : t.marketClosed}
              </span>
            </div>
            <p className="hourly-report-summary">{asset.summary_ar}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
