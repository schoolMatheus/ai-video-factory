"""Loopback-only test server with controlled seeds for Playwright E2E."""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from ai_video_factory.run_store import RunStore
from ai_video_factory.stages.review import ReviewStage
from ai_video_factory.ui_backend.app import UiSettings, create_app
from ai_video_factory.ui_backend.jobs import JobService
from ai_video_factory.ui_backend.session import BootstrapService
from ai_video_factory.ui_backend.worker import execute_job
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


class _DeterministicRunner:
    """Controlled stage delivery; only external boundaries are replaced."""

    def run(self, context, inputs):
        stage = context.stage
        directory = Path(context.artifacts_dir)
        directory.mkdir(parents=True, exist_ok=True)
        project = Path(context.project_dir)
        if stage == "research":
            bundle = ResearchBundle(topic=context.topic, synthesis="síntese E2E")
        elif stage == "script":
            bundle = ScriptBundle(
                title="Episódio E2E", language="pt-BR", estimated_duration_seconds=1500.0,
                scenes=[{
                    "scene_id": "s1", "title": "Cena", "narration_text": "Fala E2E.",
                    "estimated_seconds": 1500.0,
                    "shots": [{"shot_id": "sh1", "visual": "plano E2E"}],
                }],
            )
        elif stage == "narration":
            audio = directory / "s.wav"
            audio.write_bytes(b"RIFF")
            bundle = NarrationBundle(
                provider="fake", voice="v", language="pt-BR",
                segments=[{
                    "segment_id": "n1", "scene_id": "s1", "shot_id": "sh1", "text": "Fala E2E.",
                    "audio": ArtifactRef.from_path(audio, project, "audio/wav").model_dump(),
                    "start_seconds": 0.0, "duration_seconds": 1500.0,
                }],
                spoken_text="Fala E2E.", total_duration_seconds=1500.0,
            )
        elif stage == "media":
            shot = directory / "s.mp4"
            shot.write_bytes(b"media")
            ref = ArtifactRef.from_path(shot, project, "video/mp4")
            bundle = MediaBundle(
                candidates=[{
                    "candidate_id": "m1", "scene_id": "s1", "shot_id": "sh1",
                    "license": "CC0", "file": ref.model_dump(),
                }],
                selected=[{
                    "scene_id": "s1", "shot_id": "sh1", "candidate_id": "m1",
                    "file": ref.model_dump(),
                }],
                rights=[{
                    "candidate_id": "m1", "license": "CC0", "attribution": "E2E",
                    "source_url": "https://example.test/clipe",
                }],
            )
        else:
            master = directory / "master.mp4"
            master.write_bytes(b"master")
            bundle = EditingBundle(
                filmcraft_version="e2e", mode="bridge", project_path="p.fcproj",
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
                type="stage_completed", source="e2e", summary=f"{stage} entregue",
                event_key=f"{context.request.production_id}:{stage}:completed",
            )],
            effective_config=dict(context.effective_settings),
        )


class _E2EJobService(JobService):
    def _spawn(self, job_id: str) -> None:
        # The E2E harness runs the worker deterministically on demand.
        pass

ROOT = Path(__file__).resolve().parents[1]
PORT = 8766


def build_test_app() -> FastAPI:
    temporary = Path(tempfile.mkdtemp(prefix="avf-e2e-"))
    data_root = temporary / "data"
    bootstrap = BootstrapService(data_root / "ui" / "bootstrap.token")
    settings = UiSettings(
        project_root=temporary,
        data_root=data_root,
        profiles_db=data_root / "profiles" / "profiles.sqlite3",
        static_dir=ROOT / "web" / "dist",
        port=PORT,
    )
    app = create_app(settings, bootstrap=bootstrap)
    runner = _DeterministicRunner()
    e2e_jobs = _E2EJobService(
        data_root / "ui" / "control.sqlite3",
        transports={
            **{stage: runner for stage in STAGE_ORDER if stage != "review"},
            "review": ReviewStage(probe=lambda path: {
                "width": 1920, "height": 1080, "duration": 1500.0, "audio_streams": 1,
            }),
        },
    )
    app.state.services = replace(app.state.services, jobs=e2e_jobs)

    @app.post("/__e2e/run-job/{job_id}", include_in_schema=False)
    def run_job(job_id: str) -> dict[str, str]:
        if e2e_jobs.claim(job_id=job_id) is None:
            return {"status": "already_running"}
        result = execute_job(e2e_jobs, job_id, e2e_jobs.run_default_executor)
        return {"status": str(result.status)}

    @app.get("/__e2e/ping", include_in_schema=False)
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/__e2e/token", include_in_schema=False)
    def token() -> dict[str, str]:
        return {"token": bootstrap.issue()}

    @app.post("/__e2e/seed", include_in_schema=False)
    def seed() -> dict[str, str]:
        store = RunStore(temporary / "state", artifact_root=temporary / "runs")
        run = store.start("research", {"topic": "Episódio E2E"})
        store.event(run.run_id, "source_found", {"url": "https://example.test/fonte"})
        return {"production_id": run.run_id}

    @app.post("/__e2e/seed-profiles", include_in_schema=False)
    def seed_profiles() -> dict[str, str]:
        from ai_video_factory.profiles.models import Observation, ProfileSpec
        from ai_video_factory.profiles.store import ProfileStore

        db = data_root / "profiles" / "profiles.sqlite3"
        db.parent.mkdir(parents=True, exist_ok=True)
        store = ProfileStore(db)
        for identifier in ("canal-a", "canal-b"):
            try:
                store.create_profile(
                    ProfileSpec(
                        profile_id=identifier,
                        name=f"Canal {identifier}",
                        language="pt-BR",
                        operation_budget={"max_external_calls": 20},
                    )
                )
            except Exception:
                pass
        try:
            store.record_observation(
                Observation(
                    observation_id="e2e-observation",
                    profile_id="canal-a",
                    stage="script",
                    attempt=1,
                    type="user_feedback",
                    source="e2e",
                    summary="Abertura longa demais",
                    event_key="e2e:abertura",
                )
            )
        except Exception:
            pass
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    uvicorn.run(build_test_app(), host="127.0.0.1", port=PORT, log_level="warning")
