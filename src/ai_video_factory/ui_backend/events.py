"""Idempotent event projection with resumable cursors and SSE streaming."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from ai_video_factory.ui_backend.control_store import ControlStore
from ai_video_factory.ui_backend.cursors import decode_cursor, encode_cursor
from ai_video_factory.ui_backend.models import ConflictError, EventView
from ai_video_factory.ui_backend.read_models import ProductionReadModels


class CursorExpired(ConflictError):
    code = "cursor_expired"
    status_code = 409
    recoverable = True
    suggested_action = "Solicite um novo snapshot antes de continuar."


class EventService:
    def __init__(self, read_models: ProductionReadModels, control_db: Path) -> None:
        self.read_models = read_models
        self.store = ControlStore(control_db)

    # -- cursors -----------------------------------------------------------

    def _encode_cursor(self, production_id: str, generation: str, event_id: str) -> str:
        return encode_cursor({"k": "event", "p": production_id, "g": generation, "i": event_id})

    def _decode_cursor(self, production_id: str, cursor: str) -> str:
        try:
            payload = decode_cursor(cursor)
            if payload.get("k") != "event" or payload.get("p") != production_id:
                raise ValueError("cursor belongs to another production or stream")
            event_id = str(payload["i"])
            generation = str(payload["g"])
        except (ValueError, KeyError, TypeError) as error:
            raise CursorExpired("Cursor de eventos inválido ou expirado.") from error
        if generation != self.store.generation(production_id):
            raise CursorExpired("Cursor de eventos expirado.")
        return event_id

    def cursor_for_event(self, production_id: str, event_id: str) -> str:
        return self._encode_cursor(
            production_id, self.store.generation(production_id), event_id
        )

    # -- projections -------------------------------------------------------

    def _reconcile(self, production_id: str) -> None:
        # get_production validates scope and existence before any projection.
        self.read_models.get_production(production_id)
        self.store.insert_events(self.read_models.list_events(production_id))

    def snapshot_cursor(self, production_id: str) -> str:
        self._reconcile(production_id)
        last = self.store.last_event_id(production_id) or ""
        return self.cursor_for_event(production_id, last)

    def replay(self, production_id: str, after_cursor: str | None = None) -> list[EventView]:
        if after_cursor is None:
            event_id = None
        else:
            event_id = self._decode_cursor(production_id, after_cursor)
        self._reconcile(production_id)
        events = self.store.events_after(production_id, event_id)
        if after_cursor is not None and event_id and not self._known(production_id, event_id):
            raise CursorExpired("Cursor aponta para evento que não existe mais.")
        return events

    def _known(self, production_id: str, event_id: str) -> bool:
        return any(event.id == event_id for event in self.store.events_after(production_id))

    def count_projected_events(self, production_id: str) -> int:
        return self.store.count_events(production_id)

    # -- streaming ---------------------------------------------------------

    async def subscribe(
        self,
        production_id: str,
        after_cursor: str | None = None,
        *,
        poll_interval: float = 0.25,
        max_polls: int = 100,
        sleep: Callable[[float], Any] | None = None,
        on_poll: Callable[[], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        heartbeat_after: int | None = None,
    ) -> AsyncIterator[EventView]:
        """Yield projected events; heartbeats never report production progress."""
        pause = sleep or asyncio.sleep
        current = after_cursor or self.snapshot_cursor(production_id)

        async def stopped() -> bool:
            if should_stop is None:
                return False
            result = should_stop()
            if inspect.isawaitable(result):
                return bool(await result)
            return bool(result)

        for poll in range(max_polls):
            if await stopped():
                return
            if poll > 0 and on_poll is not None:
                on_poll()
            events = self.replay(production_id, current)
            for event in events:
                yield event
                current = self.cursor_for_event(production_id, event.id)
            if not events and heartbeat_after is not None and poll >= heartbeat_after:
                yield EventView(
                    id=f"{production_id}:heartbeat:{poll}",
                    production_id=production_id,
                    type="heartbeat",
                    payload={},
                )
            if await stopped():
                return
            waited = pause(poll_interval)
            if inspect.isawaitable(waited):
                await waited
