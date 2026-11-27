"""Autonomous learning review, evaluation, activation and reversal.

Observations are evidence, never authority. Free-form text from a model or an
external source cannot become an operational patch: only typed patches that
pass policy checks and evaluation may be activated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import (
    EvaluationCheck,
    LearningCandidate,
    LearningEvaluation,
    LearningPolicy,
    LearningRevision,
    Observation,
    ProfileSnapshot,
    StageName,
    TypedPatch,
    utc_now,
)
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.workflow.contracts import StageContext

LearningReviewer = Callable[[StageContext, list[Observation]], list[LearningCandidate]]
_FORBIDDEN_SOURCES = {"external_source", "source_content", "web_page"}


def _candidate_from_observation(
    context: StageContext, observation: Observation
) -> LearningCandidate | None:
    """Deterministic base reviewer: only explicit typed proposals qualify."""
    if observation.source in _FORBIDDEN_SOURCES:
        return None
    payload = observation.effective_config.get("proposed_patch")
    if not isinstance(payload, dict):
        return None
    try:
        patch = TypedPatch.model_validate(payload)
    except Exception:  # noqa: BLE001 - a malformed proposal is not a candidate
        return None
    return LearningCandidate(
        candidate_id=uuid4().hex,
        profile_id=observation.profile_id,
        scope="channel",
        stage=observation.stage,
        change=patch,
        evidence_ids=[observation.event_key],
        evaluator="technical" if observation.type.startswith("technical") else "editorial",
        rationale=observation.summary,
        is_hypothesis=not observation.evidence_refs,
    )


def review_observations(
    context: StageContext,
    observations: list[Observation],
    reviewer: LearningReviewer | None = None,
) -> list[LearningCandidate]:
    """Group observations and produce bounded, typed proposals."""
    reviewer = reviewer or (lambda ctx, items: [
        candidate
        for item in items
        if (candidate := _candidate_from_observation(ctx, item)) is not None
    ])
    candidates = reviewer(context, list(observations))
    for candidate in candidates:
        if candidate.profile_id != context.snapshot.profile_id:
            raise ValueError("candidate belongs to another profile")
        if candidate.stage != context.stage:
            raise ValueError("candidate does not apply to this stage")
    return candidates


def evaluate_and_apply(
    context: StageContext,
    candidate: LearningCandidate,
    evaluator: Any,
    store: ProfileStore,
    *,
    production_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate one candidate and activate it only on verified evidence."""
    policy: LearningPolicy = context.snapshot.learning_policy
    candidate = candidate.model_copy(update={
        "evidence_ids": [str(item) for item in candidate.evidence_ids],
        "state": "evaluating",
    })
    store.save_candidate(candidate)

    evidence_valid = bool(candidate.evidence_ids) and _evidence_is_trusted(
        store, candidate, Path(context.project_dir)
    )
    scope_ok = candidate.scope in policy.allowed_scopes
    patch_ok = _patch_allowed(context.snapshot, candidate.change)
    if candidate.evaluator == "editorial" and not evidence_valid:
        scope_ok = False

    if evaluator is not None and hasattr(evaluator, "evaluate"):
        evaluation = evaluator.evaluate(candidate, context)
    else:
        passed = bool(evidence_valid and scope_ok and patch_ok)
        evaluation = LearningEvaluation(
            evaluation_id=uuid4().hex,
            candidate_id=candidate.candidate_id,
            candidate_version=1,
            trial="rule-based policy check",
            evidence_ids=list(candidate.evidence_ids),
            checks=[EvaluationCheck(name=name, passed=passed, detail=reason) for name, reason in (
                ("evidence", "evidência verificável"),
                ("scope", "escopo permitido"),
                ("typed_patch", "patch tipado e em campo não explícito"),
            )],
            result="pass" if passed else "inconclusive",
            rationale="avaliacao deterministica sem pesos calibrados",
        )
    store.save_evaluation(evaluation)

    trial_ok = bool(evaluation.trial.strip()) and bool(evaluation.checks) and all(
        item.passed for item in evaluation.checks
    )
    can_activate = (
        evaluation.result == "pass"
        and trial_ok
        and policy.allow_autonomous_activation
        and (not policy.require_evaluation or evaluation.checks or evaluator is not None)
        and (not policy.require_evidence or evidence_valid)
        and scope_ok
        and patch_ok
    )
    if not can_activate:
        store.set_candidate_state(candidate.candidate_id, "proposed", profile_id=candidate.profile_id)
        return {
            "learning_id": None,
            "candidate_id": candidate.candidate_id,
            "evaluation_id": evaluation.evaluation_id,
            "status": "hypothesis" if not (evidence_valid and trial_ok) else "proposed",
        }

    snapshot = store.get_snapshot(context.snapshot.profile_id)
    revised = store.activate_learning(
        candidate.candidate_id, evaluation.evaluation_id,
        expected_revision=snapshot.revision,
    )
    latest = store.list_learnings(context.snapshot.profile_id)
    learning_id = next(
        (item.learning_id for item in latest if item.candidate_id == candidate.candidate_id),
        None,
    )
    return {
        "learning_id": learning_id,
        "candidate_id": candidate.candidate_id,
        "evaluation_id": evaluation.evaluation_id,
        "status": "active",
        "revision": revised.revision,
    }


