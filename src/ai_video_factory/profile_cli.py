"""CLI for channel profiles, scoped memory, feedback and export."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import typer

from ai_video_factory.profiles.models import Observation, ProfileSpec
from ai_video_factory.profiles.store import ProfileStore, ProfileStoreError

profile_app = typer.Typer(no_args_is_help=True)


def data_dir() -> Path:
    return Path(os.environ.get("AI_VIDEO_FACTORY_DATA_DIR", "data"))


def open_store() -> ProfileStore:
    return ProfileStore(data_dir() / "profiles" / "profiles.sqlite3")


@profile_app.command("create")
def create_profile(
    from_file: str = typer.Option(..., "--from-file", help="JSON file with explicit profile settings"),
) -> None:
    """Create a versioned channel profile from explicit operator settings."""
    path = Path(from_file)
    if not path.is_file():
        raise typer.BadParameter(f"profile file not found: {path}")
    try:
        spec = ProfileSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as error:  # noqa: BLE001 - surface a clear config error
        raise typer.BadParameter(f"invalid profile file: {error}") from error
    snapshot = open_store().create_profile(spec)
    typer.echo(json.dumps({
        "profile_id": snapshot.profile_id,
        "revision": snapshot.revision,
        "settings_digest": snapshot.settings_digest,
    }, ensure_ascii=False))


@profile_app.command("list")
def list_profiles() -> None:
    """List all channel profiles and their current revisions."""
    store = open_store()
    typer.echo(json.dumps([
        {"profile_id": item.profile_id, "revision": item.revision,
         "language": item.language, "digest": item.settings_digest}
        for item in store.list_profiles()
    ], ensure_ascii=False, indent=2))


@profile_app.command("show")
def show_profile(profile_id: str = typer.Argument(..., help="Channel profile id")) -> None:
    """Show the current pinned snapshot without secrets."""
    try:
        snapshot = open_store().get_snapshot(profile_id)
    except ProfileStoreError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(snapshot.model_dump_json(indent=2))


@profile_app.command("memory")
def memory(
    profile_id: str = typer.Argument(..., help="Channel profile id"),
    stage: str | None = typer.Option(None, "--stage", help="Filter by stage"),
) -> None:
    """Show stage-scoped observations and active learnings."""
    store = open_store()
    store.get_snapshot(profile_id)  # explicit scope check
    filtered_stage = stage if stage in {"research", "script", "narration", "media", "editing", "review"} else None
    payload: dict[str, Any] = {
        "profile_id": profile_id,
        "observations": [
            item.model_dump() for item in store.list_observations(profile_id, stage=filtered_stage)
        ],
        "learnings": [
            item.model_dump() for item in store.list_learnings(profile_id, stage=filtered_stage)
        ],
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@profile_app.command("feedback")
def feedback(
    profile_id: str = typer.Argument(..., help="Channel profile id"),
    production: str = typer.Option(..., "--production", help="Production id"),
    stage: str = typer.Option(..., "--stage", help="Stage the feedback applies to"),
    note: str = typer.Option(..., "--note", help="Explicit operator evaluation"),
) -> None:
    """Record explicit user feedback, distinct from inferred preferences."""
    if stage not in {"research", "script", "narration", "media", "editing", "review"}:
        raise typer.BadParameter(f"unknown stage: {stage}")
    store = open_store()
    snapshot = store.get_snapshot(profile_id)
    try:
        store.get_production(production, profile_id)
        production_id: str | None = production
    except Exception:  # noqa: BLE001 - feedback can precede a production record
        production_id = None
    observation = Observation(
        observation_id=uuid4().hex,
        profile_id=profile_id,
        production_id=production_id,
        stage=stage,  # type: ignore[arg-type]
        attempt=1,
        type="user_feedback",
        source="user",
        summary=note,
        evidence_refs=[],
        effective_config={"language": snapshot.language},
        event_key=f"{production}:{stage}:user_feedback:{uuid4().hex[:12]}",
    )
    store.record_observation(observation)
    typer.echo(json.dumps({"observation_id": observation.observation_id, "source": "user"}, ensure_ascii=False))


@profile_app.command("export")
def export_profile(
    profile_id: str = typer.Argument(..., help="Channel profile id"),
    output: str = typer.Option(..., "--output", help="Destination JSON file"),
) -> None:
    """Export profile history for inspection; this is not a physical backup."""
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = open_store().export_profile(profile_id)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(str(destination))
