"use client";

import { useCallback, useEffect, useState } from "react";
import type {
  JournalAnalysis,
  JournalEntry,
  JournalEntryCreate,
  PositionManagerStatus,
} from "@/types";
import {
  createJournalEntry,
  fetchJournalAnalysis,
  fetchJournalEntries,
  fetchPositionManagerStatus,
} from "@/lib/api";
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

const SOURCE_AR: Record<string, string> = {
  system_signal: "إشارة النظام",
  personal: "قرار شخصي",
};

const EMOTION_AR: Record<string, string> = {
  confident: "واثق",
  hesitant: "متردد",
  fearful: "خائف",
};

const RESULT_AR: Record<string, string> = {
  win: "ربح",
  loss: "خسارة",
  neutral: "محايد",
};

interface Props {
  accountMode?: "demo" | "real";
}

export default function TradingJournalPanel({ accountMode = "demo" }: Props) {
  const [form, setForm] = useState<JournalEntryCreate>(EMPTY_FORM);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [analysis, setAnalysis] = useState<JournalAnalysis | null>(null);
  const [position, setPosition] = useState<PositionManagerStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [list, anal, pos] = await Promise.all([
      fetchJournalEntries(),
      fetchJournalAnalysis(),
      fetchPositionManagerStatus(form.symbol),
    ]);
    setEntries(list);
    setAnalysis(anal);
    setPosition(pos);
  }, [form.symbol, accountMode]);

  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [refresh]);

  const handleSubmit = async (e: React.FormEvent) => {
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

      <div className="card col-12">
        <div className="card-title">{t.registerTrade}</div>
        {error && <div className="form-error">{error}</div>}
        {success && <div className="form-success">{success}</div>}
        <form className="journal-form" onSubmit={handleSubmit}>
          <label>
            {t.asset}
            <select
              value={form.symbol}
              onChange={(e) => setForm({ ...form, symbol: e.target.value })}
            >
              <option value="XAUUSD">{ASSET_LABELS.XAUUSD}</option>
              <option value="EURUSD">{ASSET_LABELS.EURUSD}</option>
              <option value="BTCUSDT">{ASSET_LABELS.BTCUSDT}</option>
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
            {t.tradeSource}
            <select
              value={form.source}
              onChange={(e) =>
                setForm({ ...form, source: e.target.value as JournalEntryCreate["source"] })
              }
            >
              <option value="system_signal">إشارة النظام</option>
              <option value="personal">قرار شخصي</option>
            </select>
          </label>
          <label>
            {t.entryEmotion}
            <select
              value={form.emotion}
              onChange={(e) =>
                setForm({ ...form, emotion: e.target.value as JournalEntryCreate["emotion"] })
              }
            >
              <option value="confident">واثق</option>
              <option value="hesitant">متردد</option>
              <option value="fearful">خائف</option>
            </select>
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
          <label className="journal-notes">
            {t.notes}
            <textarea
              rows={3}
              value={form.notes || ""}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </label>
          <button type="submit" className="tab-btn active" disabled={loading}>
            {loading ? t.saving : t.saveTrade}
          </button>
        </form>
      </div>

      {analysis && (
        <div className="card col-12 journal-analysis">
          <div className="card-title">{t.journalAnalysis}</div>
          <div className="analysis-grid">
            <div className="analysis-item">
              <span>{t.personalWinRate}</span>
              <strong className="mono">{(analysis.win_rate * 100).toFixed(0)}%</strong>
            </div>
            <div className="analysis-item">
              <span>{t.bestTimeOfDay}</span>
              <strong>{analysis.best_time_of_day_ar}</strong>
            </div>
            <div className="analysis-item">
              <span>{t.systemVsPersonal}</span>
              <strong>{analysis.worse_source_ar}</strong>
            </div>
            <div className="analysis-item">
              <span>{t.emotionImpact}</span>
              <strong>{analysis.worse_emotion_ar}</strong>
            </div>
          </div>
          <p className="analysis-recommendation">{analysis.recommendation_ar}</p>
        </div>
      )}

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
              <span>{t.tradeResult}</span>
              <span>{t.tradeSource}</span>
              <span>{t.entryEmotion}</span>
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
                <span className={entry.result === "win" ? "text-green" : entry.result === "loss" ? "text-red" : ""}>
                  {RESULT_AR[entry.result]}
                </span>
                <span>{SOURCE_AR[entry.source]}</span>
                <span>{EMOTION_AR[entry.emotion]}</span>
                <span className={`mono ${entry.pnl >= 0 ? "text-green" : "text-red"}`}>
                  {entry.pnl >= 0 ? "+" : ""}
                  {entry.pnl.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
