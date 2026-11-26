"""Resumable event replay, snapshots and SSE heartbeats."""

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

import pytest

from ai_video_factory.run_store import RunStore
from ai_video_factory.ui_backend.events import CursorExpired, EventService
from ai_video_factory.ui_backend.read_models import ProductionReadModels


@pytest.fixture
def event_service(tmp_path: Path) -> EventService:
    models = ProductionReadModels(tmp_path / "state", tmp_path / "runs")
    return EventService(models, tmp_path / "data" / "ui" / "control.sqlite3")


def _run(tmp_path: Path) -> str:
    store = RunStore(tmp_path / "state", artifact_root=tmp_path / "runs")
    return store.start("research", {"topic": "tema"}).run_id


def _add_event(tmp_path: Path, run_id: str, name: str) -> None:
    path = tmp_path / "state" / "research" / run_id / "events.jsonl"
    with path.open("a", encoding="utf-8") as events_file:
        events_file.write(
            json.dumps(
                {
                    "timestamp": "2026-11-23T00:00:00+00:00",
                    "run_id": run_id,
                    "stage": "research",
                    "event": name,
                    "fields": {"step": name},
                },
                separators=(",", ":"),
            )
            + "\n"
        )


def test_reconnect_replays_only_events_after_cursor(
    tmp_path: Path, event_service: EventService
) -> None:
    run_id = _run(tmp_path)
    _add_event(tmp_path, run_id, "source_found")
    cursor = event_service.snapshot_cursor(run_id)
    _add_event(tmp_path, run_id, "claim_extracted")

    replayed = event_service.replay(run_id, cursor)

    assert [event.type for event in replayed] == ["claim_extracted"]
    assert replayed[0].payload == {"step": "claim_extracted"}


def test_duplicate_event_is_not_inserted_twice(
    tmp_path: Path, event_service: EventService
) -> None:
    run_id = _run(tmp_path)
    _add_event(tmp_path, run_id, "source_found")

    first = event_service.replay(run_id)
    second = event_service.replay(run_id)

    assert [event.id for event in first] == [event.id for event in second]
    assert event_service.count_projected_events(run_id) == len(first)


def test_expired_cursor_requires_new_snapshot(
    tmp_path: Path, event_service: EventService
) -> None:
    run_id = _run(tmp_path)
    cursor = event_service.snapshot_cursor(run_id)
    expired = cursor[:-2] + "xx" if not cursor.endswith("xx") else cursor[:-2] + "yy"

    with pytest.raises(CursorExpired):
        event_service.replay(run_id, expired)


def test_event_between_snapshot_and_subscription_is_received(
    tmp_path: Path, event_service: EventService
) -> None:
    run_id = _run(tmp_path)
    _add_event(tmp_path, run_id, "source_found")
    cursor = event_service.snapshot_cursor(run_id)
    added = False

    def on_poll() -> None:
        nonlocal added
        if not added:
            _add_event(tmp_path, run_id, "claim_extracted")
            added = True

    async def collect() -> list[str]:
        stream = event_service.subscribe(
            run_id,
            cursor,
            max_polls=3,
            sleep=lambda _: None,
            on_poll=on_poll,
        )
        return [event.type async for event in stream]

    assert asyncio.run(collect()) == ["claim_extracted"]


def test_partial_line_does_not_corrupt_cursor(
    tmp_path: Path, event_service: EventService
) -> None:
    run_id = _run(tmp_path)
    _add_event(tmp_path, run_id, "source_found")
    cursor = event_service.snapshot_cursor(run_id)
    count_before = event_service.count_projected_events(run_id)

    path = tmp_path / "state" / "research" / run_id / "events.jsonl"
    with path.open("a", encoding="utf-8") as events_file:
        events_file.write('{"timestamp":"2026-11-23","event":"half"')
    event_service.replay(run_id, cursor)

    assert event_service.count_projected_events(run_id) == count_before
    assert event_service.snapshot_cursor(run_id) == cursor


def test_heartbeats_do_not_claim_progress(
    tmp_path: Path, event_service: EventService
) -> None:
    run_id = _run(tmp_path)
    cursor = event_service.snapshot_cursor(run_id)

    async def collect() -> AsyncIterator[object]:
        async for event in event_service.subscribe(
            run_id, cursor, max_polls=1, sleep=lambda _: None, heartbeat_after=0
        ):
            yield event

    events = asyncio.run(_list(collect()))
    assert events
    assert all(event.type == "heartbeat" for event in events)
    assert all("progress" not in event.payload for event in events)


def test_long_replay_reads_the_source_once_per_call(
    tmp_path: Path, event_service: EventService, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = _run(tmp_path)
    for index in range(50):
        _add_event(tmp_path, run_id, f"source_found_{index}")
    original = event_service.read_models.list_events
    reads: list[int] = []

    def counted(*args, **kwargs):  # type: ignore[no-untyped-def]
        reads.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(event_service.read_models, "list_events", counted)

    for _ in range(5):
        assert len(event_service.replay(run_id)) == 51

    assert len(reads) == 5
    assert event_service.count_projected_events(run_id) == 51


def test_stop_callback_releases_stream(
    tmp_path: Path, event_service: EventService
) -> None:
    run_id = _run(tmp_path)
    cursor = event_service.snapshot_cursor(run_id)
    stopped = False

    def should_stop() -> bool:
        return stopped

    async def collect() -> int:
        nonlocal stopped
        count = 0
        stream = event_service.subscribe(
            run_id,
            cursor,
            max_polls=100,
            sleep=lambda _: None,
            should_stop=should_stop,
            heartbeat_after=0,
        )
        async for _ in stream:
            count += 1
            stopped = True
        return count

    assert asyncio.run(collect()) >= 1


async def _list(iterator: AsyncIterator[object]) -> list[object]:
    return [item async for item in iterator]
