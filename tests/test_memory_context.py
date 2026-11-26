"""Effective settings and stage-scoped summaries (plan task 5)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ai_video_factory.profiles.context import build_memory_context, stage_settings_digest
from ai_video_factory.profiles.models import (
    LearningCandidate,
    LearningEvaluation,
    Observation,
    ProfilePatch,
    ProfileSpec,
    TypedPatch,
)
from ai_video_factory.profiles.store import ProfileStore


def _store(tmp_path: Path) -> ProfileStore:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal",
        "name": "Canal",
        "language": "pt-BR",
        "settings": {
            "editing.music": "none",
            "research.preferred_sources": [],
            "narration.voice": "af_heart",
        },
        "explicit_fields": ["narration.voice"],
    }))
    return store


def _activate(
    store: ProfileStore,
    patch: TypedPatch,
    *,
    stage: str = "editing",
    tools: dict[str, str] | None = None,
    evidence: list[str] | None = None,
) -> object:
    snapshot = store.get_snapshot("canal")
    candidate_id = uuid4().hex
    store.save_candidate(LearningCandidate(
        candidate_id=candidate_id,
        profile_id="canal",
        scope="channel",
        stage=stage,  # type: ignore[arg-type]
        change=patch,
        evidence_ids=evidence or ["obs-1"],
        compatible_tool_versions=tools or {},
    ))
    store.save_evaluation(LearningEvaluation(
        evaluation_id=uuid4().hex,
        candidate_id=candidate_id,
        candidate_version=1,
        result="pass",
    ))
    return store.activate_learning(
        candidate_id, _last_evaluation(store, candidate_id),
        expected_revision=snapshot.revision,
    )


def _last_evaluation(store: ProfileStore, candidate_id: str) -> str:
    import sqlite3
    import json

    connection = sqlite3.connect(store.path)
    row = connection.execute(
        "SELECT evaluation_id FROM learning_evaluations "
        "WHERE candidate_id = ? ORDER BY created_at DESC LIMIT 1",
        (candidate_id,),
    ).fetchone()
    connection.close()
    return str(row[0])


def test_editing_change_preserves_research_digest(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = store.get_snapshot("canal")
    research_before = stage_settings_digest(original, "research")
    editing_before = stage_settings_digest(original, "editing")

    edited = store.revise_profile(
        "canal", ProfilePatch(settings={"editing.music": "bed"}),
        expected_revision=1, reason="music",
    )
    assert stage_settings_digest(edited, "research") == research_before
    assert stage_settings_digest(edited, "editing") != editing_before

    sourced = store.revise_profile(
        "canal", ProfilePatch(settings={"research.preferred_sources": ["https://example.org"]}),
        expected_revision=2, reason="source",
    )
    assert stage_settings_digest(sourced, "research") != research_before


def test_old_snapshot_resolves_superseded_learning(tmp_path: Path) -> None:
    store = _store(tmp_path)
    old_snapshot = store.get_snapshot("canal")
    old_context = build_memory_context(store, old_snapshot, "editing", "tema")
    assert old_context.rules == []

    _activate(store, TypedPatch(op="set", path="settings.editing.music", value="bed"))
    current = store.get_snapshot("canal")
    current_context = build_memory_context(store, current, "editing", "tema")
    assert any("editing.music" in rule for rule in current_context.rules)

    # A production pinned to the first learning keeps resolving that id after
    # the rule was superseded in the current profile.
    pinned = build_memory_context(store, current, "editing", "tema")
    pinned_ids = list(pinned.learning_ids)
    _activate(store, TypedPatch(op="set", path="settings.editing.music", value="bed2"))
    newest = store.get_snapshot("canal")
    assert newest.revision == 3
    pinned_context = build_memory_context(store, current, "editing", "tema")
    assert pinned_context.learning_ids == pinned_ids
    assert any("'bed'" in rule for rule in pinned_context.rules)
    current_context = build_memory_context(store, newest, "editing", "tema")
    assert any("'bed2'" in rule for rule in current_context.rules)
    assert old_snapshot.settings["editing.music"] == "none"


def test_explicit_preference_overrides_inference_and_episode_exception(tmp_path: Path) -> None:
    store = _store(tmp_path)
    # A learning must not overwrite the explicit voice preference.
    snapshot = store.get_snapshot("canal")
    context = build_memory_context(store, snapshot, "narration", "tema")
    assert context.settings["narration.voice"] == "af_heart"
    assert context.digest


def test_incompatible_tool_version_is_excluded(tmp_path: Path) -> None:
    store = _store(tmp_path)
    from ai_video_factory.profiles.models import ProfilePatch

    store.revise_profile(
        "canal", ProfilePatch(tool_versions={"filmcraft": "0.2"}),
        expected_revision=1, reason="tool upgraded",
    )
    _activate(
        store, TypedPatch(op="set", path="settings.editing.music", value="bed"),
        tools={"filmcraft": "0.1"},
    )
    current = store.get_snapshot("canal")
    context = build_memory_context(store, current, "editing", "tema")
    assert context.learning_ids == []
    assert "editing.music" not in " ".join(context.rules)


def test_summary_filtered_by_stage_and_topic(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record_observation(Observation(
        observation_id=uuid4().hex, profile_id="canal", production_id=None,
        stage="editing", attempt=1, type="command_failure",
        source="filmcraft", summary="comando de edição falhou",
        evidence_refs=["artifacts/05_editing/log.json"], event_key="editing:cmd",
    ))
    store.record_observation(Observation(
        observation_id=uuid4().hex, profile_id="canal", production_id=None,
        stage="research", attempt=1, type="source_failure",
        source="research", summary="fonte fora do ar", event_key="research:src",
    ))
    editing = build_memory_context(store, store.get_snapshot("canal"), "editing", "tema")
    research = build_memory_context(store, store.get_snapshot("canal"), "research", "tema")
    assert any("command_failure" in rule for rule in editing.rules)
    assert not any("source_failure" in rule for rule in editing.rules)
    assert any("source_failure" in rule for rule in research.rules)
    assert "artifacts/05_editing/log.json" in editing.references
