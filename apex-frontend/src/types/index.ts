export type SignalDirection = "LONG" | "SHORT" | "NEUTRAL";
export type RegimeType =
  | "TRENDING_UP"
  | "TRENDING_DOWN"
  | "RANGING"
  | "VOLATILE"
  | "UNKNOWN";
export type KillSwitchStatus = "ACTIVE" | "INACTIVE";
export type AgentRole = "market_analyst" | "risk" | "news";
export type AlertSeverity = "info" | "warning" | "critical";
export type AlertType =
  | "high_confidence"
  | "kill_switch"
  | "consecutive_losses"
  | "new_signal";

export interface RegimeSnapshot {
  symbol: string;
  timestamp: string;
  regime: RegimeType;
  confidence: number;
  adx_value?: number | null;
  volatility_pct?: number | null;
  trend_strength?: number | null;
}

export interface TradingSignal {
  id?: number | null;
  symbol: string;
  timestamp: string;
  direction: SignalDirection;
  confidence: number;
  entry_price: number;
  entry_zone_low?: number | null;
  entry_zone_high?: number | null;
  stop_loss: number;
  take_profit: number;
  position_size: number;
  regime: RegimeType;
  degraded: boolean;
  degradation_reason?: string | null;
  kill_switch_active: boolean;
  snr_state?: string | null;
  snr_penalty?: number | null;
  snr_explain_ar?: string | null;
}

export interface KillSwitchState {
  status: KillSwitchStatus;
  reason?: string | null;
  triggered_at?: string | null;
  drawdown_pct?: number | null;
  daily_loss_pct?: number | null;
  consecutive_losses?: number | null;
}

export interface AgentVerdict {
  agent_id: AgentRole;
  agent_name_ar: string;
  direction: SignalDirection;
  confidence: number;
  reasoning: string[];
  weight: number;
  latency_ms?: number | null;
  used_llm: boolean;
  error?: string | null;
}

export interface AgentConsensus {
  symbol: string;
  timestamp: string;
  final_direction: SignalDirection;
  final_confidence: number;
  verdicts: AgentVerdict[];
  vote_scores: Record<string, number>;
  reasoning_summary: string[];
  signal_decision?: string | null;
  rejection_reason?: string | null;
  rejection_reason_ar?: string | null;
  proposed_direction?: SignalDirection | null;
  proposed_confidence?: number | null;
  snr_state?: string | null;
  snr_state_ar?: string | null;
  snr_warning_ar?: string | null;
  final_decision?: string | null;
  final_decision_ar?: string | null;
  is_stale?: boolean;
  stale_warning_ar?: string | null;
}

export interface PriceBar {
  symbol: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
}

export interface SNRLevels {
  symbol: string;
  timestamp: string;
  price: number;
  support_1: number | null;
  support_2: number | null;
  support_3: number | null;
  resistance_1: number | null;
  resistance_2: number | null;
  resistance_3: number | null;
  distance_to_support_pct: number | null;
  distance_to_resistance_pct: number | null;
  pivot_high_count?: number;
  pivot_low_count?: number;
}

export interface MarketStatus {
  symbol: string;
  is_open: boolean;
  timezone: string;
  schedule_ar: string;
  next_open_at: string | null;
  next_signal_at: string | null;
  seconds_until_open: number | null;
  seconds_until_next_signal: number | null;
}

export interface HourlyReportAsset {
  symbol: string;
  display_name_ar: string;
  is_market_open: boolean;
  market_direction: string;
  last_signal_direction: string | null;
  last_signal_confidence_pct: number | null;
  agent_recommendation: string | null;
  agent_confidence_pct: number | null;
  summary_ar: string;
}

export interface HourlyReport {
  timestamp: string;
  assets: HourlyReportAsset[];
}

export interface DashboardState {
  regime: RegimeSnapshot | null;
  latest_signal: TradingSignal | null;
  kill_switch: KillSwitchState;
  signal_history: TradingSignal[];
  current_price: number | null;
  symbol: string;
  agent_consensus: AgentConsensus | null;
  market_status: MarketStatus | null;
}

export interface AccountMode {
  mode: "demo" | "real";
  balance: number;
  label_ar: string;
  balance_editable?: boolean;
}

export interface FeedStatus {
  symbol: string;
  status: "connected" | "disconnected" | "reconnecting";
  status_ar: string;
  last_update: string | null;
  age_seconds: number | null;
  consecutive_failures: number;
  detail?: string | null;
}

export interface MultiAssetDashboard {
  assets: Record<string, DashboardState>;
  kill_switch: KillSwitchState;
  memory_patterns: Record<string, MemoryPattern[]>;
  memory_summaries: Record<string, MemorySummary>;
  account: AccountMode;
  active_alerts: Alert[];
  market_status: Record<string, MarketStatus>;
  feed_status: Record<string, FeedStatus>;
  hourly_report: HourlyReport | null;
}

export interface RegimeBacktestStats {
  regime: string;
  total: number;
  wins: number;
  losses: number;
  partials: number;
  win_rate: number;
  avg_rr: number;
}

export interface BacktestResults {
  symbol: string;
  total_signals: number;
  evaluated: number;
  wins: number;
  losses: number;
  partials: number;
  overall_win_rate: number;
  overall_avg_rr: number;
  by_regime: RegimeBacktestStats[];
  best_regime: string | null;
  run_at: string;
}

