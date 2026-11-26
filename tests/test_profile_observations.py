"""Scoped evidence, idempotent events and legacy boundary (plan task 4)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from ai_video_factory.asset_memory import AssetMemory, import_legacy_rejections, scoped_memory_path
from ai_video_factory.profiles.models import Observation, ProfileSpec
from ai_video_factory.profiles.store import (
    ProfileStore,
    ScopeViolation,
    TECHNICAL_SCOPE,
)


def _store(tmp_path: Path) -> ProfileStore:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(_spec("canal-a"))
    store.create_profile(_spec("canal-b"))
    store.record_production("prod-a", "canal-a", "state/manifest.json")
    store.record_production("prod-b", "canal-b", "state/manifest.json")
    return store


def _spec(profile_id: str) -> ProfileSpec:
    return ProfileSpec.model_validate({
        "profile_id": profile_id,
        "name": profile_id,
        "language": "pt-BR",
    })


def _observation(profile_id: str, event_key: str, **overrides: object) -> Observation:
    payload: dict = {
        "observation_id": uuid4().hex,
        "profile_id": profile_id,
        "production_id": f"prod-{profile_id[-1]}",
        "stage": "media",
        "attempt": 1,
        "type": "editorial_rejection",
        "source": "stage",
        "summary": "rejeição contextual",
        "evidence_refs": ["artifacts/04_media/candidate.json"],
        "event_key": event_key,
    }
    payload.update(overrides)
    return Observation.model_validate(payload)


def test_repeated_event_key_is_idempotent_but_new_attempt_is_not(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.record_observation(_observation("canal-a", "prod-a:media:1:reject"))
    repeated = store.record_observation(
        _observation("canal-a", "prod-a:media:1:reject", summary="duplicata")
    )
    second_attempt = store.record_observation(
        _observation("canal-a", "prod-a:media:2:reject", attempt=2)
    )
    assert first == repeated
    assert second_attempt != first
    assert len(store.list_observations("canal-a")) == 2


def test_editorial_rejection_in_a_does_not_block_b(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record_observation(_observation("canal-a", "prod-a:media:1:reject"))
    assert [item.summary for item in store.list_observations("canal-a")] == ["rejeição contextual"]
    assert store.list_observations("canal-b") == []

    memory_a = AssetMemory(scoped_memory_path("canal-a", data_dir=tmp_path / "data"), profile_id="canal-a")
    memory_b = AssetMemory(scoped_memory_path("canal-b", data_dir=tmp_path / "data"), profile_id="canal-b")
    memory_a.record_rejection("clip-1", "não combina com o canal A")
    assert memory_a.is_blocked("clip-1")
    assert not memory_b.is_blocked("clip-1")


def test_technical_history_requires_explicit_scope(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ScopeViolation):
        store.record_observation(
            _observation("canal-a", "codec", scope="technical")
        )
    store.record_technical_observation(
        Observation(
            observation_id=uuid4().hex,
            profile_id=TECHNICAL_SCOPE,
            scope="technical",
            production_id=None,
            stage="editing",
            attempt=1,
            type="codec_incompatibility",
            source="editor",
            summary="codec X falha na versão Y",
            event_key="codec:v1",
        )
    )
    assert len(store.list_technical_observations()) == 1
    assert all(
        item.scope == "channel" for item in store.list_observations("canal-a")
    )


def test_legacy_rejections_import_as_history_not_preference(tmp_path: Path) -> None:
    store = _store(tmp_path)
    legacy = tmp_path / "data" / "asset_memory.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({
        "schema_version": 1,
        "rejections": {"clip-x": {"reason": "baixa qualidade", "count": 2}},
    }), encoding="utf-8")
    count = import_legacy_rejections(store, legacy)
    assert count == 1
    imported = store.list_technical_observations()[0]
    assert imported.type == "legacy_technical_rejection"
    assert imported.scope == "technical"
    assert store.list_observations("canal-a") == []


def test_channel_memory_requires_explicit_scope(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        AssetMemory()
    shared = AssetMemory(
        scoped_memory_path(TECHNICAL_SCOPE, data_dir=tmp_path / "data"),
        scope="technical", profile_id=TECHNICAL_SCOPE,
    )
    shared.record_rejection("clip-1", "codec corrompido", classification="technical")
    assert shared.is_blocked("clip-1")
