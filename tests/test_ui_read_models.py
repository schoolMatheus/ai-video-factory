"""Read-only projections of already persisted production manifests and events."""

import json
from pathlib import Path

import pytest

from ai_video_factory.run_store import RunStore
from ai_video_factory.ui_backend.models import StageName
from ai_video_factory.ui_backend.read_models import ProductionReadModels


def _legacy_run(tmp_path: Path, stage: str = "research") -> tuple[RunStore, str]:
    store = RunStore(tmp_path / "state", artifact_root=tmp_path / "runs")
    run = store.start(stage, {"topic": "um tema real"})
    return store, run.run_id


def test_legacy_run_is_shown_without_invented_profile(tmp_path: Path) -> None:
    _, run_id = _legacy_run(tmp_path)

    models = ProductionReadModels(tmp_path / "state", tmp_path / "runs")
    production = models.get_production(run_id)

    assert production.id == run_id
    assert production.mode == "legacy"
    assert production.profile_id is None
    assert production.profile_revision is None
    assert production.title == "um tema real"
    assert production.stages[0].name is StageName.research
    assert production.stages[0].status == "running"


def test_partial_jsonl_line_preserves_previous_events(tmp_path: Path) -> None:
    store, run_id = _legacy_run(tmp_path)
    store.event(run_id, "source_found", {"url": "https://example.test/a"})
    event_path = tmp_path / "state" / "research" / run_id / "events.jsonl"
    with event_path.open("a", encoding="utf-8") as events_file:
        events_file.write('{"timestamp":"2026-11-23T00:00:00+00:00","run_id"')

    models = ProductionReadModels(tmp_path / "state", tmp_path / "runs")
    events = models.list_events(run_id)

    assert [event.type for event in events] == [
        "run_started",
        "source_found",
    ]
    assert events[-1].payload == {"url": "https://example.test/a"}
    assert event_path.read_text(encoding="utf-8").endswith('"run_id"')


def test_unknown_stage_is_not_marked_completed(tmp_path: Path) -> None:
    store, run_id = _legacy_run(tmp_path, stage="render")
    video = tmp_path / "runs" / run_id / "master.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    store.complete(
        run_id,
        {"video": str(video)},
        expected_artifacts={"video": video},
    )

    models = ProductionReadModels(tmp_path / "state", tmp_path / "runs")
    production = models.get_production(run_id)

    assert production.mode == "legacy"
    assert {stage.name for stage in production.stages} == set(StageName)
    assert all(stage.status == "unknown" for stage in production.stages)
    assert production.observed_stages == ["render"]


def test_reading_does_not_modify_manifests(tmp_path: Path) -> None:
    _, run_id = _legacy_run(tmp_path)
    manifest_path = tmp_path / "state" / "research" / run_id / "manifest.json"
    before = manifest_path.read_bytes()

    models = ProductionReadModels(tmp_path / "state", tmp_path / "runs")
    models.get_production(run_id)
    models.list_productions()
    models.list_events(run_id)

    assert manifest_path.read_bytes() == before


def test_list_productions_is_paginated(tmp_path: Path) -> None:
    _, first = _legacy_run(tmp_path)
    _, second = _legacy_run(tmp_path)

    models = ProductionReadModels(tmp_path / "state", tmp_path / "runs")
    first_page = models.list_productions(page_size=1)
    assert len(first_page.items) == 1
    assert first_page.next_cursor is not None

    second_page = models.list_productions(
        page_size=1, cursor=first_page.next_cursor
    )
    assert len(second_page.items) == 1
    assert {first_page.items[0].id, second_page.items[0].id} == {first, second}


def test_get_production_rejects_missing_id(tmp_path: Path) -> None:
    from ai_video_factory.ui_backend.models import NotFoundError

    models = ProductionReadModels(tmp_path / "state", tmp_path / "runs")
    with pytest.raises(NotFoundError):
        models.get_production("0" * 32)


def test_invalid_cursor_is_rejected(tmp_path: Path) -> None:
    from ai_video_factory.ui_backend.models import InvalidRequestError

    models = ProductionReadModels(tmp_path / "state", tmp_path / "runs")
    with pytest.raises(InvalidRequestError):
        models.list_productions(cursor="not-a-cursor")


def test_artifact_integrity_is_exposed_without_recomputing_it(tmp_path: Path) -> None:
    store, run_id = _legacy_run(tmp_path)
    document = tmp_path / "runs" / run_id / "brief.md"
    document.parent.mkdir(parents=True)
    document.write_text("# dossiê", encoding="utf-8")
    store.complete(
        run_id,
        {"brief": str(document)},
        expected_artifacts={"brief": document},
    )

    models = ProductionReadModels(tmp_path / "state", tmp_path / "runs")
    artifacts = models.list_artifacts(run_id)

    assert len(artifacts) == 1
    assert artifacts[0].name == "brief"
    assert artifacts[0].size_bytes == len("# dossiê".encode("utf-8"))
    assert artifacts[0].sha256
    assert artifacts[0].stage is StageName.research
