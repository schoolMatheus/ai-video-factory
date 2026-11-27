"""CLI for the six-stage production workflow."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import typer

from ai_video_factory.integrations.filmcraft import FilmCraftMcpClient, load_filmcraft_config
from ai_video_factory.preflight import check_filmcraft_bridge
from ai_video_factory.profile_cli import data_dir, open_store
from ai_video_factory.profiles.models import OperationBudget, StageName
from ai_video_factory.stages.editing import EditingStage
from ai_video_factory.stages.media import MediaStage
from ai_video_factory.stages.narration import NarrationStage
from ai_video_factory.stages.research import ResearchStage
from ai_video_factory.stages.review import ReviewStage
from ai_video_factory.stages.script import ScriptStage
from ai_video_factory.workflow.models import STAGE_ORDER, ProductionRequest
from ai_video_factory.workflow.orchestrator import run_production

workflow_app = typer.Typer(no_args_is_help=True)

RunnerBuilder = Callable[[Any, Any, Path], dict[StageName, Any]]


class _UnconfiguredFilmCraft:
    """Fails with a clear operator error instead of an attribute error."""

    def connect(self) -> Any:
        raise RuntimeError(
            "config/filmcraft.toml is missing: copy config/filmcraft.example.toml "
            "and set the native MCP command before running the editing stage"
        )

    def inspect(self) -> Any:
        raise RuntimeError("FilmCraft is not configured")

    def execute(self, command_id: str, params: dict[str, Any]) -> Any:
        raise RuntimeError("FilmCraft is not configured")

    def close(self) -> None:
        pass


def _stock_runners(data_root: Path) -> MediaStage:
    from ai_video_factory.stock_providers import StockFootageProvider

    provider = StockFootageProvider(cache_dir=data_root / "cache" / "stock")

    def search(query: str, limit: int) -> list[dict[str, Any]]:
        asset = provider.fetch_clip(query, min_duration_sec=0.0)
        if asset is None:
            return []
        return [{
            "id": asset.source_url or asset.path,
            "title": asset.title,
            "license": asset.license,
            "attribution": asset.artist,
            "url": asset.source_url,
            "path": asset.path,
        }]

    return MediaStage(search=search, fetch=lambda raw, directory: Path(str(raw["path"])),
                      data_dir=data_root)


def build_runners(store: Any, snapshot: Any, data_root: Path) -> dict[StageName, Any]:
    """Default runner map; tests replace this boundary with deterministic runners.

    The CLI and the UI worker use the same composition root in
    ``workflow.services``; only the transports differ.
    """
    from ai_video_factory.workflow.services import build_production_services

    config = load_filmcraft_config(Path("config") / "filmcraft.toml")
    filmcraft = FilmCraftMcpClient(config) if config is not None else _UnconfiguredFilmCraft()
    services = build_production_services(
        snapshot,
        {"data_root": data_root},
        {"editor": filmcraft},
        store=store,
    )
    return dict(services.runners)


def _request(
    profile: str,
    topic: str,
    angle: str,
    target_minutes: float,
    production: str | None,
    base_dir: str | None,
    budget_calls: int | None,
    seed_source_urls: list[str] | None = None,
) -> ProductionRequest:
    payload: dict[str, Any] = {
        "production_id": production or f"production-{os.getpid()}",
        "profile_id": profile,
        "topic": topic,
        "angle": angle,
        "target_minutes": target_minutes,
        "seed_source_urls": list(seed_source_urls or []),
        "base_dir": base_dir or str(data_dir() / "projects"),
    }
    if budget_calls is not None:
        payload["budget"] = OperationBudget(max_external_calls=budget_calls).model_dump()
    return ProductionRequest.model_validate(payload)


@workflow_app.command("run")
def run(
    profile: str = typer.Option(..., "--profile", help="Explicit channel profile id (never inferred)"),
    topic: str = typer.Option(..., "--topic", help="Topic supplied by the operator"),
    angle: str = typer.Option("", "--angle", help="Editorial angle"),
    target_minutes: float = typer.Option(25.0, "--target-minutes", min=0.01),
    through: str = typer.Option("review", "--through", help="Last stage to execute"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan without external services or learning"),
    base_dir: str | None = typer.Option(None, "--base-dir", help="Production root override"),
    budget_calls: int | None = typer.Option(None, "--budget-calls", min=0),
    production: str | None = typer.Option(None, "--production", help="Explicit production id"),
    seed_source_urls: list[str] = typer.Option(
        [], "--seed-source-url", help="Initial source URL (repeatable; optional)",
    ),
) -> None:
    """Start a staged production for one explicit profile."""
    if through not in STAGE_ORDER:
        raise typer.BadParameter(f"unknown stage: {through}")
    store = open_store()
    snapshot = store.get_snapshot(profile)
    request = _request(profile, topic, angle, target_minutes, production, base_dir,
                       budget_calls, seed_source_urls)
    runners = build_runners(store, snapshot, data_dir())
    result = run_production(
        request, store=store, runners=runners, through=through, dry_run=dry_run,
    )
    typer.echo(result.model_dump_json(indent=2))
    if result.status == "failed":
        raise typer.Exit(code=2)


@workflow_app.command("resume")
def resume(
    profile: str = typer.Option(..., "--profile", help="Explicit channel profile id"),
    production: str = typer.Option(..., "--production", help="Production id to resume"),
    through: str = typer.Option("review", "--through"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    base_dir: str | None = typer.Option(None, "--base-dir"),
    budget_calls: int | None = typer.Option(None, "--budget-calls", min=0),
) -> None:
    """Resume an existing production, reusing valid predecessor deliveries."""
    if through not in STAGE_ORDER:
        raise typer.BadParameter(f"unknown stage: {through}")
    store = open_store()
    snapshot = store.get_snapshot(profile)
    store.get_production(production, profile)
    request = _request(profile, "retomada", "", 25.0, production, base_dir, budget_calls)
    # Topic/angle/budget are restored from the persisted request on resume.
    persisted = json.loads((request.project_dir / "production.json").read_text(encoding="utf-8"))
    request = ProductionRequest.model_validate(persisted)
    runners = build_runners(store, snapshot, data_dir())
    result = run_production(request, store=store, runners=runners, through=through, dry_run=dry_run)
    typer.echo(result.model_dump_json(indent=2))
    if result.status == "failed":
        raise typer.Exit(code=2)


@workflow_app.command("filmcraft-doctor")
def filmcraft_doctor() -> None:
    """Read-only diagnosis of the optional FilmCraft MCP bridge."""
    check = check_filmcraft_bridge(Path("config") / "filmcraft.toml")
    typer.echo(json.dumps({"name": check.name, "status": check.status, "detail": check.detail}, ensure_ascii=False))
