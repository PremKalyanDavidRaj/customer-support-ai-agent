"""Celery beat scans the durable queue; duplicate deliveries are safe in this demo."""
import os
import sqlite3
from celery import Celery
from dotenv import load_dotenv
from .domain import process_pending

load_dotenv()
celery = Celery('customer_agent', broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
celery.conf.update(
    broker_connection_retry_on_startup=True,
    beat_schedule={'process-return-queue': {'task': 'process_returns', 'schedule': 5.0}},
    task_acks_late=True,
)


@celery.task(name='process_returns', autoretry_for=(sqlite3.OperationalError,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def process_returns():
    return {'processed': process_pending()}
