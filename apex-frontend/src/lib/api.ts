const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function deriveWebSocketBase(apiUrl: string): string {
  if (apiUrl.startsWith("https://")) return apiUrl.replace("https://", "wss://");
  if (apiUrl.startsWith("http://")) return apiUrl.replace("http://", "ws://");
  return "ws://localhost:8000";
}

import type {
  AccountMode,
  BacktestResults,
  DashboardState,
  JournalAnalysis,
  JournalEntry,
  JournalEntryCreate,
  JournalFollowUp,
  JournalSignalReport,
  MultiAssetDashboard,
  PositionManagerStatus,
  PerformanceSummary,
  PriceBar,
} from "@/types";

const ACCOUNT_MODE_KEY = "apex_account_mode";

export function getStoredAccountMode(): "demo" | "real" {
  if (typeof window === "undefined") return "demo";
  const v = localStorage.getItem(ACCOUNT_MODE_KEY);
  return v === "real" ? "real" : "demo";
}

export function storeAccountMode(mode: "demo" | "real") {
  localStorage.setItem(ACCOUNT_MODE_KEY, mode);
}

export async function fetchAccountMode(): Promise<AccountMode> {
  const res = await fetch(`${API_URL}/api/v1/account/mode`, { cache: "no-store" });
  if (!res.ok) throw new Error("فشل جلب نوع الحساب");
  return res.json();
}

export async function setAccountMode(mode: "demo" | "real", balance?: number): Promise<AccountMode> {
  const body: { mode: string; balance?: number } = { mode };
  if (balance !== undefined) body.balance = balance;
  const res = await fetch(`${API_URL}/api/v1/account/mode`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("فشل تبديل الحساب");
  storeAccountMode(mode);
  return res.json();
}

export async function setAccountBalance(balance: number): Promise<AccountMode> {
  const res = await fetch(`${API_URL}/api/v1/account/balance`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ balance }),
  });
  if (!res.ok) throw new Error("فشل تحديث الرصيد");
  return res.json();
}

export async function fetchPriceBars(
  symbol: string,
  limit = 200
): Promise<{ symbol: string; bars: PriceBar[] }> {
  const res = await fetch(
    `${API_URL}/api/v1/market/bars?symbol=${symbol}&limit=${limit}`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error("Failed to fetch price bars");
  return res.json();
}

export async function fetchDashboard(symbol = "XAUUSD"): Promise<DashboardState> {
  const res = await fetch(`${API_URL}/api/v1/dashboard?symbol=${symbol}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch dashboard");
  return res.json();
}

export async function fetchMultiDashboard(): Promise<MultiAssetDashboard> {
  const res = await fetch(`${API_URL}/api/v1/dashboard/multi`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch dashboard");
  return res.json();
}

export async function fetchBacktestResults(symbol?: string): Promise<BacktestResults> {
  const q = symbol ? `?symbol=${symbol}` : "";
  const res = await fetch(`${API_URL}/api/v1/backtest/results${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch backtest");
  return res.json();
}

export async function runBacktest(symbol?: string): Promise<BacktestResults> {
  const q = symbol ? `?symbol=${symbol}` : "";
  const res = await fetch(`${API_URL}/api/v1/backtest/run${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to run backtest");
  return res.json();
}

export async function fetchPerformanceSummary(symbol?: string): Promise<PerformanceSummary> {
  const q = symbol ? `?symbol=${symbol}` : "";
  const res = await fetch(`${API_URL}/api/v1/performance/summary${q}`, { cache: "no-store" });
  if (!res.ok) throw new Error("فشل جلب أداء النظام");
  return res.json();
}

export function getWebSocketUrl(): string {
  const wsBase = process.env.NEXT_PUBLIC_WS_URL || deriveWebSocketBase(API_URL);
  return `${wsBase.replace(/\/$/, "")}/ws/dashboard`;
}

export async function fetchJournalEntries(limit = 50): Promise<JournalEntry[]> {
  const res = await fetch(`${API_URL}/api/v1/journal/entries?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error("فشل جلب سجل التداول");
  return res.json();
}

export async function createJournalEntry(
  data: JournalEntryCreate
): Promise<{ entry: JournalEntry; analysis: JournalAnalysis | null }> {
  const res = await fetch(`${API_URL}/api/v1/journal/entries`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("فشل تسجيل الصفقة");
  return res.json();
}

export async function fetchJournalSignalReport(): Promise<JournalSignalReport> {
  const res = await fetch(`${API_URL}/api/v1/journal/signal-report`, { cache: "no-store" });
  if (!res.ok) throw new Error("فشل جلب تقرير الإشارات");
  return res.json();
}

export async function submitJournalFollowUp(
  entryId: number,
  data: JournalFollowUp
): Promise<JournalEntry> {
  const res = await fetch(`${API_URL}/api/v1/journal/entries/${entryId}/follow-up`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "فشل تحديث الإشارة");
  }
  return res.json();
}

export async function fetchJournalAnalysis(): Promise<JournalAnalysis | null> {
  const res = await fetch(`${API_URL}/api/v1/journal/analysis`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) return null;
  const data = await res.json();
  return data ?? null;
}

export async function fetchPositionManagerStatus(
  symbol = "XAUUSD"
): Promise<PositionManagerStatus> {
  const res = await fetch(`${API_URL}/api/v1/position-manager/status?symbol=${symbol}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("فشل جلب مدير المراكز");
  return res.json();
}
