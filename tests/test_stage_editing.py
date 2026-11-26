"""Editing assembly, reconciliation and export checks (plan task 12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.stages.editing import EditingStage, EditingStageError
from ai_video_factory.workflow.contracts import StageContext
from ai_video_factory.workflow.models import (
    ArtifactRef,
    EditorCapabilities,
    EditorCommandResult,
    EditorSnapshot,
    MediaBundle,
    NarrationBundle,
    ProductionRequest,
    ScriptBundle,
    StageInputs,
)


class FakeEditor:
    def __init__(
        self,
        *,
        items: list[dict[str, Any]] | None = None,
        offline: list[str] | None = None,
        timeout_insert: bool = False,
    ) -> None:
        self.items = list(items or [])
        self.offline = list(offline or [])
        self.timeout_insert = timeout_insert
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def connect(self) -> EditorCapabilities:
        return EditorCapabilities(
            version="0.1-alpha", mode="bridge",
            commands=["inspect_project", "insert_item", "save_project", "render_preview", "export_project"],
        )

    def inspect(self) -> EditorSnapshot:
        return EditorSnapshot(project_path="p.fcproj", items=self.items, offline_media=self.offline,
                              raw_digest=json.dumps(self.items, sort_keys=True))

    def execute(self, command_id: str, params: dict[str, Any]) -> EditorCommandResult:
        self.calls.append((command_id, params))
        if command_id == "insert_item":
            if self.timeout_insert:
                return EditorCommandResult(command_id=command_id, status="indeterminate")
            item_id = f"item-{params['shot_id']}"
            self.items.append({"shot_id": params["shot_id"], "item_id": item_id})
            return EditorCommandResult(command_id=command_id, state={"item_id": item_id})
        if command_id == "export_project":
            Path(params["output"]).write_bytes(b"master")
            return EditorCommandResult(command_id=command_id, state={"output": params["output"]})
        return EditorCommandResult(command_id=command_id)

    def close(self) -> None:
        pass


def _context(tmp_path: Path) -> StageContext:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    snapshot = store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
    }))
    request = ProductionRequest.model_validate({
        "production_id": "prod-1", "profile_id": "canal", "topic": "Tema",
        "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
    })
    request.project_dir.mkdir(parents=True, exist_ok=True)
    memory = build_memory_context(store, snapshot, "editing", request.topic)
    return StageContext(
        request=request, snapshot=snapshot, stage="editing", attempt=1,
        artifacts_dir=request.project_dir / "artifacts" / "05_editing",
        memory=memory, effective_settings=memory.settings, project_dir=request.project_dir,
    )


def _inputs(context: StageContext, shot_id: str = "sh0") -> StageInputs:
    media_file = context.project_dir / "media.mp4"
    media_file.write_bytes(b"video")
    media_ref = ArtifactRef.from_path(media_file, context.project_dir, "video/mp4")
    script = ScriptBundle(
        title="T", language="pt-BR", estimated_duration_seconds=1.0,
        scenes=[{
            "scene_id": "s0", "title": "Cena", "narration_text": "fala",
            "estimated_seconds": 1.0,
            "shots": [{"shot_id": shot_id, "visual": "v"}],
        }],
    )
    narration = NarrationBundle(
        provider="p", voice="v", language="pt-BR",
        segments=[{
            "segment_id": "n0", "scene_id": "s0", "shot_id": shot_id,
            "text": "fala", "audio": media_ref.model_dump(),
            "start_seconds": 0.0, "duration_seconds": 1.0,
        }],
        total_duration_seconds=1.0,
    )
    media = MediaBundle(
        candidates=[{"candidate_id": "m0", "scene_id": "s0", "shot_id": shot_id,
                     "license": "CC0", "file": media_ref.model_dump()}],
        selected=[{"scene_id": "s0", "shot_id": shot_id, "candidate_id": "m0",
                   "file": media_ref.model_dump()}],
    )
    refs = {}
    for name, bundle in (("script", script), ("narration", narration), ("media", media)):
        path = context.project_dir / f"{name}.json"
        bundle.save(path)
        refs[name] = ArtifactRef.from_path(path, context.project_dir, "application/json")
    return StageInputs.load("editing", refs, context.project_dir)


def test_resume_after_applied_command_does_not_duplicate_clip(tmp_path: Path) -> None:
    context = _context(tmp_path)
    editor = FakeEditor(items=[{"shot_id": "sh0", "item_id": "already-there"}])
    result = EditingStage(editor, probe=lambda path: {"width": 1920, "height": 1080, "duration": 1.0}).run(
        context, _inputs(context)
    )
    assert not any(command == "insert_item" for command, _ in editor.calls)
    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    assert bundle["item_map"] == {"sh0": "already-there"}
    assert result.artifacts["master"].resolve(context.project_dir).is_file()


def test_partial_batch_and_manual_change_are_observed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    previous = context.artifacts_dir / "previous_snapshot.json"
    previous.parent.mkdir(parents=True, exist_ok=True)
    previous.write_text(EditorSnapshot(project_path="p.fcproj", items=[]).model_dump_json(), encoding="utf-8")
    editor = FakeEditor(items=[{"shot_id": "manual", "item_id": "manual-1"}])
    result = EditingStage(editor, probe=lambda path: {"width": 1920, "height": 1080}).run(
        context, _inputs(context)
    )
    assert any(command == "insert_item" for command, _ in editor.calls)
    assert any(item.type == "manual_edit_observed" for item in result.observations)
    assert any("alterado manualmente" in warning for warning in result.artifacts["bundle"].read_json(context.project_dir)["warnings"])


def test_indeterminate_mutation_requires_inspection(tmp_path: Path) -> None:
    context = _context(tmp_path)
    editor = FakeEditor(timeout_insert=True)
    with pytest.raises(EditingStageError, match="indeterminate"):
        EditingStage(editor).run(context, _inputs(context))
    assert sum(command == "insert_item" for command, _ in editor.calls) == 1


def test_offline_media_is_not_a_valid_delivery(tmp_path: Path) -> None:
    context = _context(tmp_path)
    editor = FakeEditor(offline=["missing.mp4"])
    with pytest.raises(EditingStageError, match="offline media"):
        EditingStage(editor, probe=lambda path: {"width": 1920, "height": 1080}).run(
            context, _inputs(context)
        )
