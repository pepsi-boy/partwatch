"""Celery app and Beat schedule.

Celery runs functions ("tasks") in separate worker processes. Redis is the broker:
the queue that holds task messages until a worker picks them up. Celery Beat is a
small scheduler process that puts a task on the queue on a fixed interval.
"""

from datetime import timedelta

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery("partwatch", broker=settings.redis_url, include=["app.tasks"])

celery_app.conf.update(
    timezone="UTC",
    # Results live in Postgres (snapshots, job_runs), so no result backend is needed.
    task_ignore_result=True,
    # Ack a message only after the task finishes, so a worker crash mid-task puts the
    # message back on the queue instead of losing it. Safe because tasks are idempotent.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Take one message at a time so a slow task doesn't hold a backlog hostage.
    worker_prefetch_multiplier=1,
    beat_schedule={
        "check-all-prices": {
            "task": "app.tasks.check_all_prices",
            "schedule": timedelta(hours=settings.check_interval_hours),
        },
    },
)
