"""TTS adapter around the existing local narration engines.

The adapter declares real language support and records the provider/voice that
was actually used. It never silently substitutes a low-quality voice in another
language for an approved one.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from ai_video_factory.narration import NarrationError, clean_for_speech, synthesize_to_wav
from ai_video_factory.workflow.models import (
    ArtifactRef,
    SpeechRequest,
    SpeechResult,
    TtsCapabilities,
)


class TtsCapabilityError(RuntimeError):
    """The selected provider cannot honour the requested language or feature."""


def wav_duration(path: Path) -> float | None:
    """Measure a WAV's duration from its header; ``None`` for non-WAV data."""
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            if rate <= 0:
                return None
            return handle.getnframes() / rate
    except (OSError, EOFError, wave.Error):
        return None


class LocalTtsProvider:
    """Adapter for Kokoro/Piper/espeak behind one explicit boundary."""

    def __init__(
        self,
        root: Path,
        *,
        provider: str = "kokoro",
        languages: tuple[str, ...] = ("en",),
        voices: tuple[str, ...] = ("af_heart",),
        supports_pause: bool = True,
        supports_alignment: bool = False,
        speed_wpm: int = 170,
        pitch: int = 50,
        synthesizer: Any = None,
        allow_engine_fallback: bool = False,
    ) -> None:
        self.root = Path(root)
        self.provider = provider
        self.languages = tuple(languages)
        self.voices = tuple(voices)
        self.supports_pause = supports_pause
        self.supports_alignment = supports_alignment
        self.speed_wpm = speed_wpm
        self.pitch = pitch
        self.synthesizer = synthesizer or synthesize_to_wav
        self.allow_engine_fallback = allow_engine_fallback

    def capabilities(self) -> TtsCapabilities:
        return TtsCapabilities(
            provider=self.provider,
            languages=list(self.languages),
            voices=list(self.voices),
            supports_pause=self.supports_pause,
            supports_alignment=self.supports_alignment,
        )

    def synthesize(self, request: SpeechRequest, destination: Path) -> SpeechResult:
        capabilities = self.capabilities()
        language = request.language.split("-", 1)[0].lower()
        supported = {item.split("-", 1)[0].lower() for item in capabilities.languages}
        if language not in supported:
            raise TtsCapabilityError(
                f"provider {self.provider} does not support language {request.language}; "
                "no silent fallback to another language/voice"
            )
        metadata: dict[str, Any] = {}
        try:
            self.synthesizer(
                request.speakable_text,
                destination,
                engine=self.provider,
                voice=request.voice or (self.voices[0] if self.voices else ""),
                speed_wpm=self.speed_wpm,
                pitch=self.pitch,
                metadata=metadata,
            )
        except NarrationError as error:
            raise TtsCapabilityError(str(error)) from error
        effective_engine = str(metadata.get("tts_engine", self.provider))
        effective_voice = str(metadata.get("tts_voice", request.voice))
        effective_language = str(metadata.get("tts_language", request.language.split("-", 1)[0]))
        if (
            not self.allow_engine_fallback
            and (
                effective_engine != self.provider
                or (effective_voice and effective_voice != request.voice)
                or effective_language.split("-", 1)[0] != language
            )
        ):
            raise TtsCapabilityError(
                f"engine/voz/idioma efetivos ({effective_engine}, {effective_voice}, "
                f"{effective_language}) divergem do contrato ({self.provider}, "
                f"{request.voice}, {request.language}); degradação não permitida"
            )
        duration = wav_duration(destination)
        if duration is None or duration <= 0:
            raise TtsCapabilityError(f"provider {self.provider} did not produce measurable audio")
        return SpeechResult(
            audio=ArtifactRef.from_path(destination, self.root, "audio/wav"),
            provider=str(metadata.get("tts_engine", self.provider)),
            model=str(metadata.get("tts_model", "")),
            voice=str(metadata.get("tts_voice", request.voice)),
            language=request.language,
            duration_seconds=duration,
            metadata=metadata,
        )
