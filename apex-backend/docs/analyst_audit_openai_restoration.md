# Analyst Audit: OpenAI Billing Restoration

## Scope

Audited Market Analyst, Risk Analyst, and News Analyst paths for signal generation,
consensus flow, error handling, and logging after OpenAI billing restoration.

## Findings

### Signal generation

- Market Analyst uses `MarketAnalystAgent.analyze()` with an LLM when configured and
  a deterministic technical fallback otherwise.
- Risk Analyst uses `RiskAgent.analyze()` with an LLM when configured and a
  deterministic risk/kill-switch fallback otherwise.
- News Analyst uses `NewsAgent.analyze()` from the news monitor, factoring headlines,
  feed staleness, and high-impact calendar events.
- `SignalGenerator` now uses 60 bars for runtime signal analysis, matching the
  existing integration tests and allowing H1 signal checks to run with the available
  warm buffer.

### Consensus flow

- H1 consensus runs Market Analyst and Risk Analyst through
  `TeamDiscussionService.analyze_h1()`.
- Fresh News Analyst verdicts are produced by `run_news_monitor_for_symbol()` and
  cached with `set_news_verdict()`.
- `AgentOrchestrator.run_h1()` merges cached News verdicts into H1 Market/Risk
  verdicts and sends them through `AdaptiveWeightedEngine.vote()`.
- Voting preserves the Risk minimum weight, computes signed weighted direction, and
  includes neutral agents as support in confidence calculations.

### Error handling and logging

- OpenAI API errors are logged as `openai_api_error` with status, type, code, message,
  context, and attempt.
- Groq API errors are logged as `groq_api_error`; Groq-primary mode falls back to
  OpenAI when OpenAI is configured.
- 429 handling opens or updates the Redis-backed LLM circuit breaker.
- Market, Risk, News, and combined analyst paths now all catch circuit-open errors and
  fall back to rule-based verdicts with `error` populated on the verdict.
- Optional Redis/PostgreSQL enrichments for cache, memory, candlesticks, SNR, market
  status, and alert deduplication now fail soft where the core feature can continue.

## Verification

- Full backend suite passes: 383 tests.
- Added regression coverage for all three analysts falling back when the LLM circuit
  is open.
- Existing coverage verifies provider routing, Groq-to-OpenAI fallback, team discussion
  parsing/fallback, News rule-based output, weighted consensus, signal generation, and
  XAUUSD readiness.

## Recommendations

- Run one production smoke test with real OpenAI billing restored and
  `LLM_PRIMARY_PROVIDER=openai`: force an H1 agent analysis and confirm
  `agent_analysis_complete`, `used_llm=true`, and `llm_provider=openai`.
- Add operational monitoring for `openai_api_error`, `agent_analysis_llm_fallback`,
  and `news_monitor_complete used_llm=false` so billing or quota regressions are caught
  quickly.
- Consider a scheduled synthetic LLM health probe that records provider, model,
  latency, and circuit state without generating trade signals.
