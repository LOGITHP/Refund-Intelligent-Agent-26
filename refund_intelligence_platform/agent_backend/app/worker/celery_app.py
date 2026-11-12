"""Celery application configuration and Beat schedule for background refund intelligence."""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "refund_intelligence_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_hijack_root_logger=False,
    beat_schedule={
        "poll-due-followups-every-5m": {
            "task": "app.worker.tasks.poll_due_followups_task",
            "schedule": 300.0,
        },
        "reconcile-pending-paypal-refunds-every-10m": {
            "task": "app.worker.tasks.reconcile_pending_paypal_refunds_task",
            "schedule": 600.0,
        },
        "detect-overdue-cases-every-15m": {
            "task": "app.worker.tasks.detect_overdue_cases_task",
            "schedule": 900.0,
        },
    },
)
