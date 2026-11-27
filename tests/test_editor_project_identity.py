"""FilmCraft project identity and item reconciliation across episodes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.stages.editing import EditingStage
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


class RecordingEditor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.items: list[dict[str, Any]] = []

    def connect(self) -> EditorCapabilities:
        return EditorCapabilities(
            version="0.2", mode="bridge",
            commands=["open_project", "create_project", "save_project", "inspect_project",
                      "insert_item", "render_preview", "export_project"],
        )

    def inspect(self) -> EditorSnapshot:
        return EditorSnapshot(
            project_path="p.fcproj", items=list(self.items), offline_media=[],
            raw_digest=json.dumps(self.items, sort_keys=True),
        )

    def execute(self, command_id: str, params: dict[str, Any]) -> EditorCommandResult:
        self.calls.append((command_id, params))
        if command_id == "insert_item":
            item = {
                "item_id": f"item-{params['shot_id']}-{len(self.items)}",
                "identity": params.get("identity"),
                "shot_id": params["shot_id"],
                "production_id": params.get("production_id"),
                "kind": params.get("kind"),
                "source": params.get("media_path"),
                "media_digest": params.get("media_digest"),
            }
            self.items.append(item)
            return EditorCommandResult(command_id=command_id, state=item)
        if command_id == "export_project":
            Path(params["output"]).write_bytes(b"master")
            return EditorCommandResult(command_id=command_id, state={"output": params["output"]})
        return EditorCommandResult(command_id=command_id)

    def close(self) -> None:
        pass


def _context(tmp_path: Path, production_id: str) -> StageContext:
    store = ProfileStore(tmp_path / f"profiles-{production_id}.sqlite3")
    snapshot = store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
    }))
    request = ProductionRequest.model_validate({
        "production_id": production_id, "profile_id": "canal", "topic": "Tema",
        "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
    })
    request.project_dir.mkdir(parents=True, exist_ok=True)
    memory = build_memory_context(store, snapshot, "editing", request.topic)
    return StageContext(
        request=request, snapshot=snapshot, stage="editing", attempt=1,
        artifacts_dir=request.project_dir / "artifacts" / "05_editing",
        memory=memory, effective_settings=memory.settings, project_dir=request.project_dir,
    )


def _inputs(context: StageContext, digest_seed: str) -> StageInputs:
    shot = context.project_dir / f"shot-{digest_seed}.mp4"
    shot.write_bytes(digest_seed.encode())
    file_ref = ArtifactRef.from_path(shot, context.project_dir, "video/mp4")
    script = ScriptBundle(
        title="T", language="pt-BR", estimated_duration_seconds=1.0,
        scenes=[{"scene_id": "s1", "title": "Cena", "narration_text": "fala",
                 "estimated_seconds": 1.0,
                 "shots": [{"shot_id": "sh1", "visual": "v", "on_screen_text": "texto"}]}],
    )
    narration = NarrationBundle(
        provider="fake", voice="v", language="pt-BR",
        segments=[{"segment_id": "n1", "scene_id": "s1", "shot_id": "sh1", "text": "fala",
                   "audio": file_ref.model_dump(), "start_seconds": 0.0, "duration_seconds": 1.0}],
        total_duration_seconds=1.0,
    )
    media = MediaBundle(
        candidates=[{"candidate_id": "m1", "scene_id": "s1", "shot_id": "sh1",
                     "license": "CC0", "file": file_ref.model_dump()}],
        selected=[{"scene_id": "s1", "shot_id": "sh1", "candidate_id": "m1",
                   "file": file_ref.model_dump()}],
    )
    refs: dict[str, ArtifactRef] = {}
    for name, bundle in (("script", script), ("narration", narration), ("media", media)):
        path = context.project_dir / f"{name}.json"
        bundle.save(path)
        refs[name] = ArtifactRef.from_path(path, context.project_dir, "application/json")
    return StageInputs.load("editing", refs, context.project_dir)


def _run(context: StageContext, editor: RecordingEditor) -> None:
    EditingStage(editor, probe=lambda path: {
        "width": 1920, "height": 1080, "duration": 1.0,
    }).run(context, _inputs(context, context.request.production_id))


def test_project_is_opened_before_inspection_and_items_carry_episode_identity(tmp_path) -> None:
    context = _context(tmp_path, "episode-a")
    editor = RecordingEditor()

    _run(context, editor)

    names = [name for name, _ in editor.calls]
    assert names[0] in {"open_project", "create_project"}
    assert "insert_item" in names
    insert = next(params for name, params in editor.calls if name == "insert_item")
    assert insert["production_id"] == "episode-a"
    assert insert["media_digest"]
    assert insert["kind"] in {"video", "narration", "text", "caption", "music"}
    assert any(name == "save_project" for name in names)


def test_same_shot_id_in_two_episodes_never_reuses_an_item(tmp_path) -> None:
    first = _context(tmp_path, "episode-a")
    second = _context(tmp_path, "episode-b")
    editor_a = RecordingEditor()
    editor_b = RecordingEditor()

    _run(first, editor_a)
    _run(second, editor_b)

    insert_a = next(params for name, params in editor_a.calls if name == "insert_item")
    insert_b = next(params for name, params in editor_b.calls if name == "insert_item")
    assert insert_a["media_digest"] != insert_b["media_digest"]
    assert insert_a["production_id"] != insert_b["production_id"]


def test_changed_media_forces_correction_on_resume(tmp_path) -> None:
    context = _context(tmp_path, "episode-a")
    editor = RecordingEditor()
    EditingStage(editor, probe=lambda path: {
        "width": 1920, "height": 1080, "duration": 1.0,
    }).run(context, _inputs(context, "old-media"))

    changed = _inputs(context, "new-media")
    EditingStage(editor, probe=lambda path: {
        "width": 1920, "height": 1080, "duration": 1.0,
    }).run(context, changed)

    inserts = [params for name, params in editor.calls if name == "insert_item"]
    assert len(inserts) >= 2
    assert inserts[-1]["media_digest"] != inserts[0]["media_digest"]
