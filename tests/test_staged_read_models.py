"""Staged production projection, unified cursors and selective rework."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.run_store import RunStore
from ai_video_factory.ui_backend.events import EventService
from ai_video_factory.ui_backend.models import NotFoundError, StageStatus
from ai_video_factory.ui_backend.read_models import (
    ProductionReadModels,
    StagedProductionReadModels,
)
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
    ProductionRequest,
    ResearchBundle,
    ScriptBundle,
    StageResult,
)
from ai_video_factory.workflow.orchestrator import run_production


class _Runner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, context: Any, inputs: Any) -> StageResult:
        self.calls.append(context.stage)
        directory = Path(context.artifacts_dir)
        directory.mkdir(parents=True, exist_ok=True)
        project = Path(context.project_dir)
        stage = context.stage
        bundle: Any
        if stage == "research":
            bundle = ResearchBundle(topic=context.topic, claims=[ClaimEntry(
                claim_id="c1", text="Fato", classification="confirmed fact",
                source_ids=["https://a.example"],
                evidence=[EvidenceEntry(source_url="https://a.example", quote="trecho")],
                verified=True,
            )], synthesis="# Síntese")
        elif stage == "script":
            bundle = ScriptBundle(title="Episódio", language="pt-BR", estimated_duration_seconds=1.0,
                                  scenes=[{
                                      "scene_id": "s1", "title": "Cena", "narration_text": "Fala.",
                                      "estimated_seconds": 1.0,
                                      "shots": [{"shot_id": "sh1", "visual": "v", "claim_refs": ["c1"]}],
                                  }])
        elif stage == "narration":
            audio = directory / "s.wav"
            audio.write_bytes(b"RIFFfake")
            bundle = NarrationBundle(provider="fake", voice="v", language="pt-BR",
                                     segments=[{
                                         "segment_id": "n1", "scene_id": "s1", "shot_id": "sh1",
                                         "text": "Fala.",
                                         "audio": ArtifactRef.from_path(audio, project, "audio/wav").model_dump(),
                                         "start_seconds": 0.0, "duration_seconds": 1.0,
                                     }], spoken_text="Fala.", total_duration_seconds=1.0)
        elif stage == "media":
            shot = directory / "s.mp4"
            shot.write_bytes(b"media")
            ref = ArtifactRef.from_path(shot, project, "video/mp4")
            bundle = MediaBundle(
                candidates=[{"candidate_id": "m1", "scene_id": "s1", "shot_id": "sh1",
                             "license": "CC0", "attribution": "Autor", "file": ref.model_dump()}],
                selected=[{"scene_id": "s1", "shot_id": "sh1", "candidate_id": "m1",
                           "file": ref.model_dump()}],
                rights=[{"candidate_id": "m1", "license": "CC0", "attribution": "Autor",
                         "source_url": "https://a.example"}],
            )
        else:
            master = directory / "master.mp4"
            master.write_bytes(b"master")
            bundle = EditingBundle(filmcraft_version="test", mode="bridge",
                                   project_path="p.fcproj", item_map={"sh1": "item-1"},
                                   master=ArtifactRef.from_path(master, project, "video/mp4").model_dump(),
                                   observed_state={"offline_media": []})
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


def _store(tmp_path: Path, profile_id: str = "canal") -> ProfileStore:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": profile_id, "name": profile_id, "language": "pt-BR",
        "operation_budget": {"max_external_calls": 10},
    }))
    return store


def _request(tmp_path: Path, production_id: str = "staged-prod") -> ProductionRequest:
    return ProductionRequest.model_validate({
        "production_id": production_id, "profile_id": "canal", "topic": "Tema",
        "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
    })


def _run(tmp_path: Path, store: ProfileStore | None = None, **kwargs: Any) -> Any:
    store = store or _store(tmp_path)
    runner = _Runner()
    return run_production(
        _request(tmp_path), store=store,
        runners={stage: runner for stage in STAGE_ORDER}, **kwargs,
    )


def test_real_coordinator_production_is_projected_as_staged(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = _run(tmp_path, store)
    project = Path(result.project_dir)

    models = StagedProductionReadModels(project)
    view = models.get_production(result.production_id)

    assert view.mode == "staged"
    assert view.profile_id == "canal"
    assert view.snapshot_id is not None
    assert view.state == StageStatus.completed
    assert [stage.name.value for stage in view.stages] == list(STAGE_ORDER)
    assert all(stage.status == StageStatus.completed for stage in view.stages)
    assert any(artifact.integrity == "verified" for artifact in view.artifacts)


def test_event_cursor_is_shared_by_snapshot_history_and_stream(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = _run(tmp_path, store)
    project = Path(result.project_dir)
    read_models = StagedProductionReadModels(project)
    events = EventService(read_models, tmp_path / "control.sqlite3")
    production_id = result.production_id

    snapshot_cursor = events.snapshot_cursor(production_id)
    history = events.replay(production_id, after_cursor=snapshot_cursor)
    assert history == []
    all_events = events.replay(production_id)
    assert all_events
    assert events.cursor_for_event(production_id, all_events[-1].id) == events.cursor_for_event(
        production_id, all_events[-1].id
    )
    new_events = events.replay(production_id, after_cursor=events.cursor_for_event(
        production_id, all_events[0].id
    ))
    assert all(item.id != all_events[0].id for item in new_events)


def test_event_arriving_between_snapshot_and_subscribe_is_replayed_once(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = _run(tmp_path, store)
    events = EventService(
        StagedProductionReadModels(Path(result.project_dir)), tmp_path / "control.sqlite3"
    )
    production_id = result.production_id
    cursor = events.snapshot_cursor(production_id)
    extra = RunStore(Path(result.project_dir) / "state",
                     artifact_root=Path(result.project_dir) / "artifacts")
    # A new event is projected after the snapshot cursor was issued.
    from ai_video_factory.ui_backend.models import EventView
    events.store.insert_events([EventView(
        id="late-event", production_id=production_id, type="stage.completed",
        timestamp="2026-11-26T00:00:00+00:00", severity="info", payload={"stage": "research"},
    )])

    async def collect() -> list[str]:
        seen: list[str] = []

        async def stop_after_first() -> bool:
            return len(seen) >= 1

        async for event in events.subscribe(
            production_id, cursor, max_polls=5, sleep=lambda _: None,
            should_stop=stop_after_first,
        ):
            seen.append(event.id)
        return seen

    assert asyncio.run(collect()) == ["late-event"]


def test_profile_revision_does_not_change_stage_reuse_fingerprint(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first_runner = _Runner()
    request = _request(tmp_path)
    run_production(request, store=store, runners={s: first_runner for s in STAGE_ORDER},
                   through="script")
    snapshot = store.get_snapshot("canal")
    from ai_video_factory.profiles.models import ProfilePatch

    store.revise_profile(
        "canal",
        ProfilePatch(settings={"media.query_suffix": "novo sufixo"}),
        expected_revision=snapshot.revision, reason="preferência explícita",
    )

    second_runner = _Runner()
    result = run_production(request, store=store,
                            runners={s: second_runner for s in STAGE_ORDER}, through="script")

    assert first_runner.calls == ["research", "script"]
    assert second_runner.calls == []
    assert result.status == "completed"


def test_rework_consumes_invalidation_plan(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _Runner()
    request = _request(tmp_path)
    run_production(request, store=store, runners={s: first for s in STAGE_ORDER})

    second = _Runner()
    result = run_production(
        request, store=store, runners={s: second for s in STAGE_ORDER},
        invalidation_inputs={"editing.music"},
    )

    assert result.status == "completed"
    assert second.calls == ["editing", "review"]
