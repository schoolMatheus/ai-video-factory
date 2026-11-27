"""Operational learning: evidence, trials, autonomy and reversible effects."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.learning import (
    evaluate_and_apply,
    suspend_incompatible,
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
from ai_video_factory.workflow.models import ProductionRequest


class _Evaluator:
    def __init__(self, *, checks: bool = True, trial: str = "ensaio controlado") -> None:
        self.checks = checks
        self.trial = trial

    def evaluate(self, candidate: LearningCandidate, context: object) -> LearningEvaluation:
        return LearningEvaluation(
            evaluation_id=uuid4().hex, candidate_id=candidate.candidate_id,
            candidate_version=1, trial=self.trial,
            evidence_ids=list(candidate.evidence_ids),
            checks=[EvaluationCheck(name="trial", passed=True)] if self.checks else [],
            result="pass", rationale="ensaio verificou a mudança",
        )


def _store(tmp_path: Path) -> ProfileStore:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
        "settings": {"narration.voice": "base", "narration.languages": ["pt-BR"]},
        "learning_policy": LearningPolicy(
            allow_autonomous_activation=True, require_evaluation=True,
            require_evidence=True, allowed_scopes=["channel"],
        ).model_dump(),
        "operation_budget": {"max_external_calls": 10},
    }))
    store.record_production("A", "canal", "state/run_ids.json")
    return store


def _candidate(*, evidence: list[str], value: str = "aprendida", tools: dict[str, str] | None = None) -> LearningCandidate:
    return LearningCandidate(
        candidate_id=uuid4().hex, profile_id="canal", scope="channel", stage="narration",
        change=TypedPatch(op="set", path="settings.narration.voice", value=value),
        evidence_ids=evidence, evaluator="technical",
        compatible_tool_versions=tools or {},
    )


def _context(store: ProfileStore, tmp_path: Path, topic: str = "Tema A"):
    from ai_video_factory.workflow.contracts import StageContext

    snapshot = store.get_snapshot("canal")
    request = ProductionRequest.model_validate({
        "production_id": "prod-" + uuid4().hex[:8], "profile_id": "canal", "topic": topic,
        "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
    })
    memory = build_memory_context(store, snapshot, "narration", topic)
    return StageContext(
        request=request, snapshot=snapshot, stage="narration", attempt=1,
        artifacts_dir=request.project_dir / "artifacts" / "03_narration",
        memory=memory, effective_settings=memory.settings, project_dir=request.project_dir,
    )


def test_observation_without_artifact_cannot_activate_learning(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record_observation(Observation(
        observation_id=uuid4().hex, profile_id="canal", production_id="A",
        stage="narration", attempt=1, type="technical_failure", source="stage",
        summary="falha sem artefato", event_key="A:narration:failure",
    ))
    candidate = _candidate(evidence=["A:narration:failure"])

    result = evaluate_and_apply(_context(store, tmp_path), candidate, _Evaluator(), store)

    assert result["learning_id"] is None
    assert store.get_snapshot("canal").revision == 1


def test_evaluation_without_trial_or_checks_cannot_activate(tmp_path: Path) -> None:
    store = _store(tmp_path)
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    store.record_observation(Observation(
        observation_id=uuid4().hex, profile_id="canal", production_id="A",
        stage="narration", attempt=1, type="technical_trial", source="stage",
        summary="ensaio registrado", evidence_refs=[str(evidence)],
        event_key="A:narration:trial",
    ))
    context = _context(store, tmp_path)
    candidate = _candidate(evidence=["A:narration:trial"])

    result = evaluate_and_apply(context, candidate, _Evaluator(checks=False, trial=""), store)

    assert result["learning_id"] is None
    assert result["status"] == "hypothesis"


def test_learned_rule_changes_the_next_production_effect(tmp_path: Path) -> None:
    store = _store(tmp_path)
    evidence = tmp_path / "trial.json"
    evidence.write_text("{}", encoding="utf-8")
    store.record_observation(Observation(
        observation_id=uuid4().hex, profile_id="canal", production_id="A",
        stage="narration", attempt=1, type="technical_trial", source="stage",
        summary="ensaio verificou voz", evidence_refs=[str(evidence)],
        event_key="A:narration:trial",
    ))
    context_a = _context(store, tmp_path)
    result = evaluate_and_apply(context_a, _candidate(evidence=["A:narration:trial"]),
                                _Evaluator(), store)
    assert result["status"] == "active", result

    snapshot_b = store.get_snapshot("canal")
    context_b = _context(store, tmp_path, topic="Tema B")
    memory = build_memory_context(store, snapshot_b, "narration", context_b.request.topic)
    assert memory.settings["narration.voice"] == "aprendida"

    from ai_video_factory.workflow.services import build_production_services

    services = build_production_services(
        snapshot_b, {"data_root": tmp_path / "data"},
        {"research": object(), "script": object(), "narration": object(),
         "media": object(), "editing": object(), "review": object()},
        store=store,
    )
    assert services.snapshot.settings["narration.voice"] == "aprendida"
    assert not any("secret" in str(value).lower() for value in services.describe().values())


def test_incompatible_tool_version_triggers_automatic_suspension(tmp_path: Path) -> None:
    store = _store(tmp_path)
    evidence = tmp_path / "trial.json"
    evidence.write_text("{}", encoding="utf-8")
    store.record_observation(Observation(
        observation_id=uuid4().hex, profile_id="canal", production_id="A",
        stage="narration", attempt=1, type="technical_trial", source="stage",
        summary="ensaio", evidence_refs=[str(evidence)], event_key="A:narration:trial",
    ))
    result = evaluate_and_apply(
        _context(store, tmp_path),
        _candidate(evidence=["A:narration:trial"], tools={"tts": "v1"}),
        _Evaluator(), store,
    )
    assert result["status"] == "active"

    suspended = suspend_incompatible(store, "canal", {"tts": "v2"}, reason="ferramenta incompatível")

    assert suspended
    snapshot = store.get_snapshot("canal")
    assert snapshot.settings["narration.voice"] == "base"
