"use client";

import { useCallback, useEffect, useState } from "react";
import type {
  JournalAnalysis,
  JournalEntry,
  JournalEntryCreate,
  JournalFollowUp,
  JournalSignalReport,
  PositionManagerStatus,
} from "@/types";
import {
  createJournalEntry,
  fetchJournalAnalysis,
  fetchJournalEntries,
  fetchJournalSignalReport,
  fetchPositionManagerStatus,
  submitJournalFollowUp,
} from "@/lib/api";
import { formatAssetPrice, pricePrefix } from "@/lib/formatPrice";
import { t, translateDirection } from "@/lib/i18n";
import { ASSET_LABELS } from "@/types";
import PositionManagerPanel from "./PositionManagerPanel";

const EMPTY_FORM: JournalEntryCreate = {
  symbol: "XAUUSD",
  direction: "LONG",
  entry_price: 0,
  exit_price: 0,
  stop_loss: 0,
  take_profit: 0,
  source: "personal",
  emotion: "confident",
  result: "win",
  notes: "",
};

const FOLLOW_UP_AR: Record<string, string> = {
  pending: "بانتظار",
  entered: "دخلت",
  lost: "خسرت",
  ignored: "تجاهلت",
};

const RESULT_AR: Record<string, string> = {
  win: "ربح",
  loss: "خسارة",
  neutral: "محايد",
  pending: "—",
};

interface Props {
  accountMode?: "demo" | "real";
}

