"use client";

import type { AccountMode } from "@/types";
import { t } from "@/lib/i18n";

interface Props {
  account: AccountMode | null;
  onSwitch: (mode: "demo" | "real") => void;
  loading?: boolean;
}

export default function AccountModeToggle({ account, onSwitch, loading }: Props) {
  const mode = account?.mode ?? "demo";

  return (
    <div className="account-mode-toggle">
      <span className="account-mode-label">{t.accountMode}:</span>
      <button
        type="button"
        className={`account-mode-btn ${mode === "demo" ? "active demo" : ""}`}
        disabled={loading}
        onClick={() => onSwitch("demo")}
      >
        {t.demoAccount}
      </button>
      <button
        type="button"
        className={`account-mode-btn ${mode === "real" ? "active real" : ""}`}
        disabled={loading}
        onClick={() => onSwitch("real")}
      >
        {t.realAccount}
      </button>
      {account && (
        <span className="account-balance-badge mono">
          ${account.balance.toLocaleString("en-US")}
        </span>
      )}
    </div>
  );
}
