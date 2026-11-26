"""Structured actions, editor boundary and cooperative stop reporting."""

from pathlib import Path

import pytest

from ai_video_factory.ui_backend import domain
from ai_video_factory.ui_backend.jobs import JobService
from ai_video_factory.ui_backend.models import (
    ActionName,
    ActionRequest,
    CapabilitiesView,
    DependencyUnavailableError,
    InvalidRequestError,
)


@pytest.fixture
def domain_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        domain,
        "get_capabilities",
        lambda: CapabilitiesView(
            api_version="v1",
            staged_flow=True,
            editor=True,
            stop_control=True,
            profiles=True,
        ),
    )


def test_editor_action_refuses_shell_commands(domain_modules) -> None:
    with pytest.raises(InvalidRequestError):
        domain.execute_action(
            "production-1",
            ActionRequest(
                action=ActionName.open_editor,
                payload={"command": "powershell -c Remove-Item C:\\"},
            ),
        )


def test_open_editor_uses_configured_integration(domain_modules, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domain, "load_filmcraft_config", lambda: object())
    result = domain.execute_action(
        "production-1", ActionRequest(action=ActionName.open_editor)
    )

    assert result.production_id == "production-1"
    assert result.status == "requested"
    assert "worker" in result.note.lower()


def test_open_editor_without_config_is_unavailable(
    domain_modules, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(domain, "load_filmcraft_config", lambda: None)

    with pytest.raises(DependencyUnavailableError):
        domain.execute_action(
            "production-1", ActionRequest(action=ActionName.open_editor)
        )


def test_stop_request_is_not_reported_as_completed_cancellation(
    tmp_path: Path, domain_modules
) -> None:
    jobs = JobService(tmp_path / "control.sqlite3")
    receipt = jobs.submit(
        {"production_id": "stop-production", "topic": "tema"},
        idempotency_key="stop-key",
    )
    jobs.claim(job_id=receipt.job_id)
    jobs.request_stop(receipt.job_id)
    control = jobs.control(receipt.job_id, jobs.worker_token(receipt.job_id))

    result = domain.execute_action(
        "stop-production",
        ActionRequest(action=ActionName.stop_after_stage, payload={"stage": "script"}),
        control=control,
    )

    assert result.status == "stop_requested"
    assert result.status not in {"completed", "cancelled"}


def test_script_revision_invalidates_only_dependents(domain_modules, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        domain,
        "invalidation_plan",
        lambda changed: ["script", "narration", "media", "editing", "review"],
    )
    result = domain.execute_action(
        "production-1",
        ActionRequest(
            action=ActionName.revise_script,
            payload={"scene_id": "cena-1", "new_text": "texto", "reason": "correção"},
        ),
    )

    assert result.invalidated_stages == [
        "script",
        "narration",
        "media",
        "editing",
        "review",
    ]
    assert "research" not in result.invalidated_stages


def test_missing_domain_action_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        domain, "get_capabilities", lambda: CapabilitiesView(api_version="v1")
    )

    with pytest.raises(DependencyUnavailableError):
        domain.execute_action("production-1", ActionRequest(action=ActionName.resume))
