"""Read-only projections over RunStore manifests and append-only event files.

Nothing in this module writes to disk. Unknown legacy stages and incomplete
JSONL lines are surfaced as unknown data, never as completed work.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_video_factory.models import ArtifactIntegrity, RunManifest, StageStatus
from ai_video_factory.run_store import RunStore
from ai_video_factory.workflow.models import STAGE_ORDER, ArtifactRef
from ai_video_factory.ui_backend.models import (
    ActionAvailability,
    ArtifactView,
    EventView,
    InvalidRequestError,
    NotFoundError,
    ProblemView,
    ProductionFilters,
    ProductionMode,
    ProductionPage,
    ProductionView,
    StageName,
    StageStatus as UiStageStatus,
    StageView,
)

_RUN_ID = re.compile(r"^[0-9a-f]{32}$")

# Legacy stage names that have a truthful counterpart in the six-stage model.
# Every other legacy stage (render, daily, ...) stays as an observed stage and
# must not light up any of the six stages as completed.
_LEGACY_STAGE_MAP: dict[str, StageName] = {
    "research": StageName.research,
    "script": StageName.script,
    "narration": StageName.narration,
    "media": StageName.media,
    "editing": StageName.editing,
    "review": StageName.review,
}

_STATUS_MAP: dict[StageStatus, UiStageStatus] = {
    StageStatus.pending: UiStageStatus.pending,
    StageStatus.running: UiStageStatus.running,
    StageStatus.completed: UiStageStatus.completed,
    StageStatus.failed: UiStageStatus.failed,
    StageStatus.superseded: UiStageStatus.superseded,
}


@dataclass(frozen=True)
class _ObservedRun:
    manifest: RunManifest
    manifest_path: Path


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _sort_key(run: _ObservedRun) -> tuple[datetime, str]:
    parsed = _parse_timestamp(run.manifest.updated_at)
    if parsed is None:
        parsed = datetime.min.replace(tzinfo=UTC)
    return parsed, run.manifest.run_id


def _page_key(run: _ObservedRun) -> tuple[str, str]:
    """(updated_at, identity) matches the reverse sort used by the page."""
    identity = str(run.manifest.inputs.get("production_id") or run.manifest.run_id)
    return run.manifest.updated_at, identity


def _encode_cursor(key: tuple[str, str]) -> str:
    from ai_video_factory.ui_backend.cursors import encode_cursor

    return encode_cursor({"k": "page", "u": key[0], "p": key[1]})


def _decode_cursor(cursor: str) -> tuple[str, str]:
    from ai_video_factory.ui_backend.cursors import decode_cursor

    try:
        payload = decode_cursor(cursor)
        if payload.get("k") != "page" or not isinstance(payload.get("u"), str):
            raise ValueError("wrong cursor kind")
        return str(payload["u"]), str(payload.get("p", ""))
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidRequestError("Cursor de paginação inválido.") from error


class ProductionReadModels:
    """Consistent snapshot of what the persisted RunStore actually contains."""

    def __init__(self, state_root: Path, artifact_root: Path) -> None:
        self.state_root = Path(state_root)
        self.artifact_root = Path(artifact_root).resolve()

    # -- discovery ---------------------------------------------------------

    def _all_runs(self) -> list[_ObservedRun]:
        runs: list[_ObservedRun] = []
        if not self.state_root.is_dir():
            return runs
        for stage_directory in self.state_root.iterdir():
            if not stage_directory.is_dir():
                continue
            for run_directory in stage_directory.iterdir():
                if (
                    not run_directory.is_dir()
                    or _RUN_ID.fullmatch(run_directory.name) is None
                ):
                    continue
                manifest_path = run_directory / "manifest.json"
                if not manifest_path.is_file():
                    continue
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest = RunManifest.from_dict(data)
                except (OSError, ValueError, KeyError, TypeError):
                    # A damaged manifest is not a completed production.
                    continue
                runs.append(_ObservedRun(manifest, manifest_path))
        return runs

    def _find_run(self, production_id: str) -> _ObservedRun:
        if _RUN_ID.fullmatch(production_id) is None:
            raise NotFoundError("Produção não encontrada.")
        for run in self._all_runs():
            if run.manifest.run_id == production_id:
                return run
        raise NotFoundError("Produção não encontrada.")

    # -- projections -------------------------------------------------------

    def list_productions(
        self,
        filters: ProductionFilters | None = None,
        cursor: str | None = None,
        *,
        page_size: int = 50,
    ) -> ProductionPage:
        if page_size < 1 or page_size > 200:
            raise InvalidRequestError("Tamanho de página inválido.")
        filters = filters or ProductionFilters()
        after = _decode_cursor(cursor) if cursor else None
        runs = sorted(self._all_runs(), key=_sort_key, reverse=True)
        if after is not None:
            runs = [run for run in runs if _page_key(run) < after]
        if filters.profile_id is not None:
            runs = [
                run
                for run in runs
                if str(run.manifest.inputs.get("profile_id")) == filters.profile_id
            ]
        if filters.state is not None:
            runs = [run for run in runs if self._overall_status(run) is filters.state]
        if filters.search:
            needle = filters.search.casefold()
            runs = [run for run in runs if needle in self._title(run.manifest).casefold()]
        if filters.since:
            since = _parse_timestamp(filters.since)
            if since is not None:
                runs = [
                    run
                    for run in runs
                    if (parsed := _parse_timestamp(run.manifest.updated_at)) is None
                    or parsed >= since
                ]

        page = runs[:page_size]
        items = [self._project(run) for run in page]
        next_cursor = _encode_cursor(_page_key(page[-1])) if len(runs) > page_size else None
        return ProductionPage(items=items, next_cursor=next_cursor)

    def get_production(self, production_id: str) -> ProductionView:
        return self._project(self._find_run(production_id))

    def get_stage(self, production_id: str, stage: StageName) -> StageView:
        production = self.get_production(production_id)
        for stage_view in production.stages:
            if stage_view.name is stage:
                return stage_view
        raise NotFoundError("Estágio não encontrado nesta produção.")

    def list_events(
        self, production_id: str, after_cursor: str | None = None
    ) -> list[EventView]:
        run = self._find_run(production_id)
        event_path = run.manifest_path.parent / "events.jsonl"
        if not event_path.is_file():
            return []
        try:
            raw = event_path.read_bytes()
        except OSError:
            return []
        events: list[EventView] = []
        offset = 0
        for line in raw.splitlines(keepends=True):
            if not line.endswith(b"\n"):
                # Incomplete final line: keep earlier events, do not repair the file.
                break
            start = offset
            offset += len(line)
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            if not isinstance(record, dict):
                continue
            event_id = f"{production_id}:{start}"
            if after_cursor and event_id <= after_cursor:
                continue
            fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
            severity = "info"
            event_type = str(record.get("event", "unknown"))
            if "fail" in event_type or "invalid" in event_type:
                severity = "error"
            elif "supersed" in event_type or "warn" in event_type:
                severity = "warning"
            events.append(
                EventView(
                    id=event_id,
                    production_id=production_id,
                    type=event_type,
                    timestamp=str(record.get("timestamp")) if record.get("timestamp") else None,
                    severity=severity,  # type: ignore[arg-type]
                    attempt=fields.get("attempt") if isinstance(fields.get("attempt"), int) else None,
                    payload=fields,
                )
            )
        return events

    def list_artifacts(self, production_id: str) -> list[ArtifactView]:
        run = self._find_run(production_id)
        return self._artifacts(run.manifest)

    def find_artifact(
        self, artifact_id: str
    ) -> tuple[str, str, ArtifactIntegrity] | None:
        """Return (production_id, key, integrity) for a stable artifact id."""
        for run in self._all_runs():
            for key, integrity in run.manifest.artifact_integrity.items():
                if self._artifact_id(run.manifest.run_id, key) == artifact_id:
                    return run.manifest.run_id, key, integrity
        return None

    # -- helpers -----------------------------------------------------------

    def _title(self, manifest: RunManifest) -> str:
        for key in ("topic", "title", "topic_id"):
            value = manifest.inputs.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return f"Execução {manifest.run_id[:8]}"

    def _overall_status(self, run: _ObservedRun) -> UiStageStatus:
        return _STATUS_MAP[run.manifest.status]

    def _artifacts(self, manifest: RunManifest) -> list[ArtifactView]:
        integrity: dict[str, ArtifactIntegrity] = manifest.artifact_integrity
        mapped_stage = _LEGACY_STAGE_MAP.get(manifest.stage)
        artifacts: list[ArtifactView] = []
        for key, record in integrity.items():
            name = key if key in {"video", "audio", "brief", "master"} else Path(record.path).name
            artifacts.append(
                ArtifactView(
                    id=self._artifact_id(manifest.run_id, key),
                    name=name,
                    media_type=_media_type(record.path),
                    size_bytes=record.size_bytes,
                    sha256=record.sha256,
                    stage=mapped_stage,
                    integrity="verified",
                )
            )
        return sorted(artifacts, key=lambda artifact: artifact.id)

    @staticmethod
    def _artifact_id(production_id: str, key: str) -> str:
        digest = hashlib.sha256(f"{production_id}:{key}".encode("utf-8")).hexdigest()
        return digest[:24]

    def _project(self, run: _ObservedRun) -> ProductionView:
        manifest = run.manifest
        mapped_stage = _LEGACY_STAGE_MAP.get(manifest.stage)
        status = self._overall_status(run)
        problems: list[ProblemView] = []
        if manifest.error:
            problems.append(
                ProblemView(
                    code="stage_failed",
                    message=manifest.error,
                    recoverable=True,
                    suggested_action="Inspecione o estágio e solicite retomada.",
                )
            )

        artifacts = self._artifacts(manifest)
        stages: list[StageView] = []
        for stage in StageName:
            is_observed = stage is mapped_stage
            stages.append(
                StageView(
                    name=stage,
                    status=status if is_observed else UiStageStatus.unknown,
                    observed=is_observed,
                    started_at=manifest.started_at if is_observed else None,
                    updated_at=manifest.updated_at if is_observed else None,
                    last_activity_at=manifest.last_heartbeat_at if is_observed else None,
                    artifacts=[artifact for artifact in artifacts if artifact.stage is stage],
                    problem=problems[0] if is_observed and problems else None,
                )
            )

        capabilities = [
            ActionAvailability(
                action="resume",
                enabled=False,
                reason="Retomada do fluxo novo ainda não disponível neste perfil.",
            ),
            ActionAvailability(
                action="open_editor",
                enabled=False,
                reason="Integração com editor não configurada.",
            ),
        ]
        return ProductionView(
            id=manifest.run_id,
            mode=ProductionMode.legacy,
            title=self._title(manifest),
            topic=str(manifest.inputs.get("topic")) if "topic" in manifest.inputs else None,
            state=status,
            observed_stages=[manifest.stage],
            stages=stages,
            artifacts=artifacts,
            capabilities=capabilities,
            problems=problems,
            started_at=manifest.started_at or manifest.created_at,
            updated_at=manifest.updated_at,
            cursor=f"{manifest.run_id}:0",
        )


def _media_type(path: str) -> str:
    suffix = Path(path).suffix.casefold()
    return {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".json": "application/json",
        ".md": "text/markdown",
    }.get(suffix, "application/octet-stream")


def list_productions(
    models: ProductionReadModels,
    filters: ProductionFilters | None = None,
    cursor: str | None = None,
) -> ProductionPage:
    """Module-level convenience wrapper used by the API layer."""
    return models.list_productions(filters, cursor)


def get_production(models: ProductionReadModels, production_id: str) -> ProductionView:
    return models.get_production(production_id)


def get_stage(
    models: ProductionReadModels, production_id: str, stage: StageName
) -> StageView:
    return models.get_stage(production_id, stage)


class StagedProductionReadModels:
    """Read-only view of one real coordinator production.

    There is no run_id-as-production shortcut: the resource id is the
    ProductionRequest id, and each of the six stages is projected from its
    persisted StageResult and RunStore integrity record.
    """

    def __init__(self, project_root: Path) -> None:
        self.root = Path(project_root)
        self.state_root = self.root / "state"
        self.artifact_root = (self.root / "artifacts").resolve()

    def _json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def get_production(self, production_id: str) -> ProductionView:
        request_path = self.root / "production.json"
        snapshot_path = self.root / "profile_snapshot.json"
        if not request_path.is_file() or not snapshot_path.is_file():
            raise NotFoundError("Produção não encontrada.")
        request = self._json(request_path)
        if request.get("production_id") != production_id:
            raise NotFoundError("Produção não encontrada.")
        snapshot = self._json(snapshot_path)

        state_dir = self.root / "state"
        verified: dict[str, str] = {}
        run_ids = self._json(state_dir / "run_ids.json") if (state_dir / "run_ids.json").is_file() else {}
        store = RunStore(state_dir, artifact_root=self.root / "artifacts")
        for stage in STAGE_ORDER:
            run_id = run_ids.get(stage)
            if not run_id:
                continue
            try:
                manifest = store._load_run(str(run_id))
            except Exception:  # noqa: BLE001 - a damaged run is not verified
                continue
            for key, record in manifest.artifact_integrity.items():
                verified[f"{stage}.{key}"] = record.path

        stages: list[StageView] = []
        artifacts: list[ArtifactView] = []
        statuses: list[UiStageStatus] = []
        for stage in STAGE_ORDER:
            result_path = state_dir / f"{stage}_result.json"
            if result_path.is_file():
                result = self._json(result_path)
                status = UiStageStatus(result.get("status", "completed"))
                refs = result.get("artifacts", {})
            else:
                status = UiStageStatus.pending
                refs = {}
            stage_artifacts: list[ArtifactView] = []
            for key, ref in refs.items():
                name = Path(str(ref.get("path", key))).name
                identity = f"{stage}.{key}"
                stage_artifacts.append(ArtifactView(
                    id=identity, name=name,
                    media_type=str(ref.get("media_type", "application/octet-stream")),
                    size_bytes=int(ref.get("size_bytes", 0) or 0),
                    sha256=str(ref.get("sha256")) if ref.get("sha256") else None,
                    integrity="verified" if identity in verified else "not_recorded",
                    stage=StageName(stage),
                ))
            artifacts.extend(stage_artifacts)
            statuses.append(status)
            stages.append(StageView(
                name=StageName(stage), status=status,
                activity=f"{stage}: {status.value}", observed=result_path.is_file(),
                artifacts=stage_artifacts,
            ))

        if UiStageStatus.failed in statuses:
            overall = UiStageStatus.failed
        elif all(status == UiStageStatus.completed for status in statuses):
            overall = UiStageStatus.completed
        elif UiStageStatus.running in statuses:
            overall = UiStageStatus.running
        else:
            overall = UiStageStatus.pending

        profile_id = str(snapshot.get("profile_id") or request.get("profile_id") or "")
        revision = int(snapshot.get("revision") or 0)
        return ProductionView(
            id=production_id,
            mode=ProductionMode.staged,
            title=str(request.get("topic") or production_id),
            topic=str(request.get("topic")) if request.get("topic") else None,
            profile_id=profile_id or None,
            profile_revision=revision or None,
            snapshot_id=f"{profile_id}:r{revision}" if profile_id else None,
            state=overall,
            stages=stages,
            artifacts=artifacts,
            started_at=request.get("created_at"),
            updated_at=str(snapshot.get("revision")) if revision else None,
        )

    def find_artifact(
        self, artifact_id: str
    ) -> tuple[str, str, ArtifactIntegrity] | None:
        state_dir = self.root / "state"
        run_ids = self._json(state_dir / "run_ids.json") if (state_dir / "run_ids.json").is_file() else {}
        store = RunStore(state_dir, artifact_root=self.artifact_root)
        for stage in STAGE_ORDER:
            run_id = run_ids.get(stage)
            if not run_id:
                continue
            try:
                manifest = store._load_run(str(run_id))
            except Exception:  # noqa: BLE001 - damaged run is not an artifact
                continue
            for key, record in manifest.artifact_integrity.items():
                if ProductionReadModels._artifact_id(manifest.run_id, key) == artifact_id:
                    return manifest.run_id, key, record
        return None

    def list_artifacts(self, production_id: str) -> list[ArtifactView]:
        state_dir = self.root / "state"
        run_ids = self._json(state_dir / "run_ids.json") if (state_dir / "run_ids.json").is_file() else {}
        store = RunStore(state_dir, artifact_root=self.artifact_root)
        artifacts: list[ArtifactView] = []
        for stage in STAGE_ORDER:
            run_id = run_ids.get(stage)
            if not run_id:
                continue
            try:
                manifest = store._load_run(str(run_id))
            except Exception:  # noqa: BLE001
                continue
            for key, record in manifest.artifact_integrity.items():
                artifacts.append(ArtifactView(
                    id=ProductionReadModels._artifact_id(manifest.run_id, key),
                    name=Path(record.path).name,
                    media_type=_media_type(record.path),
                    size_bytes=record.size_bytes,
                    sha256=record.sha256,
                    stage=StageName(stage),
                    integrity="verified",
                ))
        return sorted(artifacts, key=lambda item: item.id)

    def get_bundle(self, production_id: str, stage: str) -> dict[str, Any]:
        """Return the persisted delivery bundle for one stage, when it exists."""
        self.get_production(production_id)
        state_dir = self.root / "state"
        result_path = state_dir / f"{stage}_result.json"
        if not result_path.is_file():
            raise NotFoundError("Entrega de estágio ainda não disponível.")
        result = self._json(result_path)
        ref = result.get("artifacts", {}).get("bundle")
        if ref is None:
            raise NotFoundError("Bundle do estágio não registrado.")
        path = ArtifactRef.model_validate(ref).resolve(self.root)
        return self._json(path)

    def list_events(self, production_id: str) -> list[EventView]:
        """Project RunStore events as typed, replayable UI events."""
        self.get_production(production_id)
        state_dir = self.root / "state"
        run_ids = self._json(state_dir / "run_ids.json") if (state_dir / "run_ids.json").is_file() else {}
        events: list[EventView] = []
        for stage in STAGE_ORDER:
            run_id = run_ids.get(stage)
            if not run_id:
                continue
            path = state_dir / stage / str(run_id) / "events.jsonl"
            if not path.is_file():
                continue
            for index, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    # An incomplete trailing line after a crash is ignored;
                    # the file itself is never rewritten.
                    continue
                name = str(record.get("event", "run_event"))
                events.append(EventView(
                    id=f"{run_id}:{index}",
                    production_id=production_id,
                    type=f"stage.{name.removeprefix('run_')}",
                    timestamp=str(record.get("timestamp")) if record.get("timestamp") else None,
                    severity="error" if "fail" in name else "info",
                    payload=dict(record.get("fields") or {}),
                ))
        return sorted(events, key=lambda item: (item.timestamp or "", item.id))

