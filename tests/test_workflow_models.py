"""Behaviour tests for the six versioned delivery contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_video_factory.workflow.models import (
    ArtifactRef,
    EditingBundle,
    MediaBundle,
    NarrationBundle,
    ResearchBundle,
    ReviewBundle,
    ScriptBundle,
    StageInputs,
    StageInputError,
)


def _ref(tmp_path: Path, name: str = "asset.mp4") -> ArtifactRef:
    path = tmp_path / name
    path.write_bytes(b"fixture bytes")
    return ArtifactRef.from_path(path, tmp_path, "video/mp4")


def _research() -> ResearchBundle:
    return ResearchBundle(
        topic="Tema informado",
        angle="recorte",
        sources=[{"url": "https://example.org/a", "quality": "reliable", "content_hash": "abc"}],
        claims=[{
            "claim_id": "c1", "text": "afirmação sustentada",
            "classification": "confirmed fact", "source_ids": ["https://example.org/a"],
            "evidence": [{"source_url": "https://example.org/a", "quote": "trecho real"}],
            "verified": True,
        }],
        contradictions=[],
        uncertainties=["fonte secundária"],
        synthesis="síntese",
    )


def _script() -> ScriptBundle:
    return ScriptBundle(
        title="Episódio",
        language="pt-BR",
        chapters=[{"chapter_id": "ch1", "title": "Abertura", "scene_ids": ["s1"]}],
        scenes=[{
            "scene_id": "s1", "title": "Cena 1", "narration_text": "Fala exata.",
            "estimated_seconds": 12.0,
            "pauses": [{"after_shot_id": "sh1", "seconds": 0.4}],
            "shots": [{
                "shot_id": "sh1", "visual": "imagem de arquivo", "intent": "contextualizar",
                "on_screen_text": "Título na tela", "transition": "dissolve", "overlap_seconds": 0.5,
                "claim_refs": ["c1"], "target_seconds": 11.0,
            }],
        }],
        estimated_duration_seconds=12.0,
    )


def _narration(ref: ArtifactRef) -> NarrationBundle:
    return NarrationBundle(
        provider="kokoro", voice="af_heart", language="pt-BR",
        segments=[{
            "segment_id": "n1", "scene_id": "s1", "shot_id": "sh1",
            "text": "Fala exata.", "audio": ref.model_dump(),
            "start_seconds": 0.0, "duration_seconds": 11.5,
        }],
        spoken_text="Fala exata.", total_duration_seconds=11.5,
    )


def _media(ref: ArtifactRef) -> MediaBundle:
    return MediaBundle(
        candidates=[{
            "candidate_id": "m1", "scene_id": "s1", "shot_id": "sh1",
            "query": "arquivo", "license": "CC-BY", "attribution": "Autor",
            "file": ref.model_dump(), "relevance": 0.9,
        }],
        selected=[{"scene_id": "s1", "shot_id": "sh1", "candidate_id": "m1", "file": ref.model_dump()}],
        rights=[{"candidate_id": "m1", "license": "CC-BY", "attribution": "Autor"}],
    )


def _editing(ref: ArtifactRef) -> EditingBundle:
    return EditingBundle(
        filmcraft_version="0.1-alpha", mode="bridge", project_path="editing/project.fcproj",
        item_map={"sh1": "item-1"}, applied_plan_digest="a" * 64,
        observed_state={"items": [{"shot_id": "sh1"}]}, master=ref.model_dump(),
    )


def _review() -> ReviewBundle:
    return ReviewBundle(
        checks=[{"name": "duration", "category": "technical", "passed": True}],
        editorial_review="ok", rights_review="ok", status="passed",
        package_path="package",
    )


def test_script_roundtrip_preserves_direction_and_evidence(tmp_path: Path) -> None:
    bundle = _script()
    path = bundle.save(tmp_path / "script_bundle.json")
    loaded = ScriptBundle.load(path)
    shot = loaded.scenes[0].shots[0]
    assert loaded.title == "Episódio"
    assert loaded.scenes[0].narration_text == "Fala exata."
    assert loaded.scenes[0].pauses[0].seconds == 0.4
    assert shot.visual == "imagem de arquivo"
    assert shot.intent == "contextualizar"
    assert shot.on_screen_text == "Título na tela"
    assert shot.transition == "dissolve"
    assert shot.overlap_seconds == 0.5
    assert shot.claim_refs == ["c1"]
    assert loaded.chapters[0].scene_ids == ["s1"]


def test_invalid_scene_reference_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown scene_id"):
        ScriptBundle(
            title="x", language="pt-BR", estimated_duration_seconds=1.0,
            chapters=[{"chapter_id": "ch1", "title": "bad", "scene_ids": ["nao-existe"]}],
            scenes=[{
                "scene_id": "s1", "title": "s", "narration_text": "fala",
                "estimated_seconds": 1.0,
                "shots": [{"shot_id": "sh1", "visual": "v"}],
            }],
        )


def test_all_six_bundles_roundtrip(tmp_path: Path) -> None:
    ref = _ref(tmp_path)
    bundles = [
        _research(), _script(), _narration(ref), _media(ref), _editing(ref), _review(),
    ]
    for index, bundle in enumerate(bundles):
        path = tmp_path / f"bundle-{index}.json"
        bundle.save(path)
        reloaded = type(bundle).load(path)
        assert reloaded.model_dump() == bundle.model_dump()


def test_duplicate_ids_and_invalid_durations_fail() -> None:
    scene = {
        "scene_id": "s1", "title": "s", "narration_text": "fala",
        "estimated_seconds": 1.0,
        "shots": [{"shot_id": "sh1", "visual": "v"}],
    }
    with pytest.raises(ValidationError, match="duplicate scene_id"):
        ScriptBundle(title="x", language="pt-BR", estimated_duration_seconds=1.0, scenes=[scene, scene])
    with pytest.raises(ValidationError):
        ResearchBundle(topic="x", claims=[{"claim_id": "c", "text": "t", "classification": "x"}], contradictions=[
            {"contradiction_id": "d", "claim_ids": ["missing"], "nature": "conflito"}
        ])
    with pytest.raises(ValidationError):
        MediaBundle(selected=[{"scene_id": "s", "shot_id": "sh", "candidate_id": "m"}])


def test_stage_inputs_validate_predecessors(tmp_path: Path) -> None:
    ref = _ref(tmp_path)
    bundles = {
        "research": _research(), "script": _script(),
        "narration": _narration(ref), "media": _media(ref),
    }
    refs = {}
    for name, bundle in bundles.items():
        path = tmp_path / f"{name}.json"
        bundle.save(path)
        refs[name] = ArtifactRef.from_path(path, tmp_path, "application/json")

    with pytest.raises(StageInputError, match="missing predecessor"):
        StageInputs.load("script", {}, tmp_path)
    inputs = StageInputs.load("editing", refs, tmp_path)
    assert inputs.script.shot("sh1") is not None
    assert inputs.narration.total_duration_seconds == 11.5
    assert "research" not in inputs.bundles
    # review is the only stage that reads every deliverable
    refs["editing"] = ArtifactRef.from_path(
        _editing(_ref(tmp_path, "editing.mp4")).save(tmp_path / "editing.json"),
        tmp_path, "application/json",
    )
    review_inputs = StageInputs.load("review", refs, tmp_path)
    assert review_inputs.research.topic == "Tema informado"
