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
                    payload TEXT NOT NULL DEFAULT '{}',
                    worker_token TEXT,
                    pid INTEGER,
                    heartbeat_at TEXT,
                    result_reference TEXT,
                    stop_requested INTEGER NOT NULL DEFAULT 0,
                    progress TEXT,
                    problem TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
            }
            for name, declaration in (
                ("payload", "TEXT NOT NULL DEFAULT '{}'"),
                ("worker_token", "TEXT"),
                ("pid", "INTEGER"),
                ("stop_requested", "INTEGER NOT NULL DEFAULT 0"),
                ("progress", "TEXT"),
                ("created_at", "TEXT"),
                ("updated_at", "TEXT"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE jobs ADD COLUMN {name} {declaration}")

    # -- jobs --------------------------------------------------------------

    def insert_idempotency(self, key: str, job_id: str, created_at: str) -> bool:
        """Return True when the key was new; False when it already existed."""
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO idempotency_keys (key, job_id, created_at) VALUES (?, ?, ?)",
                (key, job_id, created_at),
            )
            return cursor.rowcount == 1

    def idempotent_job_id(self, key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT job_id FROM idempotency_keys WHERE key = ?", (key,)
            ).fetchone()
        return str(row["job_id"]) if row else None

    def insert_job(self, job: dict[str, object]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, production_id, status, idempotency_key, payload,
                    worker_token, pid, heartbeat_at, result_reference,
                    stop_requested, progress, problem, created_at, updated_at
                ) VALUES (
                    :job_id, :production_id, :status, :idempotency_key, :payload,
                    :worker_token, :pid, :heartbeat_at, :result_reference,
                    :stop_requested, :progress, :problem, :created_at, :updated_at
                )
                """,
                job,
            )

    def job(self, job_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_job(self, job_id: str, fields: dict[str, object]) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE jobs SET {assignments} WHERE job_id = ?",
                (*fields.values(), job_id),
            )

    def claim_job(self, job_id: str, token: str, now: str) -> bool:
        """Atomically claim one job; returns False when another worker won."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT status FROM jobs WHERE job_id = ?
                    AND status IN ('queued', 'running') AND worker_token IS NULL
                    """,
                    (job_id,),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    return False
                connection.execute(
                    """
                    UPDATE jobs SET status = 'running', worker_token = ?, heartbeat_at = ?,
                    updated_at = ? WHERE job_id = ?
                    """,
                    (token, now, now, job_id),
                )
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise

    def next_queued_job(self, now: str) -> dict[str, object] | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                active = connection.execute(
                    "SELECT COUNT(*) AS total FROM jobs WHERE status IN ('running', 'stop_requested')"
                ).fetchone()
                if int(active["total"]) > 0:
                    connection.rollback()
                    return None
                row = connection.execute(
                    """
                    SELECT * FROM jobs WHERE status = 'queued' AND worker_token IS NULL
                    ORDER BY created_at, job_id LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    connection.rollback()
                    return None
                token = secrets.token_hex(16)
                connection.execute(
                    """
                    UPDATE jobs SET status = 'running', worker_token = ?, heartbeat_at = ?,
                    updated_at = ? WHERE job_id = ?
                    """,
                    (token, now, now, row["job_id"]),
                )
                connection.commit()
                updated = dict(row)
                updated["worker_token"] = token
                return updated
            except Exception:
                connection.rollback()
                raise

    def all_jobs(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM jobs").fetchall()
        return [dict(row) for row in rows]

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
