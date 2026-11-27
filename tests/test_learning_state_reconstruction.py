"""Deterministic profile reconstruction after supersession and suspension."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import (
    EvaluationCheck,
    LearningCandidate,
    LearningEvaluation,
    ProfilePatch,
    ProfileSpec,
    TypedPatch,
)
from ai_video_factory.profiles.store import ProfileStore, ScopeViolation
from ai_video_factory.workflow.models import ProductionRequest


def _store(tmp_path: Path) -> ProfileStore:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
        "settings": {"editing.music": "none", "narration.voice": "base-voice"},
        "explicit_fields": [],
        "operation_budget": {"max_external_calls": 10},
    }))
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": "outro", "name": "Outro", "language": "pt-BR",
    }))
    return store


def _activate(
    store: ProfileStore,
    *,
    candidate_id: str,
    path: str,
    value: object,
    condition: str = "always",
    tools: dict[str, str] | None = None,
) -> str:
    candidate = LearningCandidate(
        candidate_id=candidate_id, profile_id="canal", scope="channel", stage="editing",
        condition=condition, change=TypedPatch(op="set", path=f"settings.{path}", value=value),
        evidence_ids=["ev-1"], evaluator="technical",
        compatible_tool_versions=tools or {},
    )
    store.save_candidate(candidate)
    evaluation = LearningEvaluation(
        evaluation_id=f"eval-{candidate_id}", candidate_id=candidate_id, candidate_version=1,
        result="pass", checks=[EvaluationCheck(name="trial", passed=True)],
    )
    store.save_evaluation(evaluation)
    expected = store.get_snapshot("canal").revision
    revised = store.activate_learning(candidate_id, evaluation.evaluation_id,
                                      expected_revision=expected)
    return next(item for item in revised.active_learning_ids if item.startswith(candidate_id))


def _settings(store: ProfileStore) -> dict[str, object]:
    return dict(store.get_snapshot("canal").settings)


def test_superseding_rule_does_not_restore_an_older_music(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _activate(store, candidate_id="z-old", path="editing.music", value="antiga")
    _activate(store, candidate_id="a-independent", path="editing.mode", value="headless")
    _activate(store, candidate_id="m-new", path="editing.music", value="nova")

    settings = _settings(store)
    assert settings["editing.music"] == "nova"
    assert settings["editing.mode"] == "headless"
    snapshot = store.get_snapshot("canal")
    assert len(snapshot.active_learning_ids) == 2
    assert "z-old" not in " ".join(snapshot.active_learning_ids) or "superseded" in [
        item.state for item in store.list_learnings("canal") if item.candidate_id == "z-old"
    ]


def test_suspension_preserves_later_explicit_preferences(tmp_path: Path) -> None:
    store = _store(tmp_path)
    learning_id = _activate(store, candidate_id="music-rule", path="editing.music", value="aprendida")
    snapshot = store.get_snapshot("canal")
    store.revise_profile(
        "canal",
        ProfilePatch(settings={"narration.voice": "voz-explicita"},
                     explicit_fields=["narration.voice"]),
        expected_revision=snapshot.revision, reason="preferência do operador",
    )

    revised = store.suspend_learning(
        "canal", learning_id,
        expected_revision=store.get_snapshot("canal").revision, reason="regra não verificada",
    )

    assert revised.settings["narration.voice"] == "voz-explicita"
    assert revised.settings["editing.music"] == "none"
    assert "music-rule" not in revised.active_learning_ids


def test_incompatible_tool_version_and_unmatched_condition_have_no_effect(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _activate(store, candidate_id="old-tool", path="editing.music", value="tool-v1",
              tools={"filmcraft": "v1"})
    _activate(store, candidate_id="topic-rule", path="narration.voice", value="so-para-tema-x",
              condition="topic:tema-x")

    snapshot = store.get_snapshot("canal")
    request = ProductionRequest.model_validate({
        "production_id": "prod-ctx", "profile_id": "canal", "topic": "Tema outro",
        "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
    })
    memory = build_memory_context(
        store, snapshot.model_copy(update={
            "tool_versions": {"filmcraft": "v2"},
        }), "editing", request.topic,
    )

    assert memory.settings["editing.music"] == "none"
    assert memory.settings["narration.voice"] == "base-voice"
    assert "tool-v1" not in memory.settings.values()
    assert "so-para-tema-x" not in memory.settings.values()


def test_candidate_and_evaluation_scope_cannot_cross_profiles(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = LearningCandidate(
        candidate_id="shared-id", profile_id="canal", scope="channel", stage="editing",
        change=TypedPatch(op="set", path="settings.editing.mode", value="bridge"),
        evidence_ids=["ev-1"],
    )
    store.save_candidate(candidate)
    foreign = candidate.model_copy(update={"profile_id": "outro"})
    with pytest.raises(ScopeViolation):
        store.save_candidate(foreign)
    with pytest.raises(ScopeViolation):
        store.get_candidate("shared-id", profile_id="outro")
    store.save_evaluation(LearningEvaluation(
        evaluation_id="eval-shared", candidate_id="shared-id", candidate_version=1,
        result="pass", checks=[EvaluationCheck(name="trial", passed=True)],
    ))
    with pytest.raises(ScopeViolation):
        store.get_evaluation("eval-shared", profile_id="outro")
