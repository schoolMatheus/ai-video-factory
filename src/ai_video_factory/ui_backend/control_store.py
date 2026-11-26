"""Small SQLite journal for UI control state, event projections and cursors.

This is not a second source of truth for production content: every projected
event references evidence already persisted by the RunStore.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from pathlib import Path

from ai_video_factory.ui_backend.models import EventView


class ControlStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projected_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    production_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    timestamp TEXT,
                    severity TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS projected_events_production
                    ON projected_events(production_id, sequence);
                CREATE TABLE IF NOT EXISTS cursor_generations (
                    production_id TEXT PRIMARY KEY,
                    generation TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    production_id TEXT,
                    status TEXT NOT NULL,
                    idempotency_key TEXT,
                    heartbeat_at TEXT,
                    result_reference TEXT,
                    problem TEXT
                );
                """
            )

    def insert_events(self, events: list[EventView]) -> None:
        if not events:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO projected_events
                    (event_id, production_id, type, timestamp, severity, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        event.id,
                        event.production_id,
                        event.type,
                        event.timestamp,
                        event.severity,
                        json.dumps(event.payload, sort_keys=True, ensure_ascii=False),
                    )
                    for event in events
                ],
            )

    def events_after(self, production_id: str, event_id: str | None = None) -> list[EventView]:
        with self._connect() as connection:
            if event_id is None:
                rows = connection.execute(
                    """
                    SELECT event_id, type, timestamp, severity, payload
                    FROM projected_events WHERE production_id = ? ORDER BY sequence
                    """,
                    (production_id,),
                ).fetchall()
            else:
                sequence = connection.execute(
                    "SELECT sequence FROM projected_events WHERE event_id = ? AND production_id = ?",
                    (event_id, production_id),
                ).fetchone()
                if sequence is None:
                    return []
                rows = connection.execute(
                    """
                    SELECT event_id, type, timestamp, severity, payload
                    FROM projected_events
                    WHERE production_id = ? AND sequence > ? ORDER BY sequence
                    """,
                    (production_id, sequence["sequence"]),
                ).fetchall()
        return [
            EventView(
                id=row["event_id"],
                production_id=production_id,
                type=row["type"],
                timestamp=row["timestamp"],
                severity=row["severity"],  # type: ignore[arg-type]
                payload=json.loads(row["payload"]),
            )
            for row in rows
        ]

    def count_events(self, production_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM projected_events WHERE production_id = ?",
                (production_id,),
            ).fetchone()
        return int(row["total"])

    def last_event_id(self, production_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT event_id FROM projected_events WHERE production_id = ?
                ORDER BY sequence DESC LIMIT 1
                """,
                (production_id,),
            ).fetchone()
        return str(row["event_id"]) if row else None

    def generation(self, production_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT generation FROM cursor_generations WHERE production_id = ?",
                (production_id,),
            ).fetchone()
            if row is not None:
                return str(row["generation"])
            generation = secrets.token_hex(8)
            connection.execute(
                "INSERT INTO cursor_generations (production_id, generation) VALUES (?, ?)",
                (production_id, generation),
            )
        return generation
