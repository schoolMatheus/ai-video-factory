"""Public DTOs shared by the local API and the generated TypeScript client.

Only observable facts are represented here. Absent domain modules, missing
measurements and unknown stages are explicit values, never invented defaults.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StageName(StrEnum):
    research = "research"
    script = "script"
    narration = "narration"
    media = "media"
    editing = "editing"
    review = "review"


class StageStatus(StrEnum):
    unknown = "unknown"
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    superseded = "superseded"


class ProductionMode(StrEnum):
    legacy = "legacy"
    staged = "staged"


class ProgressUnit(StrEnum):
    sources = "sources"
    scenes = "scenes"
    segments = "segments"
    shots = "shots"
    frames = "frames"
    bytes = "bytes"


class Progress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed: int = Field(ge=0)
    total: int | None = Field(default=None, ge=0)
    unit: ProgressUnit
    source: str


class ActionAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    enabled: bool
    reason: str | None = None


class ProblemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    recoverable: bool = True
    suggested_action: str | None = None
    diagnostic_reference: str | None = None


class ArtifactView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    media_type: str
    size_bytes: int | None = None
    sha256: str | None = None
    stage: StageName | None = None
    integrity: Literal["verified", "not_recorded"] = "not_recorded"


class StageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StageName
    status: StageStatus = StageStatus.unknown
    activity: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    last_activity_at: str | None = None
    progress: Progress | None = None
    artifacts: list[ArtifactView] = Field(default_factory=list)
    problem: ProblemView | None = None
    observed: bool = False


class ProductionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    mode: ProductionMode
    title: str
    topic: str | None = None
    profile_id: str | None = None
    profile_revision: int | None = None
    snapshot_id: str | None = None
    state: StageStatus = StageStatus.unknown
    observed_stages: list[str] = Field(default_factory=list)
    stages: list[StageView] = Field(default_factory=list)
    artifacts: list[ArtifactView] = Field(default_factory=list)
    capabilities: list[ActionAvailability] = Field(default_factory=list)
    problems: list[ProblemView] = Field(default_factory=list)
    started_at: str | None = None
    updated_at: str | None = None
    cursor: str | None = None


class ProductionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str | None = None
    topic: str = Field(min_length=1)
    angle: str | None = None
    target_minutes: int | None = Field(default=None, ge=1, le=120)
    seed_source_urls: list[str] = Field(default_factory=list)


class ProductionFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str | None = None
    state: StageStatus | None = None
    search: str | None = None
    since: str | None = None


class ProductionPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProductionView]
    next_cursor: str | None = None


class ProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    language: str = Field(min_length=2)
    niche: str = ""
    explicit_fields: list[str] = Field(default_factory=list)


class ProfilePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    settings: dict[str, Any] = Field(default_factory=dict)
    explicit_fields: list[str] | None = None
    reason: str = "Alteração pelo painel local"


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    stage: StageName = StageName.research
    production_id: str | None = None
    evidence: list[str] = Field(default_factory=list)


class SuspendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1)


class ProductionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    production_id: str
    status: str
    note: str = ""
    stage: StageName | None = None
    artifacts: list[str] = Field(default_factory=list)
    invalidated_stages: list[StageName] = Field(default_factory=list)
    problems: list[ProblemView] = Field(default_factory=list)


class PreflightView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_start: bool
    through: StageName | None = None
    actions: list[ActionAvailability] = Field(default_factory=list)
    problems: list[ProblemView] = Field(default_factory=list)


class EventView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    production_id: str
    type: str
    timestamp: str | None = None
    scope: str = "production"
    severity: Literal["info", "warning", "error"] = "info"
    attempt: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EventView]
    next_cursor: str | None = None


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    stop_requested = "stop_requested"
    stopped = "stopped"
    completed = "completed"
    failed = "failed"
    unknown = "unknown"


class JobView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    production_id: str | None = None
    status: JobStatus = JobStatus.unknown
    heartbeat_at: str | None = None
    result_reference: str | None = None
    problem: ProblemView | None = None


class CapabilitiesView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_version: str
    legacy_read: bool = True
    profiles: bool = False
    staged_flow: bool = False
    editor: bool = False
    stop_control: bool = False
    upload: bool = False


class ProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    niche: str = ""
    revision: int
    settings: dict[str, Any] = Field(default_factory=dict)
    explicit_fields: list[str] = Field(default_factory=list)
    available: bool = True
    problem: ProblemView | None = None


class MemoryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    profile_id: str
    stage: StageName | None = None
    state: str
    summary: str
    origin: Literal["explicit", "inferred", "observed"] = "observed"
    condition: str | None = None
    evidence: list[str] = Field(default_factory=list)
    before: str | None = None
    after: str | None = None
    revision: int | None = None
    updated_at: str | None = None


class MemoryPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MemoryView]
    next_cursor: str | None = None


class ActionName(StrEnum):
    resume = "resume"
    stop_after_stage = "stop_after_stage"
    revise_script = "revise_script"
    replace_media = "replace_media"
    reconcile_editor = "reconcile_editor"
    open_editor = "open_editor"


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ActionName
    expected_revision: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class OperationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    production_id: str | None = None
    status: JobStatus = JobStatus.queued
    accepted: bool = True
    problem: ProblemView | None = None


class UiError(Exception):
    """Base for structured API failures that never expose raw diagnostics."""

    code = "ui_error"
    status_code = 500
    recoverable = False
    suggested_action: str | None = None

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def as_problem(self) -> ProblemView:
        return ProblemView(
            code=self.code,
            message=self.message,
            recoverable=self.recoverable,
            suggested_action=self.suggested_action,
            diagnostic_reference=self.detail,
        )


class NotFoundError(UiError):
    code = "not_found"
    status_code = 404
    recoverable = True
    suggested_action = "Verifique o identificador ou atualize a lista."


class InvalidRequestError(UiError):
    code = "invalid_request"
    status_code = 422
    recoverable = True
    suggested_action = "Revise os campos informados."


class ConflictError(UiError):
    code = "revision_conflict"
    status_code = 409
    recoverable = True
    suggested_action = "Recarregue o estado atual e tente novamente."


class DependencyUnavailableError(UiError):
    code = "dependency_unavailable"
    status_code = 503
    recoverable = True
    suggested_action = "Verifique a configuração em Ferramentas e tente novamente."
