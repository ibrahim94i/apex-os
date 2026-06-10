from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_postgres_url(url: str) -> str:
    """Railway provides postgresql:// — SQLAlchemy async needs postgresql+asyncpg://."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", ".env.production", "../.env.production"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://apex:apex@localhost:5432/apexdb"
    redis_url: str = "redis://localhost:6379/0"
    binance_ws_url: str = "wss://stream.binance.com:9443/ws/btcusdt@kline_1h"
    twelvedata_api_key: str = ""
    twelvedata_symbol: str = "XAU/USD"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    environment: str = "development"
    log_level: str = "INFO"
    demo_account_balance: float = 10000.0
    real_account_balance: float = 100.0
    account_balance: float = 10000.0  # legacy default = demo
    signal_timeframe: str = "1h"
    min_signal_confidence_pct: float = 70.0
    min_signal_confidence_pct_post_learning: float = 80.0
    selectivity_confidence_floor_pct: float = 70.0
    selectivity_filter_band_max_pct: float = 75.0
    strong_agent_bypass_threshold_pct: float = 75.0
    learning_period_days: int = 14
    high_selectivity_learning_start: str = "2026-05-29"
    signal_cooldown_hours: float = 2.0
    rsi_filter_min: float = 35.0
    rsi_filter_max: float = 65.0
    atr_volatility_floor_ratio: float = 0.5
    adx_trend_clear_threshold: float = 25.0
    calibration_min_signals: int = 30
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    xauusd_min_price_move: float = 0.50
    xauusd_default_spread: float = 0.30
    max_risk_per_trade_pct: float = 1.0
    min_risk_reward_ratio: float = 2.0
    max_drawdown_pct: float = 5.0
    max_daily_loss_pct: float = 2.0
    max_consecutive_losses: int = 3
    feed_staleness_limit_seconds: int = 300
    feed_disconnect_threshold_seconds: int = 60
    feed_startup_grace_seconds: int = 180
    feed_max_consecutive_failures: int = 3
    feed_recovery_cooldown_seconds: int = 120
    feed_health_interval_seconds: int = 30
    llm_min_request_interval_seconds: float = 10.0
    llm_429_backoff_seconds: float = 30.0
    llm_circuit_open_seconds: int = 3600
    agent_symbol_gap_seconds: float = 10.0
    agent_consensus_ttl_seconds: int = 1800
    agent_consensus_last_good_ttl_seconds: int = 86400
    agent_cache_ttl_seconds: int = 300
    h1_agent_cache_ttl_seconds: int = 3600
    news_monitor_interval_seconds: int = 300
    news_verdict_ttl_seconds: int = 3600
    news_block_window_minutes: int = 30
    finnhub_api_key: str = ""
    finnhub_news_limit: int = 5
    finnhub_market_min_gap_seconds: float = 1.0
    news_aggregate_limit: int = 20
    alphavantage_news_enabled: bool = True
    alphavantage_news_limit: int = 15
    finnhub_calendar_cache_ttl_seconds: int = 300
    economic_calendar_pre_event_minutes: int = 30
    economic_calendar_post_event_minutes: int = 15
    economic_calendar_news_warn_minutes: int = 60
    economic_calendar_hours_ahead: int = 24
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    agent_timeout_seconds: int = 30
    agent_max_retries: int = 2
    agent_circuit_breaker_threshold: int = 3
    agent_data_max_age_seconds: int = 300
    twelvedata_stale_retry_count: int = 2
    twelvedata_stale_retry_delay_seconds: float = 5.0
    twelvedata_min_gap_seconds: float = 12.0
    twelvedata_429_recovery_pause_seconds: int = 1800
    twelvedata_daily_credit_limit: int = 800
    alphavantage_api_key: str = ""
    alphavantage_poll_interval_seconds: int = 3600
    alphavantage_min_gap_seconds: float = 12.0
    frankfurter_poll_interval_seconds: int = 180
    fixer_api_key: str = ""
    currencyapi_key: str = ""
    llm_primary_provider: str = "openai"
    emergency_signal_confidence_threshold: float = 0.75
    signal_emission_interval_hours: float = 1.0
    advisor_timeout_seconds: int = 90

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if isinstance(value, str):
            return _normalize_postgres_url(value)
        return value

    @model_validator(mode="after")
    def apply_railway_redis_defaults(self) -> "Settings":
        """Use REDIS_URL for Celery when broker/backend not explicitly set."""
        if self.celery_broker_url == "redis://localhost:6379/1" and self.redis_url != "redis://localhost:6379/0":
            self.celery_broker_url = self.redis_url
        if self.celery_result_backend == "redis://localhost:6379/2" and self.redis_url != "redis://localhost:6379/0":
            self.celery_result_backend = self.redis_url
        return self

    @property
    def allowed_cors_origins(self) -> list[str]:
        origins = [self.frontend_url, "http://localhost:3000"]
        if self.cors_origins:
            origins.extend(part.strip() for part in self.cors_origins.split(",") if part.strip())
        return list(dict.fromkeys(origins))


settings = Settings()
