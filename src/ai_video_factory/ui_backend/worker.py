"""Structured worker entry point for durable production jobs."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_video_factory.ui_backend.jobs import JobService, RunControl


def execute_job(
    service: JobService,
    job_id: str,
    executor: Callable[[dict[str, Any], RunControl], Any],
    *,
    worker_token: str | None = None,
) -> Any:
    token = worker_token or service.worker_token(job_id)
    service._verify_token(job_id, token)  # noqa: SLF001 - same package boundary
    control = service.control(job_id, token)
    job = service.store.job(job_id)
    if job is None or not isinstance(job.get("payload"), str):
        raise ValueError("job payload is missing")
    payload = json.loads(job["payload"])
    try:
        result = executor(payload, control)
    except Exception as error:
        service.fail(job_id, token, error)
        raise
    status = service.get_job(job_id).status
    if status in {"stopped", "stop_requested"}:
        if status == "stop_requested":
            service.confirm_stop(job_id, token)
    else:
        try:
            stopped = bool(control.stop_requested())
        except PermissionError:
            # A checkpoint already confirmed the stop and cleared the token.
            stopped = True
        if stopped:
            service.confirm_stop(job_id, token)
        else:
            service.complete(job_id, token, str(result))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executa um job da interface local.")
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args(argv)

    control_db = Path(
        os.environ.get(
            "AVF_CONTROL_DB",
            str(Path.cwd() / "data" / "ui" / "control.sqlite3"),
        )
    )
    service = JobService(control_db)
    if service.claim(args.job_id) is None:
        return 0
    execute_job(service, args.job_id, service.run_default_executor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
