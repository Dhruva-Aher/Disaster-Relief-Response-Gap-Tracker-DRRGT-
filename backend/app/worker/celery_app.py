"""
Celery application: daily ETL schedule + task configuration.

task_acks_late=True:
  The task is acknowledged (removed from Redis queue) only after it
  completes successfully. If the worker crashes mid-pipeline, the task
  re-queues and will be retried on the next available worker.
  Without this, a crashed worker silently drops the task.

task_reject_on_worker_lost=True:
  Pairs with task_acks_late — ensures the message is requeued (not
  discarded) when a worker process dies unexpectedly.

max_retries=2, default_retry_delay=300:
  On ETL failure the task retries twice with a 5-minute gap before
  giving up. This handles transient FEMA API outages (common) without
  running the pipeline in a tight loop.
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("drrgt", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # one task at a time per worker process
    beat_schedule={
        "daily-etl": {
            "task":     "app.worker.celery_app.run_etl",
            "schedule": crontab(hour=6, minute=0),
        },
    },
)


@celery_app.task(
    name="app.worker.celery_app.run_etl",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def run_etl(self):
    from app.etl.pipeline import run_pipeline
    try:
        run_pipeline()
        return "ok"
    except Exception as exc:
        raise self.retry(exc=exc)
