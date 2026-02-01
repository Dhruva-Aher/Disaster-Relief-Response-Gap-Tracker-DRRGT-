"""Celery app: schedules daily ETL ingest."""
from celery import Celery
from celery.schedules import crontab
from app.core.config import get_settings
from app.etl.pipeline import run_pipeline

settings = get_settings()
celery_app = Celery("drrgt", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.beat_schedule = {
    "daily-etl": {"task": "app.worker.celery_app.run_etl", "schedule": crontab(hour=6, minute=0)},
}


@celery_app.task(name="app.worker.celery_app.run_etl")
def run_etl():
    run_pipeline()
    return "ok"
