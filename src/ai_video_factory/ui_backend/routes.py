"""Thin HTTP routes: validation, session scope and delegation to services."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from ai_video_factory.ui_backend import domain
from ai_video_factory.ui_backend.models import (
    ActionRequest,
    CapabilitiesView,
    EventPage,
    JobView,
    NotFoundError,
    OperationReceipt,
    ProductionCreateRequest,
    ProductionFilters,
    ProductionPage,
    ProductionView,
    StageName,
    StageStatus,
    StageView,
)
from ai_video_factory.ui_backend.events import EventService
from ai_video_factory.ui_backend.read_models import ProductionReadModels
from ai_video_factory.sanitization import sanitize_diagnostic
from ai_video_factory.ui_backend.session import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    BootstrapService,
    Session,
    SessionService,
)

router = APIRouter(prefix="/api/v1")


def session_of(request: Request) -> Session:
    session = getattr(request.state, "session", None)
    if session is None:
        from ai_video_factory.ui_backend.models import UiError

        class _Unauthenticated(UiError):
            code = "unauthenticated"
            status_code = 401
            recoverable = True
            suggested_action = "Abra novamente o painel pelo iniciador local."

        raise _Unauthenticated("Sessão local não encontrada.")
    return session


def services_of(request: Request) -> tuple[BootstrapService, SessionService, ProductionReadModels]:
    services = request.app.state.services
    return services.bootstrap, services.sessions, services.read_models


@router.post("/session/bootstrap", status_code=204)
def bootstrap(request: Request, response: Response, payload: dict[str, str]) -> None:
    from fastapi import HTTPException

    bootstrap_service, sessions, _ = services_of(request)
    token = payload.get("token", "")
    if not bootstrap_service.redeem(token):
        raise HTTPException(status_code=401, detail="bootstrap_failed")
    cookie, csrf = sessions.issue()
    response.set_cookie(
        SESSION_COOKIE,
        cookie,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,
        samesite="strict",
        secure=False,
        path="/",
    )


@router.get("/session")
def current_session(session: Session = Depends(session_of)) -> dict[str, object]:
    return {"authenticated": True, "csrf": session.csrf}


@router.get("/capabilities", response_model=CapabilitiesView)
def capabilities() -> CapabilitiesView:
    return domain.get_capabilities()


@router.post("/productions", status_code=202, response_model=OperationReceipt)
def create_production(
    payload: ProductionCreateRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> OperationReceipt:
    from ai_video_factory.ui_backend.models import InvalidRequestError

    if not idempotency_key:
        raise InvalidRequestError("Cabeçalho Idempotency-Key é obrigatório.")
    job_service = jobs_of(request)
    production_id = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:32]
    document = payload.model_dump()
    document["production_id"] = production_id
    return job_service.submit(document, idempotency_key=idempotency_key)


@router.get("/productions", response_model=ProductionPage)
def productions(
    request: Request,
    profile_id: str | None = None,
    state: StageStatus | None = None,
    search: str | None = None,
    since: str | None = None,
    cursor: str | None = None,
    page_size: int = Query(default=50, ge=1, le=200),
) -> ProductionPage:
    _, _, models = services_of(request)
    filters = ProductionFilters(profile_id=profile_id, state=state, search=search, since=since)
    return models.list_productions(filters, cursor, page_size=page_size)


@router.get("/productions/{production_id}", response_model=ProductionView)
def production(production_id: str, request: Request) -> ProductionView:
    _, _, models = services_of(request)
    return models.get_production(production_id)


@router.get("/productions/{production_id}/stages/{stage}", response_model=StageView)
def stage(production_id: str, stage: StageName, request: Request) -> StageView:
    _, _, models = services_of(request)
    return models.get_stage(production_id, stage)


def jobs_of(request: Request):  # type: ignore[no-untyped-def]
    from ai_video_factory.ui_backend.jobs import JobService
    from ai_video_factory.ui_backend.models import DependencyUnavailableError

    job_service = request.app.state.services.jobs
    if job_service is None:
        raise DependencyUnavailableError("Fila de jobs não disponível.")
    return job_service


def events_of(request: Request) -> EventService:
    events = request.app.state.services.events
    if events is None:
        from ai_video_factory.ui_backend.models import DependencyUnavailableError

        raise DependencyUnavailableError("Journal de eventos não disponível.")
    return events


@router.get("/productions/{production_id}/events", response_model=EventPage)
def events(
    production_id: str,
    request: Request,
    after_cursor: str | None = None,
) -> EventPage:
    items = events_of(request).replay(production_id, after_cursor)
    return EventPage(items=items, next_cursor=items[-1].id if items else None)


@router.get("/productions/{production_id}/stream")
async def stream(production_id: str, request: Request) -> StreamingResponse:
    event_service = events_of(request)
    event_service.read_models.get_production(production_id)
    last_event_id = request.headers.get("last-event-id")
    cursor = (
        event_service.cursor_for_event(production_id, last_event_id)
        if last_event_id
        else event_service.snapshot_cursor(production_id)
    )

    settings = request.app.state.settings

    async def frames():
        stream = event_service.subscribe(
            production_id,
            cursor,
            poll_interval=settings.sse_poll_interval,
            max_polls=settings.sse_max_polls,
            heartbeat_after=settings.sse_heartbeat_after,
            should_stop=request.is_disconnected,
        )
        async for event in stream:
            data = sanitize_diagnostic(
                json.dumps(event.payload, sort_keys=True, ensure_ascii=False)
            )
            yield f"id: {event.id}\nevent: {event.type}\ndata: {data}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/productions/{production_id}/actions", response_model=OperationReceipt)
def action(
    production_id: str,
    action_request: ActionRequest,
    request: Request,
) -> OperationReceipt:
    _, _, models = services_of(request)
    models.get_production(production_id)
    capability = "editor" if action_request.action == "open_editor" else "staged_flow"
    domain.require_capability(capability)
    raise NotFoundError("Ação ainda não executável neste ambiente.")


@router.get("/profiles/{profile_id}/productions", response_model=ProductionPage)
def profile_productions(profile_id: str, request: Request) -> ProductionPage:
    _, _, models = services_of(request)
    filters = ProductionFilters(profile_id=profile_id)
    return models.list_productions(filters)


@router.get("/profiles/{profile_id}")
def profile(profile_id: str) -> None:
    raise NotFoundError("Perfis ainda não estão disponíveis neste ambiente.")


@router.get("/profiles/{profile_id}/memory")
def memory(profile_id: str) -> None:
    raise NotFoundError("Memória de perfil ainda não está disponível neste ambiente.")


@router.get("/jobs/{job_id}", response_model=JobView)
def job(job_id: str, request: Request) -> JobView:
    return jobs_of(request).get_job(job_id)
