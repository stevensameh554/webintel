from uuid import uuid4

import pytest

from app.workers import dispatcher


def test_enqueue_uses_stable_task_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def capture_send_task(name: str, **options: object) -> None:
        calls.append({"name": name, **options})

    monkeypatch.setattr(dispatcher.celery_app, "send_task", capture_send_task)
    job_id = uuid4()

    dispatcher.enqueue_crawl_job(job_id)

    assert calls == [
        {
            "name": dispatcher.CRAWL_TASK_NAME,
            "args": [str(job_id)],
            "queue": "crawl_jobs",
            "task_id": str(job_id),
        }
    ]
