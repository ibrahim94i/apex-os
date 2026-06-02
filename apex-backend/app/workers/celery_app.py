"""Celery application and scheduled tasks."""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "apex",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "evaluate-kill-switch": {
            "task": "app.workers.tasks.evaluate_kill_switch",
            "schedule": 60.0,
        },
        "check-feed-staleness": {
            "task": "app.workers.tasks.check_feed_staleness",
            "schedule": 120.0,
        },
        "cleanup-old-bars": {
            "task": "app.workers.tasks.cleanup_old_bars",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)

celery_app.autodiscover_tasks(["app.workers"])
