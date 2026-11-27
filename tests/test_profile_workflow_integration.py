"""Two-channel integration, legacy isolation and backup behaviour (task 16)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

from ai_video_factory.asset_memory import import_legacy_rejections
from ai_video_factory.profiles.models import (
    EvaluationCheck,
    LearningCandidate,
    LearningEvaluation,
    LearningPolicy,
    ProfileSpec,
    TypedPatch,
)
from ai_video_factory.profiles.store import ProfileStore, TECHNICAL_SCOPE
from ai_video_factory.workflow.models import STAGE_ORDER, ProductionRequest
from ai_video_factory.workflow.orchestrator import run_production

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_staged_workflow import RecordingRunner  # noqa: E402


def _profile(tmp_path: Path, profile_id: str, *, autonomous: bool = False) -> ProfileStore:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": profile_id,
        "name": profile_id,
        "language": "pt-BR",
        "settings": {"editing.music": "none"},
        "learning_policy": LearningPolicy(
            allow_autonomous_activation=autonomous,
            require_evaluation=True,
            require_evidence=True,
            allowed_scopes=["channel"],
        ),
        "operation_budget": {"max_external_calls": 10},
    }))
    return store


def _request(tmp_path: Path, profile_id: str, production_id: str) -> ProductionRequest:
    return ProductionRequest.model_validate({
        "production_id": production_id,
        "profile_id": profile_id,
        "topic": "Tema compartilhado",
        "target_minutes": 1.0,
        "base_dir": str(tmp_path / "projects"),
    })


def _runners() -> dict:
    runner = RecordingRunner()
    return {stage: runner for stage in STAGE_ORDER}


def _activate_music(store: ProfileStore, profile_id: str) -> str:
    candidate_id = uuid4().hex
    store.save_candidate(LearningCandidate(
        candidate_id=candidate_id, profile_id=profile_id, scope="channel",
        stage="editing", evidence_ids=["legacy:clip"],
        change=TypedPatch(op="set", path="settings.editing.music", value="bed"),
    ))
    store.record_technical_observation(
        __import__("ai_video_factory.profiles.models", fromlist=["Observation"]).Observation(
            observation_id=uuid4().hex, profile_id=TECHNICAL_SCOPE, scope="technical",
            stage="editing", attempt=1, type="codec_test", source="editor",
            summary="ensaio técnico", event_key="legacy:clip",
        )
    )
    evaluation_id = uuid4().hex
    store.save_evaluation(LearningEvaluation(
        evaluation_id=evaluation_id, candidate_id=candidate_id,
        candidate_version=1, trial="ensaio controlado", result="pass",
        checks=[EvaluationCheck(name="trial", passed=True)],
    ))
    store.activate_learning(
        candidate_id, evaluation_id,
        expected_revision=store.get_snapshot(profile_id).revision,
    )
    return candidate_id


def test_two_profiles_share_media_bytes_without_leaking_preferences(tmp_path: Path) -> None:
    store = _profile(tmp_path, "canal-a", autonomous=True)
    _profile(tmp_path, "canal-b")
    _activate_music(store, "canal-a")

    for profile_id in ("canal-a", "canal-b"):
        result = run_production(
            _request(tmp_path, profile_id, f"prod-{profile_id}"),
            store=store, runners=_runners(),
        )
        assert result.status == "completed", result.failures

    project_a = tmp_path / "projects" / "canal-a" / "prod-canal-a"
    project_b = tmp_path / "projects" / "canal-b" / "prod-canal-b"
    media_a = json.loads((project_a / "state" / "media_result.json").read_text(encoding="utf-8"))
    media_b = json.loads((project_b / "state" / "media_result.json").read_text(encoding="utf-8"))
    assert media_a["artifacts"]["bundle"]["sha256"] == media_b["artifacts"]["bundle"]["sha256"]

    editing_a = json.loads((project_a / "state" / "editing_result.json").read_text(encoding="utf-8"))
    editing_b = json.loads((project_b / "state" / "editing_result.json").read_text(encoding="utf-8"))
    assert editing_a["effective_config"]["editing.music"] == "bed"
    assert editing_b["effective_config"]["editing.music"] == "none"
    assert all(item.profile_id == "canal-a" for item in store.list_observations("canal-a"))
    assert all(item.profile_id == "canal-b" for item in store.list_observations("canal-b"))
    assert store.get_snapshot("canal-b").settings["editing.music"] == "none"


def test_legacy_import_is_idempotent_and_unscoped_runs_stay_legacy(tmp_path: Path) -> None:
    store = _profile(tmp_path, "canal-a")
    legacy = tmp_path / "data" / "asset_memory.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({
        "rejections": {"clip-1": {"reason": "antigo"}},
    }), encoding="utf-8")
    assert import_legacy_rejections(store, legacy) == 1
    assert import_legacy_rejections(store, legacy) == 1
    assert len(store.list_technical_observations()) == 1
    assert store.list_observations("canal-a") == []
    assert store.list_productions("canal-a") == []


def test_backup_and_resume_after_interruption(tmp_path: Path) -> None:
    store = _profile(tmp_path, "canal-a")
    request = _request(tmp_path, "canal-a", "prod-a")
    run_production(request, store=store, runners=_runners(), through="script")
    backup = store.backup(tmp_path / "backup.sqlite3")

    restored = ProfileStore(backup)
    assert restored.get_snapshot("canal-a").settings_digest == store.get_snapshot("canal-a").settings_digest

    connection = sqlite3.connect(store.path)
    connection.execute("DELETE FROM observations")
    connection.commit()
    connection.close()
    assert store.list_observations("canal-a") == []

    resumed = _runners()
    result = run_production(request, store=store, runners=resumed, through="script")
    assert result.status == "completed"
    assert resume_calls(resumed) == []
    assert len(store.list_observations("canal-a")) == 2


def resume_calls(runners: dict) -> list[str]:
    runner = next(iter(runners.values()))
    return list(runner.calls)