def _evidence_is_trusted(
    store: ProfileStore, candidate: LearningCandidate, root: Path
) -> bool:
    """An event key alone is not evidence: a persisted artifact must exist."""
    try:
        observations = store.list_observations(candidate.profile_id)
    except Exception:  # noqa: BLE001 - unreadable store is not evidence
        return False
    trusted = {item.event_key: item for item in observations if item.source not in _FORBIDDEN_SOURCES}
    for key in candidate.evidence_ids:
        observation = trusted.get(key)
        if observation is None or not observation.evidence_refs:
            return False
        if not any((root / ref).is_file() for ref in observation.evidence_refs):
            return False
    return True


def _patch_allowed(snapshot: ProfileSnapshot, patch: TypedPatch) -> bool:
    if patch.targets_explicit_field(snapshot):
        return False
    forbidden = ("secret", "token", "password", "api_key", "credential", "budget")
    path = patch.path.lower()
    if any(part in path for part in forbidden):
        return False
    if patch.path.startswith("tool_versions.") and patch.op == "set":
        # Tool versions describe observed reality; a learning must not forge one.
        return False
    return True


def activate_learning(
    store: ProfileStore,
    candidate_id: str,
    evaluation_id: str,
    *,
    expected_revision: int,
) -> ProfileSnapshot:
    return store.activate_learning(candidate_id, evaluation_id, expected_revision=expected_revision)


def suspend_learning(
    store: ProfileStore,
    profile_id: str,
    learning_id: str,
    *,
    expected_revision: int,
    reason: str,
) -> ProfileSnapshot:
    return store.suspend_learning(
        profile_id, learning_id, expected_revision=expected_revision, reason=reason
    )


def suspend_incompatible(
    store: ProfileStore,
    profile_id: str,
    tool_versions: dict[str, str],
    *,
    reason: str,
) -> list[str]:
    """Suspend active rules whose tool compatibility no longer holds."""
    suspended: list[str] = []
    for revision in store.list_learnings(profile_id):
        required = revision.compatible_tool_versions
        if not required or all(tool_versions.get(tool) == version for tool, version in required.items()):
            continue
        snapshot = store.get_snapshot(profile_id)
        store.suspend_learning(
            profile_id, revision.learning_id,
            expected_revision=snapshot.revision,
            reason=f"{reason}: {required}",
        )
        suspended.append(revision.learning_id)
    return suspended


def record_manual_observation(
    store: ProfileStore,
    context: StageContext,
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    source: str = "filmcraft_snapshot",
) -> Observation | None:
    """Capture an observed change without claiming confirmed intent."""
    if before == after:
        return None
    return Observation(
        observation_id=uuid4().hex,
        profile_id=context.snapshot.profile_id,
        production_id=context.request.production_id,
        stage=context.stage,
        attempt=context.attempt,
        type="manual_state_change",
        source=source,
        summary="estado observado mudou entre checkpoints; intenção não inferida",
        evidence_refs=[],
        effective_config=dict(context.effective_settings),
        event_key=f"{context.request.production_id}:{context.stage}:manual:{utc_now()}",
    )
