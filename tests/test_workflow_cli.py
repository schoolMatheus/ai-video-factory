"""Workflow CLI behaviour (plan task 15)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from ai_video_factory import workflow_cli
from ai_video_factory.cli import app
from ai_video_factory.profiles.store import ProfileStore


sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_staged_workflow import RecordingRunner  # noqa: E402


def _setup(tmp_path: Path) -> None:
    Path(tmp_path / "canal.json").write_text(json.dumps({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
        "operation_budget": {"max_external_calls": 10},
    }), encoding="utf-8")
    runner = CliRunner()
    created = runner.invoke(app, ["profiles", "create", "--from-file", str(tmp_path / "canal.json")],
                            env={"AI_VIDEO_FACTORY_DATA_DIR": str(tmp_path)})
    assert created.exit_code == 0, created.output


def _invoke(tmp_path: Path, *args: str):
    return CliRunner().invoke(app, list(args), env={"AI_VIDEO_FACTORY_DATA_DIR": str(tmp_path)})


def test_dry_run_does_not_call_runners_or_activate_learning(tmp_path: Path, monkeypatch) -> None:
    _setup(tmp_path)
    runner = RecordingRunner()
    monkeypatch.setattr(workflow_cli, "build_runners", lambda store, snapshot, root: {
        stage: runner for stage in ("research", "script", "narration", "media", "editing", "review")
    })
    result = _invoke(
        tmp_path, "workflow", "run", "--profile", "canal", "--topic", "Tema",
        "--dry-run", "--base-dir", str(tmp_path / "projects"),
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "pending"
    assert runner.calls == []
    store = ProfileStore(tmp_path / "profiles" / "profiles.sqlite3")
    assert store.list_observations("canal") == []


def test_run_through_and_resume(tmp_path: Path, monkeypatch) -> None:
    _setup(tmp_path)
    first = RecordingRunner()
    monkeypatch.setattr(workflow_cli, "build_runners", lambda store, snapshot, root: {
        stage: first for stage in ("research", "script", "narration", "media", "editing", "review")
    })
    started = _invoke(
        tmp_path, "workflow", "run", "--profile", "canal", "--topic", "Tema",
        "--through", "script", "--base-dir", str(tmp_path / "projects"),
        "--production", "prod-cli",
    )
    assert started.exit_code == 0, started.output
    assert first.calls == ["research", "script"]

    second = RecordingRunner()
    monkeypatch.setattr(workflow_cli, "build_runners", lambda store, snapshot, root: {
        stage: second for stage in ("research", "script", "narration", "media", "editing", "review")
    })
    resumed = _invoke(
        tmp_path, "workflow", "resume", "--profile", "canal", "--production", "prod-cli",
        "--base-dir", str(tmp_path / "projects"),
    )
    assert resumed.exit_code == 0, resumed.output
    assert second.calls == ["narration", "media", "editing", "review"]


def test_explicit_profile_is_required(tmp_path: Path) -> None:
    result = _invoke(tmp_path, "workflow", "run", "--topic", "Tema")
    assert result.exit_code != 0
    assert "Missing option" in result.output


def test_filmcraft_doctor_is_read_only(tmp_path: Path) -> None:
    result = _invoke(tmp_path, "workflow", "filmcraft-doctor")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["name"] == "filmcraft_bridge"
