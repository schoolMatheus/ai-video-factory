"""Durable production jobs, idempotency and cooperative stop control."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from ai_video_factory.sanitization import sanitize_diagnostic
from ai_video_factory.ui_backend.control_store import ControlStore
from ai_video_factory.ui_backend.models import (
    ConflictError,
    DependencyUnavailableError,
    InvalidRequestError,
    JobStatus,
    JobView,
    OperationReceipt,
    ProblemView,
)

DEFAULT_HEARTBEAT_TTL = 15 * 60


def _now() -> str:
    return datetime.now(UTC).isoformat()


class RunControl:
    """Safe points where a worker observes stop requests and reports work."""

    def __init__(self, service: "JobService", job_id: str, token: str) -> None:
        self._service = service
        self._job_id = job_id
        self._token = token

    def stop_requested(self) -> bool:
        return self._service.stop_requested(self._job_id, self._token)

    def report_progress(
        self, unit: str, completed: int, total: int | None = None
    ) -> None:
        self._service.report_progress(
            self._job_id, self._token, unit, completed, total
        )

    def checkpoint(self, stage: str) -> None:
        self._service.checkpoint(self._job_id, self._token, stage)


class JobService:
    def __init__(
        self,
        db_path: Path,
        *,
        heartbeat_ttl: int = DEFAULT_HEARTBEAT_TTL,
        transports: Mapping[str, Any] | None = None,
        services_factory: Any = None,
    ) -> None:
        self.store = ControlStore(db_path)
        self.heartbeat_ttl = heartbeat_ttl
        self.transports = dict(transports or {})
        self.services_factory = services_factory

    # -- submission --------------------------------------------------------

    def submit(
        self, request: dict[str, Any], *, idempotency_key: str
    ) -> OperationReceipt:
        if not idempotency_key or not idempotency_key.strip():
            raise InvalidRequestError("Chave de idempotência é obrigatória.")
        production_id = request.get("production_id")
        if not isinstance(production_id, str) or not production_id:
            raise InvalidRequestError("Identificador da produção é obrigatório.")

        existing = self.store.idempotent_job_id(idempotency_key)
        if existing is not None:
            return self._receipt(existing)

        job_id = uuid.uuid4().hex
        now = _now()
        job = {
            "job_id": job_id,
            "production_id": production_id,
            "status": JobStatus.queued.value,
            "idempotency_key": idempotency_key,
            "payload": json.dumps(request, sort_keys=True, ensure_ascii=False),
            "worker_token": None,
            "pid": None,
            "heartbeat_at": None,
            "result_reference": None,
            "stop_requested": 0,
            "progress": None,
            "problem": None,
            "created_at": now,
            "updated_at": now,
        }
        production = {
            "production_id": production_id,
            "profile_id": request.get("profile_id"),
            "topic": request.get("topic"),
            "job_id": job_id,
            "status": JobStatus.queued.value,
            "created_at": now,
            "updated_at": now,
        }
        if not self.store.submit_transaction(idempotency_key, job, production, now):
            return self._receipt(self.store.idempotent_job_id(idempotency_key) or job_id)
        try:
            self._spawn(job_id)
        except OSError as error:
            self.store.update_job(
                job_id,
                {
                    "status": JobStatus.unknown.value,
                    "problem": sanitize_diagnostic(error),
                    "updated_at": _now(),
                },
            )
        return self._receipt(job_id)

    def _spawn(self, job_id: str) -> None:
        """Start a detached Python worker with fixed arguments and no shell."""
        kwargs: dict[str, Any] = {"shell": False, "close_fds": True}
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            creation_flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
            kwargs["creationflags"] = creation_flags
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "ai_video_factory.ui_backend.worker",
                "--job-id",
                job_id,
            ],
            **kwargs,
        )

    # -- claiming ----------------------------------------------------------

    def claim(self, job_id: str | None = None) -> str | None:
        token = secrets.token_hex(16)
        now = _now()
        if job_id is not None:
            if not self.store.claim_job(job_id, token, now):
                return None
        else:
            job = self.store.next_queued_job(now)
            if job is None:
                return None
            job_id = str(job["job_id"])
            token = str(job["worker_token"])
        self.store.update_job(job_id, {"pid": os.getpid(), "updated_at": now})
        return token

    def claim_next(self) -> dict[str, object] | None:
        return self.store.next_queued_job(_now())

    def worker_token(self, job_id: str) -> str:
        job = self._job(job_id)
        token = job.get("worker_token")
        if not isinstance(token, str) or not token:
            raise ConflictError("Este job não possui um worker ativo.")
        return token

    def _verify_token(self, job_id: str, token: str) -> None:
        if not secrets.compare_digest(self.worker_token(job_id), token):
            raise PermissionError("Token de worker inválido.")

    # -- cooperative control -----------------------------------------------

    def control(self, job_id: str, token: str) -> RunControl:
        self._verify_token(job_id, token)
        return RunControl(self, job_id, token)

    def stop_requested(self, job_id: str, token: str) -> bool:
        self._verify_token(job_id, token)
        job = self._job(job_id)
        return bool(job.get("stop_requested"))

    def request_stop(self, job_id: str) -> None:
        job = self._job(job_id)
        if job.get("status") not in {JobStatus.running.value, JobStatus.stop_requested.value}:
            raise ConflictError("Somente um job em execução pode receber pedido de parada.")
        self.store.update_job(
            job_id,
            {
                "stop_requested": 1,
                "status": JobStatus.stop_requested.value,
                "updated_at": _now(),
            },
        )

    def cancel_queued(self, job_id: str) -> None:
        job = self._job(job_id)
        if job.get("status") != JobStatus.queued.value:
            raise ConflictError("Somente um job na fila pode ser cancelado.")
        self.store.update_job(
            job_id,
            {"status": JobStatus.stopped.value, "updated_at": _now()},
        )

    def confirm_stop(self, job_id: str, token: str) -> None:
        self._verify_token(job_id, token)
        self.store.update_job(
            job_id,
            {
                "status": JobStatus.stopped.value,
                "worker_token": None,
                "updated_at": _now(),
            },
        )
        self.dispatch_next()

    def checkpoint(self, job_id: str, token: str, stage: str) -> None:
        self._verify_token(job_id, token)
        if self.stop_requested(job_id, token):
            self.confirm_stop(job_id, token)
            return
        self.heartbeat(job_id, token)

    def report_progress(
        self,
        job_id: str,
        token: str,
        unit: str,
        completed: int,
        total: int | None,
    ) -> None:
        self._verify_token(job_id, token)
        self.store.update_job(
            job_id,
            {
                "progress": json.dumps(
                    {"unit": unit, "completed": completed, "total": total}
                ),
                "updated_at": _now(),
            },
        )

    def heartbeat(self, job_id: str, token: str) -> None:
        self._verify_token(job_id, token)
        now = _now()
        self.store.update_job(
            job_id, {"heartbeat_at": now, "updated_at": now}
        )

    def dispatch_next(self) -> str | None:
        """Start the next queued job after a terminal one; claim stays atomic."""
        job_id = self.store.next_queued_job_id()
        if job_id is None:
            return None
        try:
            self._spawn(job_id)
        except OSError as error:
            self.store.update_job(
                job_id,
                {
                    "status": JobStatus.unknown.value,
                    "problem": sanitize_diagnostic(error),
                    "updated_at": _now(),
                },
            )
        return job_id

    def complete(self, job_id: str, token: str, result_reference: str) -> None:
        self._verify_token(job_id, token)
        self.store.update_job(
            job_id,
            {
                "status": JobStatus.completed.value,
                "result_reference": result_reference,
                "worker_token": None,
                "updated_at": _now(),
            },
        )
        self.dispatch_next()

    def fail(self, job_id: str, token: str, error: object) -> None:
        self._verify_token(job_id, token)
        self.store.update_job(
            job_id,
            {
                "status": JobStatus.failed.value,
                "problem": sanitize_diagnostic(error),
                "worker_token": None,
                "updated_at": _now(),
            },
        )
        self.dispatch_next()

    # -- reconciliation and queries ----------------------------------------

    def reconcile(self) -> list[str]:
        """Mark abandoned jobs unknown; never relaunch a request automatically."""
        expired: list[str] = []
        for job in self.store.all_jobs():
            status = job.get("status")
            if status not in {JobStatus.running.value, JobStatus.stop_requested.value}:
                continue
            heartbeat = job.get("heartbeat_at")
            stale = True
            if isinstance(heartbeat, str):
                try:
                    moment = datetime.fromisoformat(heartbeat)
                    if moment.tzinfo is None:
                        moment = moment.replace(tzinfo=UTC)
                    stale = (datetime.now(UTC) - moment).total_seconds() > self.heartbeat_ttl
                except ValueError:
                    stale = True
            if stale:
                self.store.update_job(
                    str(job["job_id"]),
                    {
                        "status": JobStatus.unknown.value,
                        "problem": "Worker sem heartbeat confirmado; revisar evidência.",
                        "worker_token": None,
                        "updated_at": _now(),
                    },
                )
                expired.append(str(job["job_id"]))
        return expired

    # -- real domain execution --------------------------------------------

    def _build_services(self, profile_id: str, request_payload: Mapping[str, Any]) -> Any:
        from ai_video_factory.profiles.store import ProfileStore
        from ai_video_factory.workflow.services import build_production_services

        if self.services_factory is not None:
            return self.services_factory(profile_id, request_payload)
        data_root = self.store.db_path.parent.parent
        store = ProfileStore(data_root / "profiles" / "profiles.sqlite3")
        snapshot = store.get_snapshot(
            profile_id, revision=request_payload.get("profile_revision")
        )
        return build_production_services(
            snapshot,
            {"data_root": data_root},
            self.transports,
            store=store,
        )

    def run_default_executor(self, payload: dict[str, Any], control: Any = None) -> Any:
        """Execute an accepted job through the shared production services.

        The worker calls this as ``executor(payload, control)``; the job id is
        carried in the persisted payload/context, not in the executor contract.
        """
        from ai_video_factory.workflow.services import execute_production_job

        request_payload = payload.get("request")
        if not isinstance(request_payload, dict):
            # A submission from the HTTP API carries the request fields at the
            # top level; an action job carries them under "request".
            candidate = {
                key: value for key, value in payload.items()
                if key not in {"action", "action_payload", "through"}
            }
            if not {"production_id", "profile_id", "topic"} <= candidate.keys():
                raise DependencyUnavailableError(
                    "Pedido de produção ausente; esta solicitação não tem execução real."
                )
            request_payload = candidate
        profile_id = request_payload.get("profile_id")
        if not profile_id:
            raise DependencyUnavailableError(
                "Perfil ausente no pedido; não é possível compor serviços reais."
            )
        services = self._build_services(str(profile_id), request_payload)
        return execute_production_job(
            {**payload, "request": request_payload}, control, services
        )

    def request_action(
        self,
        production_id: str,
        action: Any,
        *,
        idempotency_key: str,
    ) -> OperationReceipt:
        """Turn a typed action into a real job, or fail when it is unavailable."""
        from ai_video_factory.ui_backend import domain
        from ai_video_factory.ui_backend.models import NotFoundError

        submission = self.store.staged_production(production_id)
        if submission is None:
            raise NotFoundError("Produção não encontrada.")
        action_name = str(action.action)
        if action_name == "stop_after_stage":
            for job in self.store.all_jobs():
                if (
                    str(job.get("production_id")) == production_id
                    and job.get("status") in {JobStatus.running.value, JobStatus.stop_requested.value}
                ):
                    self.request_stop(str(job["job_id"]))
                    return self._receipt(str(job["job_id"]))
            raise ConflictError("Nenhum job ativo nesta produção para receber parada.")

        domain.execute_action(production_id, action)
        changed: set[str] = set()
        if action_name == "revise_script":
            changed = {"script.scene"}
        elif action_name == "replace_media":
            changed = {"media.shot"}
        elif action_name == "reconcile_editor":
            changed = {"editing.project"}
        key = idempotency_key or (
            f"action:{production_id}:{action_name}:"
            f"{json.dumps(action.payload, sort_keys=True, ensure_ascii=False)}"
        )
        existing = self.store.idempotent_job_id(key)
        if existing is not None:
            return self._receipt(existing)

        job_id = uuid.uuid4().hex
        now = _now()
        payload = {
            "action": action_name,
            "production_id": production_id,
            "request": {
                "production_id": production_id,
                "profile_id": submission.get("profile_id"),
                "topic": submission.get("topic") or "retomada",
                "target_minutes": 25.0,
                "base_dir": str(self.store.db_path.parent.parent / "projects"),
            },
            "through": "review" if action_name != "open_editor" else "editing",
            "action_payload": action.payload,
            "invalidation_inputs": sorted(changed),
        }
        job = {
            "job_id": job_id,
            "production_id": production_id,
            "status": JobStatus.queued.value,
            "idempotency_key": key,
            "payload": json.dumps(payload, sort_keys=True, ensure_ascii=False),
            "worker_token": None,
            "pid": None,
            "heartbeat_at": None,
            "result_reference": None,
            "stop_requested": 0,
            "progress": None,
            "problem": None,
            "created_at": now,
            "updated_at": now,
        }
        submission_update = dict(submission)
        submission_update["job_id"] = job_id
        submission_update["status"] = JobStatus.queued.value
        submission_update["updated_at"] = now
        if not self.store.submit_transaction(key, job, submission_update, now):
            return self._receipt(self.store.idempotent_job_id(key) or job_id)
        try:
            self._spawn(job_id)
        except OSError as error:
            self.store.update_job(
                job_id,
                {
                    "status": JobStatus.unknown.value,
                    "problem": sanitize_diagnostic(error),
                    "updated_at": _now(),
                },
            )
        return self._receipt(job_id)

    def get_job(self, job_id: str) -> JobView:
        job = self._job(job_id)
        return self._view(job)

    def _job(self, job_id: str) -> dict[str, object]:
        from ai_video_factory.ui_backend.models import NotFoundError

        job = self.store.job(job_id)
        if job is None:
            raise NotFoundError("Job não encontrado.")
        return job

    def _receipt(self, job_id: str) -> OperationReceipt:
        return OperationReceipt(
            job_id=job_id,
            production_id=self.get_job(job_id).production_id,
            status=self.get_job(job_id).status,
        )

    @staticmethod
    def _view(job: dict[str, object]) -> JobView:
        problem_text = job.get("problem")
        problem = None
        if isinstance(problem_text, str) and problem_text:
            problem = ProblemView(
                code="job_failed",
                message=problem_text,
                recoverable=True,
            )
        return JobView(
            id=str(job["job_id"]),
            production_id=str(job["production_id"]) if job.get("production_id") else None,
            status=JobStatus(str(job["status"])),
            heartbeat_at=str(job["heartbeat_at"]) if job.get("heartbeat_at") else None,
            result_reference=(
                str(job["result_reference"]) if job.get("result_reference") else None
            ),
            problem=problem,
        )
