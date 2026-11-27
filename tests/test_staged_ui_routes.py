"""Staged productions must reach events and artifacts through the running app."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.ui_backend.app import UiSettings, create_app
from ai_video_factory.ui_backend.jobs import JobService
from ai_video_factory.ui_backend.session import BootstrapService
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    STAGE_ORDER,
    ArtifactRef,
    EditingBundle,
    MediaBundle,
    NarrationBundle,
    ObservationSeed,
    ResearchBundle,
    ScriptBundle,
    StageResult,
)
from ai_video_factory.workflow.orchestrator import run_production


class _Runner:
    def run(self, context, inputs):
        stage = context.stage
        directory = Path(context.artifacts_dir)
        directory.mkdir(parents=True, exist_ok=True)
        project = Path(context.project_dir)
        if stage == "research":
            bundle = ResearchBundle(topic=context.topic, synthesis="síntese")
        elif stage == "script":
            bundle = ScriptBundle(
                title="T", language="pt-BR", estimated_duration_seconds=1.0,
                scenes=[{"scene_id": "s1", "title": "Cena", "narration_text": "fala",
                         "estimated_seconds": 1.0, "shots": [{"shot_id": "sh1", "visual": "v"}]}],
            )
        elif stage == "narration":
            audio = directory / "s.wav"
            audio.write_bytes(b"RIFF")
            bundle = NarrationBundle(
                provider="p", voice="v", language="pt-BR",
                segments=[{"segment_id": "n1", "scene_id": "s1", "shot_id": "sh1", "text": "fala",
                           "audio": ArtifactRef.from_path(audio, project, "audio/wav").model_dump(),
                           "start_seconds": 0.0, "duration_seconds": 1.0}],
                total_duration_seconds=1.0,
            )
        elif stage == "media":
            shot = directory / "s.mp4"
            shot.write_bytes(b"media")
            ref = ArtifactRef.from_path(shot, project, "video/mp4")
            bundle = MediaBundle(
                candidates=[{"candidate_id": "m1", "scene_id": "s1", "shot_id": "sh1",
                             "license": "CC0", "file": ref.model_dump()}],
                selected=[{"scene_id": "s1", "shot_id": "sh1", "candidate_id": "m1",
                           "file": ref.model_dump()}],
            )
        else:
            master = directory / "master.mp4"
            master.write_bytes(b"master")
            bundle = EditingBundle(
                filmcraft_version="t", mode="bridge", project_path="p.fcproj",
                item_map={"sh1": "i1"},
                master=ArtifactRef.from_path(master, project, "video/mp4").model_dump(),
                observed_state={"offline_media": []},
            )
        path = directory / BUNDLE_FILENAMES[stage]
        bundle.save(path)
        return StageResult(
            stage=stage, attempt=context.attempt,
            artifacts={"bundle": ArtifactRef.from_path(path, project, "application/json")},
            observations=[ObservationSeed(
                type="stage_completed", source="test", summary=f"{stage} entregue",
                event_key=f"{context.request.production_id}:{stage}:completed",
            )],
            effective_config=dict(context.effective_settings),
        )


def _client(tmp_path: Path) -> TestClient:
    bootstrap = BootstrapService(tmp_path / "bootstrap.token")
    app = create_app(
        UiSettings(project_root=tmp_path, data_root=tmp_path / "data"),
        bootstrap=bootstrap,
    )
    http = TestClient(app, base_url="http://127.0.0.1:8787")
    token = bootstrap.issue()
    assert http.post("/api/v1/session/bootstrap", json={"token": token}).status_code == 204
    csrf = http.cookies.get("avf_session_csrf")
    if csrf:
        http.headers["X-CSRF-Token"] = csrf
    return http


def _seed_staged_production(tmp_path: Path) -> str:
    store = ProfileStore(tmp_path / "data" / "profiles" / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
        "operation_budget": {"max_external_calls": 10},
    }))
    from ai_video_factory.workflow.models import ProductionRequest

    request = ProductionRequest.model_validate({
        "production_id": "staged-ui", "profile_id": "canal", "topic": "Tema",
        "target_minutes": 1 / 60, "base_dir": str(tmp_path / "data" / "projects"),
    })
    runner = _Runner()
    run_production(request, store=store, runners={stage: runner for stage in STAGE_ORDER})
    jobs = JobService(tmp_path / "data" / "ui" / "control.sqlite3")
    import json

    now = "2026-11-26T00:00:00+00:00"
    jobs.store.submit_transaction(
        "staged-ui-key",
        {
            "job_id": "job-staged-ui", "production_id": "staged-ui",
            "status": "completed", "idempotency_key": "staged-ui-key",
            "payload": "{}", "worker_token": None, "pid": None, "heartbeat_at": None,
            "result_reference": None, "stop_requested": 0, "progress": None,
            "problem": None, "created_at": now, "updated_at": now,
        },
        {
            "production_id": "staged-ui", "profile_id": "canal", "topic": "Tema",
            "job_id": "job-staged-ui", "status": "completed",
            "created_at": now, "updated_at": now,
        },
        now,
    )
    return "staged-ui"


def test_staged_production_events_and_artifacts_are_reachable(tmp_path: Path) -> None:
    production_id = _seed_staged_production(tmp_path)
    http = _client(tmp_path)

    events = http.get(f"/api/v1/productions/{production_id}/events")
    assert events.status_code == 200, events.text
    assert events.json()["items"]

    cursor = events.json()["next_cursor"]
    replay = http.get(
        f"/api/v1/productions/{production_id}/events", params={"after_cursor": cursor}
    )
    assert replay.status_code == 200, replay.text

    artifacts = http.get(f"/api/v1/productions/{production_id}/artifacts")
    assert artifacts.status_code == 200, artifacts.text
    assert artifacts.json()

    artifact_id = artifacts.json()[0]["id"]
    content = http.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert content.status_code in {200, 206}, content.text
