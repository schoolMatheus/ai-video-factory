"""Versioned profile persistence behaviour (plan task 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_video_factory.profiles.models import ProfilePatch, ProfileSpec
from ai_video_factory.profiles.store import (
    NotFound,
    ProfileStore,
    ProfileStoreError,
    RevisionConflict,
)


def _spec(profile_id: str = "canal-a", **overrides: object) -> ProfileSpec:
    payload: dict = {
        "profile_id": profile_id,
        "name": f"Canal {profile_id}",
        "language": "pt-BR",
        "settings": {"editing.music": "none", "research.preferred_sources": []},
    }
    payload.update(overrides)
    return ProfileSpec.model_validate(payload)


def test_two_profiles_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "profiles.sqlite3"
    store = ProfileStore(path)
    first = store.create_profile(_spec("canal-a"))
    second = store.create_profile(_spec("canal-b", language="en-US"))
    store.close()

    reopened = ProfileStore(path)
    assert reopened.get_snapshot("canal-a").settings_digest == first.settings_digest
    assert reopened.get_snapshot("canal-b").language == "en-US"
    assert reopened.get_snapshot("canal-b").profile_id == second.profile_id
    assert {item.profile_id for item in reopened.list_profiles()} == {"canal-a", "canal-b"}


def test_revision_history_is_immutable_and_concurrency_is_detected(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    original = store.create_profile(_spec())
    revised = store.revise_profile(
        "canal-a", ProfilePatch(settings={"editing.music": "bed-1"}),
        expected_revision=1, reason="operator preference",
    )
    assert revised.revision == 2
    assert revised.settings["editing.music"] == "bed-1"
    assert store.get_snapshot("canal-a", revision=1).settings["editing.music"] == "none"
    with pytest.raises(RevisionConflict):
        store.revise_profile(
            "canal-a", ProfilePatch(settings={"editing.music": "bed-2"}),
            expected_revision=1, reason="stale writer",
        )
    assert store.get_snapshot("canal-a").settings["editing.music"] == "bed-1"


def test_repeated_migration_and_failed_transaction_keep_data(tmp_path: Path) -> None:
    path = tmp_path / "profiles.sqlite3"
    store = ProfileStore(path)
    store.create_profile(_spec())
    ProfileStore(path)  # repeated migration on reopen
    with pytest.raises(ProfileStoreError):
        store.create_profile(_spec())  # duplicate rolls back cleanly
    assert len(store.list_profiles()) == 1
    assert store.get_snapshot("canal-a").revision == 1


def test_productions_are_scoped_to_their_profile(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(_spec("canal-a"))
    store.create_profile(_spec("canal-b"))
    store.record_production("run-a", "canal-a", "state/manifest.json")
    with pytest.raises(NotFound):
        store.get_production("missing", "canal-a")
    # B cannot read A's production through its own scope.
    from ai_video_factory.profiles.store import ScopeViolation

    with pytest.raises(ScopeViolation):
        store.get_production("run-a", "canal-b")
    assert [row["production_id"] for row in store.list_productions("canal-a")] == ["run-a"]
    assert store.list_productions("canal-b") == []


def test_export_and_backup_are_consistent(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(_spec())
    export = store.export_profile("canal-a")
    assert export["schema_version"] == 1
    assert export["revisions"][0]["snapshot"]["profile_id"] == "canal-a"
    backup = store.backup(tmp_path / "backup.sqlite3")
    copy = ProfileStore(backup)
    assert copy.get_snapshot("canal-a").settings_digest == export["revisions"][0]["snapshot"]["settings_digest"]
