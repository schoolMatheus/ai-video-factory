"""Read-only projections over RunStore manifests and append-only event files.

Nothing in this module writes to disk. Unknown legacy stages and incomplete
JSONL lines are surfaced as unknown data, never as completed work.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_video_factory.models import ArtifactIntegrity, RunManifest, StageStatus
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


def _encode_cursor(run_id: str) -> str:
    payload = json.dumps({"id": run_id}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> str:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        run_id = payload["id"]
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidRequestError("Cursor de paginação inválido.") from error
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise InvalidRequestError("Cursor de paginação inválido.")
    return run_id


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
            runs = [run for run in runs if _sort_key(run) < _sort_key(self._find_run(after))]
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
        next_cursor = _encode_cursor(page[-1].manifest.run_id) if len(runs) > page_size else None
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
