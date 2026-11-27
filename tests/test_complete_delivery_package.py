"""Substantive QC and a portable, self-contained delivery package."""

from __future__ import annotations

import json
import shutil
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
    MediaGap,
    NarrationBundle,
    ProductionRequest,
    ResearchBundle,
    ReviewBundle,
    ScriptBundle,
    StageInputs,
)


def _inputs(
    context: StageContext,
    *,
    offline: list[str] | None = None,
    claim_evidence: bool = True,
    gap_strategy: str | None = None,
    composition: bool = True,
) -> StageInputs:
    project = context.project_dir
    master = context.artifacts_dir / "master.mp4"
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"master")
    shot = project / "shot.mp4"
    shot.write_bytes(b"media")
    file_ref = ArtifactRef.from_path(shot, project, "video/mp4")
    master_ref = ArtifactRef.from_path(master, project, "video/mp4")

    claim = ClaimEntry(
        claim_id="c1", text="Fato sustentado", classification="confirmed fact",
        source_ids=["https://a.example"],
        evidence=[EvidenceEntry(source_url="https://a.example", quote="trecho")] if claim_evidence else [],
        verified=claim_evidence,
    )
    research = ResearchBundle(topic="Tema", claims=[claim], synthesis="# Síntese")
    script = ScriptBundle(
        title="Episódio", language="pt-BR", estimated_duration_seconds=1.0,
        scenes=[{"scene_id": "s1", "title": "Cena", "narration_text": "Fala canônica.",
                 "estimated_seconds": 1.0,
                 "shots": [{"shot_id": "sh1", "visual": "v", "claim_refs": ["c1"]}]}],
    )
    narration = NarrationBundle(
        provider="p", voice="v", language="pt-BR",
        segments=[{"segment_id": "n1", "scene_id": "s1", "shot_id": "sh1", "text": "Fala canônica.",
                   "audio": file_ref.model_dump(), "start_seconds": 0.0, "duration_seconds": 1.0}],
        spoken_text="Fala canônica.", total_duration_seconds=1.0,
    )
    gaps: list[MediaGap] = []
    if gap_strategy:
        gaps.append(MediaGap(scene_id="s1", shot_id="sh1", reason="plano ausente", strategy=gap_strategy))
    media = MediaBundle(
        candidates=[{"candidate_id": "m1", "scene_id": "s1", "shot_id": "sh1",
                     "license": "CC0", "attribution": "Autor", "file": file_ref.model_dump()}],
        selected=[{"scene_id": "s1", "shot_id": "sh1", "candidate_id": "m1", "file": file_ref.model_dump()}],
        rights=[{"candidate_id": "m1", "license": "CC0", "attribution": "Autor",
                 "source_url": "https://a.example"}],
        gaps=gaps,
    )
    project_file = context.artifacts_dir / "project.fcproj"
    project_file.write_text(json.dumps({
        "editable": True, "production": context.request.production_id,
    }), encoding="utf-8")
    previews: list[ArtifactRef] = []
    if composition:
        preview = context.artifacts_dir / "preview.mp4"
        preview.write_bytes(b"preview")
        previews.append(ArtifactRef.from_path(preview, project, "video/mp4"))
    editing = EditingBundle(
        filmcraft_version="0.1", mode="bridge", project_path="p.fcproj",
        item_map={"sh1": "item-1"}, master=master_ref.model_dump(),
        observed_state={"offline_media": offline or []}, previews=previews,
    )
    refs: dict[str, ArtifactRef] = {}
    for name, bundle in (("research", research), ("script", script), ("narration", narration),
                         ("media", media), ("editing", editing)):
        path = project / f"{name}.json"
        bundle.save(path)
        refs[name] = ArtifactRef.from_path(path, project, "application/json")
    return StageInputs.load("review", refs, project)


def _context(tmp_path: Path, *, target_minutes: float = 25.0) -> StageContext:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    snapshot = store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
    }))
    request = ProductionRequest.model_validate({
        "production_id": "prod-qc", "profile_id": "canal", "topic": "Tema",
        "target_minutes": target_minutes, "base_dir": str(tmp_path / "projects"),
    })
    request.project_dir.mkdir(parents=True, exist_ok=True)
    memory = build_memory_context(store, snapshot, "review", request.topic)
    return StageContext(
        request=request, snapshot=snapshot, stage="review", attempt=1,
        artifacts_dir=request.project_dir / "artifacts" / "06_review",
        memory=memory, effective_settings=memory.settings, project_dir=request.project_dir,
    )


def _stage(duration: float = 1.0, *, audio: bool = True) -> ReviewStage:
    return ReviewStage(probe=lambda path: {
        "width": 1920, "height": 1080, "duration": duration,
        "audio_streams": 1 if audio else 0,
    })


def test_short_master_unsupported_claim_offline_and_missing_composition_all_fail(tmp_path: Path) -> None:
    context = _context(tmp_path)
    result = _stage(duration=10.0, audio=False).run(context, _inputs(
        context, offline=["missing.mp4"], claim_evidence=False,
        gap_strategy="compor plano com base no plano", composition=False,
    ))
    bundle = ReviewBundle.load(result.artifacts["bundle"].resolve(context.project_dir))
    joined = " ".join(bundle.failures)
    assert bundle.status == "failed"
    assert "duração" in joined
    assert "áudio" in joined
    assert "evidência" in joined
    assert "offline" in joined
    assert "composição" in joined


def test_approved_package_contains_all_deliverables_and_is_portable(tmp_path: Path) -> None:
    context = _context(tmp_path, target_minutes=1 / 60)
    result = _stage(duration=1.0).run(context, _inputs(context, gap_strategy="compor plano"))
    bundle = ReviewBundle.load(result.artifacts["bundle"].resolve(context.project_dir))
    assert bundle.status == "passed", bundle.failures
    package = Path(bundle.package_path).resolve()
    expected = [
        "master.mp4", "thumbnail.jpg", "chapters.json", "captions.srt", "captions.vtt",
        "description.txt", "sources.json", "rights_manifest.json", "filmcraft_project.fcproj",
        "media_manifest.json", "review_report.json", "approval.json", "review_manifest.json",
    ]
    for name in expected:
        assert (package / name).is_file(), name
    approval = json.loads((package / "approval.json").read_text(encoding="utf-8"))
    assert approval["status"] == "pending"
    project = json.loads((package / "filmcraft_project.fcproj").read_text(encoding="utf-8"))
    assert project["editable"] is True
    assert project["production"] == "prod-qc"
    srt = (package / "captions.srt").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,000" in srt
    assert "Fala canônica." in srt

    relocated = tmp_path / "restored" / "package"
    shutil.copytree(package, relocated)
    assert (relocated / "master.mp4").is_file()
    manifest = json.loads((relocated / "review_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "passed"
    assert not any(str(package) in str(value) for value in manifest.values() if isinstance(value, str))
