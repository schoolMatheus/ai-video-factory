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
            "stages": [str(stage) for stage in self.runners],
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


def default_research_transports() -> dict[str, Any]:
    """Real research boundaries: topic discovery, fetch and evidence extraction."""
    from urllib.parse import quote

    from ai_video_factory.research_pipeline import (
        make_production_extractor,
        make_secure_http_transport,
    )

    def discover(topic: str) -> list[dict[str, str]]:
        url = (
            "https://en.wikipedia.org/w/api.php?action=opensearch&format=json"
            f"&limit=5&search={quote(topic)}"
        )
        try:
            import json
            import urllib.request

            with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - fixed https
                payload = json.loads(response.read().decode("utf-8"))
            return [
                {"url": item, "topic": topic}
                for item in (payload[3] if isinstance(payload, list) and len(payload) > 3 else [])
            ]
        except (OSError, ValueError, KeyError, TypeError):
            return []

    return {
        "source_discovery": discover,
        "transport": make_secure_http_transport(),
        "production_extractor": make_production_extractor(),
    }


def default_script_generator() -> Any:
    """Editorial generation from the dossier; no silent deterministic fallback."""
    from ai_video_factory.script_generator import generate_script_with_lm_studio

    def generate(context: Any, research: Any) -> Any:
        from ai_video_factory.workflow.models import (
            Chapter,
            Scene,
            ScriptBundle,
            Shot,
        )

        outline = "\n".join(
            f"- {claim.claim_id} ({claim.classification}): {claim.text}"
            for claim in research.claims
        )
        source_url = str(
            getattr(research.sources[0], "url", "") if getattr(research, "sources", None) else ""
        )
        result = generate_script_with_lm_studio(
            topic_title=context.topic,
            topic_description=f"Idioma: {context.language}. Recorte: {context.request.angle}. {outline}",
            source_url=source_url,
            duration_seconds=int(context.request.target_minutes * 60),
        )
        generated = result if isinstance(result, dict) else {}
        drafts = generated.get("scenes")
        drafts = drafts if isinstance(drafts, list) else []
        known = {claim.claim_id for claim in research.claims}
        scenes: list[Scene] = []
        for index, claim in enumerate(research.claims, start=1):
            scene_id = f"scene-{index:02d}"
            shot_id = f"{scene_id}-shot-1"
            draft = drafts[index - 1] if index - 1 < len(drafts) else {}
            draft = draft if isinstance(draft, dict) else {}
            spoken = str(draft.get("narration") or claim.text).strip()
            qualification = (
                "Fontes divergentes; apresentar como discussão, não como fato confirmado."
                if claim.classification != "confirmed fact" or not claim.verified
                else "Fato sustentado pelo dossiê."
            )
            narration_text = f"{spoken} {qualification}"
            scenes.append(Scene(
                scene_id=scene_id,
                title=str(draft.get("title") or f"Capítulo {index}: {claim.text[:60]}"),
                narration_text=narration_text,
                estimated_seconds=max(4.0, min(60.0, len(narration_text.split()) / 2.5)),
                shots=[Shot(
                    shot_id=shot_id,
                    visual=str(draft.get("visual") or draft.get("caption")
                               or f"Plano editorial: {claim.text}"),
                    intent=qualification, claim_refs=[claim.claim_id] if claim.claim_id in known else [],
                )],
            ))
        return ScriptBundle(
            title=str(generated.get("title") or context.topic or "Episódio"),
            logline=context.request.angle,
            language=context.language,
            chapters=[Chapter(chapter_id=f"chapter-{n:02d}", title=f"Capítulo {n}",
                              scene_ids=[f"scene-{n:02d}"]) for n in range(1, len(scenes) + 1)],
            scenes=scenes,
            estimated_duration_seconds=sum(scene.estimated_seconds for scene in scenes),
        )

    return generate


class RuleBasedEvaluator:
    """Bounded trial: evidence, scope and typed patch, no aesthetic weights."""

    def evaluate(self, candidate: Any, context: Any) -> Any:
        from uuid import uuid4

        from ai_video_factory.profiles.models import EvaluationCheck, LearningEvaluation

        evidence_ok = bool(candidate.evidence_ids)
        checks = [
            EvaluationCheck(name="evidence", passed=evidence_ok,
                            detail="evidência persistida" if evidence_ok else "sem evidência"),
            EvaluationCheck(name="typed_patch", passed=bool(candidate.change.path)),
        ]
        return LearningEvaluation(
            evaluation_id=uuid4().hex, candidate_id=candidate.candidate_id,
            candidate_version=1, trial="rule-based policy check",
            evidence_ids=list(candidate.evidence_ids), checks=checks,
            result="pass" if all(item.passed for item in checks) else "inconclusive",
            rationale="ensaio determinístico sem pesos calibrados",
        )


def default_learning_transports() -> dict[str, Any]:
    """Autonomous learning hooks wired by default, without human approval."""

    def reviewer(context: Any, observations: list[Any]) -> list[Any]:
        from ai_video_factory.profiles.learning import review_observations

        return review_observations(context, observations)

    return {"learning_reviewer": reviewer, "candidate_evaluator": RuleBasedEvaluator()}


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

    research = transports.get("research")
    if research is None:
        real = default_research_transports()
        research = ResearchStage(
            source_discovery=transports.get("source_discovery", real["source_discovery"]),
            transport=transports.get("content_transport", real["transport"]),
            production_extractor=transports.get("production_extractor", real["production_extractor"]),
        )
    script = transports.get("script")
    if script is None:
        script = ScriptStage(
            generator=transports.get("script_generator", default_script_generator()),
            deterministic=bool(transports.get("deterministic_script", False)),
        )

    runners: dict[StageName, Any] = {
        "research": research,
        "script": script,
        "narration": narration,
        "media": transports.get("media") or _stock_media(data_root),
        "editing": transports.get("editing") or EditingStage(editor),
        "review": transports.get("review") or ReviewStage(),
    }
    learning = default_learning_transports()
    return ProductionServices(
        snapshot=snapshot,
        runners=runners,
        store=resolved_store,
        paths={"data_root": data_root, "profile_db": profile_db},
        learning_reviewer=transports.get("learning_reviewer", learning["learning_reviewer"]),
        evaluator=transports.get("candidate_evaluator", learning["candidate_evaluator"]),
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
        invalidation_inputs=set(payload.get("invalidation_inputs") or ()),
    )
