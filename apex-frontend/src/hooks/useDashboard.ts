"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DashboardState, WSMessage } from "@/types";
import { fetchDashboard, getWebSocketUrl } from "@/lib/api";
import { t } from "@/lib/i18n";
import { shouldApplyDisplayPriceUpdate } from "@/lib/displayPrice";

export function useDashboard(symbol = "XAUUSD") {
  const [state, setState] = useState<DashboardState | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

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
          setState(msg.data as DashboardState);
        } else if (msg.type === "new_signal") {
          setState((prev) => {
            if (!prev) return prev;
            const signal = msg.data as DashboardState["latest_signal"];
            return {
              ...prev,
              latest_signal: signal,
              signal_history: signal
                ? [signal, ...prev.signal_history].slice(0, 20)
                : prev.signal_history,
            };
          });
        } else if (msg.type === "regime_update") {
          setState((prev) =>
            prev ? { ...prev, regime: msg.data as DashboardState["regime"] } : prev
          );
        } else if (msg.type === "kill_switch_update") {
          setState((prev) =>
            prev ? { ...prev, kill_switch: msg.data as DashboardState["kill_switch"] } : prev
          );
        } else if (msg.type === "price_update") {
          const priceData = msg.data as { price: number };
          setState((prev) =>
            prev ? { ...prev, current_price: priceData.price } : prev
          );
        } else if (msg.type === "display_price_update") {
          const priceData = msg.data as {
            symbol?: string;
            price: number;
            timestamp?: string;
            source?: string;
          };
          setState((prev) => {
            if (!prev) return prev;
            if (
              !shouldApplyDisplayPriceUpdate(prev.display_price_source, priceData.source)
            ) {
              return prev;
            }
            return {
              ...prev,
              display_price: priceData.price,
              display_price_timestamp:
                priceData.timestamp ?? prev.display_price_timestamp,
              display_price_source: priceData.source ?? prev.display_price_source,
            };
          });
        } else if (msg.type === "agent_consensus_update") {
          setState((prev) =>
            prev
              ? { ...prev, agent_consensus: msg.data as DashboardState["agent_consensus"] }
              : prev
          );
        }
      } catch {
        /* ignore malformed messages */
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
  }, []);

  useEffect(() => {
    fetchDashboard(symbol)
      .then(setState)
      .catch((err) => setError(err.message));

    connect();

    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [symbol, connect]);

  return { state, connected, error };
}
