"""Real API/ProfileStore integration: clean install, revisions and scoped memory."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ai_video_factory.profiles.models import (
    EvaluationCheck,
    LearningEvaluation,
    Observation,
    ProfileSpec,
    TypedPatch,
)
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.ui_backend.app import UiSettings, create_app
from ai_video_factory.ui_backend.session import BootstrapService


def _client(tmp_path: Path) -> TestClient:
    bootstrap = BootstrapService(tmp_path / "bootstrap.token")
    app = create_app(
        UiSettings(
            project_root=tmp_path,
            data_root=tmp_path / "data",
            profiles_db=tmp_path / "data" / "profiles" / "profiles.sqlite3",
        ),
        bootstrap=bootstrap,
    )
    http = TestClient(app, base_url="http://127.0.0.1:8787")
    token = bootstrap.issue()
    assert http.post("/api/v1/session/bootstrap", json={"token": token}).status_code == 204
    csrf = http.cookies.get("avf_session_csrf")
    if csrf:
        http.headers["X-CSRF-Token"] = csrf
    return http


def test_first_profile_can_be_created_on_a_clean_install(tmp_path: Path) -> None:
    http = _client(tmp_path)

    response = http.post("/api/v1/profiles", json={
        "profile_id": "canal-a", "name": "Canal A", "language": "pt-BR",
        "niche": "astronomia",
    })

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["name"] == "Canal A"
    assert payload["language"] == "pt-BR"
    assert payload["niche"] == "astronomia"
    assert payload["revision"] == 1
    assert http.get("/api/v1/profiles").json()["items"][0]["id"] == "canal-a"


def test_profile_patch_persists_identity_fields_and_two_saves_work(tmp_path: Path) -> None:
    http = _client(tmp_path)
    http.post("/api/v1/profiles", json={
        "profile_id": "canal-a", "name": "Antigo", "language": "pt-BR", "niche": "velho",
    })

    first = http.patch("/api/v1/profiles/canal-a", json={
        "expected_revision": 1, "name": "Novo nome", "language": "en-US",
        "niche": "nova area", "settings": {"narration.voice": "voz"},
    })
    assert first.status_code == 200, first.text
    second = http.patch("/api/v1/profiles/canal-a", json={
        "expected_revision": first.json()["revision"],
        "name": "Terceiro nome", "settings": {"narration.voice": "outra"},
    })

    assert second.status_code == 200, second.text
    payload = http.get("/api/v1/profiles/canal-a").json()
    assert payload["name"] == "Terceiro nome"
    assert payload["language"] == "en-US"
    assert payload["niche"] == "nova area"
    assert payload["revision"] == 3


def test_conflict_and_not_found_are_translated(tmp_path: Path) -> None:
    http = _client(tmp_path)
    http.post("/api/v1/profiles", json={
        "profile_id": "canal-a", "name": "Canal A", "language": "pt-BR",
    })

    conflict = http.patch("/api/v1/profiles/canal-a", json={
        "expected_revision": 99, "settings": {"narration.voice": "x"},
    })
    missing = http.get("/api/v1/profiles/inexistente")

    assert conflict.status_code == 409
    assert missing.status_code == 404


def test_memory_reports_real_revision_candidates_and_trials(tmp_path: Path) -> None:
    http = _client(tmp_path)
    assert http.post("/api/v1/profiles", json={
        "profile_id": "canal-a", "name": "Canal A", "language": "pt-BR",
    }).status_code == 201
    db = tmp_path / "data" / "profiles" / "profiles.sqlite3"
    store = ProfileStore(db)
    store.record_production("prod-1", "canal-a", "state/run_ids.json")
    store.record_observation(Observation(
        observation_id="obs-1", profile_id="canal-a", production_id="prod-1",
        stage="narration", attempt=1, type="technical_trial", source="stage",
        summary="ensaio", evidence_refs=["artifacts/log.json"], event_key="prod-1:trial",
    ))
    response = http.get("/api/v1/profiles/canal-a/memory")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert any(item["stage"] == "narration" for item in items)
    assert all(item["profile_id"] == "canal-a" for item in items)
    assert all("revision" in item for item in items)
