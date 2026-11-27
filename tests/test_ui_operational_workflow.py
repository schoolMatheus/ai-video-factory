"""HTTP acceptance, durable jobs and the real coordinator behind the UI."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.stages.review import ReviewStage
from ai_video_factory.ui_backend.app import UiSettings, create_app
from ai_video_factory.ui_backend.jobs import JobService
from ai_video_factory.ui_backend.session import (
    CSRF_COOKIE,
    CSRF_HEADER,
    BootstrapService,
)
from ai_video_factory.ui_backend.worker import execute_job
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    STAGE_ORDER,
    ArtifactRef,
    ClaimEntry,
    EditingBundle,
    EvidenceEntry,
    MediaBundle,
    NarrationBundle,
    ObservationSeed,
    ProductionResult,
    ResearchBundle,
    ScriptBundle,
    StageResult,
)
from ai_video_factory.workflow.orchestrator import run_production


class _ClientFactory:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.bootstrap = BootstrapService(tmp_path / "bootstrap.token")

    def client(self, *, jobs: JobService | None = None) -> TestClient:
        app = create_app(
            UiSettings(project_root=self.tmp_path, data_root=self.tmp_path / "data"),
            bootstrap=self.bootstrap,
        )
        if jobs is not None:
            app.state.services = replace(app.state.services, jobs=jobs)
        http = TestClient(app, base_url="http://127.0.0.1:8787")
        token = self.bootstrap.issue()
        response = http.post("/api/v1/session/bootstrap", json={"token": token})
        assert response.status_code == 204
        csrf = http.cookies.get(CSRF_COOKIE)
        if csrf:
            http.headers[CSRF_HEADER] = csrf
        return http


@pytest.fixture
def factory(tmp_path: Path) -> _ClientFactory:
    return _ClientFactory(tmp_path)


class _DeterministicRunner:
    """A genuine predecessor delivery on disk, with no external services."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, context: Any, inputs: Any) -> StageResult:
        self.calls.append(context.stage)
        directory = Path(context.artifacts_dir)
        directory.mkdir(parents=True, exist_ok=True)
        project = Path(context.project_dir)
        bundle: Any

        if context.stage == "research":
            bundle = ResearchBundle(
                topic=context.topic,
                claims=[ClaimEntry(
                    claim_id="c1", text="Fato", classification="confirmed fact",
                    source_ids=["https://a.example"],
                    evidence=[EvidenceEntry(source_url="https://a.example", quote="trecho")],
                    verified=True,
                )],
                synthesis="# Síntese",
            )
        elif context.stage == "script":
            bundle = ScriptBundle(
                title="Episódio", language="pt-BR", estimated_duration_seconds=1.0,
                scenes=[{
                    "scene_id": "s1", "title": "Cena", "narration_text": "Fala canônica.",
                    "estimated_seconds": 1.0,
                    "shots": [{"shot_id": "sh1", "visual": "v", "claim_refs": ["c1"]}],
                }],
            )
        elif context.stage == "narration":
            audio = directory / "segment.wav"
            audio.write_bytes(b"RIFFfake")
            bundle = NarrationBundle(
                provider="fake", voice="v", language="pt-BR",
                segments=[{
                    "segment_id": "n1", "scene_id": "s1", "shot_id": "sh1",
                    "text": "Fala canônica.",
                    "audio": ArtifactRef.from_path(audio, project, "audio/wav").model_dump(),
                    "start_seconds": 0.0, "duration_seconds": 1.0,
                }],
                spoken_text="Fala canônica.", total_duration_seconds=1.0,
            )
        elif context.stage == "media":
            shot = directory / "shot.mp4"
            shot.write_bytes(b"media")
            file_ref = ArtifactRef.from_path(shot, project, "video/mp4")
            bundle = MediaBundle(
                candidates=[{
                    "candidate_id": "m1", "scene_id": "s1", "shot_id": "sh1",
                    "license": "CC0", "attribution": "Autor", "file": file_ref.model_dump(),
                }],
                selected=[{
                    "scene_id": "s1", "shot_id": "sh1", "candidate_id": "m1",
                    "file": file_ref.model_dump(),
                }],
                rights=[{
                    "candidate_id": "m1", "license": "CC0", "attribution": "Autor",
                    "source_url": "https://a.example",
                }],
            )
        else:
            master = directory / "master.mp4"
            master.write_bytes(b"master")
            bundle = EditingBundle(
                filmcraft_version="test", mode="bridge", project_path="p.fcproj",
                item_map={"sh1": "item-1"},
                master=ArtifactRef.from_path(master, project, "video/mp4").model_dump(),
                observed_state={"offline_media": []},
            )

        path = directory / BUNDLE_FILENAMES[context.stage]
        bundle.save(path)
        return StageResult(
            stage=context.stage,
            attempt=context.attempt,
            artifacts={"bundle": ArtifactRef.from_path(path, project, "application/json")},
            observations=[ObservationSeed(
                type="stage_completed", source="deterministic",
                summary=f"{context.stage} entregue",
                event_key=f"{context.request.production_id}:{context.stage}:completed",
            )],
            effective_config=dict(context.effective_settings),
        )


def _transports() -> dict[str, Any]:
    runner = _DeterministicRunner()
    return {
        **{stage: runner for stage in STAGE_ORDER if stage != "review"},
        "review": ReviewStage(probe=lambda path: {
            "width": 1920, "height": 1080, "duration": 1.0,
        }),
    }


def _profile_store(tmp_path: Path) -> ProfileStore:
    store = ProfileStore(tmp_path / "data" / "profiles" / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
        "operation_budget": {"max_external_calls": 10},
    }))
    return store


