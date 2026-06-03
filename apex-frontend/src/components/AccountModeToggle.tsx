"use client";

import { useState } from "react";
import type { AccountMode } from "@/types";
import { setAccountBalance } from "@/lib/api";
import { t } from "@/lib/i18n";

interface Props {
  account: AccountMode | null;
  onSwitch: (mode: "demo" | "real") => void;
  onBalanceUpdated?: (account: AccountMode) => void;
  loading?: boolean;
}

export default function AccountModeToggle({
  account,
  onSwitch,
  onBalanceUpdated,
  loading,
}: Props) {
  const mode = account?.mode ?? "demo";
  const [editBalance, setEditBalance] = useState(false);
  const [balanceInput, setBalanceInput] = useState("");
  const [saving, setSaving] = useState(false);

  const startEdit = () => {
    setBalanceInput(String(account?.balance ?? 100));
    setEditBalance(true);
  };

  const saveBalance = async () => {
    const value = parseFloat(balanceInput);
    if (!Number.isFinite(value) || value <= 0) return;
    setSaving(true);
    try {
      const updated = await setAccountBalance(value);
      onBalanceUpdated?.(updated);
      setEditBalance(false);
    } finally {
      setSaving(false);
    }
  };

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
      {account && !editBalance && (
        <span className="account-balance-badge mono">
          ${account.balance.toLocaleString("en-US")}
          {account.balance_editable && mode === "real" && (
            <button
              type="button"
              className="account-balance-edit-btn"
              onClick={startEdit}
              title="تعديل الرصيد"
            >
              ✎
            </button>
          )}
        </span>
      )}
      {editBalance && account?.balance_editable && (
        <span className="account-balance-edit">
          <input
            type="number"
            min={1}
            step={1}
            value={balanceInput}
            onChange={(e) => setBalanceInput(e.target.value)}
            className="account-balance-input mono"
          />
          <button type="button" disabled={saving} onClick={saveBalance}>
            {saving ? "..." : "حفظ"}
          </button>
          <button type="button" onClick={() => setEditBalance(false)}>
            إلغاء
          </button>
        </span>
      )}
    </div>
  );
}
