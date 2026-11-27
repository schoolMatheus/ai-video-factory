"""Durable job submission, idempotency, leases and cooperative stop."""

from pathlib import Path

import pytest

from ai_video_factory.ui_backend.jobs import JobService, RunControl
from ai_video_factory.ui_backend.models import (
    ConflictError,
    DependencyUnavailableError,
    InvalidRequestError,
)


@pytest.fixture
def jobs(tmp_path: Path) -> JobService:
    return JobService(tmp_path / "data" / "ui" / "control.sqlite3")


def _request(production_id: str = "production-1") -> dict[str, object]:
    return {"production_id": production_id, "topic": "um tema"}


def test_same_idempotency_key_launches_one_worker(
    jobs: JobService, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawns: list[str] = []
    monkeypatch.setattr(jobs, "_spawn", lambda job_id: spawns.append(job_id))

    first = jobs.submit(_request(), idempotency_key="same-key")
    second = jobs.submit(_request(), idempotency_key="same-key")

    assert first.job_id == second.job_id
    assert spawns == [first.job_id]


def test_api_restart_does_not_relaunch_running_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "data" / "ui" / "control.sqlite3"
    first = JobService(db_path)
    spawns: list[str] = []
    monkeypatch.setattr(first, "_spawn", lambda job_id: spawns.append(job_id))
    receipt = first.submit(_request(), idempotency_key="restart-key")
    first.claim(job_id=receipt.job_id)

    restarted = JobService(db_path)
    monkeypatch.setattr(restarted, "_spawn", lambda job_id: spawns.append(job_id))
    restarted.reconcile()

    assert spawns == [receipt.job_id]
    assert restarted.get_job(receipt.job_id).status == "running"


def test_claim_is_exclusive(jobs: JobService) -> None:
    first = jobs.submit(_request("p1"), idempotency_key="k1")
    jobs.submit(_request("p2"), idempotency_key="k2")

    claimed = jobs.claim(job_id=first.job_id)
    assert claimed is not None
    assert jobs.claim(job_id=first.job_id) is None


def test_queue_allows_only_one_active_job(jobs: JobService) -> None:
    first = jobs.submit(_request("p1"), idempotency_key="k1")
    second = jobs.submit(_request("p2"), idempotency_key="k2")

    assert jobs.get_job(first.job_id).status == "queued"
    assert jobs.get_job(second.job_id).status == "queued"
    assert jobs.claim_next() is not None
    assert jobs.claim_next() is None


def test_cancel_queued_job(jobs: JobService) -> None:
    receipt = jobs.submit(_request(), idempotency_key="cancel-key")

    jobs.cancel_queued(receipt.job_id)

    assert jobs.get_job(receipt.job_id).status == "stopped"
    assert jobs.claim_next() is None


def test_cannot_cancel_running_job(jobs: JobService) -> None:
    receipt = jobs.submit(_request(), idempotency_key="running-key")
    jobs.claim(job_id=receipt.job_id)

    with pytest.raises(ConflictError):
        jobs.cancel_queued(receipt.job_id)


def test_stop_request_is_pending_until_checkpoint(jobs: JobService) -> None:
    receipt = jobs.submit(_request(), idempotency_key="stop-key")
    jobs.claim(job_id=receipt.job_id)
    token = jobs.worker_token(receipt.job_id)

    jobs.request_stop(receipt.job_id)
    assert jobs.get_job(receipt.job_id).status == "stop_requested"
    assert jobs.stop_requested(receipt.job_id, token) is True

    jobs.confirm_stop(receipt.job_id, token)
    assert jobs.get_job(receipt.job_id).status == "stopped"


def test_stop_request_requires_active_job(jobs: JobService) -> None:
    receipt = jobs.submit(_request(), idempotency_key="stop-inactive")

    with pytest.raises(ConflictError):
        jobs.request_stop(receipt.job_id)


def test_launch_failure_is_recorded_and_not_retried(
    jobs: JobService, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(job_id: str) -> None:
        raise OSError("failed to start")

    monkeypatch.setattr(jobs, "_spawn", fail)

    receipt = jobs.submit(_request(), idempotency_key="launch-fail")

    assert jobs.get_job(receipt.job_id).status == "unknown"
    jobs.reconcile()
    assert jobs.get_job(receipt.job_id).status == "unknown"


def test_resume_reuses_same_production(jobs: JobService) -> None:
    first = jobs.submit(_request("same-production"), idempotency_key="k1")
    second = jobs.submit(_request("same-production"), idempotency_key="k2")

    assert first.job_id != second.job_id
    assert jobs.get_job(first.job_id).production_id == "same-production"
    assert jobs.get_job(second.job_id).production_id == "same-production"


def test_missing_idempotency_key_is_rejected(jobs: JobService) -> None:
    with pytest.raises(InvalidRequestError):
        jobs.submit(_request(), idempotency_key="")


def test_action_without_domain_returns_dependency_error(jobs: JobService) -> None:
    receipt = jobs.submit(_request(), idempotency_key="action-key")
    jobs.claim(job_id=receipt.job_id)

    with pytest.raises(DependencyUnavailableError):
        jobs.run_default_executor({"action": "resume"}, None)


def test_control_checkpoint_reports_progress(jobs: JobService) -> None:
    receipt = jobs.submit(_request(), idempotency_key="control-key")
    jobs.claim(job_id=receipt.job_id)
    token = jobs.worker_token(receipt.job_id)
    control: RunControl = jobs.control(receipt.job_id, token)

    control.report_progress("segments", 2, 5)
    control.checkpoint("script")

    assert jobs.get_job(receipt.job_id).status == "running"
