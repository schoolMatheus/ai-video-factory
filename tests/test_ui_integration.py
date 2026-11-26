"""End-to-end API scenarios with real files and two browser-like clients."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_video_factory.run_store import RunStore
from ai_video_factory.ui_backend.app import UiSettings, create_app
from ai_video_factory.ui_backend.session import BootstrapService


def _client(root: Path) -> TestClient:
    bootstrap = BootstrapService(root / "data" / "ui" / "bootstrap.token")
    app = create_app(UiSettings(project_root=root), bootstrap=bootstrap)
    client = TestClient(app, base_url="http://127.0.0.1:8787")
    token = bootstrap.issue()
    assert client.post("/api/v1/session/bootstrap", json={"token": token}).status_code == 204
    return client


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("avf_session_csrf")}


def test_two_tabs_reuse_one_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_video_factory.ui_backend.jobs import JobService

    spawned: list[str] = []
    monkeypatch.setattr(JobService, "_spawn", lambda self, job_id: spawned.append(job_id))
    first = _client(tmp_path)
    second = _client(tmp_path)

    headers = {**_csrf(first), "Idempotency-Key": "duas-abas"}
    payload = {"topic": "mesmo tema"}
    one = first.post("/api/v1/productions", json=payload, headers=headers)
    two = second.post(
        "/api/v1/productions",
        json=payload,
        headers={**_csrf(second), "Idempotency-Key": "duas-abas"},
    )

    assert one.status_code == two.status_code == 202
    assert one.json()["job_id"] == two.json()["job_id"]
    assert len(spawned) == 1


def test_api_restart_keeps_running_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_video_factory.ui_backend.jobs import JobService

    spawned: list[str] = []
    monkeypatch.setattr(JobService, "_spawn", lambda self, job_id: spawned.append(job_id))
    original = _client(tmp_path)
    receipt = original.post(
        "/api/v1/productions",
        json={"topic": "tema"},
        headers={**_csrf(original), "Idempotency-Key": "restart"},
    ).json()

    restarted = _client(tmp_path)
    job = restarted.get(f"/api/v1/jobs/{receipt['job_id']}")

    assert job.status_code == 200
    assert job.json()["status"] == "queued"
    assert len(spawned) == 1


def test_large_media_is_served_by_range(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "state", artifact_root=tmp_path / "runs")
    run = store.start("research", {"topic": "tema"})
    media = tmp_path / "runs" / run.run_id / "longo.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"x" * 2_000_000)
    store.complete(
        run.run_id, {"video": str(media)}, expected_artifacts={"video": media}
    )
    client = _client(tmp_path)
    artifact_id = client.get(f"/api/v1/productions/{run.run_id}/artifacts").json()[0]["id"]

    response = client.get(
        f"/api/v1/artifacts/{artifact_id}/content",
        headers={"Range": "bytes=0-1023"},
    )

    assert response.status_code == 206
    assert len(response.content) == 1024
    assert "base64" not in response.text[:1]


def test_real_legacy_production_is_visible(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "state", artifact_root=tmp_path / "runs")
    run = store.start("research", {"topic": "Tema real"})
    store.event(run.run_id, "source_found", {"url": "https://example.test/a"})
    client = _client(tmp_path)

    list_response = client.get("/api/v1/productions")
    events_response = client.get(f"/api/v1/productions/{run.run_id}/events")

    assert list_response.json()["items"][0]["title"] == "Tema real"
    assert {event["type"] for event in events_response.json()["items"]} >= {
        "run_started",
        "source_found",
    }
