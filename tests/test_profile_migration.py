"""Schema migration and artifact-reference recovery (plan task 16)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ai_video_factory.profiles.models import ProfilePatch, ProfileSpec
from ai_video_factory.profiles.store import ProfileStore


def _spec(profile_id: str = "canal") -> ProfileSpec:
    return ProfileSpec.model_validate({
        "profile_id": profile_id, "name": "Canal", "language": "pt-BR",
        "settings": {"editing.music": "none"},
    })


def test_migration_is_idempotent_and_preserves_schema_rows(tmp_path: Path) -> None:
    path = tmp_path / "profiles.sqlite3"
    store = ProfileStore(path)
    store.create_profile(_spec())
    store.revise_profile(
        "canal", ProfilePatch(settings={"editing.music": "bed"}),
        expected_revision=1, reason="migration baseline",
    )
    for _ in range(3):
        reopened = ProfileStore(path)
        assert reopened.get_snapshot("canal").revision == 2
    connection = sqlite3.connect(path)
    versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations")]
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )}
    connection.close()
    assert versions == [1]
    assert {
        "profiles", "profile_revisions", "productions", "observations",
        "learning_candidates", "learning_evaluations", "learning_revisions", "memory_events",
    } <= tables


def test_backup_restores_revisions_and_artifact_references(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(_spec())
    store.record_production("prod-1", "canal", "state/refs.json")
    backup = store.backup(tmp_path / "nested" / "backup.sqlite3")
    copy = ProfileStore(backup)
    assert copy.get_production("prod-1", "canal")["manifest_ref"] == "state/refs.json"
    assert copy.get_snapshot("canal").revision == 1


def test_interrupted_transaction_leaves_original_revision(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(_spec())
    try:
        with store._write() as connection:
            connection.execute(
                "INSERT INTO memory_events (profile_id, kind, ref_id, detail_json, created_at) "
                "VALUES ('canal', 'forced_rollback', 'x', '{}', '2026-01-01T00:00:00+00:00')"
            )
            raise RuntimeError("interrupted")
    except RuntimeError:
        pass
    assert store.get_snapshot("canal").revision == 1
    connection = sqlite3.connect(store.path)
    rows = connection.execute(
        "SELECT COUNT(*) FROM memory_events WHERE kind = 'forced_rollback'"
    ).fetchone()[0]
    connection.close()
    assert rows == 0
    assert store.export_profile("canal")["revisions"][0]["snapshot"]["revision"] == 1
