"""Effective settings: the value chosen in the profile must reach the runner."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import pytest

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.stages.narration import NarrationStage
from ai_video_factory.workflow.contracts import StageContext
from ai_video_factory.workflow.models import (
    ArtifactRef,
    NarrationBundle,
    ProductionRequest,
    ScriptBundle,
    SpeechRequest,
    SpeechResult,
    StageInputs,
    TtsCapabilities,
)
from ai_video_factory.workflow.planning import build_assembly


def _context(
    tmp_path: Path,
    stage: str,
    settings: dict[str, Any],
    *,
    language: str = "pt-BR",
    explicit_fields: list[str] | None = None,
) -> StageContext:
    store = ProfileStore(tmp_path / f"profiles-{stage}.sqlite3")
    snapshot = store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal",
        "name": "Canal",
        "language": language,
        "settings": settings,
        "explicit_fields": explicit_fields if explicit_fields is not None else list(settings),
    }))
    request = ProductionRequest.model_validate({
        "production_id": f"prod-{stage}", "profile_id": "canal", "topic": "Tema",
        "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
    })
    request.project_dir.mkdir(parents=True, exist_ok=True)
    memory = build_memory_context(store, snapshot, stage, request.topic)
    return StageContext(
        request=request, snapshot=snapshot, stage=stage, attempt=1,  # type: ignore[arg-type]
        artifacts_dir=request.project_dir / "artifacts" / stage,
        memory=memory, effective_settings=memory.settings,
        tool_versions={"tts": "fake"}, project_dir=request.project_dir,
    )


def _script_inputs(context: StageContext) -> StageInputs:
    script = ScriptBundle(
        title="Episódio", language=context.language, estimated_duration_seconds=2.0,
        scenes=[{
            "scene_id": "s1", "title": "Cena", "narration_text": "Texto falado.",
            "estimated_seconds": 2.0,
            "shots": [{"shot_id": "sh1", "visual": "imagem da cena"}],
        }],
    )
    path = context.project_dir / "script.json"
    script.save(path)
    return StageInputs.load("narration", {
        "script": ArtifactRef.from_path(path, context.project_dir, "application/json"),
    }, context.project_dir)


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\0\0" * 8000)


class _CapturingTts:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.requests: list[SpeechRequest] = []

    def capabilities(self) -> TtsCapabilities:
        return TtsCapabilities(
            provider="fake", languages=["pt-BR"], voices=["padrao"],
            supports_pause=True, supports_alignment=False,
        )

    def synthesize(self, request: SpeechRequest, destination: Path) -> SpeechResult:
        self.requests.append(request)
        _write_wav(destination)
        return SpeechResult(
            audio=ArtifactRef.from_path(destination, self.root, "audio/wav"),
            provider="fake", model="m", voice="padrao",
            language=request.language, duration_seconds=1.0, metadata={},
        )


def test_explicit_voice_reaches_tts_provider(tmp_path: Path) -> None:
    context = _context(tmp_path, "narration", {
        "narration.voice": "voz-escolhida",
        "narration.languages": ["pt-BR"],
    })
    provider = _CapturingTts(context.project_dir)

    NarrationStage(tts=provider).run(context, _script_inputs(context))

    assert provider.requests
    assert provider.requests[0].voice == "voz-escolhida"
    assert context.setting("narration.voice") == "voz-escolhida"


def test_media_settings_reach_the_real_media_stage(tmp_path: Path) -> None:
    context = _context(tmp_path, "media", {
        "media.candidates_per_shot": 1,
        "media.query_suffix": "documentário",
    })
    calls: list[tuple[str, int]] = []
    own_file = tmp_path / "own.mp4"
    own_file.write_bytes(b"video")

    def search(query: str, limit: int) -> list[dict[str, Any]]:
        calls.append((query, limit))
        return [{"id": "m1", "title": "imagem da cena", "license": "CC0", "path": str(own_file)}]

    from ai_video_factory.asset_memory import AssetMemory, scoped_memory_path
    from ai_video_factory.stages.media import MediaStage

    result = MediaStage(
        search=search, fetch=lambda raw, directory: Path(str(raw["path"])),
        memory=AssetMemory(scoped_memory_path("canal", data_dir=tmp_path / "data"), profile_id="canal"),
        data_dir=tmp_path / "data",
    ).run(context, _media_inputs(context))

    assert calls and calls[0][1] == 1
    assert "documentário" in calls[0][0]
    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    assert len(bundle["candidates"]) == 1


def _media_inputs(context: StageContext) -> StageInputs:
    script = ScriptBundle(
        title="Episódio", language=context.language, estimated_duration_seconds=2.0,
        scenes=[{
            "scene_id": "s1", "title": "Cena", "narration_text": "fala",
            "estimated_seconds": 2.0,
            "shots": [{"shot_id": "sh1", "visual": "imagem da cena"}],
        }],
    )
    audio = context.project_dir / "seg.wav"
    audio.write_bytes(b"RIFFfake")
    narration = NarrationBundle(
        provider="fake", voice="v", language=context.language,
        segments=[{
            "segment_id": "n1", "scene_id": "s1", "shot_id": "sh1", "text": "fala",
            "audio": ArtifactRef.from_path(audio, context.project_dir, "audio/wav").model_dump(),
            "start_seconds": 0.0, "duration_seconds": 2.0,
        }],
        total_duration_seconds=2.0,
    )
    refs: dict[str, ArtifactRef] = {}
    for name, bundle in (("script", script), ("narration", narration)):
        path = context.project_dir / f"{name}.json"
        bundle.save(path)
        refs[name] = ArtifactRef.from_path(path, context.project_dir, "application/json")
    return StageInputs.load("media", refs, context.project_dir)


def test_assembly_and_review_share_the_same_flat_resolution_settings(tmp_path: Path) -> None:
    context = _context(tmp_path, "review", {
        "editing.width": 1280,
        "editing.height": 720,
        "review.duration_tolerance_seconds": 2.5,
    })
    script = ScriptBundle(
        title="T", language=context.language, estimated_duration_seconds=1.0,
        scenes=[{"scene_id": "s1", "title": "Cena", "narration_text": "fala",
                 "estimated_seconds": 1.0, "shots": [{"shot_id": "sh1", "visual": "v"}]}],
    )
    audio = context.project_dir / "seg.wav"
    audio.write_bytes(b"RIFFfake")
    from ai_video_factory.workflow.models import MediaBundle
    narration = NarrationBundle(
        provider="fake", voice="v", language=context.language,
        segments=[{"segment_id": "n1", "scene_id": "s1", "shot_id": "sh1", "text": "fala",
                   "audio": ArtifactRef.from_path(audio, context.project_dir, "audio/wav").model_dump(),
                   "start_seconds": 0.0, "duration_seconds": 1.0}],
        total_duration_seconds=1.0,
    )
    plan = build_assembly(script, narration, MediaBundle(), context.snapshot)

    assert plan.width == 1280 and plan.height == 720
    assert context.setting("editing.width") == plan.width
    assert context.setting("editing.height") == plan.height
    assert context.setting("review.duration_tolerance_seconds") == 2.5


def test_mixed_flat_and_nested_settings_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ambígu|ambiguous|mistur"):
        _context(tmp_path, "narration", {
            "narration.voice": "plana",
            "narration": {"voice": "aninhada"},
        })
