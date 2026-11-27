"""One production service composition, shared by the CLI and the UI worker.

The factory resolves runners, learning and configuration from a pinned profile
snapshot. External boundaries (HTTP, LLM, TTS, editor) arrive as transports;
no secret is kept in the returned services object.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ai_video_factory.integrations.filmcraft import FilmCraftMcpClient, load_filmcraft_config
from ai_video_factory.profiles.models import ProfileSnapshot, StageName
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.stages.editing import EditingStage
from ai_video_factory.stages.media import MediaStage
from ai_video_factory.stages.narration import NarrationStage
from ai_video_factory.stages.research import ResearchStage
from ai_video_factory.stages.review import ReviewStage
from ai_video_factory.stages.script import ScriptStage
from ai_video_factory.workflow.models import ProductionRequest, ProductionResult
from ai_video_factory.workflow.orchestrator import run_production


class UnconfiguredEditor:
    """A clear operator error instead of an attribute error on an empty setup."""

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


@dataclass(frozen=True)
class ProductionServices:
    """Everything needed to execute one job, with no serializable secrets."""

    snapshot: ProfileSnapshot
    runners: Mapping[StageName, Any]
    store: ProfileStore
    paths: Mapping[str, Any]
    learning_reviewer: Callable | None = None
    evaluator: object | None = None

    def describe(self) -> dict[str, Any]:
        """Operator-safe description: ids and paths only, never credentials."""
        return {
            "profile_id": self.snapshot.profile_id,
            "profile_revision": self.snapshot.revision,
            "stages": [stage.value for stage in self.runners],
        }


def _stock_media(data_root: Path) -> MediaStage:
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
            "path": str(asset.path),
        }]

    return MediaStage(
        search=search,
        fetch=lambda raw, directory: Path(str(raw["path"])) if raw.get("path") else None,
        data_dir=data_root,
    )


def build_production_services(
    snapshot: ProfileSnapshot,
    paths: Mapping[str, Any],
    transports: Mapping[str, Any] | None = None,
    *,
    store: ProfileStore | None = None,
) -> ProductionServices:
    """Compose the six runners from a pinned snapshot and controlled transports."""
    transports = transports or {}
    data_root = Path(paths.get("data_root", Path.cwd() / "data"))
    profile_db = Path(paths.get("profile_db", data_root / "profiles" / "profiles.sqlite3"))
    resolved_store = store or ProfileStore(profile_db)

    editor = transports.get("editor")
    if editor is None:
        config = load_filmcraft_config(paths.get("filmcraft_config") or Path("config") / "filmcraft.toml")
        editor = FilmCraftMcpClient(config) if config is not None else UnconfiguredEditor()

    narration = transports.get("narration")
    if narration is None:
        tts_factory = transports.get("tts_factory")
        narration = NarrationStage(tts_factory=tts_factory) if tts_factory else NarrationStage()

    runners: dict[StageName, Any] = {
        "research": transports.get("research") or ResearchStage(),
        "script": transports.get("script") or ScriptStage(),
        "narration": narration,
        "media": transports.get("media") or _stock_media(data_root),
        "editing": transports.get("editing") or EditingStage(editor),
        "review": transports.get("review") or ReviewStage(),
    }
    return ProductionServices(
        snapshot=snapshot,
        runners=runners,
        store=resolved_store,
        paths={"data_root": data_root, "profile_db": profile_db},
        learning_reviewer=transports.get("learning_reviewer"),
        evaluator=transports.get("candidate_evaluator"),
    )


def execute_production_job(
    payload: Mapping[str, Any],
    control: object | None,
    services: ProductionServices,
) -> ProductionResult:
    """Execute one accepted job through the real coordinator."""
    document = payload.get("request", payload)
    request = ProductionRequest.model_validate(dict(document))
    through = str(payload.get("through", "review"))
    return run_production(
        request,
        store=services.store,
        runners=services.runners,
        through=through,  # type: ignore[arg-type]
        resume=bool(payload.get("resume", True)),
        control=control,
        learning_reviewer=services.learning_reviewer,
        candidate_evaluator=services.evaluator,
    )
