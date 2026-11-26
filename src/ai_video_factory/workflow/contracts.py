"""Protocols and execution context for stage runners and external adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ai_video_factory.profiles.models import MemoryContext, ProfileSnapshot, StageName
from ai_video_factory.workflow.models import (
    EditorCapabilities,
    EditorCommandResult,
    EditorSnapshot,
    ProductionRequest,
    SpeechRequest,
    SpeechResult,
    StageInputs,
    StageResult,
    TtsCapabilities,
)


@dataclass(frozen=True)
class StageContext:
    """Everything a stage is allowed to know, with the profile revision pinned."""

    request: ProductionRequest
    snapshot: ProfileSnapshot
    stage: StageName
    attempt: int
    artifacts_dir: Path
    memory: MemoryContext
    effective_settings: dict[str, Any] = field(default_factory=dict)
    tool_versions: dict[str, str] = field(default_factory=dict)
    dry_run: bool = False
    project_dir: Path = field(default_factory=Path)

    @property
    def topic(self) -> str:
        return self.request.topic

    @property
    def language(self) -> str:
        return self.request.language or self.snapshot.language

    def setting(self, path: str, default: Any = None) -> Any:
        """Read a dot-separated setting from the effective stage settings."""
        value: Any = self.effective_settings
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value


class StageRunner(Protocol):
    external: bool

    def run(self, context: StageContext, inputs: StageInputs) -> StageResult: ...


class TtsProvider(Protocol):
    def capabilities(self) -> TtsCapabilities: ...

    def synthesize(self, request: SpeechRequest, destination: Path) -> SpeechResult: ...


class FilmCraftClient(Protocol):
    def connect(self) -> EditorCapabilities: ...

    def inspect(self) -> EditorSnapshot: ...

    def execute(self, command_id: str, params: dict[str, Any]) -> EditorCommandResult: ...

    def close(self) -> None: ...


class CandidateEvaluator(Protocol):
    def evaluate(self, candidate: Any, context: Any) -> Any: ...
