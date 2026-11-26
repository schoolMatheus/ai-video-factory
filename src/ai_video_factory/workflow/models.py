"""Delivery contracts for the six-stage production workflow.

Every bundle is a strict, versioned Pydantic model. ``EditDocument`` remains the
legacy contract and is not modified here; conversions are always explicit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from ai_video_factory.profiles.models import (
    OperationBudget,
    StageName,
    StrictModel,
)

SCHEMA_VERSION = 1
STAGE_ORDER: tuple[StageName, ...] = (
    "research", "script", "narration", "media", "editing", "review",
)
REQUIRED_PREDECESSORS: dict[StageName, tuple[StageName, ...]] = {
    "research": (),
    "script": ("research",),
    "narration": ("script",),
    "media": ("script", "narration"),
    "editing": ("script", "narration", "media"),
    "review": ("research", "script", "narration", "media", "editing"),
}
ExecutionStatus = Literal["pending", "running", "completed", "failed", "superseded"]


class StageInputError(ValueError):
    """Raised when a stage's predecessors are absent or invalid."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactRef(StrictModel):
    """A content-addressed reference to a file inside the production root."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    media_type: str = Field(min_length=1)

    @classmethod
    def from_path(cls, path: Path, root: Path, media_type: str = "application/octet-stream") -> ArtifactRef:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"artifact does not exist: {path}")
        try:
            relative = path.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError as error:
            raise ValueError(f"artifact {path} is outside the production root {root}") from error
        return cls(
            path=relative,
            sha256=_digest(path),
            size_bytes=path.stat().st_size,
            media_type=media_type,
        )

    def resolve(self, root: Path) -> Path:
        candidate = (Path(root) / self.path).resolve()
        root_resolved = Path(root).resolve()
        if candidate != root_resolved and root_resolved not in candidate.parents:
            raise ValueError("artifact path escapes the production root")
        return candidate

    def read_json(self, root: Path) -> Any:
        return json.loads(self.resolve(root).read_text(encoding="utf-8"))


class BundleModel(StrictModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    schema_version: Literal[1] = 1

    @classmethod
    def load(cls, path: Path) -> BundleModel:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return path


class ProductionRequest(StrictModel):
    schema_version: Literal[1] = 1
    production_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    angle: str = ""
    target_minutes: float = Field(gt=0)
    seed_source_urls: list[str] = Field(default_factory=list)
    base_dir: str = "data/projects"
    language: str | None = None
    tools: dict[str, str] = Field(default_factory=dict)
    budget: OperationBudget | None = None
    profile_revision: int | None = Field(default=None, ge=1)

    @field_validator("production_id", "profile_id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        from ai_video_factory.profiles.models import SAFE_ID

        if SAFE_ID.fullmatch(value) is None:
            raise ValueError("identifier must be a safe path component")
        return value

    @property
    def project_dir(self) -> Path:
        return Path(self.base_dir) / self.profile_id / self.production_id


class ProfileSnapshotRef(StrictModel):
    """A stored snapshot, kept as its own artifact next to the production."""

    snapshot: dict[str, Any]


# ---------------- Research ----------------

class SourceEntry(StrictModel):
    url: str = Field(min_length=1)
    title: str = ""
    quality: str = "unverified"
    content_hash: str = ""
    content_ref: ArtifactRef | None = None


class EvidenceEntry(StrictModel):
    source_url: str = Field(min_length=1)
    quote: str
    chunk_id: str = ""


class ClaimEntry(StrictModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    classification: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    verified: bool = False


class ContradictionEntry(StrictModel):
    contradiction_id: str = Field(min_length=1)
    claim_ids: list[str] = Field(default_factory=list)
    nature: str
    resolution: str = ""


class ResearchBundle(BundleModel):
    topic: str = Field(min_length=1)
    angle: str = ""
    sources: list[SourceEntry] = Field(default_factory=list)
    claims: list[ClaimEntry] = Field(default_factory=list)
    contradictions: list[ContradictionEntry] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    synthesis: str = ""
    brief_ref: ArtifactRef | None = None

    @model_validator(mode="after")
    def referenced_claims_exist(self) -> ResearchBundle:
        known = {claim.claim_id for claim in self.claims}
        for contradiction in self.contradictions:
            if any(claim_id not in known for claim_id in contradiction.claim_ids):
                raise ValueError("contradiction references an unknown claim_id")
        return self

    @property
    def verified_claims(self) -> list[ClaimEntry]:
        return [claim for claim in self.claims if claim.verified]


# ---------------- Script ----------------

class Pause(StrictModel):
    after_shot_id: str = Field(min_length=1)
    seconds: float = Field(gt=0)


class Shot(StrictModel):
    shot_id: str = Field(min_length=1)
    visual: str = Field(min_length=1)
    intent: str = ""
    on_screen_text: str = ""
    transition: str = "cut"
    overlap_seconds: float = Field(default=0, ge=0)
    claim_refs: list[str] = Field(default_factory=list)
    target_seconds: float | None = Field(default=None, gt=0)


class Scene(StrictModel):
    scene_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    narration_text: str = Field(min_length=1)
    shots: list[Shot] = Field(default_factory=list)
    pauses: list[Pause] = Field(default_factory=list)
    estimated_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def has_shots(self) -> Scene:
        if not self.shots:
            raise ValueError("each scene needs at least one shot")
        return self


class Chapter(StrictModel):
    chapter_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    scene_ids: list[str] = Field(default_factory=list)


class ScriptBundle(BundleModel):
    title: str = Field(min_length=1)
    logline: str = ""
    language: str = Field(min_length=2)
    chapters: list[Chapter] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    estimated_duration_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def stable_ids(self) -> ScriptBundle:
        scene_ids = [scene.scene_id for scene in self.scenes]
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("duplicate scene_id")
        shot_ids = [shot.shot_id for scene in self.scenes for shot in scene.shots]
        if len(shot_ids) != len(set(shot_ids)):
            raise ValueError("duplicate shot_id")
        known_shots = set(shot_ids)
        for scene in self.scenes:
            for pause in scene.pauses:
                if pause.after_shot_id not in {shot.shot_id for shot in scene.shots}:
                    raise ValueError("pause references a shot outside its scene")
        for chapter in self.chapters:
            if any(scene_id not in scene_ids for scene_id in chapter.scene_ids):
                raise ValueError("chapter references an unknown scene_id")
        return self

    @property
    def canonical_narration(self) -> str:
        return "\n\n".join(scene.narration_text for scene in self.scenes)

    def shot(self, shot_id: str) -> tuple[Scene, Shot] | None:
        for scene in self.scenes:
            for shot in scene.shots:
                if shot.shot_id == shot_id:
                    return scene, shot
        return None


# ---------------- Narration ----------------

class SpeechSegment(StrictModel):
    segment_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    shot_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    audio: ArtifactRef
    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0)
    alignment: Literal["segment", "word"] = "segment"


class NarrationBundle(BundleModel):
    provider: str = Field(min_length=1)
    voice: str = Field(min_length=1)
    model: str = ""
    language: str = Field(min_length=2)
    segments: list[SpeechSegment] = Field(default_factory=list)
    spoken_text: str = ""
    timing_precision: Literal["segment", "word"] = "segment"
    total_duration_seconds: float = Field(gt=0)
    alignment_ref: ArtifactRef | None = None

    @model_validator(mode="after")
    def unique_segments(self) -> NarrationBundle:
        ids = [segment.segment_id for segment in self.segments]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate segment_id")
        return self


# ---------------- Media ----------------

class MediaCandidate(StrictModel):
    candidate_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    shot_id: str = Field(min_length=1)
    query: str = ""
    url: str = ""
    title: str = ""
    license: str | None = None
    attribution: str = ""
    file: ArtifactRef | None = None
    source_in_seconds: float = Field(default=0, ge=0)
    source_duration_seconds: float | None = Field(default=None, gt=0)
    technical_ok: bool = True
    relevance: float = Field(default=0, ge=0, le=1)
    rejection_reason: str | None = None


class RightsRecord(StrictModel):
    candidate_id: str = Field(min_length=1)
    license: str = Field(min_length=1)
    attribution: str = ""
    source_url: str = ""


class MediaGap(StrictModel):
    scene_id: str = Field(min_length=1)
    shot_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    strategy: str = ""


class MediaSelection(StrictModel):
    scene_id: str = Field(min_length=1)
    shot_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    file: ArtifactRef | None = None
    strategy: str | None = None
    source_in_seconds: float = Field(default=0, ge=0)
    source_duration_seconds: float | None = Field(default=None, gt=0)
    movement: str = "static"

    @model_validator(mode="after")
    def has_source(self) -> MediaSelection:
        if self.file is None and not self.strategy:
            raise ValueError("a selection needs a file or an explicit composition strategy")
        return self


class MediaBundle(BundleModel):
    candidates: list[MediaCandidate] = Field(default_factory=list)
    selected: list[MediaSelection] = Field(default_factory=list)
    rights: list[RightsRecord] = Field(default_factory=list)
    gaps: list[MediaGap] = Field(default_factory=list)
    rights_complete: bool = True

    @model_validator(mode="after")
    def selections_reference_candidates(self) -> MediaBundle:
        known = {candidate.candidate_id for candidate in self.candidates}
        if any(selection.candidate_id not in known for selection in self.selected):
            raise ValueError("selection references an unknown candidate_id")
        return self


# ---------------- Assembly / editing ----------------

class AssemblyItem(StrictModel):
    item_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    shot_id: str = Field(min_length=1)
    start_ticks: int = Field(ge=0)
    duration_ticks: int = Field(gt=0)
    source_in_ticks: int = Field(ge=0)
    source_duration_ticks: int | None = Field(default=None, gt=0)
    overlap_ticks: int = Field(default=0, ge=0)
    media_ref: ArtifactRef | None = None
    text: str | None = None


class AssemblyTrack(StrictModel):
    track_id: str = Field(min_length=1)
    kind: Literal["video", "narration", "text", "caption", "music"]
    items: list[AssemblyItem] = Field(default_factory=list)


class AssemblyPlan(BundleModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(gt=0)
    timebase_ticks_per_second: int = Field(gt=0)
    tracks: list[AssemblyTrack] = Field(default_factory=list)
    audio_intent: str = ""
    plan_digest: str = Field(min_length=1)


class EditingBundle(BundleModel):
    filmcraft_version: str = Field(min_length=1)
    mode: Literal["bridge", "headless"]
    project_path: str = Field(min_length=1)
    item_map: dict[str, str] = Field(default_factory=dict)
    applied_plan_digest: str = ""
    observed_state: dict[str, Any] = Field(default_factory=dict)
    previews: list[ArtifactRef] = Field(default_factory=list)
    master: ArtifactRef | None = None
    media_manifest: ArtifactRef | None = None
    warnings: list[str] = Field(default_factory=list)


# ---------------- Review ----------------

class ReviewCheck(StrictModel):
    name: str = Field(min_length=1)
    category: Literal["content", "rights", "technical", "editorial"]
    passed: bool
    detail: str = ""


class Reroute(StrictModel):
    stage: StageName
    reason: str = Field(min_length=1)
    invalidation_keys: list[str] = Field(default_factory=list)


class ReviewBundle(BundleModel):
    checks: list[ReviewCheck] = Field(default_factory=list)
    editorial_review: str = ""
    rights_review: str = ""
    failures: list[str] = Field(default_factory=list)
    reroutes: list[Reroute] = Field(default_factory=list)
    status: Literal["passed", "failed", "blocked"] = "blocked"
    package_path: str | None = None


# ---------------- Results and runtime types ----------------

class StructuredError(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class ObservationSeed(StrictModel):
    type: str = Field(min_length=1)
    source: str = Field(min_length=1)
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    event_key: str = Field(min_length=1)


class StageResult(StrictModel):
    stage: StageName
    status: ExecutionStatus = "completed"
    attempt: int = Field(ge=1)
    artifacts: dict[str, ArtifactRef] = Field(default_factory=dict)
    observations: list[ObservationSeed] = Field(default_factory=list)
    effective_config: dict[str, Any] = Field(default_factory=dict)
    error: StructuredError | None = None


class ProductionResult(StrictModel):
    production_id: str
    profile_id: str
    status: ExecutionStatus
    final_stage: StageName
    project_dir: str
    artifacts: dict[str, ArtifactRef] = Field(default_factory=dict)
    package_path: str | None = None
    failures: list[StructuredError] = Field(default_factory=list)
    learning_revision_ids: list[str] = Field(default_factory=list)


class TtsCapabilities(StrictModel):
    provider: str
    languages: list[str] = Field(default_factory=list)
    voices: list[str] = Field(default_factory=list)
    supports_pause: bool = False
    supports_alignment: bool = False


class SpeechRequest(StrictModel):
    text: str = Field(min_length=1)
    speakable_text: str = Field(min_length=1)
    language: str = Field(min_length=2)
    voice: str = ""
    instructions: str = ""
    scene_id: str = Field(min_length=1)
    shot_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    pauses: list[Pause] = Field(default_factory=list)


class SpeechResult(StrictModel):
    audio: ArtifactRef
    provider: str
    model: str = ""
    voice: str
    language: str
    duration_seconds: float = Field(gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditorCapabilities(StrictModel):
    version: str = Field(min_length=1)
    mode: str = "bridge"
    commands: list[str] = Field(default_factory=list)
    timebase_ticks_per_second: int = Field(default=254016000000, gt=0)
    confirmed: dict[str, Any] = Field(default_factory=dict)


class EditorSnapshot(StrictModel):
    project_path: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)
    dirty: bool = False
    offline_media: list[str] = Field(default_factory=list)
    raw_digest: str = ""


class EditorCommandResult(StrictModel):
    command_id: str
    status: Literal["applied", "rejected", "indeterminate", "no_op"] = "applied"
    warnings: list[str] = Field(default_factory=list)
    job_id: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    error: StructuredError | None = None

    @property
    def requires_inspection(self) -> bool:
        return self.status == "indeterminate"


BUNDLE_TYPES: dict[StageName, type[BundleModel]] = {
    "research": ResearchBundle,
    "script": ScriptBundle,
    "narration": NarrationBundle,
    "media": MediaBundle,
    "editing": EditingBundle,
    "review": ReviewBundle,
}
BUNDLE_FILENAMES: dict[StageName, str] = {
    "research": "research_bundle.json",
    "script": "script_bundle.json",
    "narration": "narration_bundle.json",
    "media": "media_bundle.json",
    "editing": "editing_bundle.json",
    "review": "review_bundle.json",
}


@dataclass(frozen=True)
class StageInputs:
    """Only the validated predecessor bundles a stage is allowed to see."""

    bundles: dict[StageName, BundleModel]
    refs: dict[StageName, ArtifactRef]

    @classmethod
    def load(cls, stage: StageName, refs: dict[StageName, ArtifactRef], root: Path) -> StageInputs:
        required = REQUIRED_PREDECESSORS[stage]
        missing = [name for name in required if name not in refs]
        if missing:
            raise StageInputError(f"{stage} is missing predecessor bundles: {', '.join(missing)}")
        bundles: dict[StageName, BundleModel] = {}
        for name in required:
            bundle = BUNDLE_TYPES[name].load(refs[name].resolve(root))
            if bundle.schema_version != SCHEMA_VERSION:
                raise StageInputError(f"unsupported schema_version for {name}")
            bundles[name] = bundle
        return cls(bundles=bundles, refs=dict(refs))

    def __getitem__(self, stage: StageName) -> BundleModel:
        return self.bundles[stage]

    @property
    def research(self) -> ResearchBundle:
        return self.bundles["research"]  # type: ignore[return-value]

    @property
    def script(self) -> ScriptBundle:
        return self.bundles["script"]  # type: ignore[return-value]

    @property
    def narration(self) -> NarrationBundle:
        return self.bundles["narration"]  # type: ignore[return-value]

    @property
    def media(self) -> MediaBundle:
        return self.bundles["media"]  # type: ignore[return-value]

    @property
    def editing(self) -> EditingBundle:
        return self.bundles["editing"]  # type: ignore[return-value]
