"use client";

import type { PositionManagerStatus } from "@/types";
import { t } from "@/lib/i18n";

interface Props {
  status: PositionManagerStatus | null;
}

export default function PositionManagerPanel({ status }: Props) {
  if (!status) {
    return (
      <div className="card col-12">
        <div className="card-title">{t.positionManager}</div>
        <div className="empty-state">{t.awaitingData}</div>
      </div>
    );
  }

  return (
    <div className={`card col-12 position-manager ${status.can_trade ? "" : "position-blocked"}`}>
      <div className="card-title">{t.positionManager}</div>
      <p className={`position-message ${status.can_trade ? "ok" : "blocked"}`}>
        {status.message_ar}
      </p>
      <div className="position-grid">
        <div className="position-stat">
          <span className="label">{t.accountBalance}</span>
          <span className="mono">${status.account_balance.toLocaleString()}</span>
        </div>
        <div className="position-stat">
          <span className="label">{t.dailyRiskRemaining}</span>
          <span className="mono">${status.daily_loss_remaining_usd.toFixed(2)}</span>
        </div>
        <div className="position-stat">
          <span className="label">{t.riskPerTrade}</span>
          <span className="mono">${status.risk_per_trade_usd.toFixed(2)}</span>
        </div>
        <div className="position-stat">
          <span className="label">{t.tradesAllowedToday}</span>
          <span className="mono">{status.additional_trades_allowed}</span>
        </div>
        <div className="position-stat">
          <span className="label">{t.losingTradesToday}</span>
          <span className="mono">{status.losing_trades_today}</span>
        </div>
        <div className="position-stat">
          <span className="label">{t.marketRegime}</span>
          <span>{status.market_state_ar}</span>
        </div>
      </div>
    </div>
  );
}
