"use client";

import type { KillSwitchState } from "@/types";
import { t, translateKillSwitch } from "@/lib/i18n";

interface Props {
  killSwitch: KillSwitchState;
}

export default function KillSwitchPanel({ killSwitch }: Props) {
  const isActive = killSwitch.status === "ACTIVE";

  return (
    <div className="card col-3">
      <div className="card-title">{t.safetyStatus}</div>
      <div className="kill-switch">
        <div className={`kill-switch-indicator kill-switch-${killSwitch.status}`} />
        <span
          className="mono metric-value"
          style={{ color: isActive ? "var(--red)" : "var(--green)" }}
        >
          {translateKillSwitch(killSwitch.status)}
        </span>
      </div>
      {killSwitch.reason && (
        <div style={{ marginTop: "0.75rem", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
          {killSwitch.reason}
        </div>
      )}
      <div style={{ marginTop: "1rem", fontSize: "0.75rem" }}>
        {killSwitch.drawdown_pct != null && (
          <div>
            <span className="card-title">{t.drawdown} </span>
            <span className="mono">{killSwitch.drawdown_pct.toFixed(2)}%</span>
          </div>
        )}
        {killSwitch.daily_loss_pct != null && (
          <div style={{ marginTop: "0.25rem" }}>
            <span className="card-title">{t.dailyLoss} </span>
            <span className="mono">{killSwitch.daily_loss_pct.toFixed(2)}%</span>
          </div>
        )}
        {killSwitch.consecutive_losses != null && (
          <div style={{ marginTop: "0.25rem" }}>
            <span className="card-title">{t.consecutiveLosses} </span>
            <span className="mono">{killSwitch.consecutive_losses}</span>
          </div>
        )}
      </div>
    </div>
  );
}