export default function TradingJournalPanel({ accountMode = "demo" }: Props) {
  const [form, setForm] = useState<JournalEntryCreate>(EMPTY_FORM);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [report, setReport] = useState<JournalSignalReport | null>(null);
  const [analysis, setAnalysis] = useState<JournalAnalysis | null>(null);
  const [position, setPosition] = useState<PositionManagerStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [followUpId, setFollowUpId] = useState<number | null>(null);
  const [followAction, setFollowAction] = useState<JournalFollowUp["action"] | null>(null);
  const [exitPrice, setExitPrice] = useState("");
  const [outcome, setOutcome] = useState<"win" | "loss">("win");

  const refresh = useCallback(async () => {
    const [list, rep, anal, pos] = await Promise.all([
      fetchJournalEntries(),
      fetchJournalSignalReport(),
      fetchJournalAnalysis(),
      fetchPositionManagerStatus(form.symbol),
    ]);
    setEntries(list);
    setReport(rep);
    setAnalysis(anal);
    setPosition(pos);
  }, [form.symbol, accountMode]);

  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [refresh]);

  const pending = entries.filter((e) => e.follow_up_status === "pending");

  const resetFollowForm = () => {
    setFollowUpId(null);
    setFollowAction(null);
    setExitPrice("");
    setOutcome("win");
  };

  const handleIgnore = async (entryId: number) => {
    setLoading(true);
    setError(null);
    try {
      await submitJournalFollowUp(entryId, { action: "ignored" });
      setSuccess("تم تسجيل تجاهل الإشارة");
      resetFollowForm();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "فشل التحديث");
    } finally {
      setLoading(false);
    }
  };

  const handleFollowSubmit = async (entryId: number) => {
    setLoading(true);
    setError(null);
    try {
      let payload: JournalFollowUp;
      if (followAction === "ignored") {
        payload = { action: "ignored" };
      } else if (followAction === "lost") {
        payload = { action: "lost", exit_price: parseFloat(exitPrice) };
      } else {
        payload = {
          action: "entered",
          exit_price: parseFloat(exitPrice),
          result: outcome,
        };
      }
      await submitJournalFollowUp(entryId, payload);
      setSuccess("تم تحديث الإشارة");
      resetFollowForm();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "فشل التحديث");
    } finally {
      setLoading(false);
    }
  };

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await createJournalEntry(form);
      setSuccess("تم تسجيل الصفقة بنجاح");
      if (res.analysis) setAnalysis(res.analysis);
      setForm({ ...EMPTY_FORM, symbol: form.symbol });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "فشل التسجيل");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="journal-layout">
      <PositionManagerPanel status={position} />

      {error && <div className="form-error col-12">{error}</div>}
      {success && <div className="form-success col-12">{success}</div>}

      {report && (
        <div className="card col-12 journal-signal-report">
          <div className="card-title">{t.signalReport}</div>
          <div className="signal-report-grid">
            <div className="analysis-item">
              <span>{t.totalSignals}</span>
              <strong className="mono">{report.total_signals}</strong>
            </div>
            <div className="analysis-item">
              <span>{t.signalsEntered}</span>
              <strong className="mono">{report.entered_count}</strong>
            </div>
            <div className="analysis-item">
              <span>{t.signalsIgnored}</span>
              <strong className="mono">{report.ignored_count}</strong>
            </div>
            <div className="analysis-item">
              <span>{t.signalsLost}</span>
              <strong className="mono">{report.lost_count}</strong>
            </div>
            <div className="analysis-item">
              <span>{t.signalsPending}</span>
              <strong className="mono">{report.pending_count}</strong>
            </div>
            <div className="analysis-item">
              <span>{t.personalWinRate}</span>
              <strong className="mono">{(report.win_rate * 100).toFixed(0)}%</strong>
            </div>
            <div className="analysis-item">
              <span>{t.totalProfit}</span>
              <strong className="mono text-green">+{report.total_profit.toFixed(2)}</strong>
            </div>
            <div className="analysis-item">
              <span>{t.totalLoss}</span>
              <strong className="mono text-red">-{report.total_loss.toFixed(2)}</strong>
            </div>
            <div className="analysis-item">
              <span>{t.netPnl}</span>
              <strong className={`mono ${report.net_pnl >= 0 ? "text-green" : "text-red"}`}>
                {report.net_pnl >= 0 ? "+" : ""}
                {report.net_pnl.toFixed(2)}
              </strong>
            </div>
          </div>
        </div>
      )}

      <div className="card col-12">
        <div className="card-title">{t.pendingSignals}</div>
        {pending.length === 0 ? (
          <div className="empty-state">{t.noJournalEntries}</div>
        ) : (
          <div className="pending-signals-list">
            {pending.map((entry) => (
              <div key={entry.id} className="pending-signal-card">
                <div className="pending-signal-header">
                  <strong>{ASSET_LABELS[entry.symbol] || entry.symbol}</strong>
                  <span>{translateDirection(entry.direction as never)}</span>
                  <span className="mono">
                    {pricePrefix(entry.symbol)}
                    {formatAssetPrice(entry.entry_price, entry.symbol)}
                  </span>
                  {entry.signal_confidence != null && (
                    <span className="mono">
                      {t.signalConfidenceLabel} {(entry.signal_confidence * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                {followUpId === entry.id ? (
                  <div className="follow-up-form">
                    {followAction === "entered" && (
                      <>
                        <label>
                          {t.closePrice}
                          <input
                            type="number"
                            step="any"
                            required
                            value={exitPrice}
                            onChange={(e) => setExitPrice(e.target.value)}
                          />
                        </label>
                        <label>
                          {t.tradeOutcome}
                          <select
                            value={outcome}
                            onChange={(e) => setOutcome(e.target.value as "win" | "loss")}
                          >
                            <option value="win">ربح</option>
                            <option value="loss">خسارة</option>
                          </select>
                        </label>
                      </>
                    )}
                    {followAction === "lost" && (
                      <label>
                        {t.closePrice}
                        <input
                          type="number"
                          step="any"
                          required
                          value={exitPrice}
                          onChange={(e) => setExitPrice(e.target.value)}
                        />
                      </label>
                    )}
                    <div className="follow-up-actions">
                      <button
                        type="button"
                        className="tab-btn active"
                        disabled={loading}
                        onClick={() => handleFollowSubmit(entry.id)}
                      >
                        {loading ? t.saving : t.saveTrade}
                      </button>
                      <button type="button" className="tab-btn" onClick={resetFollowForm}>
                        إلغاء
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="follow-up-buttons">
                    <button
                      type="button"
                      className="follow-btn follow-entered"
                      onClick={() => {
                        setFollowUpId(entry.id);
                        setFollowAction("entered");
                      }}
                    >
                      ✅ {t.followEntered}
                    </button>
                    <button
                      type="button"
                      className="follow-btn follow-lost"
                      onClick={() => {
                        setFollowUpId(entry.id);
                        setFollowAction("lost");
                      }}
                    >
                      ❌ {t.followLost}
                    </button>
                    <button
                      type="button"
                      className="follow-btn follow-ignored"
                      disabled={loading}
                      onClick={() => void handleIgnore(entry.id)}
                    >
                      ⏭️ {t.followIgnored}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card col-12">
        <div className="card-title">{t.tradeHistory}</div>
        {entries.length === 0 ? (
          <div className="empty-state">{t.noJournalEntries}</div>
        ) : (
          <div className="journal-table">
            <div className="journal-row journal-header">
              <span>{t.time}</span>
              <span>{t.asset}</span>
              <span>{t.direction}</span>
              <span>الحالة</span>
              <span>{t.tradeResult}</span>
              <span>PnL</span>
            </div>
            {entries.map((entry) => (
              <div key={entry.id} className="journal-row">
                <span className="mono">
                  {new Date(entry.closed_at).toLocaleString("ar-IQ", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                <span>{ASSET_LABELS[entry.symbol] || entry.symbol}</span>
                <span>{translateDirection(entry.direction as never)}</span>
                <span>{FOLLOW_UP_AR[entry.follow_up_status] || entry.follow_up_status}</span>
                <span
                  className={
                    entry.result === "win"
                      ? "text-green"
                      : entry.result === "loss"
                        ? "text-red"
                        : ""
                  }
                >
                  {RESULT_AR[entry.result] || entry.result}
                </span>
                <span className={`mono ${entry.pnl >= 0 ? "text-green" : "text-red"}`}>
                  {entry.follow_up_status === "pending" ? "—" : `${entry.pnl >= 0 ? "+" : ""}${entry.pnl.toFixed(2)}`}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {analysis && (
        <div className="card col-12 journal-analysis">
          <div className="card-title">{t.journalAnalysis}</div>
          <p className="analysis-recommendation">{analysis.recommendation_ar}</p>
        </div>
      )}

      <details className="card col-12 journal-manual-details">
        <summary className="card-title">{t.manualTradeOptional}</summary>
        <form className="journal-form" onSubmit={handleManualSubmit}>
          <label>
            {t.asset}
            <select
              value={form.symbol}
              onChange={(e) => setForm({ ...form, symbol: e.target.value })}
            >
              <option value="XAUUSD">{ASSET_LABELS.XAUUSD}</option>
              <option value="EURUSD">{ASSET_LABELS.EURUSD}</option>
              <option value="USDJPY">{ASSET_LABELS.USDJPY}</option>
              <option value="GBPUSD">{ASSET_LABELS.GBPUSD}</option>
            </select>
          </label>
          <label>
            {t.direction}
            <select
              value={form.direction}
              onChange={(e) =>
                setForm({ ...form, direction: e.target.value as JournalEntryCreate["direction"] })
              }
            >
              <option value="LONG">شراء</option>
              <option value="SHORT">بيع</option>
            </select>
          </label>
          <label>
            {t.entry}
            <input
              type="number"
              step="any"
              required
              value={form.entry_price || ""}
              onChange={(e) => setForm({ ...form, entry_price: parseFloat(e.target.value) })}
            />
          </label>
          <label>
            {t.exitPrice}
            <input
              type="number"
              step="any"
              required
              value={form.exit_price || ""}
              onChange={(e) => setForm({ ...form, exit_price: parseFloat(e.target.value) })}
            />
          </label>
          <label>
            {t.stopLoss}
            <input
              type="number"
              step="any"
              required
              value={form.stop_loss || ""}
              onChange={(e) => setForm({ ...form, stop_loss: parseFloat(e.target.value) })}
            />
          </label>
          <label>
            {t.takeProfit}
            <input
              type="number"
              step="any"
              required
              value={form.take_profit || ""}
              onChange={(e) => setForm({ ...form, take_profit: parseFloat(e.target.value) })}
            />
          </label>
          <label>
            {t.tradeResult}
            <select
              value={form.result}
              onChange={(e) =>
                setForm({ ...form, result: e.target.value as JournalEntryCreate["result"] })
              }
            >
              <option value="win">ربح</option>
              <option value="loss">خسارة</option>
              <option value="neutral">محايد</option>
            </select>
          </label>
          <button type="submit" className="tab-btn active" disabled={loading}>
            {loading ? t.saving : t.saveTrade}
          </button>
        </form>
      </details>
    </div>
  );
}
