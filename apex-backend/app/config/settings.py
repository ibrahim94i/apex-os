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
    feed_max_consecutive_failures: int = 3
    feed_recovery_cooldown_seconds: int = 120
    feed_health_interval_seconds: int = 30
    groq_min_request_interval_seconds: float = 10.0
    groq_429_backoff_seconds: float = 30.0
    agent_cache_ttl_seconds: int = 300
    news_block_window_minutes: int = 30
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = ""
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    agent_timeout_seconds: int = 10
    agent_max_retries: int = 2
    agent_circuit_breaker_threshold: int = 3

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
