"""Profile isolation, expected revisions and autonomous memory visibility."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_video_factory.ui_backend.app import UiSettings, UiServices, create_app
from ai_video_factory.ui_backend.jobs import JobService
from ai_video_factory.ui_backend.models import (
    JobStatus,
    MemoryView,
    NotFoundError,
    ProfileView,
)
from ai_video_factory.ui_backend.read_models import ProductionReadModels
from ai_video_factory.ui_backend.session import BootstrapService, SessionService


class FakeProfileAdapter:
    def __init__(self) -> None:
        self.profiles: dict[str, ProfileView] = {
            "canal-a": ProfileView(
                id="canal-a", name="Canal A", revision=1, explicit_fields=["language"]
            ),
            "canal-b": ProfileView(
                id="canal-b", name="Canal B", revision=1, explicit_fields=["language"]
            ),
        }
        self.memory: dict[str, list[MemoryView]] = {
            "canal-a": [
                MemoryView(
                    id="learn-a",
                    profile_id="canal-a",
                    stage="script",
                    state="active",
                    summary="Regra ativa do canal A",
                    origin="inferred",
                    evidence=["evidence-a"],
                )
            ],
            "canal-b": [],
        }
        self.feedback_count = 0

    def list_profiles(self) -> list[ProfileView]:
        return list(self.profiles.values())

    def get_profile(self, profile_id: str) -> ProfileView:
        if profile_id not in self.profiles:
            raise NotFoundError("Perfil não encontrado.")
        return self.profiles[profile_id]

    def create_profile(self, payload: Any) -> ProfileView:
        profile = ProfileView(
            id=payload.profile_id,
            name=payload.name,
            revision=1,
            explicit_fields=payload.explicit_fields,
        )
        self.profiles[profile.id] = profile
        return profile

    def revise_profile(self, profile_id: str, payload: Any) -> ProfileView:
        current = self.get_profile(profile_id)
        expected_revision = payload.expected_revision
        if current.revision != expected_revision:
            from ai_video_factory.ui_backend.models import ConflictError

            raise ConflictError("Revisão do perfil mudou.")
        revised = current.model_copy(
            update={"revision": expected_revision + 1, "settings": payload.settings}
        )
        self.profiles[profile_id] = revised
        return revised

    def list_memory(self, profile_id: str) -> list[MemoryView]:
        self.get_profile(profile_id)
        return self.memory.get(profile_id, [])

    def add_feedback(self, profile_id: str, payload: Any) -> MemoryView:
        self.get_profile(profile_id)
        self.feedback_count += 1
        observation = MemoryView(
            id=f"feedback-{self.feedback_count}",
            profile_id=profile_id,
            state="observed",
            summary=payload.summary,
            origin="observed",
        )
        self.memory.setdefault(profile_id, []).append(observation)
        return observation

    def suspend_learning(
        self, profile_id: str, learning_id: str, expected_revision: int, reason: str
    ) -> MemoryView:
        items = self.memory.get(profile_id, [])
        for index, item in enumerate(items):
            if item.id == learning_id:
                updated = item.model_copy(update={"state": "suspended"})
                items[index] = updated
                return updated
        raise NotFoundError("Aprendizado não encontrado.")


@dataclass
class Harness:
    client: TestClient
    adapter: FakeProfileAdapter


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    bootstrap = BootstrapService(tmp_path / "bootstrap.token")
    bootstrap.issue()
    adapter = FakeProfileAdapter()
    services = UiServices(
        read_models=ProductionReadModels(tmp_path / "state", tmp_path / "runs"),
        sessions=SessionService(b"test-secret"),
        bootstrap=bootstrap,
        jobs=JobService(tmp_path / "data" / "ui" / "control.sqlite3"),
        profiles=adapter,
    )
    app = create_app(UiSettings(project_root=tmp_path), services)
    http = TestClient(app, base_url="http://127.0.0.1:8765")
    response = http.post(
        "/api/v1/session/bootstrap",
        json={"token": (tmp_path / "bootstrap.token").read_text(encoding="ascii")},
    )
    assert response.status_code == 204
    return Harness(http, adapter)


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("avf_session_csrf")}


def test_profiles_are_listed(harness: Harness) -> None:
    response = harness.client.get("/api/v1/profiles")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {"canal-a", "canal-b"}


def test_profile_revision_conflict(harness: Harness) -> None:
    response = harness.client.patch(
        "/api/v1/profiles/canal-a",
        json={"expected_revision": 99, "settings": {"language": "pt-BR"}},
        headers=csrf(harness.client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "revision_conflict"


def test_profile_create_and_revise(harness: Harness) -> None:
    created = harness.client.post(
        "/api/v1/profiles",
        json={"profile_id": "canal-c", "name": "Canal C", "language": "pt-BR"},
        headers=csrf(harness.client),
    )
    assert created.status_code == 201

    revised = harness.client.patch(
        "/api/v1/profiles/canal-c",
        json={"expected_revision": 1, "settings": {"language": "pt-BR"}},
        headers=csrf(harness.client),
    )
    assert revised.status_code == 200
    assert revised.json()["revision"] == 2


def test_memory_is_scoped_per_profile(harness: Harness) -> None:
    first = harness.client.get("/api/v1/profiles/canal-a/memory")
    second = harness.client.get("/api/v1/profiles/canal-b/memory")

    assert [item["id"] for item in first.json()["items"]] == ["learn-a"]
    assert second.json()["items"] == []


def test_feedback_creates_observation_without_approval_queue(harness: Harness) -> None:
    response = harness.client.post(
        "/api/v1/profiles/canal-b/feedback",
        json={"summary": "A narração ficou lenta", "stage": "narration"},
        headers=csrf(harness.client),
    )

    assert response.status_code == 201
    memory = harness.client.get("/api/v1/profiles/canal-b/memory").json()
    assert any(item["state"] == "observed" for item in memory["items"])
    assert all("approval_required" not in item for item in memory["items"])


def test_suspend_learning_uses_versioned_service(harness: Harness) -> None:
    response = harness.client.post(
        "/api/v1/profiles/canal-a/memory/learn-a/suspend",
        json={"reason": "regra temporariamente inválida", "expected_revision": 1},
        headers=csrf(harness.client),
    )

    assert response.status_code == 200
    assert response.json()["state"] == "suspended"
