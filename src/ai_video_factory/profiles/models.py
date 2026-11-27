"""Models for versioned channel profiles, scoped memory and autonomous learning.

All models in this module use strict Pydantic validation and carry an explicit
``schema_version``. They are a new contract: the legacy ``EditDocument`` family
is deliberately left untouched.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StageName = Literal["research", "script", "narration", "media", "editing", "review"]
LearningScope = Literal["channel", "episode", "technical"]
LearningState = Literal["proposed", "evaluating", "active", "rejected", "suspended", "superseded"]
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_digest(payload: Any) -> str:
    """Stable digest over a JSON-serialisable structure (no secret redaction here)."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class OperationBudget(StrictModel):
    """Explicit operational limits. ``None`` means 'not configured' -> preflight blocks."""

    max_external_calls: int | None = None
    max_attempts_per_stage: int | None = None
    max_runtime_seconds: float | None = None

    @field_validator("max_external_calls", "max_attempts_per_stage")
    @classmethod
    def non_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("budget limits cannot be negative")
        return value

    @field_validator("max_runtime_seconds")
    @classmethod
    def positive_seconds(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        return value

    @property
    def configured(self) -> bool:
        return any(
            value is not None
            for value in (self.max_external_calls, self.max_attempts_per_stage, self.max_runtime_seconds)
        )


class ReviewPolicy(StrictModel):
    """Editorial/technical gates. Fine-grained weights are intentionally absent."""

    required_checks: list[str] = Field(default_factory=list)
    require_rights: bool = True
    max_auto_fix_attempts: int | None = None
    require_human_approval_for_publication: bool = True

    @field_validator("max_auto_fix_attempts")
    @classmethod
    def non_negative(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("max_auto_fix_attempts cannot be negative")
        return value


class LearningPolicy(StrictModel):
    allow_autonomous_activation: bool = False
    require_evaluation: bool = True
    require_evidence: bool = True
    allowed_scopes: list[LearningScope] = Field(default_factory=lambda: ["channel"])


class ProfileSpec(StrictModel):
    schema_version: Literal[1] = 1
    profile_id: str
    name: str = Field(min_length=1)
    language: str = Field(min_length=2)
    niche: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    explicit_fields: list[str] = Field(default_factory=list)
    tool_versions: dict[str, str] = Field(default_factory=dict)
    review_policy: ReviewPolicy = Field(default_factory=ReviewPolicy)
    learning_policy: LearningPolicy = Field(default_factory=LearningPolicy)
    operation_budget: OperationBudget = Field(default_factory=OperationBudget)

    @field_validator("profile_id")
    @classmethod
    def safe_profile_id(cls, value: str) -> str:
        if SAFE_ID.fullmatch(value) is None:
            raise ValueError("profile_id must be a safe path component")
        return value


class ProfileSnapshot(StrictModel):
    schema_version: Literal[1] = 1
    profile_id: str
    revision: int = Field(ge=1)
    name: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    explicit_fields: list[str] = Field(default_factory=list)
    active_learning_ids: list[str] = Field(default_factory=list)
    settings_digest: str = Field(min_length=1)
    language: str = Field(min_length=2)
    niche: str = ""
    tool_versions: dict[str, str] = Field(default_factory=dict)
    review_policy: ReviewPolicy = Field(default_factory=ReviewPolicy)
    learning_policy: LearningPolicy = Field(default_factory=LearningPolicy)
    operation_budget: OperationBudget = Field(default_factory=OperationBudget)
    created_at: str = Field(default_factory=utc_now)


class ProfilePatch(StrictModel):
    """A typed, bounded profile change. Free-form text cannot become config."""

    name: str = ""
    language: str = ""
    niche: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    explicit_fields: list[str] = Field(default_factory=list)
    tool_versions: dict[str, str] = Field(default_factory=dict)
    review_policy: ReviewPolicy | None = None
    learning_policy: LearningPolicy | None = None
    operation_budget: OperationBudget | None = None

    @model_validator(mode="after")
    def has_content(self) -> ProfilePatch:
        if not any(
            (
                self.name,
                self.language,
                self.niche,
                self.settings,
                self.explicit_fields,
                self.tool_versions,
                self.review_policy,
                self.learning_policy,
                self.operation_budget,
            )
        ):
            raise ValueError("profile patch must change at least one field")
        return self


_ALLOWED_PATCH_PREFIXES = ("settings.", "policies.", "budget.", "tool_versions.")


class TypedPatch(StrictModel):
    """One configuration operation; paths are restricted to known submodels."""

    op: Literal["set", "remove"]
    path: str = Field(min_length=1)
    value: Any | None = None

    @field_validator("path")
    @classmethod
    def allowed_path(cls, value: str) -> str:
        if not value.startswith(_ALLOWED_PATCH_PREFIXES):
            raise ValueError("patch path must target settings, policies, budget or tool_versions")
        if any(part in {"", ".", ".."} for part in value.split(".")):
            raise ValueError("patch path contains an invalid component")
        return value

    @model_validator(mode="after")
    def consistent(self) -> TypedPatch:
        if self.op == "set" and self.value is None:
            raise ValueError("a 'set' patch requires a value")
        if self.op == "remove" and self.value is not None:
            raise ValueError("a 'remove' patch cannot carry a value")
        return self

    def targets_explicit_field(self, snapshot: ProfileSnapshot) -> bool:
        return self.path.startswith("settings.") and self.path.split(".", 1)[1] in snapshot.explicit_fields

    def apply(self, snapshot: ProfileSnapshot) -> dict[str, Any]:
        """Return a new payload of mutable profile fields with this patch applied."""
        payload: dict[str, Any] = {
            "settings": dict(snapshot.settings),
            "policies": {
                "review_policy": snapshot.review_policy.model_dump(),
                "learning_policy": snapshot.learning_policy.model_dump(),
            },
            "budget": snapshot.operation_budget.model_dump(),
            "tool_versions": dict(snapshot.tool_versions),
        }
        head, _, tail = self.path.partition(".")
        if head == "settings":
            payload["settings"][tail] = self.value if self.op == "set" else _remove_key(payload["settings"], tail)
        elif head == "tool_versions":
            payload["tool_versions"][tail] = self.value if self.op == "set" else _remove_key(payload["tool_versions"], tail)
        elif head == "policies":
            policy_name, _, field_name = tail.partition(".")
            policy = payload["policies"][policy_name]
            if self.op == "set":
                policy[field_name] = self.value
            else:
                _remove_key(policy, field_name)
        else:  # budget
            if self.op == "set":
                payload["budget"][tail] = self.value
            else:
                _remove_key(payload["budget"], tail)
        return payload


def _remove_key(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    mapping.pop(key, None)
    return mapping


def snapshot_digest(
    profile_id: str,
    revision: int,
    settings: dict[str, Any],
    explicit_fields: list[str],
    active_learning_ids: list[str],
    review_policy: ReviewPolicy,
    learning_policy: LearningPolicy,
    operation_budget: OperationBudget,
    tool_versions: dict[str, str],
) -> str:
    return canonical_digest(
        {
            "profile_id": profile_id,
            "revision": revision,
            "settings": settings,
            "explicit_fields": explicit_fields,
            "active_learning_ids": active_learning_ids,
            "review_policy": review_policy.model_dump(),
            "learning_policy": learning_policy.model_dump(),
            "budget": operation_budget.model_dump(),
            "tool_versions": tool_versions,
        }
    )


def make_snapshot(spec: ProfileSpec, revision: int = 1, active_learning_ids: list[str] | None = None) -> ProfileSnapshot:
    active = list(active_learning_ids or [])
    return ProfileSnapshot(
        profile_id=spec.profile_id,
        revision=revision,
        name=spec.name,
        settings=dict(spec.settings),
        explicit_fields=list(spec.explicit_fields),
        active_learning_ids=active,
        settings_digest=snapshot_digest(
            spec.profile_id, revision, spec.settings, spec.explicit_fields,
            active, spec.review_policy, spec.learning_policy,
            spec.operation_budget, spec.tool_versions,
        ),
        language=spec.language,
        niche=spec.niche,
        tool_versions=dict(spec.tool_versions),
        review_policy=spec.review_policy,
        learning_policy=spec.learning_policy,
        operation_budget=spec.operation_budget,
    )


def apply_profile_patch(snapshot: ProfileSnapshot, patch: ProfilePatch, reason: str) -> ProfileSnapshot:
    """Build the next revision without mutating the previous snapshot."""
    settings = dict(snapshot.settings)
    settings.update(patch.settings)
    explicit = list(dict.fromkeys([*snapshot.explicit_fields, *patch.explicit_fields]))
    tool_versions = {**snapshot.tool_versions, **patch.tool_versions}
    revision = snapshot.revision + 1
    return ProfileSnapshot(
        profile_id=snapshot.profile_id,
        revision=revision,
        name=patch.name or snapshot.name,
        settings=settings,
        explicit_fields=explicit,
        active_learning_ids=list(snapshot.active_learning_ids),
        settings_digest=snapshot_digest(
            snapshot.profile_id, revision, settings, explicit, snapshot.active_learning_ids,
            patch.review_policy or snapshot.review_policy,
            patch.learning_policy or snapshot.learning_policy,
            patch.operation_budget or snapshot.operation_budget,
            tool_versions,
        ),
        language=patch.language or snapshot.language,
        niche=patch.niche or snapshot.niche,
        tool_versions=tool_versions,
        review_policy=patch.review_policy or snapshot.review_policy,
        learning_policy=patch.learning_policy or snapshot.learning_policy,
        operation_budget=patch.operation_budget or snapshot.operation_budget,
        created_at=utc_now(),
    )


class Observation(StrictModel):
    schema_version: Literal[1] = 1
    observation_id: str
    profile_id: str
    production_id: str | None = None
    stage: StageName
    attempt: int = Field(ge=1)
    type: str = Field(min_length=1)
    source: str = Field(min_length=1)
    scope: Literal["channel", "technical"] = "channel"
    created_at: str = Field(default_factory=utc_now)
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    effective_config: dict[str, Any] = Field(default_factory=dict)
    tool_versions: dict[str, str] = Field(default_factory=dict)
    event_key: str = Field(min_length=1)

    @field_validator("profile_id", "observation_id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if SAFE_ID.fullmatch(value) is None:
            raise ValueError("identifier must be a safe path component")
        return value


class LearningCandidate(StrictModel):
    schema_version: Literal[1] = 1
    candidate_id: str
    profile_id: str
    scope: LearningScope
    stage: StageName
    condition: str = "always"
    change: TypedPatch
    evidence_ids: list[str] = Field(default_factory=list)
    evaluator: Literal["technical", "editorial", "none"] = "technical"
    compatible_tool_versions: dict[str, str] = Field(default_factory=dict)
    state: LearningState = "proposed"
    is_hypothesis: bool = False
    rationale: str = ""
    created_at: str = Field(default_factory=utc_now)


class EvaluationCheck(StrictModel):
    name: str
    passed: bool
    detail: str = ""


class LearningEvaluation(StrictModel):
    schema_version: Literal[1] = 1
    evaluation_id: str
    candidate_id: str
    candidate_version: int = Field(ge=1)
    trial: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    checks: list[EvaluationCheck] = Field(default_factory=list)
    result: Literal["pass", "fail", "inconclusive"] = "inconclusive"
    rationale: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evaluator: str = "rule-based"
    created_at: str = Field(default_factory=utc_now)


class LearningRevision(StrictModel):
    schema_version: Literal[1] = 1
    learning_id: str
    profile_id: str
    candidate_id: str
    evaluation_id: str
    action: TypedPatch
    condition: str = "always"
    compatible_tool_versions: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    activated_at: str = Field(default_factory=utc_now)
    supersedes_id: str | None = None
    state: Literal["active", "suspended", "superseded"] = "active"
    suspension_reason: str | None = None


class MemoryContext(StrictModel):
    schema_version: Literal[1] = 1
    profile_id: str
    scope: str = "channel"
    stage: StageName
    topic: str = ""
    digest: str
    rules: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    learning_ids: list[str] = Field(default_factory=list)
    snapshot_revision: int = Field(ge=1)
