"""SQLite-backed, versioned channel profiles with strictly scoped memory.

SQLite is the canonical store for profiles and memory. JSON exports are queries
or snapshots, never a second competing configuration.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from ai_video_factory.profiles.models import (
    LearningCandidate,
    LearningEvaluation,
    LearningRevision,
    LearningScope,
    Observation,
    ProfilePatch,
    ProfileSnapshot,
    ProfileSpec,
    StageName,
    TypedPatch,
    apply_profile_patch,
    make_snapshot,
    snapshot_digest,
    utc_now,
)

TECHNICAL_SCOPE = "technical-base"
_SCHEMA_VERSION = 1


class ProfileStoreError(RuntimeError):
    """Base error for profile persistence failures."""


class ScopeViolation(ProfileStoreError):
    """A caller tried to read or write memory outside the requested scope."""


class RevisionConflict(ProfileStoreError):
    """A concurrent update changed the expected profile revision."""


class NotFound(ProfileStoreError):
    """The requested profile, revision or learning does not exist."""


class ProfileStore:
    """One connection per operation; short transactions; no LLM/editor inside them."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    # -- connection helpers ---------------------------------------------

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self._write() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            current = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
            if current >= _SCHEMA_VERSION:
                return
            connection.executescript(
                """
                CREATE TABLE profiles (
                    profile_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    current_revision INTEGER NOT NULL
                );
                CREATE TABLE profile_revisions (
                    profile_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (profile_id, revision),
                    FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
                );
                CREATE TABLE productions (
                    production_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    manifest_ref TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
                );
                CREATE INDEX idx_productions_profile ON productions(profile_id);
                CREATE TABLE observations (
                    observation_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    production_id TEXT,
                    stage TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (profile_id, event_key)
                );
                CREATE INDEX idx_observations_stage ON observations(profile_id, stage);
                CREATE TABLE learning_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX idx_candidates_profile ON learning_candidates(profile_id, stage);
                CREATE TABLE learning_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (candidate_id) REFERENCES learning_candidates(candidate_id)
                );
                CREATE TABLE learning_revisions (
                    learning_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    evaluation_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (candidate_id) REFERENCES learning_candidates(candidate_id)
                );
                CREATE INDEX idx_learning_profile ON learning_revisions(profile_id, state);
                CREATE TABLE memory_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    ref_id TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, utc_now()),
            )

    def close(self) -> None:
        """No-op: connections are per-operation. Kept for symmetry with other stores."""

    # -- profiles --------------------------------------------------------

    def create_profile(self, spec: ProfileSpec) -> ProfileSnapshot:
        snapshot = make_snapshot(spec)
        with self._write() as connection:
            try:
                connection.execute(
                    "INSERT INTO profiles (profile_id, name, created_at, current_revision) "
                    "VALUES (?, ?, ?, 1)",
                    (spec.profile_id, spec.name, snapshot.created_at),
                )
            except sqlite3.IntegrityError as error:
                raise ProfileStoreError(f"profile {spec.profile_id} already exists") from error
            self._insert_snapshot(connection, snapshot, "profile created")
        return snapshot

    def get_snapshot(self, profile_id: str, revision: int | None = None) -> ProfileSnapshot:
        with self._read() as connection:
            row = connection.execute(
                "SELECT current_revision FROM profiles WHERE profile_id = ?", (profile_id,)
            ).fetchone()
            if row is None:
                raise NotFound(f"profile {profile_id} was not found")
            wanted = row["current_revision"] if revision is None else revision
            snapshot_row = connection.execute(
                "SELECT snapshot_json FROM profile_revisions "
                "WHERE profile_id = ? AND revision = ?",
                (profile_id, wanted),
            ).fetchone()
        if snapshot_row is None:
            raise NotFound(f"revision {wanted} of profile {profile_id} was not found")
        return ProfileSnapshot.model_validate(json.loads(snapshot_row["snapshot_json"]))

    def revise_profile(
        self,
        profile_id: str,
        patch: ProfilePatch,
        *,
        expected_revision: int,
        reason: str,
    ) -> ProfileSnapshot:
        with self._write() as connection:
            snapshot = self._current_snapshot(connection, profile_id)
            if snapshot.revision != expected_revision:
                raise RevisionConflict(
                    f"expected profile revision {expected_revision}, found {snapshot.revision}"
                )
            revised = apply_profile_patch(snapshot, patch, reason)
            self._insert_snapshot(connection, revised, reason)
        return revised

    def list_profiles(self) -> list[ProfileSnapshot]:
        with self._read() as connection:
            rows = connection.execute(
                "SELECT profile_id, current_revision FROM profiles ORDER BY profile_id"
            ).fetchall()
        return [self.get_snapshot(row["profile_id"], row["current_revision"]) for row in rows]

    @staticmethod
    def _current_snapshot(connection: sqlite3.Connection, profile_id: str) -> ProfileSnapshot:
        row = connection.execute(
            "SELECT current_revision FROM profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            raise NotFound(f"profile {profile_id} was not found")
        return ProfileStore._snapshot_at(connection, profile_id, int(row["current_revision"]))

    @staticmethod
    def _snapshot_at(
        connection: sqlite3.Connection, profile_id: str, revision: int
    ) -> ProfileSnapshot | None:
        snapshot_row = connection.execute(
            "SELECT snapshot_json FROM profile_revisions WHERE profile_id = ? AND revision = ?",
            (profile_id, revision),
        ).fetchone()
        if snapshot_row is None:
            return None
        return ProfileSnapshot.model_validate(json.loads(snapshot_row["snapshot_json"]))

    @staticmethod
    def _insert_snapshot(
        connection: sqlite3.Connection, snapshot: ProfileSnapshot, reason: str
    ) -> None:
        connection.execute(
            "INSERT INTO profile_revisions "
            "(profile_id, revision, snapshot_json, digest, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot.profile_id,
                snapshot.revision,
                snapshot.model_dump_json(),
                snapshot.settings_digest,
                reason,
                snapshot.created_at,
            ),
        )
        connection.execute(
            "UPDATE profiles SET current_revision = ? WHERE profile_id = ?",
            (snapshot.revision, snapshot.profile_id),
        )
        connection.execute(
            "INSERT INTO memory_events (profile_id, kind, ref_id, detail_json, created_at) "
            "VALUES (?, 'profile_revision', ?, ?, ?)",
            (
                snapshot.profile_id,
                str(snapshot.revision),
                json.dumps({"reason": reason, "digest": snapshot.settings_digest}),
                utc_now(),
            ),
        )

    # -- productions -----------------------------------------------------

    def record_production(self, production_id: str, profile_id: str, manifest_ref: str) -> None:
        with self._write() as connection:
            if connection.execute(
                "SELECT 1 FROM profiles WHERE profile_id = ?", (profile_id,)
            ).fetchone() is None:
                raise NotFound(f"profile {profile_id} was not found")
            existing = connection.execute(
                "SELECT profile_id FROM productions WHERE production_id = ?", (production_id,)
            ).fetchone()
            if existing is not None:
                if existing["profile_id"] != profile_id:
                    raise ScopeViolation("production belongs to another profile")
                return
            connection.execute(
                "INSERT INTO productions (production_id, profile_id, manifest_ref, created_at) "
                "VALUES (?, ?, ?, ?)",
                (production_id, profile_id, manifest_ref, utc_now()),
            )

    def get_production(self, production_id: str, profile_id: str) -> dict[str, Any]:
        with self._read() as connection:
            row = connection.execute(
                "SELECT * FROM productions WHERE production_id = ?", (production_id,)
            ).fetchone()
        if row is None:
            raise NotFound(f"production {production_id} was not found")
        if row["profile_id"] != profile_id:
            raise ScopeViolation("production belongs to another profile")
        return dict(row)

    def list_productions(self, profile_id: str) -> list[dict[str, Any]]:
        with self._read() as connection:
            rows = connection.execute(
                "SELECT * FROM productions WHERE profile_id = ? ORDER BY created_at",
                (profile_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # -- observations -----------------------------------------------------

    def record_observation(self, observation: Observation) -> str:
        if observation.scope == "technical":
            raise ScopeViolation("technical observations require record_technical_observation")
        with self._write() as connection:
            self._validate_observation_scope(connection, observation)
            connection.execute(
                "INSERT INTO observations "
                "(observation_id, profile_id, production_id, stage, event_key, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(profile_id, event_key) DO NOTHING",
                (
                    observation.observation_id,
                    observation.profile_id,
                    observation.production_id,
                    observation.stage,
                    observation.event_key,
                    observation.model_dump_json(),
                    observation.created_at,
                ),
            )
            row = connection.execute(
                "SELECT observation_id FROM observations WHERE profile_id = ? AND event_key = ?",
                (observation.profile_id, observation.event_key),
            ).fetchone()
            assert row is not None
            return str(row["observation_id"])

    def record_technical_observation(self, observation: Observation) -> str:
        """Explicitly shared technical history; never a channel preference."""
        if observation.scope != "technical" or observation.profile_id != TECHNICAL_SCOPE:
            raise ScopeViolation(
                f"technical observations must use the explicit {TECHNICAL_SCOPE!r} scope"
            )
        with self._write() as connection:
            connection.execute(
                "INSERT INTO observations "
                "(observation_id, profile_id, production_id, stage, event_key, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(profile_id, event_key) DO NOTHING",
                (
                    observation.observation_id, observation.profile_id, observation.production_id,
                    observation.stage, observation.event_key, observation.model_dump_json(),
                    observation.created_at,
                ),
            )
            row = connection.execute(
                "SELECT observation_id FROM observations WHERE profile_id = ? AND event_key = ?",
                (TECHNICAL_SCOPE, observation.event_key),
            ).fetchone()
            assert row is not None
            return str(row["observation_id"])

    def list_observations(
        self, profile_id: str, *, stage: StageName | None = None
    ) -> list[Observation]:
        """Profile-scoped reads never return another channel's observations."""
        with self._read() as connection:
            if connection.execute(
                "SELECT 1 FROM profiles WHERE profile_id = ?", (profile_id,)
            ).fetchone() is None:
                raise NotFound(f"profile {profile_id} was not found")
            if stage is None:
                rows = connection.execute(
                    "SELECT payload_json FROM observations WHERE profile_id = ? "
                    "ORDER BY created_at, observation_id",
                    (profile_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload_json FROM observations WHERE profile_id = ? AND stage = ? "
                    "ORDER BY created_at, observation_id",
                    (profile_id, stage),
                ).fetchall()
        return [Observation.model_validate(json.loads(row["payload_json"])) for row in rows]

    def list_technical_observations(
        self, *, stage: StageName | None = None
    ) -> list[Observation]:
        with self._read() as connection:
            if stage is None:
                rows = connection.execute(
                    "SELECT payload_json FROM observations WHERE profile_id = ?",
                    (TECHNICAL_SCOPE,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload_json FROM observations WHERE profile_id = ? AND stage = ?",
                    (TECHNICAL_SCOPE, stage),
                ).fetchall()
        return [Observation.model_validate(json.loads(row["payload_json"])) for row in rows]

    @staticmethod
    def _validate_observation_scope(
        connection: sqlite3.Connection, observation: Observation
    ) -> None:
        if connection.execute(
            "SELECT 1 FROM profiles WHERE profile_id = ?", (observation.profile_id,)
        ).fetchone() is None:
            raise NotFound(f"profile {observation.profile_id} was not found")
        if observation.production_id is not None:
            row = connection.execute(
                "SELECT profile_id FROM productions WHERE production_id = ?",
                (observation.production_id,),
            ).fetchone()
            if row is None:
                raise NotFound(f"production {observation.production_id} was not found")
            if row["profile_id"] != observation.profile_id:
                raise ScopeViolation("production belongs to another profile")

    # -- learning candidates and evaluations -----------------------------

    def save_candidate(self, candidate: LearningCandidate) -> str:
        if candidate.scope == "technical" and candidate.profile_id != TECHNICAL_SCOPE:
            raise ScopeViolation("technical candidates use the shared technical scope")
        with self._write() as connection:
            if candidate.scope != "technical" and connection.execute(
                "SELECT 1 FROM profiles WHERE profile_id = ?", (candidate.profile_id,)
            ).fetchone() is None:
                raise NotFound(f"profile {candidate.profile_id} was not found")
            connection.execute(
                "INSERT INTO learning_candidates "
                "(candidate_id, profile_id, stage, state, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(candidate_id) DO UPDATE SET state = excluded.state, "
                "payload_json = excluded.payload_json",
                (
                    candidate.candidate_id, candidate.profile_id, candidate.stage,
                    candidate.state, candidate.model_dump_json(), candidate.created_at,
                ),
            )
            connection.execute(
                "INSERT INTO memory_events (profile_id, kind, ref_id, detail_json, created_at) "
                "VALUES (?, 'learning_candidate', ?, ?, ?)",
                (
                    candidate.profile_id, candidate.candidate_id,
                    json.dumps({"state": candidate.state, "stage": candidate.stage}),
                    utc_now(),
                ),
            )
        return candidate.candidate_id

    def get_candidate(self, candidate_id: str, *, profile_id: str | None = None) -> LearningCandidate:
        with self._read() as connection:
            row = connection.execute(
                "SELECT payload_json, profile_id FROM learning_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        if row is None:
            raise NotFound(f"candidate {candidate_id} was not found")
        if profile_id is not None and row["profile_id"] != profile_id:
            raise ScopeViolation("candidate belongs to another profile")
        return LearningCandidate.model_validate(json.loads(row["payload_json"]))

    def list_candidates(
        self, profile_id: str, *, stage: StageName | None = None
    ) -> list[LearningCandidate]:
        with self._read() as connection:
            if stage is None:
                rows = connection.execute(
                    "SELECT payload_json FROM learning_candidates WHERE profile_id = ? "
                    "ORDER BY created_at, candidate_id",
                    (profile_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload_json FROM learning_candidates "
                    "WHERE profile_id = ? AND stage = ? ORDER BY created_at, candidate_id",
                    (profile_id, stage),
                ).fetchall()
        return [LearningCandidate.model_validate(json.loads(row["payload_json"])) for row in rows]

    def set_candidate_state(
        self, candidate_id: str, state: str, *, profile_id: str | None = None
    ) -> LearningCandidate:
        with self._write() as connection:
            row = connection.execute(
                "SELECT payload_json, profile_id FROM learning_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                raise NotFound(f"candidate {candidate_id} was not found")
            if profile_id is not None and row["profile_id"] != profile_id:
                raise ScopeViolation("candidate belongs to another profile")
            candidate = LearningCandidate.model_validate(json.loads(row["payload_json"]))
            candidate.state = state  # type: ignore[assignment]
            connection.execute(
                "UPDATE learning_candidates SET state = ?, payload_json = ? WHERE candidate_id = ?",
                (state, candidate.model_dump_json(), candidate_id),
            )
            return candidate

    def save_evaluation(self, evaluation: LearningEvaluation) -> str:
        with self._write() as connection:
            if connection.execute(
                "SELECT 1 FROM learning_candidates WHERE candidate_id = ?",
                (evaluation.candidate_id,),
            ).fetchone() is None:
                raise NotFound(f"candidate {evaluation.candidate_id} was not found")
            connection.execute(
                "INSERT INTO learning_evaluations "
                "(evaluation_id, candidate_id, payload_json, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(evaluation_id) DO UPDATE SET payload_json = excluded.payload_json",
                (
                    evaluation.evaluation_id, evaluation.candidate_id,
                    evaluation.model_dump_json(), evaluation.created_at,
                ),
            )
        return evaluation.evaluation_id

    def get_evaluation(self, evaluation_id: str) -> LearningEvaluation:
        with self._read() as connection:
            row = connection.execute(
                "SELECT payload_json FROM learning_evaluations WHERE evaluation_id = ?",
                (evaluation_id,),
            ).fetchone()
        if row is None:
            raise NotFound(f"evaluation {evaluation_id} was not found")
        return LearningEvaluation.model_validate(json.loads(row["payload_json"]))

    # -- learning activation / suspension --------------------------------

    def activate_learning(
        self,
        candidate_id: str,
        evaluation_id: str,
        *,
        expected_revision: int,
    ) -> ProfileSnapshot:
        with self._write() as connection:
            candidate = self._candidate_in(connection, candidate_id)
            evaluation = self._evaluation_in(connection, evaluation_id)
            if evaluation.candidate_id != candidate_id:
                raise ScopeViolation("evaluation belongs to another candidate")
            if candidate.state not in {"proposed", "evaluating", "suspended"}:
                raise ProfileStoreError(f"candidate {candidate_id} cannot be activated from {candidate.state}")
            if evaluation.result != "pass":
                raise ProfileStoreError("only a passing evaluation can activate a learning")
            snapshot = self._current_snapshot(connection, candidate.profile_id)
            if snapshot.revision != expected_revision:
                raise RevisionConflict(
                    f"expected profile revision {expected_revision}, found {snapshot.revision}"
                )
            if candidate.change.targets_explicit_field(snapshot):
                raise ScopeViolation("a learning cannot override an explicit user preference")
            learning_id = f"{candidate_id}:rev:{uuid4().hex[:12]}"
   
            learning = LearningRevision(
                learning_id=learning_id,
                profile_id=candidate.profile_id,
                candidate_id=candidate_id,
                evaluation_id=evaluation_id,
                action=candidate.change,
                condition=candidate.condition,
                compatible_tool_versions=dict(candidate.compatible_tool_versions),
                evidence_ids=list(candidate.evidence_ids),
            )
            active_ids = [item for item in snapshot.active_learning_ids if item != learning_id]
            # A new rule for the same patch path supersedes the previous one.
            for existing_id in list(active_ids):
                row = connection.execute(
                    "SELECT payload_json FROM learning_revisions WHERE learning_id = ?",
                    (existing_id,),
                ).fetchone()
                if row is None:
                    continue
                old = LearningRevision.model_validate(json.loads(row["payload_json"]))
                if old.action.path == candidate.change.path:
                    old.state = "superseded"
                    connection.execute(
                        "UPDATE learning_revisions SET state = ?, payload_json = ? "
                        "WHERE learning_id = ?",
                        (old.state, old.model_dump_json(), existing_id),
                    )
                    active_ids.remove(existing_id)
            active_ids.append(learning_id)
            connection.execute(
                "UPDATE learning_candidates SET state = 'active', payload_json = ? "
                "WHERE candidate_id = ?",
                (candidate.model_copy(update={"state": "active"}).model_dump_json(), candidate_id),
            )
            connection.execute(
                "INSERT INTO learning_revisions "
                "(learning_id, profile_id, candidate_id, evaluation_id, state, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, 'active', ?, ?)",
                (
                    learning_id, candidate.profile_id, candidate_id, evaluation_id,
                    learning.model_dump_json(), utc_now(),
                ),
            )
            # Rebuild from every active learning so unrelated rules survive.
            revised = self._rebuild_snapshot(
                snapshot, active_ids, connection,
                reason=f"activated learning {learning_id}",
            )
            self._insert_snapshot(connection, revised, f"activated learning {learning_id}")
            connection.execute(
                "INSERT INTO memory_events (profile_id, kind, ref_id, detail_json, created_at) "
                "VALUES (?, 'learning_activated', ?, ?, ?)",
                (
                    candidate.profile_id, learning_id,
                    json.dumps({"candidate_id": candidate_id, "evaluation_id": evaluation_id}),
                    utc_now(),
                ),
            )
        return revised

    def suspend_learning(
        self,
        profile_id: str,
        learning_id: str,
        *,
        expected_revision: int,
        reason: str,
    ) -> ProfileSnapshot:
        with self._write() as connection:
            row = connection.execute(
                "SELECT payload_json, profile_id FROM learning_revisions WHERE learning_id = ?",
                (learning_id,),
            ).fetchone()
            if row is None:
                raise NotFound(f"learning {learning_id} was not found")
            if row["profile_id"] != profile_id:
                raise ScopeViolation("learning belongs to another profile")
            revision = LearningRevision.model_validate(json.loads(row["payload_json"]))
            snapshot = self._current_snapshot(connection, profile_id)
            if snapshot.revision != expected_revision:
                raise RevisionConflict(
                    f"expected profile revision {expected_revision}, found {snapshot.revision}"
                )
            revision.state = "suspended"
            revision.suspension_reason = reason
            connection.execute(
                "UPDATE learning_revisions SET state = 'suspended', payload_json = ? "
                "WHERE learning_id = ?",
                (revision.model_dump_json(), learning_id),
            )
            active_ids = [item for item in snapshot.active_learning_ids if item != learning_id]
            # Rebuild from the revision before activation so the suspended
            # patch is actually removed from effective settings.
            base = self._snapshot_at(connection, profile_id, snapshot.revision - 1) or snapshot
            restored = self._rebuild_snapshot(
                base, active_ids, connection,
                reason=f"suspended learning {learning_id}",
                revision=snapshot.revision + 1,
            )
            self._insert_snapshot(connection, restored, f"suspended learning {learning_id}")
            connection.execute(
                "INSERT INTO memory_events (profile_id, kind, ref_id, detail_json, created_at) "
                "VALUES (?, 'learning_suspended', ?, ?, ?)",
                (profile_id, learning_id, json.dumps({"reason": reason}), utc_now()),
            )
        return restored

    def get_learning(self, profile_id: str, learning_id: str) -> LearningRevision:
        with self._read() as connection:
            row = connection.execute(
                "SELECT payload_json, profile_id FROM learning_revisions WHERE learning_id = ?",
                (learning_id,),
            ).fetchone()
        if row is None:
            raise NotFound(f"learning {learning_id} was not found")
        if row["profile_id"] != profile_id:
            raise ScopeViolation("learning belongs to another profile")
        return LearningRevision.model_validate(json.loads(row["payload_json"]))

    def list_learnings(
        self, profile_id: str, *, stage: StageName | None = None
    ) -> list[LearningRevision]:
        with self._read() as connection:
            if stage is None:
                rows = connection.execute(
                    "SELECT r.payload_json FROM learning_revisions r "
                    "WHERE r.profile_id = ? ORDER BY r.created_at, r.learning_id",
                    (profile_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT r.payload_json FROM learning_revisions r "
                    "JOIN learning_candidates c ON c.candidate_id = r.candidate_id "
                    "WHERE r.profile_id = ? AND c.stage = ? "
                    "ORDER BY r.created_at, r.learning_id",
                    (profile_id, stage),
                ).fetchall()
        return [LearningRevision.model_validate(json.loads(row["payload_json"])) for row in rows]

    @staticmethod
    def _candidate_in(connection: sqlite3.Connection, candidate_id: str) -> LearningCandidate:
        row = connection.execute(
            "SELECT payload_json FROM learning_candidates WHERE candidate_id = ?", (candidate_id,)
        ).fetchone()
        if row is None:
            raise NotFound(f"candidate {candidate_id} was not found")
        return LearningCandidate.model_validate(json.loads(row["payload_json"]))

    @staticmethod
    def _evaluation_in(connection: sqlite3.Connection, evaluation_id: str) -> LearningEvaluation:
        row = connection.execute(
            "SELECT payload_json FROM learning_evaluations WHERE evaluation_id = ?", (evaluation_id,)
        ).fetchone()
        if row is None:
            raise NotFound(f"evaluation {evaluation_id} was not found")
        return LearningEvaluation.model_validate(json.loads(row["payload_json"]))

    def _snapshot_after_patch(
        self, snapshot: ProfileSnapshot, patch: TypedPatch, active_ids: list[str]
    ) -> ProfileSnapshot:
        payload = patch.apply(snapshot)
        return self._rebuild_snapshot(
            snapshot, active_ids, None, payload=payload,
            reason=f"applied learning patch {patch.path}",
        )

    @staticmethod
    def _rebuild_snapshot(
        snapshot: ProfileSnapshot,
        active_ids: list[str],
        connection: sqlite3.Connection | None,
        *,
        payload: dict[str, Any] | None = None,
        reason: str,
        revision: int | None = None,
    ) -> ProfileSnapshot:
        if payload is None:
            payload = {
                "settings": dict(snapshot.settings),
                "policies": {
                    "review_policy": snapshot.review_policy.model_dump(),
                    "learning_policy": snapshot.learning_policy.model_dump(),
                },
                "budget": snapshot.operation_budget.model_dump(),
                "tool_versions": dict(snapshot.tool_versions),
            }
            if connection is not None:
                active_payloads = []
                for learning_id in active_ids:
                    row = connection.execute(
                        "SELECT payload_json FROM learning_revisions WHERE learning_id = ?",
                        (learning_id,),
                    ).fetchone()
                    if row is not None:
                        active_payloads.append(LearningRevision.model_validate(json.loads(row["payload_json"])))
                for learning in sorted(active_payloads, key=lambda item: item.learning_id):
                    applied = learning.action.apply(snapshot)
                    for key in ("settings", "tool_versions"):
                        payload[key].update(applied[key])
                    for policy_name, values in applied["policies"].items():
                        payload["policies"][policy_name].update(values)
                    payload["budget"].update(applied["budget"])
        revision = revision if revision is not None else snapshot.revision + 1
        from ai_video_factory.profiles.models import (
            LearningPolicy,
            OperationBudget,
            ReviewPolicy,
        )

        return ProfileSnapshot(
            profile_id=snapshot.profile_id,
            revision=revision,
            settings=payload["settings"],
            explicit_fields=list(snapshot.explicit_fields),
            active_learning_ids=list(active_ids),
            settings_digest=snapshot_digest(
                snapshot.profile_id, revision, payload["settings"], snapshot.explicit_fields,
                active_ids,
                ReviewPolicy.model_validate(payload["policies"]["review_policy"]),
                LearningPolicy.model_validate(payload["policies"]["learning_policy"]),
                OperationBudget.model_validate(payload["budget"]),
                payload["tool_versions"],
            ),
            language=snapshot.language,
            niche=snapshot.niche,
            tool_versions=payload["tool_versions"],
            review_policy=ReviewPolicy.model_validate(payload["policies"]["review_policy"]),
            learning_policy=LearningPolicy.model_validate(payload["policies"]["learning_policy"]),
            operation_budget=OperationBudget.model_validate(payload["budget"]),
            created_at=utc_now(),
        )

    # -- export / backup -------------------------------------------------

    def export_profile(self, profile_id: str) -> dict[str, Any]:
        with self._read() as connection:
            rows = connection.execute(
                "SELECT snapshot_json, reason FROM profile_revisions "
                "WHERE profile_id = ? ORDER BY revision",
                (profile_id,),
            ).fetchall()
            if not rows:
                raise NotFound(f"profile {profile_id} was not found")
            productions = connection.execute(
                "SELECT production_id, manifest_ref FROM productions WHERE profile_id = ?",
                (profile_id,),
            ).fetchall()
        return {
            "schema_version": 1,
            "profile_id": profile_id,
            "revisions": [
                {"reason": row["reason"], "snapshot": json.loads(row["snapshot_json"])}
                for row in rows
            ],
            "productions": [dict(row) for row in productions],
            "observations": [
                observation.model_dump()
                for observation in self.list_observations(profile_id)
            ],
            "candidates": [
                candidate.model_dump() for candidate in self.list_candidates(profile_id)
            ],
            "learnings": [
                learning.model_dump() for learning in self.list_learnings(profile_id)
            ],
        }

    def backup(self, destination: str | Path) -> Path:
        """Consistent physical backup using SQLite's online backup API."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self.path)
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        return destination


def profile_spec_example(**overrides: Any) -> ProfileSpec:
    """Small helper used by tests and the example profile CLI import."""
    payload: dict[str, Any] = {
        "profile_id": "example",
        "name": "Example channel",
        "language": "pt-BR",
        "settings": {"research.preferred_sources": [], "editing.music": "none"},
    }
    payload.update(overrides)
    return ProfileSpec.model_validate(payload)
