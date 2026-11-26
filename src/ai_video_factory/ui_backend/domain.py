"""Adapter that reports which domain capabilities are actually available."""

from __future__ import annotations

import importlib.util
import inspect
import shutil
import subprocess
from pathlib import Path

from ai_video_factory.sanitization import sanitize_diagnostic
from ai_video_factory.ui_backend.models import (
    ActionName,
    ActionRequest,
    CapabilitiesView,
    DependencyUnavailableError,
    InvalidRequestError,
    ProductionResult,
    StageName,
)

_API_VERSION = "v1"


def _available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def get_capabilities() -> CapabilitiesView:
    profiles = _available("ai_video_factory.profiles.store")
    staged = _available("ai_video_factory.workflow.orchestrator")
    editor = _available("ai_video_factory.integrations.filmcraft")

    stop_control = False
    if staged:
        try:
            from ai_video_factory.workflow.orchestrator import run_production

            stop_control = "control" in inspect.signature(run_production).parameters
        except (ImportError, ValueError):
            stop_control = False

    return CapabilitiesView(
        api_version=_API_VERSION,
        legacy_read=True,
        profiles=profiles,
        staged_flow=staged,
        editor=editor,
        stop_control=stop_control,
        upload=False,
    )


_ALLOWED_PAYLOAD: dict[ActionName, frozenset[str]] = {
    ActionName.resume: frozenset({"through"}),
    ActionName.stop_after_stage: frozenset({"stage"}),
    ActionName.revise_script: frozenset({"scene_id", "new_text", "reason"}),
    ActionName.replace_media: frozenset({"shot_id", "artifact_id", "reason"}),
    ActionName.reconcile_editor: frozenset(),
    ActionName.open_editor: frozenset(),
}
_REQUIRED_PAYLOAD: dict[ActionName, frozenset[str]] = {
    ActionName.revise_script: frozenset({"scene_id", "new_text", "reason"}),
    ActionName.replace_media: frozenset({"shot_id", "artifact_id"}),
}


def load_filmcraft_config() -> object | None:
    """Lazy adapter so tests and CLI use remain independent of the editor."""
    try:
        from ai_video_factory.integrations.filmcraft import load_filmcraft_config as load

        return load()
    except (ImportError, ValueError, OSError):
        return None


def invalidation_plan(changed_inputs: set[str]) -> list[StageName]:
    """Delegate to the domain when available; otherwise use explicit mapping."""
    if _available("ai_video_factory.workflow.orchestrator"):
        try:
            from ai_video_factory.workflow.orchestrator import plan_invalidation

            return [StageName(stage) for stage in plan_invalidation(changed_inputs)]
        except (ImportError, ValueError):
            pass
    if any(name.startswith("editing") for name in changed_inputs):
        return [StageName.editing, StageName.review]
    if any(name.startswith("script") for name in changed_inputs):
        return [
            StageName.script,
            StageName.narration,
            StageName.media,
            StageName.editing,
            StageName.review,
        ]
    return []


def execute_action(
    production_id: str,
    action: ActionRequest,
    control: object | None = None,
) -> ProductionResult:
    """Validate a typed action and report exactly what was requested or observed."""
    allowed = _ALLOWED_PAYLOAD[action.action]
    unknown = set(action.payload) - allowed
    if unknown:
        raise InvalidRequestError("Esta ação não aceita parâmeros arbitrários.")
    missing = _REQUIRED_PAYLOAD.get(action.action, frozenset()) - set(action.payload)
    if missing:
        raise InvalidRequestError("Campos obrigatórios da ação não informados.")

    capabilities = get_capabilities()
    if action.action == ActionName.open_editor:
        if not capabilities.editor or load_filmcraft_config() is None:
            raise DependencyUnavailableError("Editor não configurado neste ambiente.")
        return ProductionResult(
            production_id=production_id,
            status="requested",
            note="A abertura do projeto é feita pelo worker, não pelo navegador.",
        )
    if not capabilities.staged_flow:
        raise DependencyUnavailableError(
            "Fluxo de seis etapas ainda não disponível neste ambiente."
        )

    if action.action == ActionName.stop_after_stage:
        stage = action.payload.get("stage")
        try:
            selected = StageName(str(stage)) if stage else None
        except ValueError as error:
            raise InvalidRequestError("Estágio informado é inválido.") from error
        stop_now = bool(
            control is not None
            and getattr(control, "stop_requested", lambda: False)()
        )
        return ProductionResult(
            production_id=production_id,
            status="stop_requested" if stop_now else "requested",
            stage=selected,
            note="Parada só é confirmada em ponto seguro pelo worker.",
        )

    changed: set[str] = set()
    if action.action == ActionName.revise_script:
        changed = {"script.scene"}
    elif action.action == ActionName.replace_media:
        changed = {"media.shot"}
    elif action.action == ActionName.reconcile_editor:
        changed = {"editing.project"}
    return ProductionResult(
        production_id=production_id,
        status="requested",
        note="Retrabalho solicitado; a execução acontece no worker.",
        invalidated_stages=invalidation_plan(changed) if changed else [],
    )


_TOOL_COMMANDS = {
    "ffmpeg": ["ffmpeg", "-version"],
    "ffprobe": ["ffprobe", "-version"],
    "node": ["node", "--version"],
    "filmcraft": [],
    "llm": [],
}


def get_tools() -> list[dict[str, object]]:
    """Report observed installation/configuration without running any probe."""
    tools: list[dict[str, object]] = []
    for tool_id, command in _TOOL_COMMANDS.items():
        if command:
            state = "installed" if shutil.which(command[0]) else "not_installed"
        else:
            config_path = Path.cwd() / "config" / (
                "filmcraft.toml" if tool_id == "filmcraft" else "inference.toml"
            )
            state = "configured" if config_path.is_file() else "not_configured"
        tools.append(
            {
                "id": tool_id,
                "state": state,
                "note": "Teste de conexão disponível sob ação explícita.",
            }
        )
    return tools


def check_tool(tool_id: str) -> dict[str, object]:
    """Perform one explicit, bounded probe; never echo secrets."""
    if tool_id not in _TOOL_COMMANDS:
        raise DependencyUnavailableError("Ferramenta desconhecida.")
    command = _TOOL_COMMANDS[tool_id]
    if not command:
        return {"id": tool_id, "state": "not_verified", "observed": "sem comando de teste"}
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "id": tool_id,
            "state": "unavailable",
            "observed": sanitize_diagnostic(error)[:200],
        }
    first_line = (result.stdout or result.stderr).splitlines()[:1]
    return {
        "id": tool_id,
        "state": "validated" if result.returncode == 0 else "unavailable",
        "observed": sanitize_diagnostic(first_line[0] if first_line else "sem saída")[:200],
    }


def require_capability(capability: str) -> None:
    """Guard for actions whose domain module is still absent."""
    capabilities = get_capabilities()
    if not getattr(capabilities, capability, False):
        raise DependencyUnavailableError(
            "Esta operação ainda não está disponível neste ambiente."
        )
