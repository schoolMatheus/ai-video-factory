"""Final review, corrections and package behaviour (plan task 13)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.stages.review import ReviewStage
from ai_video_factory.workflow.contracts import StageContext
from ai_video_factory.workflow.models import (
    ArtifactRef,
    ClaimEntry,
    EditingBundle,
    EvidenceEntry,
    MediaBundle,
    NarrationBundle,
    ProductionRequest,
    ResearchBundle,
    ReviewBundle,
    ScriptBundle,
    StageInputs,
)


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
    memory = build_memory_context(store, snapshot, "review", request.topic)
    return StageContext(
        request=request, snapshot=snapshot, stage="review", attempt=1,
        artifacts_dir=request.project_dir / "artifacts" / "06_review",
        memory=memory, effective_settings=memory.settings, project_dir=request.project_dir,
    )


def _inputs(
    context: StageContext,
    *,
    offline: list[str] | None = None,
    claim_id: str = "c1",
    rights: list[dict[str, Any]] | None = None,
    spoken_text: str | None = None,
    gaps: list[dict[str, Any]] | None = None,
) -> StageInputs:
    project = context.project_dir
    media_file = project / "media.mp4"
    media_file.write_bytes(b"video")
    master_file = context.artifacts_dir / "master.mp4"
    master_file.parent.mkdir(parents=True, exist_ok=True)
    master_file.write_bytes(b"master")
    media_ref = ArtifactRef.from_path(media_file, project, "video/mp4")
    master_ref = ArtifactRef.from_path(master_file, project, "video/mp4")
    research = ResearchBundle(
        topic="Tema",
        claims=[ClaimEntry(
            claim_id="c1", text="Fato", classification="confirmed fact",
            source_ids=["https://a.example"],
            evidence=[EvidenceEntry(source_url="https://a.example", quote="trecho")],
            verified=True,
        )],
        synthesis="# Síntese real",
    )
    script = ScriptBundle(
        title="Episódio", logline="recorte", language="pt-BR", estimated_duration_seconds=10.0,
        scenes=[{
            "scene_id": "s1", "title": "Cena", "narration_text": "Fala canônica.",
            "estimated_seconds": 10.0,
            "shots": [{"shot_id": "sh1", "visual": "v", "claim_refs": [claim_id]}],
        }],
    )
    narration = NarrationBundle(
        provider="p", voice="v", language="pt-BR",
        segments=[{
            "segment_id": "n1", "scene_id": "s1", "shot_id": "sh1", "text": "Fala canônica.",
            "audio": media_ref.model_dump(), "start_seconds": 0.0, "duration_seconds": 10.0,
        }],
        spoken_text=spoken_text if spoken_text is not None else "Fala canônica.",
        total_duration_seconds=10.0,
    )
    rights_records = rights if rights is not None else [
        {"candidate_id": "m1", "license": "CC0", "attribution": "Autor", "source_url": "https://a.example"}
    ]
    media = MediaBundle(
        candidates=[{"candidate_id": "m1", "scene_id": "s1", "shot_id": "sh1",
                     "license": "CC0", "attribution": "Autor", "file": media_ref.model_dump()}],
        selected=[{"scene_id": "s1", "shot_id": "sh1", "candidate_id": "m1", "file": media_ref.model_dump()}],
        rights=rights_records,
        gaps=gaps or [],
    )
    editing = EditingBundle(
        filmcraft_version="0.1", mode="bridge", project_path="p.fcproj",
        item_map={"sh1": "item-1"}, master=master_ref.model_dump(),
        observed_state={"offline_media": offline or []},
    )
    refs: dict[str, ArtifactRef] = {}
    for name, bundle in (("research", research), ("script", script), ("narration", narration),
                         ("media", media), ("editing", editing)):
        path = project / f"{name}.json"
        bundle.save(path)
        refs[name] = ArtifactRef.from_path(path, project, "application/json")
    return StageInputs.load("review", refs, project)


def _stage(probe: dict[str, Any] | None = None) -> ReviewStage:
    return ReviewStage(probe=lambda path: probe or {
        "width": 1920, "height": 1080, "duration": 10.0,
    })


def test_technically_valid_export_with_offline_media_is_rejected(tmp_path: Path) -> None:
    context = _context(tmp_path)
    result = _stage().run(context, _inputs(context, offline=["missing.mp4"]))
    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    assert bundle["status"] == "failed"
    assert any(check["name"] == "offline_media" and not check["passed"] for check in bundle["checks"])
    assert bundle["package_path"] is None
    assert any(route["stage"] == "editing" for route in bundle["reroutes"])


def test_duration_and_broken_claim_and_missing_credits_route_to_origin(tmp_path: Path) -> None:
    context = _context(tmp_path)
    probe = {"width": 1920, "height": 1080, "duration": 30.0}
    result = ReviewStage(probe=lambda path: probe).run(context, _inputs(
        context,
        claim_id="inventado",
        rights=[{"candidate_id": "m1", "license": "CC0", "attribution": "", "source_url": ""}],
    ))
    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    names = {route["stage"] for route in bundle["reroutes"]}
    assert {"narration", "script", "media"} <= names
    assert any("duration" in failure for failure in bundle["failures"])
    assert any("créditos ausentes" in failure for failure in bundle["failures"])


def test_successful_review_packages_without_uploading(tmp_path: Path) -> None:
    context = _context(tmp_path)
    result = _stage().run(context, _inputs(context))
    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    assert bundle["status"] == "passed"
    assert bundle["package_path"]
    package = Path(bundle["package_path"])
    assert (package / "master.mp4").is_file()
    approval = json.loads((package / "approval.json").read_text(encoding="utf-8"))
    assert approval["status"] == "pending"
    assert approval["approver"] is None
    assert ReviewBundle.load(result.artifacts["bundle"].resolve(context.project_dir)).status == "passed"
