"""Stage 3 — measured narration by segment, with explicit spoken text."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ai_video_factory.integrations.tts import TtsCapabilityError, wav_duration
from ai_video_factory.narration import clean_for_speech
from ai_video_factory.workflow.contracts import StageContext, StageInputs
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    ArtifactRef,
    NarrationBundle,
    ObservationSeed,
    SpeechRequest,
    SpeechSegment,
    StageResult,
)
from ai_video_factory.workflow.contracts import TtsProvider as TtsProtocol

Aligner = Callable[[Path], dict[str, Any] | None]


class NarrationStage:
    external = True

    def __init__(
        self,
        *,
        tts: TtsProtocol | None = None,
        tts_factory: Callable[[Path], TtsProtocol] | None = None,
        aligner: Aligner | None = None,
    ) -> None:
        self.tts = tts
        self.tts_factory = tts_factory
        self.aligner = aligner

    def run(self, context: StageContext, inputs: StageInputs) -> StageResult:
        from ai_video_factory.integrations.tts import LocalTtsProvider

        provider = self.tts
        if provider is None:
            factory = self.tts_factory or (lambda root: LocalTtsProvider(
                root,
                languages=tuple(context.setting("narration.languages", ("en",))),
                voices=tuple(context.setting("narration.voices", ("af_heart",))),
                allow_engine_fallback=bool(context.setting("narration.allow_engine_fallback", False)),
            ))
            provider = factory(context.project_dir)
        capabilities = provider.capabilities()
        selected_language = context.language
        base_language = selected_language.split("-", 1)[0].lower()
        if base_language not in [item.split("-", 1)[0].lower() for item in capabilities.languages]:
            raise TtsCapabilityError(
                f"narration provider {capabilities.provider} does not support {selected_language}; "
                "configure a provider for this language instead of falling back"
            )
        voice = str(context.setting("narration.voice", capabilities.voices[0] if capabilities.voices else ""))
        script = inputs.script
        segment_dir = context.artifacts_dir / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)
        segments: list[SpeechSegment] = []
        spoken_parts: list[str] = []
        cursor = 0.0
        observations: list[ObservationSeed] = []
        use_alignment = self.aligner is not None and capabilities.supports_alignment
        effective_provider = capabilities.provider
        effective_model = ""
        effective_voice = voice

        for scene in script.scenes:
            speakable = clean_for_speech(scene.narration_text)
            if not speakable:
                raise TtsCapabilityError(f"scene {scene.scene_id} has no speakable text")
            request = SpeechRequest(
                text=scene.narration_text,
                speakable_text=speakable,
                language=selected_language,
                voice=voice,
                instructions=scene.title,
                scene_id=scene.scene_id,
                shot_id=scene.shots[0].shot_id,
                segment_id=f"{scene.scene_id}-narration",
                pauses=list(scene.pauses),
            )
            destination = segment_dir / f"{request.segment_id}.wav"
            result = provider.synthesize(request, destination)
            measured = wav_duration(destination) or result.duration_seconds
            if measured <= 0:
                raise TtsCapabilityError(f"no measurable audio for segment {request.segment_id}")
            if result.voice != voice:
                observations.append(ObservationSeed(
                    type="effective_voice_changed", source="tts",
                    summary=f"voz efetiva {result.voice} difere da solicitada {voice} no segmento {request.segment_id}",
                    event_key=f"{context.request.production_id}:narration:voice:{request.segment_id}",
                ))
            effective_provider = result.provider
            effective_model = result.model
            effective_voice = result.voice
            segments.append(SpeechSegment(
                segment_id=request.segment_id,
                scene_id=scene.scene_id,
                shot_id=request.shot_id,
                text=scene.narration_text,
                audio=result.audio,
                start_seconds=cursor,
                duration_seconds=measured,
                alignment="word" if use_alignment else "segment",
            ))
            spoken_parts.append(scene.narration_text)
            cursor += measured + sum(pause.seconds for pause in scene.pauses)

        if not segments:
            raise TtsCapabilityError("script has no scenes to narrate")
        alignment_ref = None
        if use_alignment and self.aligner is not None:
            payload = self.aligner(segment_dir)
            if payload is not None:
                path = context.artifacts_dir / "alignment.json"
                path.write_text(_json(payload), encoding="utf-8")
                alignment_ref = ArtifactRef.from_path(path, context.project_dir, "application/json")

        bundle = NarrationBundle(
            provider=effective_provider,
            voice=effective_voice,
            model=effective_model,
            language=selected_language,
            segments=segments,
            spoken_text="\n\n".join(spoken_parts),
            timing_precision="word" if alignment_ref is not None else "segment",
            total_duration_seconds=cursor,
            alignment_ref=alignment_ref,
        )
        bundle_path = context.artifacts_dir / BUNDLE_FILENAMES["narration"]
        bundle.save(bundle_path)
        text_path = context.artifacts_dir / "spoken_text.txt"
        text_path.write_text(bundle.spoken_text, encoding="utf-8")
        return StageResult(
            stage=context.stage,
            attempt=context.attempt,
            artifacts={
                "bundle": ArtifactRef.from_path(bundle_path, context.project_dir, "application/json"),
                "spoken_text": ArtifactRef.from_path(text_path, context.project_dir, "text/plain"),
                **{segment.segment_id: segment.audio for segment in segments},
            },
            observations=observations,
            effective_config=dict(context.effective_settings),
        )


def _json(payload: object) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)
