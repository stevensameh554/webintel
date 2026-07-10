from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("webintel", broker=settings.redis_url)
celery_app.conf.update(
    task_default_queue=settings.crawl_queue_name,
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
)
