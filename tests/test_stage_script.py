"""Script stage behaviour (plan task 8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.stages.script import ScriptStage, ScriptStageError
from ai_video_factory.workflow.contracts import StageContext
from ai_video_factory.workflow.models import (
    ArtifactRef,
    ClaimEntry,
    EvidenceEntry,
    ProductionRequest,
    ResearchBundle,
    ScriptBundle,
    StageInputs,
)


def _context_and_inputs(tmp_path: Path, *, language: str = "pt-BR") -> tuple[StageContext, StageInputs]:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    snapshot = store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": language,
    }))
    request = ProductionRequest.model_validate({
        "production_id": "prod-1", "profile_id": "canal", "topic": "Tema",
        "target_minutes": 2.0, "base_dir": str(tmp_path / "projects"),
    })
    request.project_dir.mkdir(parents=True, exist_ok=True)
    memory = build_memory_context(store, snapshot, "script", request.topic)
    context = StageContext(
        request=request, snapshot=snapshot, stage="script", attempt=1,
        artifacts_dir=request.project_dir / "artifacts" / "02_script",
        memory=memory, effective_settings=memory.settings, project_dir=request.project_dir,
    )
    research = ResearchBundle(
        topic="Tema", angle="recorte",
        sources=[{"url": "https://a.example/a", "content_hash": "hash"}],
        claims=[ClaimEntry(
            claim_id="c1", text="Fato sustentado", classification="confirmed fact",
            source_ids=["https://a.example/a"],
            evidence=[EvidenceEntry(source_url="https://a.example/a", quote="trecho real")],
            verified=True,
        )],
        synthesis="síntese",
    )
    path = context.project_dir / "research.json"
    research.save(path)
    ref = ArtifactRef.from_path(path, context.project_dir, "application/json")
    return context, StageInputs.load("script", {"research": ref}, context.project_dir)


def test_generated_script_links_every_fact_to_evidence_and_direction(tmp_path: Path) -> None:
    context, inputs = _context_and_inputs(tmp_path)
    result = ScriptStage().run(context, inputs)
    bundle = ScriptBundle.load(result.artifacts["bundle"].resolve(context.project_dir))
    assert bundle.language == "pt-BR"
    assert len(bundle.scenes) == 1
    scene = bundle.scenes[0]
    assert scene.narration_text.startswith("Fato sustentado")
    assert scene.pauses[0].seconds == 0.3
    assert len(scene.shots) == 2
    assert scene.shots[0].claim_refs == ["c1"]
    assert scene.shots[1].transition == "dissolve"
    assert scene.shots[1].overlap_seconds == 0.4
    assert scene.shots[0].intent and scene.shots[0].on_screen_text
    markdown = result.artifacts["script"].resolve(context.project_dir).read_text(encoding="utf-8")
    assert "Fala exata:" in markdown
    assert "pausa de 0.3s" in markdown


def test_invented_claim_reference_is_rejected(tmp_path: Path) -> None:
    context, inputs = _context_and_inputs(tmp_path)

    def generator(context: Any, research: Any) -> ScriptBundle:
        return ScriptBundle(
            title="Episódio", language=context.language, estimated_duration_seconds=10.0,
            scenes=[{
                "scene_id": "s1", "title": "Cena", "narration_text": "fala",
                "estimated_seconds": 10.0,
                "shots": [{"shot_id": "sh1", "visual": "v", "claim_refs": ["claim-inventado"]}],
            }],
        )

    with pytest.raises(ScriptStageError, match="absent from the research bundle"):
        ScriptStage(generator=generator).run(context, inputs)


def test_insufficient_script_fails_without_padding(tmp_path: Path) -> None:
    context, inputs = _context_and_inputs(tmp_path)

    def generator(context: Any, research: Any) -> ScriptBundle:
        return ScriptBundle(
            title="Episódio", language=context.language, estimated_duration_seconds=100.0,
            scenes=[{
                "scene_id": "s1", "title": "Cena", "narration_text": "   ",
                "estimated_seconds": 100.0,
                "shots": [{"shot_id": "sh1", "visual": "v"}],
            }],
        )

    with pytest.raises(ScriptStageError, match="no spoken content"):
        ScriptStage(generator=generator).run(context, inputs)


def test_language_follows_the_profile(tmp_path: Path) -> None:
    context, inputs = _context_and_inputs(tmp_path, language="en-US")
    bundle = ScriptStage().run(context, inputs).artifacts["bundle"].read_json(context.project_dir)
    assert bundle["language"] == "en-US"
