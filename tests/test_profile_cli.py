"""Profile CLI behaviour (plan task 15)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ai_video_factory.cli import app
from ai_video_factory.profiles.store import ProfileStore


def _profile_file(tmp_path: Path) -> Path:
    path = tmp_path / "canal.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "profile_id": "canal",
        "name": "Canal",
        "language": "pt-BR",
        "settings": {"editing.music": "none"},
        "operation_budget": {"max_external_calls": 5},
    }), encoding="utf-8")
    return path


def _invoke(tmp_path: Path, *args: str):
    runner = CliRunner()
    return runner.invoke(app, list(args), env={"AI_VIDEO_FACTORY_DATA_DIR": str(tmp_path)})


def test_create_list_show_memory_feedback_and_export(tmp_path: Path) -> None:
    created = _invoke(tmp_path, "profiles", "create", "--from-file", str(_profile_file(tmp_path)))
    assert created.exit_code == 0, created.output
    assert json.loads(created.output)["profile_id"] == "canal"

    listed = _invoke(tmp_path, "profiles", "list")
    assert [item["profile_id"] for item in json.loads(listed.output)] == ["canal"]

    shown = _invoke(tmp_path, "profiles", "show", "canal")
    assert json.loads(shown.output)["revision"] == 1

    store = ProfileStore(tmp_path / "profiles" / "profiles.sqlite3")
    store.record_production("prod-1", "canal", "state/run_ids.json")
    feedback = _invoke(
        tmp_path, "profiles", "feedback", "canal", "--production", "prod-1",
        "--stage", "editing", "--note", "A música encobriu a fala na abertura",
    )
    assert feedback.exit_code == 0, feedback.output
    assert json.loads(feedback.output)["source"] == "user"

    memories = _invoke(tmp_path, "profiles", "memory", "canal", "--stage", "editing")
    payload = json.loads(memories.output)
    assert payload["observations"][0]["type"] == "user_feedback"

    output = tmp_path / "export.json"
    exported = _invoke(tmp_path, "profiles", "export", "canal", "--output", str(output))
    assert exported.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["profile_id"] == "canal"


def test_missing_profile_gives_clear_error(tmp_path: Path) -> None:
    result = _invoke(tmp_path, "profiles", "show", "inexistente")
    assert result.exit_code != 0
    assert "not found" in result.output
