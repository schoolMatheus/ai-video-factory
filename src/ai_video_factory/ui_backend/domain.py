"""Adapter that reports which domain capabilities are actually available."""

from __future__ import annotations

import importlib.util
import inspect

from ai_video_factory.ui_backend.models import (
    CapabilitiesView,
    DependencyUnavailableError,
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


def require_capability(capability: str) -> None:
    """Guard for actions whose domain module is still absent."""
    capabilities = get_capabilities()
    if not getattr(capabilities, capability, False):
        raise DependencyUnavailableError(
            "Esta operação ainda não está disponível neste ambiente."
        )
