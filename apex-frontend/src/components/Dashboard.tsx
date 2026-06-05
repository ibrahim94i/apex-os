"use client";

import { useState } from "react";
import { useMultiDashboard } from "@/hooks/useMultiDashboard";
import { ASSET_LABELS } from "@/types";
import { t } from "@/lib/i18n";
import KillSwitchPanel from "./KillSwitchPanel";
import AssetColumn from "./AssetColumn";
import BacktestPanel from "./BacktestPanel";
import HourlyReportPanel from "./HourlyReportPanel";
import MemoryPatternsPanel from "./MemoryPatternsPanel";
import AlertBanner from "./AlertBanner";
import AlertOverlay from "./AlertOverlay";
import ToastContainer from "./ToastContainer";
import AccountModeToggle from "./AccountModeToggle";
import PerformancePanel from "./PerformancePanel";
import TradingJournalPanel from "./TradingJournalPanel";
import FeedStatusPanel from "./FeedStatusPanel";
import SmartAdvisorPanel from "./SmartAdvisorPanel";

type Tab = "trading" | "backtest" | "journal" | "performance" | "advisor";

const DEFAULT_ASSET = "XAUUSD";

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>("trading");
  const [selectedAsset, setSelectedAsset] = useState(DEFAULT_ASSET);
  const {
    state,
    backtest,
    alerts,
    toasts,
    connected,
    error,
    symbols,
    dismissAlert,
    refreshBacktest,
    refreshPerformance,
    performance,
    switchAccountMode,
    updateAccountBalance,
    accountLoading,
  } = useMultiDashboard();

  return (
    <div className="dashboard">
      <AlertOverlay alerts={alerts} onDismiss={dismissAlert} />
      <AlertBanner alerts={alerts} onDismiss={dismissAlert} />
      <ToastContainer toasts={toasts} />

      <header className="dashboard-header">
        <h1>APEX OS v2.0</h1>
        <div className="dashboard-tabs">
          <button
            type="button"
            className={`tab-btn ${tab === "trading" ? "active" : ""}`}
            onClick={() => setTab("trading")}
          >
            {t.tradingTab}
          </button>
          <button
            type="button"
            className={`tab-btn ${tab === "backtest" ? "active" : ""}`}
            onClick={() => setTab("backtest")}
          >
            {t.backtestResults}
          </button>
          <button
            type="button"
            className={`tab-btn ${tab === "journal" ? "active" : ""}`}
            onClick={() => setTab("journal")}
          >
            {t.journalTab}
          </button>
          <button
            type="button"
            className={`tab-btn ${tab === "performance" ? "active" : ""}`}
            onClick={() => setTab("performance")}
          >
            {t.performanceTab}
          </button>
          <button
            type="button"
            className={`tab-btn ${tab === "advisor" ? "active" : ""}`}
            onClick={() => setTab("advisor")}
          >
            {t.advisorTab}
          </button>
        </div>
        <AccountModeToggle
          account={state?.account ?? null}
          onSwitch={switchAccountMode}
          onBalanceUpdated={updateAccountBalance}
          loading={accountLoading}
        />
        <div className="connection-status">
          <div className={`connection-dot ${connected ? "connected" : ""}`} />
          <span>{connected ? t.live : t.reconnecting}</span>
          {error && <span style={{ color: "var(--red)" }}> — {error}</span>}
        </div>
      </header>

      {tab === "trading" && (
        <>
          <div className="grid">
            <KillSwitchPanel killSwitch={state?.kill_switch ?? { status: "INACTIVE" }} />
            <FeedStatusPanel
              feedStatus={state?.feed_status ?? {}}
              symbols={symbols}
            />
          </div>
          <nav className="asset-tabs" aria-label="اختيار الأصل">
            {symbols.map((sym) => (
              <button
                key={sym}
                type="button"
                className={`asset-tab-btn ${selectedAsset === sym ? "active" : ""}`}
                onClick={() => setSelectedAsset(sym)}
                aria-selected={selectedAsset === sym}
              >
                {ASSET_LABELS[sym] ?? sym}
              </button>
            ))}
          </nav>
          <div className="asset-tab-content">
            <AssetColumn
              symbol={selectedAsset}
              state={state?.assets[selectedAsset] ?? null}
              hideTitle
            />
          </div>
          <div className="grid">
            <HourlyReportPanel report={state?.hourly_report ?? null} />
            <MemoryPatternsPanel
              patterns={state?.memory_patterns ?? {}}
              summaries={state?.memory_summaries ?? {}}
            />
          </div>
        </>
      )}

      {tab === "backtest" && (
        <div className="grid">
          <BacktestPanel results={backtest} onRefresh={refreshBacktest} />
        </div>
      )}

      {tab === "journal" && (
        <div className="grid">
          <TradingJournalPanel accountMode={state?.account?.mode ?? "demo"} />
        </div>
      )}

      {tab === "performance" && (
        <div className="grid">
          <PerformancePanel performance={performance} onRefresh={refreshPerformance} />
        </div>
      )}

      {tab === "advisor" && (
        <SmartAdvisorPanel symbols={symbols} dashboardState={state} />
      )}
    </div>
  );
}
