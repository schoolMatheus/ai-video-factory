"""FastAPI composition root for the local dashboard."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_video_factory.ui_backend.events import EventService
from ai_video_factory.ui_backend.models import (
    InvalidRequestError,
    ProblemView,
    UiError,
)
from ai_video_factory.ui_backend.read_models import ProductionReadModels
from ai_video_factory.ui_backend.routes import router
from ai_video_factory.ui_backend.session import (
    CSRF_HEADER,
    SESSION_COOKIE,
    BootstrapService,
    SessionService,
)

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class UiSettings:
    project_root: Path
    data_root: Path | None = None
    control_db: Path | None = None
    static_dir: Path | None = None
    bind_host: str = "127.0.0.1"
    port: int = 8765
    sse_poll_interval: float = 1.0
    sse_max_polls: int = 3600
    sse_heartbeat_after: int = 4


@dataclass(frozen=True)
class UiServices:
    read_models: ProductionReadModels
    sessions: SessionService
    bootstrap: BootstrapService
    events: EventService | None = None


def _problem_response(status_code: int, problem: ProblemView) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json"),
    )


def _host_name(host: str | None) -> str:
    if not host:
        return ""
    return host.partition(":")[0].strip("[]").casefold()


def create_app(
    settings: UiSettings | None = None,
    services: UiServices | None = None,
    *,
    bootstrap: BootstrapService | None = None,
) -> FastAPI:
    settings = settings or UiSettings(project_root=Path.cwd())
    data_root = Path(settings.data_root or Path(settings.project_root) / "data")
    state_root = Path(settings.project_root) / "state"
    artifact_root = Path(settings.project_root) / "runs"

    services = services or UiServices(
        read_models=ProductionReadModels(state_root, artifact_root),
        sessions=SessionService.with_persisted_secret(data_root / "ui" / "session.key"),
        bootstrap=bootstrap or BootstrapService(data_root / "ui" / "bootstrap.token"),
    )
    if bootstrap is not None:
        services = replace(services, bootstrap=bootstrap)
    if services.events is None:
        control_db = Path(
            settings.control_db or data_root / "ui" / "control.sqlite3"
        )
        services = replace(
            services, events=EventService(services.read_models, control_db)
        )

    app = FastAPI(
        title="AI Video Factory UI",
        version="v1",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.settings = settings
    app.state.services = services

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        host = _host_name(request.headers.get("host"))
        if host not in LOCAL_HOSTS:
            return _problem_response(
                400,
                ProblemView(
                    code="invalid_origin",
                    message="Acesso permitido somente pelo endereço local.",
                    recoverable=False,
                ),
            )
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.scheme != "http" or parsed.netloc != request.headers.get("host"):
                return _problem_response(
                    400,
                    ProblemView(
                        code="invalid_origin",
                        message="Origem da requisição não corresponde ao painel local.",
                        recoverable=False,
                    ),
                )

        path = request.url.path
        is_api = path.startswith("/api/v1")
        is_bootstrap = path == "/api/v1/session/bootstrap"
        if is_api and not is_bootstrap:
            session = services.sessions.verify_cookie(request.cookies.get(SESSION_COOKIE))
            if session is None:
                return _problem_response(
                    401,
                    ProblemView(
                        code="unauthenticated",
                        message="Sessão local não encontrada.",
                        recoverable=True,
                        suggested_action="Abra novamente o painel pelo iniciador local.",
                    ),
                )
            request.state.session = session
            if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not SessionService.verify_csrf(
                session, request.headers.get(CSRF_HEADER)
            ):
                return _problem_response(
                    403,
                    ProblemView(
                        code="csrf_failed",
                        message="Ação bloqueada: token de proteção ausente ou inválido.",
                        recoverable=True,
                        suggested_action="Recarregue a página e tente novamente.",
                    ),
                )
        return await call_next(request)

    @app.exception_handler(UiError)
    async def handle_ui_error(request: Request, exc: UiError) -> JSONResponse:  # noqa: ARG001
        return _problem_response(exc.status_code, exc.as_problem())

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:  # noqa: ARG001
        location = ".".join(str(part) for part in (exc.errors()[0]["loc"] if exc.errors() else []))
        problem = InvalidRequestError(
            "A solicitação contém campos inválidos.", detail=location or None
        )
        return _problem_response(problem.status_code, problem.as_problem())

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:  # noqa: ARG001
        if exc.status_code == 401:
            problem = UiError(
                "Sessão local inválida.",
            )
            problem.code = "unauthenticated"
            problem.status_code = 401
            problem.recoverable = True
        elif exc.status_code == 404:
            problem = InvalidRequestError("Recurso não encontrado.")
            problem.code = "not_found"
            problem.status_code = 404
        else:
            problem = UiError("Não foi possível concluir a solicitação.")
            problem.status_code = exc.status_code
        return _problem_response(problem.status_code, problem.as_problem())

    app.include_router(router)
    return app