export interface ConfidenceBucket {
  bucket: string;
  total: number;
  wins: number;
  accuracy: number;
}

export interface RegimePerformance {
  regime: string;
  regime_ar: string;
  total: number;
  wins: number;
  losses: number;
  win_rate: number;
  profit_factor: number;
  expectancy: number;
}

export interface PerformanceSummary {
  total_signals: number;
  evaluated_signals: number;
  overall_win_rate: number;
  daily_win_rate: number;
  profit_factor: number;
  expectancy_per_trade: number;
  max_drawdown_pct: number;
  best_regime: string | null;
  best_regime_ar: string | null;
  worst_regime: string | null;
  worst_regime_ar: string | null;
  by_regime: RegimePerformance[];
  confidence_vs_accuracy: ConfidenceBucket[];
  calibration_status: string;
  calibration_status_ar: string;
  calibration_color: string;
  run_at: string;
}

export interface Alert {
  id: string;
  type: AlertType;
  severity: AlertSeverity;
  title_ar: string;
  message_ar: string;
  symbol?: string | null;
  timestamp: string;
  fullscreen?: boolean;
  play_sound?: "alert" | "warning" | "critical";
  overlay_variant?: "red" | "yellow" | null;
}

export interface MemoryPattern {
  regime: string;
  time_of_day: string;
  win_rate: number;
  avg_rr: number;
  sample_count: number;
}

export interface MemorySummary {
  symbol: string;
  overall_win_rate: number;
  total_samples: number;
  best_regime: string | null;
  best_regime_ar: string | null;
  best_time_of_day: string | null;
  best_time_of_day_ar: string | null;
}

export interface JournalEntryCreate {
  symbol: string;
  direction: SignalDirection;
  entry_price: number;
  exit_price: number;
  stop_loss: number;
  take_profit: number;
  source: "system_signal" | "personal";
  emotion: "confident" | "hesitant" | "fearful";
  result: "win" | "loss" | "neutral";
  notes?: string | null;
}

export type FollowUpAction = "entered" | "lost" | "ignored";

export interface JournalEntry extends JournalEntryCreate {
  id: number;
  follow_up_status: "pending" | "entered" | "lost" | "ignored";
  signal_confidence?: number | null;
  snr_state?: string | null;
  snr_penalty?: number | null;
  pnl: number;
  pnl_pct: number;
  closed_at: string;
  created_at?: string;
}

export interface JournalFollowUp {
  action: FollowUpAction;
  exit_price?: number;
  result?: "win" | "loss";
}

export interface JournalSignalReport {
  total_signals: number;
  entered_count: number;
  ignored_count: number;
  lost_count: number;
  pending_count: number;
  win_rate: number;
  total_profit: number;
  total_loss: number;
  net_pnl: number;
  generated_at: string;
}

export interface JournalSnrAnalytics {
  inside_zone_win_rate: number;
  inside_zone_resolved: number;
  outside_zone_win_rate: number;
  outside_zone_resolved: number;
  unknown_snr_win_rate: number;
  unknown_snr_resolved: number;
  generated_at: string;
}

export interface JournalAnalysis {
  total_trades: number;
  win_rate: number;
  best_time_of_day: string;
  best_time_of_day_ar: string;
  system_losses: number;
  personal_losses: number;
  worse_source_ar: string;
  fearful_losses: number;
  confident_losses: number;
  worse_emotion_ar: string;
  recommendation_ar: string;
  generated_at: string;
  signal_report?: JournalSignalReport | null;
  snr_analytics?: JournalSnrAnalytics | null;
}

export interface PositionManagerStatus {
  account_balance: number;
  daily_loss_limit_usd: number;
  daily_loss_used_usd: number;
  daily_loss_remaining_usd: number;
  risk_per_trade_usd: number;
  losing_trades_today: number;
  additional_trades_allowed: number;
  market_state_ar: string;
  can_trade: boolean;
  message_ar: string;
}

export interface AdvisorMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AdvisorAssetContext {
  symbol: string;
  display_name_ar: string;
  price?: number | null;
  apex_price?: number | null;
  price_timestamp?: string | null;
  price_age_minutes?: number | null;
  apex_price_stale?: boolean;
  price_source?: string | null;
  feed_type?: string | null;
  regime?: string | null;
  regime_confidence?: number | null;
  adx?: number | null;
  rsi?: number | null;
  macd?: number | null;
  macd_signal?: number | null;
  ema_9?: number | null;
  ema_21?: number | null;
  ema_50?: number | null;
  ema_200?: number | null;
  agent_direction?: string | null;
  agent_confidence?: number | null;
  agent_summary?: string | null;
  latest_signal_direction?: string | null;
  latest_signal_confidence?: number | null;
  news_count: number;
  data_complete: boolean;
}

export interface AdvisorChatResponse {
  reply: string;
  symbol?: string | null;
  model: string;
  latency_ms: number;
  web_search_used: boolean;
  apex_context: AdvisorAssetContext[];
  timestamp: string;
}

export interface WSMessage {
  type: string;
  data: unknown;
}

export const ASSET_LABELS: Record<string, string> = {
  BTCUSDT: "بيتكوين",
  XAUUSD: "الذهب",
  EURUSD: "يورو/دولار",
  USDJPY: "دولار/ين",
  GBPUSD: "جنيه/دولار",
};
