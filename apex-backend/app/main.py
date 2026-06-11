"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.phase3_routes import phase3_router
from app.api.account_routes import account_router
from app.api.journal_routes import journal_router
from app.api.advisor_routes import advisor_router
from app.api.admin_routes import admin_router
from app.api.websocket_routes import ws_router
from app.config import settings
from app.core.redis_client import close_redis, redis_health_check
from app.services.background_tasks import start_background_tasks
from app.services.hourly_report_service import publish_hourly_report
from app.services.telegram_notifier import telegram_notifier
from app.feeds.history_bootstrap import bootstrap_all_assets, refresh_dashboard_cache
from app.feeds.display_price_manager import display_price_manager
from app.feeds.manager import feed_manager
from app.logging_config import configure_logging, logger

_bg_tasks: list = []


async def _startup_warmup() -> None:
    """Heavy startup — runs in background so Railway healthchecks pass quickly."""
    try:
        await bootstrap_all_assets()
        await refresh_dashboard_cache()
        feed_manager.start_all()
        from app.services.agent_analysis_service import ensure_agent_consensus_for_active_symbols
        from app.services.feed_health_service import run_recovery_cycle

        await ensure_agent_consensus_for_active_symbols()
        await run_recovery_cycle(force=True)
        await publish_hourly_report()

        if telegram_notifier.enabled:
            ok = await telegram_notifier.send_test_message()
            logger.info("telegram_startup_test", sent=ok)
        else:
            logger.warning("telegram_not_configured")

        logger.info("apex_warmup_complete")
    except Exception as exc:
        logger.error("apex_warmup_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _bg_tasks
    configure_logging()
    logger.info("apex_starting", environment=settings.environment)

    from app.services.feed_health_service import mark_app_started

    mark_app_started()
    _bg_tasks = start_background_tasks()
    display_price_manager.start_all()
    asyncio.create_task(_startup_warmup(), name="apex_warmup")

    yield

    for task in _bg_tasks:
        task.cancel()
    await feed_manager.stop_all()
    await display_price_manager.stop_all()
    await close_redis()
    logger.info("apex_shutdown")


app = FastAPI(
    title="APEX Trading Intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(phase3_router, prefix="/api/v1")
app.include_router(journal_router, prefix="/api/v1")
app.include_router(account_router, prefix="/api/v1")
app.include_router(advisor_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(ws_router)


@app.get("/")
async def root() -> dict[str, str]:
    redis_ok = await redis_health_check()
    return {
        "service": "apex-backend",
        "status": "running",
        "redis": "ok" if redis_ok else "error",
    }
