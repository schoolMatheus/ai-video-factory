"""HTTP surface, local trust boundary and honest unavailable capabilities."""

import json
from pathlib import Path

import pytest

from ai_video_factory.run_store import RunStore
from ai_video_factory.ui_backend.app import UiSettings, create_app
from ai_video_factory.ui_backend.session import BootstrapService


class _ClientFactory:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.bootstrap = BootstrapService(tmp_path / "bootstrap.token")

    def client(self, *, authenticated: bool = True, **settings_kwargs):
        from fastapi.testclient import TestClient

        app = create_app(
            UiSettings(
                project_root=self.tmp_path,
                data_root=self.tmp_path / "data",
                **settings_kwargs,
            ),
            bootstrap=self.bootstrap,
        )
        http = TestClient(app, base_url="http://127.0.0.1:8765")
        if authenticated:
            token = self.bootstrap.issue()
            response = http.post(
                "/api/v1/session/bootstrap", json={"token": token}
            )
            assert response.status_code == 204
        return http


@pytest.fixture
def factory(tmp_path: Path) -> _ClientFactory:
    return _ClientFactory(tmp_path)


def _make_run(tmp_path: Path, topic: str = "tema de teste", profile_id: str | None = None):
    store = RunStore(tmp_path / "state", artifact_root=tmp_path / "runs")
    inputs = {"topic": topic}
    if profile_id is not None:
        inputs["profile_id"] = profile_id
    return store.start("research", inputs)


def test_capabilities_snapshot_is_honest(factory: _ClientFactory) -> None:
    response = factory.client().get("/api/v1/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "v1"
    assert payload["legacy_read"] is True
    assert isinstance(payload["profiles"], bool)
    assert isinstance(payload["staged_flow"], bool)
    assert "secret" not in json.dumps(payload).lower()


def test_capabilities_reflect_missing_domain(
    factory: _ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_video_factory.ui_backend import domain

    monkeypatch.setattr(domain, "_available", lambda module_name: False)

    response = factory.client().get("/api/v1/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profiles"] is False
    assert payload["staged_flow"] is False
    assert payload["editor"] is False
    assert payload["stop_control"] is False


def test_unauthenticated_read_is_rejected(factory: _ClientFactory) -> None:
    response = factory.client(authenticated=False).get("/api/v1/capabilities")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_bootstrap_is_single_use_over_http(factory: _ClientFactory) -> None:
    http = factory.client(authenticated=False)
    token = factory.bootstrap.issue()

    assert http.post("/api/v1/session/bootstrap", json={"token": token}).status_code == 204
    assert http.post("/api/v1/session/bootstrap", json={"token": token}).status_code == 401


def test_mutation_requires_csrf(factory: _ClientFactory, tmp_path: Path) -> None:
    http = factory.client()
    run = _make_run(tmp_path)

    response = http.post(
        f"/api/v1/productions/{run.run_id}/actions",
        json={"action": "resume"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_unexpected_host_is_rejected(factory: _ClientFactory) -> None:
    http = factory.client()

    response = http.get("/api/v1/capabilities", headers={"Host": "evil.example"})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_origin"


def test_unexpected_origin_is_rejected(factory: _ClientFactory) -> None:
    http = factory.client()

    response = http.get(
        "/api/v1/capabilities", headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_origin"


def test_nonexistent_profile_is_not_found(factory: _ClientFactory) -> None:
    response = factory.client().get("/api/v1/profiles/does-not-exist")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_cross_profile_results_are_not_returned(factory: _ClientFactory, tmp_path: Path) -> None:
    _make_run(tmp_path, topic="do canal A", profile_id="profile-a")
    _make_run(tmp_path, topic="do canal B", profile_id="profile-b")
    http = factory.client()

    response = http.get("/api/v1/profiles/profile-a/productions")

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["do canal A"]


def test_production_snapshot_and_events(factory: _ClientFactory, tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    http = factory.client()

    snapshot = http.get(f"/api/v1/productions/{run.run_id}")
    events = http.get(f"/api/v1/productions/{run.run_id}/events")

    assert snapshot.status_code == 200
    assert snapshot.json()["mode"] == "legacy"
    assert snapshot.json()["profile_id"] is None
    assert events.status_code == 200
    assert events.json()["items"][0]["type"] == "run_started"


def test_unavailable_action_returns_structured_reason(factory: _ClientFactory, tmp_path: Path) -> None:
    http = factory.client()
    csrf = http.cookies.get("avf_session_csrf")
    run = _make_run(tmp_path)

    response = http.post(
        f"/api/v1/productions/{run.run_id}/actions",
        json={"action": "open_editor"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
    assert response.json()["recoverable"] is True


def test_stage_route_rejects_unknown_stage_name(factory: _ClientFactory, tmp_path: Path) -> None:
    run = _make_run(tmp_path)

    response = factory.client().get(f"/api/v1/productions/{run.run_id}/stages/unknown")

    assert response.status_code == 422


def test_missing_production_returns_not_found(factory: _ClientFactory) -> None:
    response = factory.client().get("/api/v1/productions/" + "0" * 32)

    assert response.status_code == 404


def test_create_production_is_idempotent(
    factory: _ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_video_factory.ui_backend.jobs import JobService

    monkeypatch.setattr(JobService, "_spawn", lambda self, job_id: None)
    http = factory.client()
    csrf = http.cookies.get("avf_session_csrf")
    headers = {"Idempotency-Key": "key-1", "X-CSRF-Token": csrf}
    payload = {"topic": "tema", "profile_id": "canal-a"}

    first = http.post("/api/v1/productions", json=payload, headers=headers)
    second = http.post("/api/v1/productions", json=payload, headers=headers)

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json()["job_id"] == second.json()["job_id"]
    assert http.get(f"/api/v1/jobs/{first.json()['job_id']}").status_code == 200


def test_create_production_requires_idempotency_key(factory: _ClientFactory) -> None:
    http = factory.client()
    response = http.post(
        "/api/v1/productions",
        json={"topic": "tema"},
        headers={"X-CSRF-Token": http.cookies.get("avf_session_csrf")},
    )

    assert response.status_code == 422


def test_expired_cursor_requires_new_snapshot(factory: _ClientFactory, tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    http = factory.client()

    response = http.get(
        f"/api/v1/productions/{run.run_id}/events",
        params={"after_cursor": "invalid-cursor"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "cursor_expired"


def test_sse_stream_continues_from_last_event_id(
    factory: _ClientFactory, tmp_path: Path
) -> None:
    run = _make_run(tmp_path)
    http = factory.client(sse_poll_interval=0.0, sse_max_polls=1, sse_heartbeat_after=99)
    first = http.get(f"/api/v1/productions/{run.run_id}/events").json()
    cursor = first["items"][0]["id"]
    event_path = tmp_path / "state" / "research" / run.run_id / "events.jsonl"
    with event_path.open("a", encoding="utf-8") as events_file:
        events_file.write(
            '{"timestamp":"2026-11-23T00:00:00+00:00","run_id":"'
            + run.run_id
            + '","stage":"research","event":"source_found","fields":{}}\n'
        )

    response = http.get(
        f"/api/v1/productions/{run.run_id}/stream",
        headers={"Last-Event-ID": cursor},
    )

    assert response.status_code == 200
    assert "source_found" in response.text
    assert "run_started" not in response.text
