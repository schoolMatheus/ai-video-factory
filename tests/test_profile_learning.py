"""Autonomous learning with evidence, reversal and pinning (plan task 14)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.learning import (
    evaluate_and_apply,
    record_manual_observation,
    review_observations,
    suspend_incompatible,
    suspend_learning,
)
from ai_video_factory.profiles.models import (
    EvaluationCheck,
    LearningCandidate,
    LearningEvaluation,
    LearningPolicy,
    Observation,
    ProfileSpec,
    TypedPatch,
)
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.workflow.contracts import StageContext
from ai_video_factory.workflow.models import ProductionRequest


def _context(tmp_path: Path, *, autonomous: bool = True, explicit: list[str] | None = None) -> tuple[ProfileStore, StageContext]:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    snapshot = store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal",
        "name": "Canal",
        "language": "pt-BR",
        "settings": {"editing.music": "none", "narration.voice": "af_heart"},
        "explicit_fields": explicit or [],
        "learning_policy": LearningPolicy(
            allow_autonomous_activation=autonomous,
            require_evaluation=True,
            require_evidence=True,
            allowed_scopes=["channel"],
        ),
        "operation_budget": {"max_external_calls": 5},
    }))
    request = ProductionRequest.model_validate({
        "production_id": "prod-1", "profile_id": "canal", "topic": "Tema",
        "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
    })
    store.record_production("prod-1", "canal", "state/run_ids.json")
    evidence = tmp_path / "projects" / "canal" / "prod-1" / "artifacts" / "05_editing" / "log.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("{}", encoding="utf-8")
    memory = build_memory_context(store, snapshot, "editing", request.topic)
    return store, StageContext(
        request=request, snapshot=snapshot, stage="editing", attempt=1,
        artifacts_dir=request.project_dir / "artifacts" / "05_editing",
        memory=memory, effective_settings=memory.settings, project_dir=request.project_dir,
    )


class PassingEvaluator:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, candidate: LearningCandidate, context: StageContext) -> LearningEvaluation:
        self.calls += 1
        return LearningEvaluation(
            evaluation_id=uuid4().hex,
            candidate_id=candidate.candidate_id,
            candidate_version=1,
            trial="ensaio controlado",
            result="pass",
            checks=[EvaluationCheck(name="trial", passed=True)],
            rationale="ensaio controlado verificou a mudança",
        )


def _observation(event_key: str = "prod-1:editing:1:observed", source: str = "stage") -> Observation:
    return Observation(
        observation_id=uuid4().hex,
        profile_id="canal",
        production_id="prod-1",
        stage="editing",
        attempt=1,
        type="technical_codec_failure",
        source=source,
        summary="falha técnica observada no editor",
        evidence_refs=["artifacts/05_editing/log.json"],
        event_key=event_key,
    )


def _candidate(evidence: list[str] | None = None, *, path: str = "settings.editing.music") -> LearningCandidate:
    return LearningCandidate(
        candidate_id=uuid4().hex,
        profile_id="canal",
        scope="channel",
        stage="editing",
        change=TypedPatch(op="set", path=path, value="bed"),
        evidence_ids=evidence if evidence is not None else ["prod-1:editing:1:observed"],
        evaluator="technical",
    )


def test_verified_learning_activates_without_human_approval(tmp_path: Path) -> None:
    store, context = _context(tmp_path)
    store.record_observation(_observation())
    evaluator = PassingEvaluator()
    candidates = review_observations(context, store.list_observations("canal"), lambda ctx, items: [_candidate()])
    assert len(candidates) == 1
    result = evaluate_and_apply(context, candidates[0], evaluator, store, production_id="prod-1")
    assert result["status"] == "active"
    assert store.get_snapshot("canal").revision == 2
    assert store.get_snapshot("canal").settings["editing.music"] == "bed"
    assert evaluator.calls == 1


def test_unsupported_learning_stays_proposed(tmp_path: Path) -> None:
    store, context = _context(tmp_path)
    result = evaluate_and_apply(context, _candidate(evidence=[]), PassingEvaluator(), store)
    assert result["status"] == "hypothesis"
    assert result["learning_id"] is None
    assert store.get_snapshot("canal").revision == 1
    assert store.get_candidate(result["candidate_id"]).state == "proposed"


def test_out_of_scope_explicit_field_and_external_source_cannot_change_config(tmp_path: Path) -> None:
    store, context = _context(tmp_path, explicit=["editing.music"])
    store.record_observation(_observation("production:external"))
    for candidate in (
        _candidate(path="settings.editing.music"),
        _candidate(path="settings.some_secret"),
        _candidate(path="policies.review_policy.required_checks"),
    ):
        result = evaluate_and_apply(context, candidate, PassingEvaluator(), store)
        assert result["learning_id"] is None
    assert store.get_snapshot("canal").settings["editing.music"] == "none"
    external = _observation("external:source", source="external_source")
    assert review_observations(context, [external]) == []


def test_failure_suspends_rule_and_restores_previous_setting(tmp_path: Path) -> None:
    store, context = _context(tmp_path)
    store.record_observation(_observation())
    result = evaluate_and_apply(context, _candidate(), PassingEvaluator(), store)
    learning_id = result["learning_id"]
    assert learning_id
    revised = suspend_learning(
        store, "canal", learning_id,
        expected_revision=store.get_snapshot("canal").revision,
        reason="falha relacionada ao ajuste",
    )
    assert revised.settings["editing.music"] == "none"
    assert store.get_learning("canal", learning_id).state == "suspended"


def test_new_editor_version_suspends_incompatible_rule(tmp_path: Path) -> None:
    store, context = _context(tmp_path)
    store.record_observation(_observation())
    candidate = _candidate()
    candidate.compatible_tool_versions = {"filmcraft": "0.1"}
    store.save_candidate(candidate)
    store.save_evaluation(LearningEvaluation(
        evaluation_id=uuid4().hex, candidate_id=candidate.candidate_id,
        candidate_version=1, trial="ensaio controlado",
        result="pass", checks=[EvaluationCheck(name="trial", passed=True)],
    ))
    learning = store.get_snapshot("canal")
    store.activate_learning(
        candidate.candidate_id, _last_evaluation(store, candidate.candidate_id),
        expected_revision=learning.revision,
    )
    suspended = suspend_incompatible(store, "canal", {"filmcraft": "0.2"}, reason="editor atualizado")
    assert len(suspended) == 1
    assert store.get_snapshot("canal").settings["editing.music"] == "none"


def _last_evaluation(store: ProfileStore, candidate_id: str) -> str:
    import json
    import sqlite3

    connection = sqlite3.connect(store.path)
    row = connection.execute(
        "SELECT evaluation_id FROM learning_evaluations WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchone()
    connection.close()
    return str(row[0])


def test_pinned_snapshot_keeps_its_settings_while_next_production_adopts_learning(tmp_path: Path) -> None:
    store, context = _context(tmp_path)
    pinned = store.get_snapshot("canal")
    store.record_observation(_observation())
    evaluate_and_apply(context, _candidate(), PassingEvaluator(), store)
    assert pinned.settings["editing.music"] == "none"
    assert store.get_snapshot("canal").settings["editing.music"] == "bed"


def test_manual_state_change_is_observation_not_confirmed_intent(tmp_path: Path) -> None:
    store, context = _context(tmp_path)
    observation = record_manual_observation(
        store, context, before={"items": []}, after={"items": [{"id": "x"}]}
    )
    assert observation is not None
    assert observation.type == "manual_state_change"
    assert "intenção não inferida" in observation.summary
    assert record_manual_observation(store, context, before={"items": []}, after={"items": []}) is None
