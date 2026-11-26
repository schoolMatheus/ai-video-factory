"""Coordinator order, resumption, invalidation and reconciliation (plan task 6)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ai_video_factory.profiles.models import OperationBudget, ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    STAGE_ORDER,
    ArtifactRef,
    EditingBundle,
    MediaBundle,
    NarrationBundle,
    ObservationSeed,
    ProductionRequest,
    ResearchBundle,
    ReviewBundle,
    ScriptBundle,
    StageResult,
)
from ai_video_factory.workflow.orchestrator import plan_invalidation, run_production


class RecordingRunner:
    def __init__(self, *, fail_at: str | None = None, external: bool = False) -> None:
        self.calls: list[str] = []
        self.fail_at = fail_at
        self.external = external

    def run(self, context: Any, inputs: Any) -> StageResult:
        self.calls.append(context.stage)
        if context.stage == self.fail_at:
            raise RuntimeError("stage exploded")
        return StageResult(
            stage=context.stage,
            attempt=context.attempt,
            artifacts=_artifacts(context),
            observations=[ObservationSeed(
                type="stage_completed", source="test-runner",
                summary=f"{context.stage} completed",
                event_key=f"{context.request.production_id}:{context.stage}:{context.attempt}:completed",
            )],
            effective_config=dict(context.effective_settings),
        )


def _artifacts(context: Any) -> dict[str, ArtifactRef]:
    stage = context.stage
    directory = Path(context.artifacts_dir)
    audio = directory / "segment.wav"
    audio.write_bytes(b"RIFFfake")
    media = directory / "shot.mp4"
    media.write_bytes(b"media bytes")
    package = directory / "package.json"
    package.write_text("{}", encoding="utf-8")
    audio_ref = ArtifactRef.from_path(audio, context.project_dir, "audio/wav")
    media_ref = ArtifactRef.from_path(media, context.project_dir, "video/mp4")
    bundle: Any
    if stage == "research":
        bundle = ResearchBundle(topic=context.topic, synthesis="síntese")
    elif stage == "script":
        bundle = ScriptBundle(
            title="Episódio", language=context.language, estimated_duration_seconds=10.0,
            scenes=[{
                "scene_id": "s1", "title": "Cena", "narration_text": "fala",
                "estimated_seconds": 10.0,
                "shots": [{"shot_id": "sh1", "visual": "v"}],
            }],
        )
    elif stage == "narration":
        bundle = NarrationBundle(
            provider="fake", voice="v", language=context.language,
            segments=[{
                "segment_id": "n1", "scene_id": "s1", "shot_id": "sh1",
                "text": "fala", "audio": audio_ref.model_dump(),
                "start_seconds": 0.0, "duration_seconds": 10.0,
            }],
            total_duration_seconds=10.0,
        )
    elif stage == "media":
        bundle = MediaBundle(
            candidates=[{
                "candidate_id": "m1", "scene_id": "s1", "shot_id": "sh1",
                "license": "CC0", "file": media_ref.model_dump(),
            }],
            selected=[{"scene_id": "s1", "shot_id": "sh1", "candidate_id": "m1", "file": media_ref.model_dump()}],
        )
    elif stage == "editing":
        bundle = EditingBundle(
            filmcraft_version="test", mode="bridge", project_path="editing/project.fcproj",
            item_map={"sh1": "item-1"}, master=media_ref.model_dump(),
        )
    else:
        bundle = ReviewBundle(status="passed", package_path="package/package.json")
    path = directory / BUNDLE_FILENAMES[stage]
    bundle.save(path)
    return {
        "bundle": ArtifactRef.from_path(path, context.project_dir, "application/json"),
        "package": ArtifactRef.from_path(package, context.project_dir, "application/json"),
    }


def _store(tmp_path: Path, *, budget: OperationBudget | None = None) -> ProfileStore:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal",
        "name": "Canal",
        "language": "pt-BR",
        "operation_budget": budget.model_dump() if budget else {"max_external_calls": 10},
    }))
    return store


def _request(tmp_path: Path, production_id: str = "prod-1", **overrides: Any) -> ProductionRequest:
    payload: dict[str, Any] = {
        "production_id": production_id,
        "profile_id": "canal",
        "topic": "Tema informado",
        "target_minutes": 1.0,
        "base_dir": str(tmp_path / "projects"),
    }
    payload.update(overrides)
    return ProductionRequest.model_validate(payload)


def test_runners_execute_in_order_and_stop_at_through(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runner = RecordingRunner()
    result = run_production(
        _request(tmp_path), store=store,
        runners={stage: runner for stage in STAGE_ORDER}, through="script",
    )
    assert runner.calls == ["research", "script"]
    assert result.status == "completed"
    assert result.final_stage == "script"
    assert len(store.list_observations("canal")) == 2


def test_failure_stops_successors(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runner = RecordingRunner(fail_at="media")
    result = run_production(
        _request(tmp_path), store=store,
        runners={stage: runner for stage in STAGE_ORDER},
    )
    assert runner.calls == ["research", "script", "narration", "media"]
    assert result.status == "failed"
    assert result.failures[0].code == "RuntimeError"


def test_resume_reuses_valid_predecessors(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = RecordingRunner()
    run_production(
        _request(tmp_path), store=store,
        runners={stage: first for stage in STAGE_ORDER}, through="script",
    )
    second = RecordingRunner()
    result = run_production(
        _request(tmp_path), store=store,
        runners={stage: second for stage in STAGE_ORDER},
    )
    assert first.calls == ["research", "script"]
    assert second.calls == ["narration", "media", "editing", "review"]
    assert result.status == "completed"
    assert result.package_path is not None


def test_music_change_invalidates_only_editing_and_review() -> None:
    assert plan_invalidation({"editing.music"}) == ["editing", "review"]
    assert plan_invalidation({"script.speech"}) == [
        "narration", "media", "editing", "review",
    ]


def test_dry_run_calls_nothing_and_activates_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runner = RecordingRunner()
    result = run_production(
        _request(tmp_path), store=store,
        runners={stage: runner for stage in STAGE_ORDER}, dry_run=True,
    )
    assert runner.calls == []
    assert result.status == "pending"
    assert store.list_observations("canal") == []
    assert (Path(result.project_dir) / "profile_snapshot.json").is_file()


def test_reconciliation_restores_lost_observation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runner = RecordingRunner()
    request = _request(tmp_path)
    run_production(request, store=store, runners={stage: runner for stage in STAGE_ORDER}, through="script")
    connection = sqlite3.connect(store.path)
    connection.execute("DELETE FROM observations")
    connection.commit()
    connection.close()
    assert store.list_observations("canal") == []
    resumed = RecordingRunner()
    run_production(request, store=store, runners={stage: resumed for stage in STAGE_ORDER}, through="script")
    assert resumed.calls == []
    assert len(store.list_observations("canal")) == 2


def test_external_stage_requires_budget(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
        "operation_budget": {"max_external_calls": None},
    }))
    runner = RecordingRunner(external=True)
    result = run_production(
        _request(tmp_path), store=store,
        runners={stage: runner for stage in STAGE_ORDER},
    )
    assert runner.calls == []
    assert result.failures[0].code == "budget_not_configured"
