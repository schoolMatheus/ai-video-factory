"""Media stage behaviour (plan task 10)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_video_factory.asset_memory import AssetMemory, scoped_memory_path
from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.stages.media import MediaStage
from ai_video_factory.workflow.contracts import StageContext
from ai_video_factory.workflow.models import (
    ArtifactRef,
    NarrationBundle,
    ProductionRequest,
    ScriptBundle,
    StageInputs,
)


def _context(tmp_path: Path, profile_id: str = "canal") -> StageContext:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    snapshot = store.create_profile(ProfileSpec.model_validate({
        "profile_id": profile_id, "name": profile_id, "language": "pt-BR",
    }))
    request = ProductionRequest.model_validate({
        "production_id": f"prod-{profile_id}", "profile_id": profile_id,
        "topic": "Tema", "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
    })
    request.project_dir.mkdir(parents=True, exist_ok=True)
    memory = build_memory_context(store, snapshot, "media", request.topic)
    return StageContext(
        request=request, snapshot=snapshot, stage="media", attempt=1,
        artifacts_dir=request.project_dir / "artifacts" / "04_media",
        memory=memory, effective_settings=memory.settings, project_dir=request.project_dir,
    )


def _inputs(context: StageContext, shot_ids: list[str], *, with_narration: bool = True) -> StageInputs:
    script = ScriptBundle(
        title="Episódio", language="pt-BR", estimated_duration_seconds=20.0,
        scenes=[{
            "scene_id": "s1", "title": "Cena longa", "narration_text": "fala",
            "estimated_seconds": 20.0,
            "shots": [
                {"shot_id": shot_id, "visual": f"imagem de {shot_id}", "intent": "v"} for shot_id in shot_ids
            ],
        }],
    )
    script_path = context.project_dir / "script.json"
    script.save(script_path)
    refs: dict[str, ArtifactRef] = {
        "script": ArtifactRef.from_path(script_path, context.project_dir, "application/json")
    }
    if with_narration:
        audio = context.project_dir / "seg.wav"
        audio.write_bytes(b"RIFF")
        narration = NarrationBundle(
            provider="fake", voice="v", language="pt-BR",
            segments=[{
                "segment_id": "n1", "scene_id": "s1", "shot_id": shot_ids[0],
                "text": "fala", "audio": ArtifactRef.from_path(audio, context.project_dir, "audio/wav").model_dump(),
                "start_seconds": 0.0, "duration_seconds": 9.0,
            }],
            total_duration_seconds=9.0,
        )
        narration_path = context.project_dir / "narration.json"
        narration.save(narration_path)
        refs["narration"] = ArtifactRef.from_path(narration_path, context.project_dir, "application/json")
    return StageInputs.load("media", refs, context.project_dir)


def _memory(tmp_path: Path, profile_id: str) -> AssetMemory:
    return AssetMemory(
        scoped_memory_path(profile_id, data_dir=tmp_path / "data"),
        profile_id=profile_id,
    )


def test_multiple_shots_own_file_irrelevant_candidate_and_duplicate(tmp_path: Path) -> None:
    context = _context(tmp_path, "canal-a")
    own_file = tmp_path / "own.mp4"
    own_file.write_bytes(b"video")
    def search(query: str, limit: int) -> list[dict[str, Any]]:
        if "shot-1" in query:
            return [
                {"id": "m1", "title": "imagem de shot-1", "license": "CC0", "path": str(own_file)},
                {"id": "m1", "title": "imagem de shot-1 duplicata", "license": "CC0"},
            ]
        return [{"id": "m2", "title": "assunto sem relação", "license": "CC0"}]

    result = MediaStage(
        search=search,
        fetch=lambda raw, directory: Path(str(raw["path"])) if "path" in raw else None,
        memory=_memory(tmp_path, "canal-a"),
        data_dir=tmp_path / "data",
    ).run(context, _inputs(context, ["shot-1", "shot-2"]))
    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    assert [item["shot_id"] for item in bundle["selected"]] == ["shot-1"]
    assert [item["candidate_id"] for item in bundle["candidates"]] == ["m1"]  # duplicate/irrelevant skipped
    assert len(bundle["gaps"]) == 1
    assert bundle["selected"][0]["file"]["path"].endswith(".mp4")


def test_url_identity_produces_a_safe_contained_filename(tmp_path: Path) -> None:
    context = _context(tmp_path, "canal-url")
    own_file = tmp_path / "own.mp4"
    own_file.write_bytes(b"video")

    def search(query: str, limit: int) -> list[dict[str, Any]]:
        return [{
            "id": "https://stock.example/clips/abc?token=1",
            "url": "https://stock.example/clips/abc?token=1",
            "title": "imagem de shot-1", "license": "CC0",
            "path": str(own_file),
        }]

    result = MediaStage(
        search=search,
        fetch=lambda raw, directory: Path(str(raw["path"])),
        memory=_memory(tmp_path, "canal-url"), data_dir=tmp_path / "data",
    ).run(context, _inputs(context, ["shot-1"]))

    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    candidate = bundle["candidates"][0]
    file_path = candidate["file"]["path"]
    filename = Path(file_path).name
    assert "/" not in filename and "\\" not in filename and ":" not in filename
    assert candidate["url"].startswith("https://stock.example/")
    resolved = (context.project_dir / file_path).resolve()
    assert context.project_dir.resolve() in resolved.parents
    assert resolved.is_file()


def test_license_gap_blocks_final_and_attribution_is_preserved(tmp_path: Path) -> None:
    context = _context(tmp_path, "canal-a")
    def search(query: str, limit: int) -> list[dict[str, Any]]:
        return [
            {"id": "no-license", "title": "imagem de shot-1"},
            {"id": "licensed", "title": "imagem de shot-2", "license": "CC-BY", "attribution": "Autor"},
        ]

    result = MediaStage(
        search=search, memory=_memory(tmp_path, "canal-a"), data_dir=tmp_path / "data",
    ).run(context, _inputs(context, ["shot-1", "shot-2"]))
    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    assert bundle["rights_complete"] is False
    assert any("licença ausente" in gap["reason"] for gap in bundle["gaps"])
    assert bundle["rights"][0]["attribution"] == "Autor"
    assert any(item.type == "media_gaps" for item in result.observations)


def test_editorial_rejection_stays_in_its_channel(tmp_path: Path) -> None:
    memory_a = _memory(tmp_path, "canal-a")
    memory_b = _memory(tmp_path, "canal-b")
    memory_a.record_rejection("clip-x", "não serve para o canal A", classification="editorial")

    context_a = _context(tmp_path, "canal-a")
    def search(query: str, limit: int) -> list[dict[str, Any]]:
        return [{"id": "clip-x", "title": "imagem de shot-1", "license": "CC0"}]

    result_a = MediaStage(
        search=search, memory=memory_a, data_dir=tmp_path / "data",
    ).run(context_a, _inputs(context_a, ["shot-1"]))
    assert result_a.artifacts["bundle"].read_json(context_a.project_dir)["selected"] == []

    context_b = _context(tmp_path, "canal-b")
    result_b = MediaStage(
        search=search, memory=memory_b, data_dir=tmp_path / "data",
    ).run(context_b, _inputs(context_b, ["shot-1"]))
    assert len(result_b.artifacts["bundle"].read_json(context_b.project_dir)["selected"]) == 1


def test_technical_and_editorial_rejections_are_classified_separately(tmp_path: Path) -> None:
    memory = _memory(tmp_path, "canal-a")
    bad_file = tmp_path / "corrupt.mp4"
    bad_file.write_bytes(b"bad")
    context = _context(tmp_path, "canal-a")
    MediaStage(
        search=lambda query, limit: [
            {"id": "corrupt", "title": "imagem de shot-1", "license": "CC0", "path": str(bad_file)}
        ],
        technical_qc=lambda path: False,
        memory=memory,
        data_dir=tmp_path / "data",
    ).run(context, _inputs(context, ["shot-1"]))
    entries = json.loads(memory.path.read_text(encoding="utf-8"))["rejections"]
    assert entries["corrupt"]["classification"] == "technical"
    memory.record_rejection("clip-y", "editorial", classification="editorial")
    entries = json.loads(memory.path.read_text(encoding="utf-8"))["rejections"]
    assert entries["clip-y"]["classification"] == "editorial"
