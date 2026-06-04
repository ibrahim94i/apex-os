"use client";

import { useState } from "react";
import type { AgentConsensus, AgentVerdict, RegimeSnapshot } from "@/types";
import { t, translateDirection, translateRegime } from "@/lib/i18n";

interface Props {
  consensus: AgentConsensus | null;
  regime?: RegimeSnapshot | null;
}

function formatCollectiveConfidence(consensus: AgentConsensus): string {
  if (consensus.signal_decision === "blocked" || consensus.signal_decision === "wait") {
    return "0.0%";
  }
  return `${(consensus.final_confidence * 100).toFixed(1)}%`;
}

function getRejectionHeadline(
  consensus: AgentConsensus,
  regime: RegimeSnapshot | null | undefined
): string | null {
  if (consensus.signal_decision !== "blocked" && consensus.signal_decision !== "wait") {
    return null;
  }
  if (regime?.regime === "RANGING" || consensus.rejection_reason === "ranging_market_wait") {
    return t.signalRejectedRanging;
  }
  if (consensus.rejection_reason_ar) {
    return `🚫 ${consensus.rejection_reason_ar}`;
  }
  return `🚫 ${t.signalRejected}`;
}

function AgentCard({ verdict }: { verdict: AgentVerdict }) {
  const [open, setOpen] = useState(true);
  const agentPct = `${(verdict.confidence * 100).toFixed(0)}%`;

  return (
    <div className="agent-card">
      <button
        type="button"
        className="agent-card-header"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <div className="agent-card-title">
          <span className="agent-name">{verdict.agent_name_ar}</span>
          <span className={`signal-direction signal-${verdict.direction}`}>
            {translateDirection(verdict.direction)}
          </span>
          <span className="mono agent-confidence">{agentPct}</span>
        </div>
        <span className="agent-toggle">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="agent-card-body">
          <div className="agent-meta">
            <span>{t.voteWeight}: {(verdict.weight * 100).toFixed(0)}%</span>
            <span>{verdict.used_llm ? t.llmPowered : t.ruleBased}</span>
            {verdict.latency_ms != null && (
              <span className="mono">{verdict.latency_ms.toFixed(0)}ms</span>
            )}
          </div>
          <ul className="reasoning-list">
            {verdict.reasoning.map((reason, idx) => (
              <li key={idx}>{reason}</li>
            ))}
          </ul>
          {verdict.error && <div className="agent-error">{verdict.error}</div>}
        </div>
      )}
    </div>
  );
}

export default function ReasoningPanel({ consensus, regime }: Props) {
  if (!consensus || consensus.verdicts.length === 0) {
    return (
      <div className="card col-12">
        <div className="card-title">{t.reasoningPanel}</div>
        <div className="empty-state">{t.noAgentData}</div>
      </div>
    );
  }

  const rejectionHeadline = getRejectionHeadline(consensus, regime);
  const displayDirection = consensus.proposed_direction ?? consensus.final_direction;

  return (
    <div className="card col-12">
      <div className="card-title">{t.reasoningPanel}</div>

      {rejectionHeadline && (
        <div className="signal-rejection-banner">{rejectionHeadline}</div>
      )}

      <div className="consensus-summary">
        <span className="card-title">{t.collectiveDecision}: </span>
        <span className={`signal-direction signal-${displayDirection}`}>
          {translateDirection(displayDirection)}
        </span>
        <span className="mono metric-value" style={{ marginRight: "0.5rem" }}>
          {formatCollectiveConfidence(consensus)}
        </span>
        {regime && (
          <span className="proposed-confidence">
            ({translateRegime(regime.regime)})
          </span>
        )}
      </div>

      {consensus.reasoning_summary.length > 0 && (
        <div className="consensus-breakdown">
          {consensus.reasoning_summary.map((line, idx) => (
            <div key={idx} className="consensus-line">
              {line}
            </div>
          ))}
        </div>
      )}

      <div className="agent-cards">
        {consensus.verdicts.map((verdict) => (
          <AgentCard key={verdict.agent_id} verdict={verdict} />
        ))}
      </div>
    </div>
  );
}
