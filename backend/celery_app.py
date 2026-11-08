"""Celery 消息队列配置。"""

import os

from celery import Celery


BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
TIME_LIMIT = int(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "900"))

celery_app = Celery(
    "desktop_inventory",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["backend.tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=TIME_LIMIT,
    task_time_limit=TIME_LIMIT + 60,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)
