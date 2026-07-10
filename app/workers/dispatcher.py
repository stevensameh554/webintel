import uuid

from app.workers.celery_app import celery_app

CRAWL_TASK_NAME = "app.workers.tasks.crawl_website"


def enqueue_crawl_job(job_id: uuid.UUID) -> None:
    celery_app.send_task(
        CRAWL_TASK_NAME,
        args=[str(job_id)],
        queue=celery_app.conf.task_default_queue,
        task_id=str(job_id),
    )
