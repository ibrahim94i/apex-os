"use client";



import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import type { Alert, BacktestResults, MultiAssetDashboard, PerformanceSummary, WSMessage } from "@/types";

import { fetchBacktestResults, fetchMultiDashboard, fetchPerformanceSummary, getStoredAccountMode, getWebSocketUrl, runBacktest, setAccountMode } from "@/lib/api";

import { playAlertSound } from "@/lib/alertSounds";

import { showDesktopNotification } from "@/lib/notifications";

import { t } from "@/lib/i18n";



const SYMBOLS = ["XAUUSD"];



function handleIncomingAlert(

  alert: Alert,

  addToast: (a: Alert) => void,

  setAlerts: Dispatch<SetStateAction<Alert[]>>

) {

  if (!alert.title_ar) return;



  setAlerts((prev) => {

    if (prev.some((a) => a.id === alert.id)) return prev;

    return [alert, ...prev].slice(0, 10);

  });



  if (alert.type === "new_signal" || alert.type === "high_confidence") {

    addToast(alert);

  }



  const sound = alert.play_sound || (alert.severity === "critical" ? "critical" : alert.severity === "warning" ? "warning" : "alert");

  playAlertSound(sound).catch(() => null);

  showDesktopNotification(alert).catch(() => null);

}



export function useMultiDashboard() {

  const [state, setState] = useState<MultiAssetDashboard | null>(null);

  const [backtest, setBacktest] = useState<BacktestResults | null>(null);
  const [performance, setPerformance] = useState<PerformanceSummary | null>(null);

  const [alerts, setAlerts] = useState<Alert[]>([]);

  const [toasts, setToasts] = useState<Alert[]>([]);

  const [connected, setConnected] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [accountLoading, setAccountLoading] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);

  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();



  const addToast = useCallback((alert: Alert) => {

    setToasts((prev) => [alert, ...prev].slice(0, 5));

    setTimeout(() => {

      setToasts((prev) => prev.filter((a) => a.id !== alert.id));

    }, 5000);

  }, []);



  const refreshDashboard = useCallback(() => {

    return fetchMultiDashboard().then(setState);

  }, []);



  const connect = useCallback(() => {

    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(getWebSocketUrl());

    wsRef.current = ws;



    ws.onopen = () => {

      setConnected(true);

      setError(null);

    };



    ws.onmessage = (event) => {

      try {

        const msg: WSMessage = JSON.parse(event.data);

        if (msg.type === "dashboard_update") {

          const single = msg.data as MultiAssetDashboard["assets"][string];

          if (single?.symbol) {

            setState((prev) => {

              if (!prev) return prev;

              const existing = prev.assets[single.symbol];

              const merged = existing

                ? {

                    ...existing,

                    ...single,

                    regime: single.regime ?? existing.regime,

                    current_price: single.current_price ?? existing.current_price,

                    agent_consensus: single.agent_consensus ?? existing.agent_consensus,

                    market_status: single.market_status ?? existing.market_status,

                  }

                : single;

              return {

                ...prev,

                assets: { ...prev.assets, [single.symbol]: merged },

              };

            });

          }

        } else if (msg.type === "multi_dashboard_update") {

          setState(msg.data as MultiAssetDashboard);

        } else if (msg.type === "alert") {

          handleIncomingAlert(msg.data as Alert, addToast, setAlerts);

        } else if (msg.type === "new_signal") {

          const signal = msg.data as MultiAssetDashboard["assets"][string]["latest_signal"];

          if (signal) {

            setState((prev) => {

              if (!prev) return prev;

              const sym = (msg.data as { symbol?: string }).symbol || signal.symbol || "XAUUSD";

              const asset = prev.assets[sym];

              if (!asset) return prev;

              return {

                ...prev,

                assets: {

                  ...prev.assets,

                  [sym]: {

                    ...asset,

                    latest_signal: signal,

                    signal_history: [signal, ...asset.signal_history].slice(0, 20),

                  },

                },

              };

            });

          }

        } else if (msg.type === "regime_update") {

          const regime = msg.data as MultiAssetDashboard["assets"][string]["regime"];

          const sym = (regime as { symbol?: string })?.symbol;

          if (sym && regime) {

            setState((prev) => {

              if (!prev?.assets[sym]) return prev;

              return {

                ...prev,

                assets: { ...prev.assets, [sym]: { ...prev.assets[sym], regime } },

              };

            });

          }

        } else if (msg.type === "kill_switch_update") {

          const ks = msg.data as MultiAssetDashboard["kill_switch"];

          setState((prev) => (prev ? { ...prev, kill_switch: ks } : prev));

        } else if (msg.type === "price_update") {

          const priceData = msg.data as { symbol: string; price: number };

          setState((prev) => {

            const asset = prev?.assets[priceData.symbol];

            if (!asset || asset.market_status?.is_open === false) return prev;

            return {

              ...prev!,

              assets: {

                ...prev!.assets,

                [priceData.symbol]: {

                  ...asset,

                  current_price: priceData.price,

                },

              },

            };

          });

        } else if (msg.type === "agent_consensus_update") {

          const consensus = msg.data as MultiAssetDashboard["assets"][string]["agent_consensus"];

          const sym = (consensus as { symbol?: string })?.symbol;

          if (sym && consensus) {

            setState((prev) => {

              if (!prev?.assets[sym]) return prev;

              return {

                ...prev,

                assets: {

                  ...prev.assets,

                  [sym]: { ...prev.assets[sym], agent_consensus: consensus },

                },

              };

            });

          }

        } else if (msg.type === "market_status_update") {

          const statuses = msg.data as Record<string, MultiAssetDashboard["market_status"][string]>;

          setState((prev) => {

            if (!prev) return prev;

            const assets = { ...prev.assets };

            for (const [sym, status] of Object.entries(statuses)) {

              if (assets[sym]) {

                assets[sym] = { ...assets[sym], market_status: status };

              }

            }

            return { ...prev, assets, market_status: { ...prev.market_status, ...statuses } };

          });

        } else if (msg.type === "hourly_report_update") {

          setState((prev) =>

            prev ? { ...prev, hourly_report: msg.data as MultiAssetDashboard["hourly_report"] } : prev

          );

        } else if (msg.type === "feed_status") {

          const statuses = msg.data as MultiAssetDashboard["feed_status"];

          setState((prev) => (prev ? { ...prev, feed_status: statuses } : prev));

        } else if (msg.type === "memory_patterns_update") {

          const payload = msg.data as {

            patterns: MultiAssetDashboard["memory_patterns"];

            summaries: MultiAssetDashboard["memory_summaries"];

          };

          setState((prev) =>

            prev

              ? {

                  ...prev,

                  memory_patterns: payload.patterns ?? prev.memory_patterns,

                  memory_summaries: payload.summaries ?? prev.memory_summaries,

                }

              : prev

          );

        }

      } catch {

        /* ignore */

      }

    };



    ws.onclose = () => {

      setConnected(false);

      reconnectTimer.current = setTimeout(connect, 2000);

    };



    ws.onerror = () => {

      setError(t.wsError);

      ws.close();

    };

  }, [addToast]);



  useEffect(() => {
    const init = async () => {
      try {
        const stored = getStoredAccountMode();
        await setAccountMode(stored);
        const dash = await fetchMultiDashboard();
        setState(dash);
      } catch (err) {
        setError(err instanceof Error ? err.message : "خطأ");
      }
      fetchBacktestResults().then(setBacktest).catch(() => null);
      fetchPerformanceSummary().then(setPerformance).catch(() => null);
    };
    init();
    connect();
    const pollId = setInterval(() => {
      fetchMultiDashboard()
        .then((dash) => {
          setState((prev) => {
            if (!prev) return dash;
            const assets = { ...prev.assets };
            for (const [sym, asset] of Object.entries(dash.assets)) {
              const existing = assets[sym];
              assets[sym] = existing
                ? {
                    ...existing,
                    ...asset,
                    agent_consensus: asset.agent_consensus ?? existing.agent_consensus,
                    regime: asset.regime ?? existing.regime,
                    current_price: asset.current_price ?? existing.current_price,
                  }
                : asset;
            }
            return { ...dash, assets };
          });
        })
        .catch(() => null);
    }, 90000);
    return () => {
      clearInterval(pollId);
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const switchAccountMode = useCallback(async (mode: "demo" | "real") => {
    setAccountLoading(true);
    try {
      await setAccountMode(mode);
      const dash = await fetchMultiDashboard();
      setState(dash);
    } catch (err) {
      setError(err instanceof Error ? err.message : "فشل تبديل الحساب");
    } finally {
      setAccountLoading(false);
    }
  }, []);

  const updateAccountBalance = useCallback(async (account: import("@/types").AccountMode) => {
    setState((prev) => (prev ? { ...prev, account } : prev));
    try {
      const dash = await fetchMultiDashboard();
      setState(dash);
    } catch {
      /* keep optimistic update */
    }
  }, []);



  const dismissAlert = (id: string) => {

    setAlerts((prev) => prev.filter((a) => a.id !== id));

  };



  const refreshBacktest = useCallback(async () => {

    const results = await runBacktest();

    setBacktest(results);

    await refreshDashboard();

  }, [refreshDashboard]);



  const refreshPerformance = useCallback(async () => {
    const results = await fetchPerformanceSummary();
    setPerformance(results);
  }, []);



  return {

    state,

    backtest,

    performance,

    alerts,

    toasts,

    connected,

    error,

    symbols: SYMBOLS,

    dismissAlert,

    refreshBacktest,

    refreshPerformance,

    refreshDashboard,

    switchAccountMode,
    updateAccountBalance,
    accountLoading,

  };

}


