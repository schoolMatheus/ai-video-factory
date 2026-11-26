"""Thin HTTP routes: validation, session scope and delegation to services."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ai_video_factory.ui_backend import domain
from ai_video_factory.ui_backend.models import (
    ActionAvailability,
    ActionRequest,
    ArtifactView,
    CapabilitiesView,
    EventPage,
    FeedbackRequest,
    JobView,
    MemoryPage,
    MemoryView,
    NotFoundError,
    OperationReceipt,
    ProblemView,
    PreflightView,
    ProfileCreateRequest,
    ProfilePatchRequest,
    ProfileView,
    ProductionCreateRequest,
    ProductionFilters,
    ProductionPage,
    ProductionView,
    StageName,
    StageStatus,
    StageView,
    SuspendRequest,
)
from ai_video_factory.ui_backend.artifacts import ArtifactService
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


@router.post("/productions/preflight", response_model=PreflightView)
def preflight(payload: ProductionCreateRequest) -> PreflightView:
    """Report real capabilities; never start an external service or render."""
    capabilities = domain.get_capabilities()
    problems: list[ProblemView] = []
    actions: list[ActionAvailability] = []
    if not capabilities.staged_flow:
        problems.append(
            ProblemView(
                code="staged_flow_unavailable",
                message="O fluxo de seis etapas ainda não está configurado neste ambiente.",
                recoverable=True,
                suggested_action="Acompanhe as execuções legadas ou configure o domínio.",
            )
        )
        through = None
    else:
        through = StageName.review if capabilities.editor else StageName.media
        if not capabilities.editor:
            problems.append(
                ProblemView(
                    code="editor_unavailable",
                    message="Edição externa não configurada; é possível chegar até mídia.",
                    recoverable=True,
                )
            )
    if not payload.topic.strip():
        problems.append(
            ProblemView(
                code="topic_missing",
                message="Informe um tema para a produção.",
                recoverable=True,
            )
        )
    for action in ("resume", "stop_after_stage", "revise_script", "replace_media", "open_editor"):
        enabled = (
            action in {"resume", "stop_after_stage"}
            and capabilities.staged_flow
            and capabilities.stop_control
        ) or (action == "open_editor" and capabilities.editor)
        reason = None if enabled else "Dependência de domínio ainda não disponível."
        actions.append(
            ActionAvailability(action=action, enabled=enabled, reason=reason)
        )
    return PreflightView(
        can_start=capabilities.staged_flow and bool(payload.topic.strip()),
        through=through,
        actions=actions,
        problems=problems,
    )


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


def artifacts_of(request: Request) -> ArtifactService:
    service = request.app.state.services.artifacts
    if service is None:
        from ai_video_factory.ui_backend.models import DependencyUnavailableError

        raise DependencyUnavailableError("Serviço de artefatos não disponível.")
    return service


@router.get("/productions/{production_id}/artifacts", response_model=list[ArtifactView])
def artifacts(production_id: str, request: Request) -> list[ArtifactView]:
    _, _, models = services_of(request)
    return models.list_artifacts(production_id)


@router.get("/artifacts/{artifact_id}/content")
def artifact_content(
    artifact_id: str, request: Request, range: str | None = Header(default=None)
) -> StreamingResponse:
    service = artifacts_of(request)
    resolved = service.resolve(artifact_id)
    span = service.parse_range(range, resolved.size_bytes)

    def stream():
        with resolved.path.open("rb") as source:
            if span is not None:
                source.seek(span[0])
                remaining = span[1] - span[0] + 1
            else:
                remaining = None
            while remaining is None or remaining > 0:
                block = source.read(65_536 if remaining is None else min(65_536, remaining))
                if not block:
                    break
                if remaining is not None:
                    remaining -= len(block)
                yield block

    headers = {"Accept-Ranges": "bytes"}
    status_code = 200
    if span is not None:
        status_code = 206
        headers["Content-Range"] = f"bytes {span[0]}-{span[1]}/{resolved.size_bytes}"
    return StreamingResponse(
        stream(),
        status_code=status_code,
        media_type=resolved.media_type,
        headers=headers,
    )


@router.post("/productions/{production_id}/uploads", status_code=201)
async def upload_artifact(
    production_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> dict[str, object]:
    service = artifacts_of(request)
    _, _, models = services_of(request)
    models.get_production(production_id)
    content = await file.read(64 * 1024 * 1024 + 1)
    upload = service.store_upload(
        production_id,
        filename=file.filename or "arquivo",
        content=content,
        media_type=file.content_type or "application/octet-stream",
    )
    return {
        "id": upload.id,
        "name": upload.name,
        "sha256": upload.sha256,
        "size_bytes": upload.size_bytes,
        "confirmed_in_manifest": False,
    }


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
    result = domain.execute_action(production_id, action_request)
    return OperationReceipt(
        job_id=result.production_id,
        production_id=result.production_id,
        status="queued",
        accepted=True,
    )


@router.get("/profiles/{profile_id}/productions", response_model=ProductionPage)
def profile_productions(profile_id: str, request: Request) -> ProductionPage:
    _, _, models = services_of(request)
    filters = ProductionFilters(profile_id=profile_id)
    return models.list_productions(filters)


def profiles_of(request: Request):  # type: ignore[no-untyped-def]
    from ai_video_factory.ui_backend.models import DependencyUnavailableError

    adapter = request.app.state.services.profiles
    if adapter is None:
        raise DependencyUnavailableError("Perfis ainda não disponíveis neste ambiente.")
    return adapter


class ProfilePage(BaseModel):
    items: list[ProfileView]


@router.get("/profiles", response_model=ProfilePage)
def list_profiles(request: Request) -> ProfilePage:
    return ProfilePage(items=profiles_of(request).list_profiles())


@router.post("/profiles", status_code=201, response_model=ProfileView)
def create_profile(payload: ProfileCreateRequest, request: Request) -> ProfileView:
    return profiles_of(request).create_profile(payload)


@router.get("/profiles/{profile_id}", response_model=ProfileView)
def profile(profile_id: str, request: Request) -> ProfileView:
    return profiles_of(request).get_profile(profile_id)


@router.patch("/profiles/{profile_id}", response_model=ProfileView)
def revise_profile(
    profile_id: str, payload: ProfilePatchRequest, request: Request
) -> ProfileView:
    return profiles_of(request).revise_profile(profile_id, payload)


@router.get("/profiles/{profile_id}/memory", response_model=MemoryPage)
def memory(profile_id: str, request: Request) -> MemoryPage:
    return MemoryPage(items=profiles_of(request).list_memory(profile_id))


@router.post("/profiles/{profile_id}/feedback", status_code=201, response_model=MemoryView)
def feedback(
    profile_id: str, payload: FeedbackRequest, request: Request
) -> MemoryView:
    return profiles_of(request).add_feedback(profile_id, payload)


@router.post(
    "/profiles/{profile_id}/memory/{learning_id}/suspend",
    response_model=MemoryView,
)
def suspend_learning(
    profile_id: str, learning_id: str, payload: SuspendRequest, request: Request
) -> MemoryView:
    return profiles_of(request).suspend_learning(
        profile_id, learning_id, payload.expected_revision, payload.reason
    )


@router.get("/tools")
def tools() -> dict[str, object]:
    return {"items": domain.get_tools()}


@router.post("/tools/{tool_id}/check")
def check_tool(tool_id: str) -> dict[str, object]:
    return domain.check_tool(tool_id)


@router.get("/jobs/{job_id}", response_model=JobView)
def job(job_id: str, request: Request) -> JobView:
    return jobs_of(request).get_job(job_id)
