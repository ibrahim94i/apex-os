"use client";

import { useRef, useState } from "react";
import { postAdvisorChat } from "@/lib/api";
import { t, translateRegime } from "@/lib/i18n";
import type { AdvisorAssetContext, AdvisorMessage, MultiAssetDashboard } from "@/types";
import { ASSET_LABELS } from "@/types";

interface Props {
  symbols: string[];
  dashboardState: MultiAssetDashboard | null;
}

interface ChatEntry {
  role: "user" | "assistant";
  content: string;
  webSearch?: boolean;
  latencyMs?: number;
}

function ContextCard({ ctx }: { ctx: AdvisorAssetContext }) {
  return (
    <div className={`advisor-context-card ${ctx.data_complete ? "" : "incomplete"}`}>
      <div className="advisor-context-header">
        <span className="advisor-context-symbol">{ASSET_LABELS[ctx.symbol] ?? ctx.symbol}</span>
        <span className="mono advisor-context-price">
          {ctx.price != null ? ctx.price.toFixed(ctx.symbol === "XAUUSD" ? 2 : 5) : "—"}
        </span>
        {ctx.price_requires_web && (
          <span className="advisor-stale-badge">بحث ويب</span>
        )}
        {ctx.apex_price_stale && !ctx.price_requires_web && ctx.price_source?.startsWith("live_fallback") && (
          <span className="advisor-stale-badge">APEX قديم</span>
        )}
      </div>
      <div className="advisor-context-meta">
        {ctx.regime && <span>{translateRegime(ctx.regime)}</span>}
        {ctx.rsi != null && <span>RSI {ctx.rsi.toFixed(1)}</span>}
        {ctx.adx != null && <span>ADX {ctx.adx.toFixed(1)}</span>}
        {ctx.agent_direction && (
          <span>
            وكلاء: {ctx.agent_direction}{" "}
            {ctx.agent_confidence != null
              ? `(${(ctx.agent_confidence * 100).toFixed(0)}%)`
              : ""}
          </span>
        )}
      </div>
    </div>
  );
}

function buildContextFromDashboard(
  symbols: string[],
  state: MultiAssetDashboard | null
): AdvisorAssetContext[] {
  if (!state?.assets) return [];
  return symbols.map((sym) => {
    const asset = state.assets[sym];
    const consensus = asset?.agent_consensus;
    return {
      symbol: sym,
      display_name_ar: ASSET_LABELS[sym] ?? sym,
      price: asset?.current_price ?? null,
      regime: asset?.regime?.regime ?? null,
      regime_confidence: asset?.regime?.confidence ?? null,
      adx: asset?.regime?.adx_value ?? null,
      rsi: null,
      macd: null,
      macd_signal: null,
      ema_9: null,
      ema_21: null,
      ema_50: null,
      ema_200: null,
      agent_direction: consensus?.final_direction ?? null,
      agent_confidence: consensus?.final_confidence ?? null,
      agent_summary: consensus?.reasoning_summary?.[0] ?? null,
      latest_signal_direction: asset?.latest_signal?.direction ?? null,
      latest_signal_confidence: asset?.latest_signal?.confidence ?? null,
      news_count: 0,
      data_complete: asset?.current_price != null && asset?.regime != null,
    };
  });
}

export default function SmartAdvisorPanel({ symbols, dashboardState }: Props) {
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState("");
  const [focusSymbol, setFocusSymbol] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastContext, setLastContext] = useState<AdvisorAssetContext[]>(
    () => buildContextFromDashboard(symbols, dashboardState)
  );
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setError(null);
    const userEntry: ChatEntry = { role: "user", content: text };
    setMessages((prev) => [...prev, userEntry]);
    setLoading(true);
    scrollToBottom();

    try {
      const history: AdvisorMessage[] = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const response = await postAdvisorChat(text, {
        symbol: focusSymbol || undefined,
        history,
      });
      setLastContext(response.apex_context);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.reply,
          webSearch: response.web_search_used,
          latencyMs: response.latency_ms,
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : t.advisorError;
      setError(msg);
    } finally {
      setLoading(false);
      setTimeout(scrollToBottom, 100);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const displayContext =
    lastContext.length > 0 ? lastContext : buildContextFromDashboard(symbols, dashboardState);

  return (
    <div className="advisor-layout">
      <aside className="advisor-sidebar card">
        <h2 className="card-title">{t.advisorApexData}</h2>
        <div className="advisor-context-list">
          {displayContext.map((ctx) => (
            <ContextCard key={ctx.symbol} ctx={ctx} />
          ))}
        </div>
      </aside>

      <section className="advisor-main card">
        <div className="advisor-header">
          <div>
            <h2>{t.advisorTitle}</h2>
            <p className="advisor-subtitle">{t.advisorSubtitle}</p>
          </div>
          <div className="advisor-focus">
            <label htmlFor="advisor-focus">{t.advisorFocusAsset}</label>
            <select
              id="advisor-focus"
              value={focusSymbol}
              onChange={(e) => setFocusSymbol(e.target.value)}
            >
              <option value="">{t.advisorAllAssets}</option>
              {symbols.map((sym) => (
                <option key={sym} value={sym}>
                  {ASSET_LABELS[sym] ?? sym}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="advisor-chat">
          {messages.length === 0 && (
            <div className="advisor-empty">{t.advisorEmpty}</div>
          )}
          {messages.map((msg, idx) => (
            <div key={idx} className={`advisor-msg advisor-msg-${msg.role}`}>
              <div className="advisor-msg-content">{msg.content}</div>
              {msg.role === "assistant" && (
                <div className="advisor-msg-meta">
                  {msg.webSearch && <span>{t.advisorWebSearch} ✓</span>}
                  {msg.latencyMs != null && (
                    <span className="mono">{Math.round(msg.latencyMs)}ms</span>
                  )}
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="advisor-msg advisor-msg-assistant">
              <div className="advisor-thinking">{t.advisorThinking}</div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {error && <div className="advisor-error">{error}</div>}

        <div className="advisor-input-row">
          <textarea
            className="advisor-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t.advisorPlaceholder}
            rows={2}
            disabled={loading}
          />
          <button
            type="button"
            className="advisor-send-btn"
            onClick={handleSend}
            disabled={loading || !input.trim()}
          >
            {loading ? "..." : t.advisorSend}
          </button>
        </div>
      </section>
    </div>
  );
}
