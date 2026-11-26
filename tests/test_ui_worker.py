"""Worker entry point runs independently from any browser connection."""

from pathlib import Path
from typing import Any

import pytest

from ai_video_factory.ui_backend.jobs import JobService, RunControl
from ai_video_factory.ui_backend.worker import execute_job


@pytest.fixture
def jobs(tmp_path: Path) -> JobService:
    return JobService(tmp_path / "data" / "ui" / "control.sqlite3")


def _queued(jobs: JobService) -> str:
    return jobs.submit(
        {"production_id": "production-1", "topic": "tema"},
        idempotency_key="worker-key",
    ).job_id


def test_browser_disconnect_does_not_stop_worker(jobs: JobService) -> None:
    job_id = _queued(jobs)
    jobs.claim(job_id=job_id)

    def executor(payload: dict[str, Any], control: RunControl) -> str:
        return "artifact-reference"

    result = execute_job(jobs, job_id, executor)

    assert result == "artifact-reference"
    assert jobs.get_job(job_id).status == "completed"
    assert jobs.get_job(job_id).result_reference == "artifact-reference"


def test_worker_honors_cooperative_stop(jobs: JobService) -> None:
    job_id = _queued(jobs)
    jobs.claim(job_id=job_id)
    jobs.request_stop(job_id)

    def executor(payload: dict[str, Any], control: RunControl) -> str:
        for index in range(100):
            if control.stop_requested():
                control.checkpoint("script")
                return "stopped-at-safe-point"
        return "should-not-reach"

    result = execute_job(jobs, job_id, executor)

    assert result == "stopped-at-safe-point"
    assert jobs.get_job(job_id).status == "stopped"


def test_worker_failure_is_persisted(jobs: JobService) -> None:
    job_id = _queued(jobs)
    jobs.claim(job_id=job_id)

    def executor(payload: dict[str, Any], control: RunControl) -> str:
        raise RuntimeError("api key=hunter2 falhou")

    with pytest.raises(RuntimeError):
        execute_job(jobs, job_id, executor)

    job = jobs.get_job(job_id)
    assert job.status == "failed"
    assert job.problem is not None
    assert "hunter2" not in job.problem.message


def test_wrong_lease_cannot_complete_job(jobs: JobService) -> None:
    job_id = _queued(jobs)
    jobs.claim(job_id=job_id)

    with pytest.raises(PermissionError):
        execute_job(jobs, job_id, lambda payload, control: "x", worker_token="wrong-token")

    assert jobs.get_job(job_id).status == "running"