def _submit(http: TestClient, key: str, topic: str = "Tema") -> dict[str, Any]:
    response = http.post(
        "/api/v1/productions",
        json={"profile_id": "canal", "topic": topic, "target_minutes": 1 / 60},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_receipt_has_queryable_job_and_production_before_worker_starts(
    factory: _ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(JobService, "_spawn", lambda self, job_id: None)
    http = factory.client()

    receipt = _submit(http, "receipt-key")

    assert http.get(f"/api/v1/jobs/{receipt['job_id']}").status_code == 200
    response = http.get(f"/api/v1/productions/{receipt['production_id']}")
    assert response.status_code == 200
    assert response.json()["mode"] == "staged"
    assert response.json()["state"] == "pending"
    assert response.json()["profile_id"] == "canal"


def test_submission_runs_the_real_coordinator_with_controlled_boundaries(
    factory: _ClientFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(JobService, "_spawn", lambda self, job_id: None)
    _profile_store(tmp_path)
    jobs = JobService(
        tmp_path / "data" / "ui" / "control.sqlite3",
        transports=_transports(),
    )
    http = factory.client(jobs=jobs)

    receipt = _submit(http, "real-run")
    assert jobs.claim(job_id=receipt["job_id"]) is not None

    result = execute_job(jobs, receipt["job_id"], jobs.run_default_executor)

    assert result.status == "completed"
    assert jobs.get_job(receipt["job_id"]).status == "completed"
    project = tmp_path / "data" / "projects" / "canal" / receipt["production_id"]
    assert (project / "state" / "review_result.json").is_file()


def test_action_creates_a_real_queryable_job(
    factory: _ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(JobService, "_spawn", lambda self, job_id: None)
    http = factory.client()
    production = _submit(http, "action-submit")

    response = http.post(
        f"/api/v1/productions/{production['production_id']}/actions",
        json={"action": "resume", "payload": {}},
        headers={"Idempotency-Key": "action-1"},
    )

    assert response.status_code == 200
    receipt = response.json()
    assert receipt["job_id"] != production["production_id"]
    assert http.get(f"/api/v1/jobs/{receipt['job_id']}").status_code == 200


def test_unavailable_action_fails_instead_of_faking_queued(
    factory: _ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(JobService, "_spawn", lambda self, job_id: None)
    http = factory.client()
    production = _submit(http, "editor-submit")

    response = http.post(
        f"/api/v1/productions/{production['production_id']}/actions",
        json={"action": "open_editor", "payload": {}},
        headers={"Idempotency-Key": "action-editor"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"


def test_two_submissions_create_two_queryable_productions(
    factory: _ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(JobService, "_spawn", lambda self, job_id: None)
    http = factory.client()

    first = _submit(http, "two-1", "Tema A")
    second = _submit(http, "two-2", "Tema B")

    assert first["production_id"] != second["production_id"]
    assert http.get(f"/api/v1/productions/{first['production_id']}").status_code == 200
    assert http.get(f"/api/v1/productions/{second['production_id']}").status_code == 200
    listed = http.get("/api/v1/productions").json()["items"]
    assert {item["id"] for item in listed} >= {
        first["production_id"], second["production_id"],
    }


def test_crash_between_persistence_and_spawn_keeps_resources_queryable(
    factory: _ClientFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(self: JobService, job_id: str) -> None:
        raise OSError("spawn failed")

    monkeypatch.setattr(JobService, "_spawn", fail)
    http = factory.client()

    receipt = _submit(http, "crash-submit")

    job = http.get(f"/api/v1/jobs/{receipt['job_id']}")
    assert job.status_code == 200
    assert job.json()["status"] == "unknown"
    assert http.get(f"/api/v1/productions/{receipt['production_id']}").status_code == 200


def test_completion_dispatches_the_next_queued_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = JobService(tmp_path / "data" / "ui" / "control.sqlite3")
    spawns: list[str] = []
    monkeypatch.setattr(jobs, "_spawn", lambda job_id: spawns.append(job_id))
    first = jobs.submit({
        "production_id": "p1", "profile_id": "canal", "topic": "A",
        "angle": "", "target_minutes": 1.0, "seed_source_urls": [],
        "base_dir": str(tmp_path / "projects"),
    }, idempotency_key="dispatch-1")
    second = jobs.submit({
        "production_id": "p2", "profile_id": "canal", "topic": "B",
        "angle": "", "target_minutes": 1.0, "seed_source_urls": [],
        "base_dir": str(tmp_path / "projects"),
    }, idempotency_key="dispatch-2")
    spawns.clear()
    jobs.claim(job_id=first.job_id)
    token = jobs.worker_token(first.job_id)

    jobs.complete(first.job_id, token, "result")

    assert spawns == [second.job_id]


def test_cooperative_stop_ends_coordinator_at_a_safe_point(tmp_path: Path) -> None:
    from ai_video_factory.workflow.models import ProductionRequest

    store = _profile_store(tmp_path)
    runner = _DeterministicRunner()
    request = ProductionRequest.model_validate({
        "production_id": "stop-prod", "profile_id": "canal", "topic": "Tema",
        "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
    })

    class Control:
        def __init__(self) -> None:
            self.stop = False

        def stop_requested(self) -> bool:
            return self.stop

        def checkpoint(self, stage: str) -> None:
            self.stop = True

    control = Control()
    result: ProductionResult = run_production(
        request, store=store,
        runners={stage: runner for stage in STAGE_ORDER},
        control=control,
    )

    assert runner.calls == ["research"]
    assert result.status == "pending"
    assert result.final_stage == "script"
