"""Narration stage behaviour (plan task 9)."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import pytest

from ai_video_factory.integrations.tts import TtsCapabilityError
from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.stages.narration import NarrationStage
from ai_video_factory.workflow.contracts import StageContext
from ai_video_factory.workflow.models import (
    ArtifactRef,
    ProductionRequest,
    ScriptBundle,
    SpeechRequest,
    SpeechResult,
    StageInputs,
    TtsCapabilities,
)


def _write_wav(path: Path, seconds: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\0\0" * int(8000 * seconds))


def _context_and_inputs(tmp_path: Path, language: str = "pt-BR") -> tuple[StageContext, StageInputs]:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    snapshot = store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": language,
    }))
    request = ProductionRequest.model_validate({
        "production_id": "prod-1", "profile_id": "canal", "topic": "Tema",
        "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
    })
    request.project_dir.mkdir(parents=True, exist_ok=True)
    memory = build_memory_context(store, snapshot, "narration", request.topic)
    context = StageContext(
        request=request, snapshot=snapshot, stage="narration", attempt=1,
        artifacts_dir=request.project_dir / "artifacts" / "03_narration",
        memory=memory, effective_settings=memory.settings,
        tool_versions={"tts": "fake"}, project_dir=request.project_dir,
    )
    script = ScriptBundle(
        title="Episódio", language=language, estimated_duration_seconds=12.0,
        scenes=[{
            "scene_id": "s1", "title": "Cena", "narration_text": "Texto canônico da narração.",
            "estimated_seconds": 12.0,
            "pauses": [{"after_shot_id": "sh1", "seconds": 0.5}],
            "shots": [{"shot_id": "sh1", "visual": "v"}],
        }],
    )
    path = context.project_dir / "script.json"
    script.save(path)
    inputs = StageInputs.load("narration", {
        "script": ArtifactRef.from_path(path, context.project_dir, "application/json"),
    }, context.project_dir)
    return context, inputs


class FakeTts:
    def __init__(self, root: Path, *, language: str = "pt-BR", voice: str = "other-voice", alignment: bool = True) -> None:
        self.root = root
        self.language = language
        self.voice = voice
        self.alignment = alignment
        self.requests: list[SpeechRequest] = []

    def capabilities(self) -> TtsCapabilities:
        return TtsCapabilities(
            provider="fake-provider", languages=[self.language],
            voices=["approved-voice"], supports_pause=True,
            supports_alignment=self.alignment,
        )

    def synthesize(self, request: SpeechRequest, destination: Path) -> SpeechResult:
        self.requests.append(request)
        _write_wav(destination, 2.0)
        return SpeechResult(
            audio=ArtifactRef.from_path(destination, self.root, "audio/wav"),
            provider="fake-provider", model="fake-model", voice=self.voice,
            language=request.language, duration_seconds=1.0,
            metadata={"alignment": "word" if self.alignment else "segment"},
        )


def test_unsupported_language_fails_without_hidden_fallback(tmp_path: Path) -> None:
    context, inputs = _context_and_inputs(tmp_path, language="ja-JP")
    provider = FakeTts(context.project_dir, language="pt-BR")
    with pytest.raises(TtsCapabilityError, match="does not support"):
        NarrationStage(tts=provider).run(context, inputs)
    assert provider.requests == []


def test_spoken_text_pauses_and_measured_duration(tmp_path: Path) -> None:
    context, inputs = _context_and_inputs(tmp_path)
    provider = FakeTts(context.project_dir)
    result = NarrationStage(tts=provider).run(context, inputs)
    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    assert bundle["spoken_text"] == "Texto canônico da narração."
    segment = bundle["segments"][0]
    assert segment["duration_seconds"] == 2.0  # measured, not the provider's 1.0 claim
    assert bundle["total_duration_seconds"] == 2.5  # 2s audio + 0.5s explicit pause
    assert bundle["voice"] == "other-voice"
    assert any(item.type == "effective_voice_changed" for item in result.observations)
    assert provider.requests[0].pauses[0].seconds == 0.5
    assert result.artifacts["spoken_text"].resolve(context.project_dir).is_file()


def test_engine_degradation_is_blocked_unless_explicitly_allowed(tmp_path: Path) -> None:
    from ai_video_factory.integrations.tts import LocalTtsProvider
    from ai_video_factory.workflow.models import SpeechRequest

    def degrading_synthesizer(text: str, destination: Path, **kwargs: Any) -> None:
        _write_wav(destination, 1.0)
        kwargs["metadata"].update({
            "tts_engine": "espeak", "tts_voice": "en-us", "tts_language": "en",
        })

    provider = LocalTtsProvider(
        tmp_path, provider="kokoro", languages=("pt-BR",), voices=("voz-aprovada",),
        synthesizer=degrading_synthesizer,
    )
    request = SpeechRequest(
        text="Texto", speakable_text="Texto", language="pt-BR", voice="voz-aprovada",
        scene_id="s1", shot_id="sh1", segment_id="n1",
    )
    with pytest.raises(Exception, match="engine|voz|idioma|language"):
        provider.synthesize(request, tmp_path / "degradado.wav")

    allowed = LocalTtsProvider(
        tmp_path, provider="kokoro", languages=("pt-BR",), voices=("voz-aprovada",),
        allow_engine_fallback=True, synthesizer=degrading_synthesizer,
    )
    result = allowed.synthesize(request, tmp_path / "permitido.wav")
    assert result.voice == "en-us"
    assert result.provider == "espeak"


def test_alignment_marks_word_precision(tmp_path: Path) -> None:
    context, inputs = _context_and_inputs(tmp_path)
    provider = FakeTts(context.project_dir)
    stage = NarrationStage(tts=provider, aligner=lambda directory: {"words": [{"word": "Texto"}]})
    result = stage.run(context, inputs)
    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    assert bundle["timing_precision"] == "word"
    assert bundle["segments"][0]["alignment"] == "word"
    assert bundle["alignment_ref"] is not None
