"""Research stage behaviour (plan task 7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_video_factory.profiles.context import build_memory_context
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.research_pipeline import Extraction
from ai_video_factory.stages.research import ResearchStage, ResearchStageError
from ai_video_factory.workflow.contracts import StageContext
from ai_video_factory.workflow.models import ProductionRequest, StageInputs


def _context(tmp_path: Path, topic: str = "Tema informado", urls: list[str] | None = None) -> StageContext:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    snapshot = store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
    }))
    request = ProductionRequest.model_validate({
        "production_id": "prod-1", "profile_id": "canal", "topic": topic,
        "target_minutes": 1.0, "base_dir": str(tmp_path / "projects"),
        "seed_source_urls": urls or [],
    })
    request.project_dir.mkdir(parents=True, exist_ok=True)
    memory = build_memory_context(store, snapshot, "research", topic)
    return StageContext(
        request=request, snapshot=snapshot, stage="research", attempt=1,
        artifacts_dir=request.project_dir / "artifacts" / "01_research",
        memory=memory, effective_settings=memory.settings, project_dir=request.project_dir,
    )


def test_supplied_topic_survives_an_unrelated_trend(tmp_path: Path) -> None:
    queries: list[str] = []
    def discovery(query: str) -> list[dict[str, Any]]:
        queries.append(query)
        return [{"url": "https://a.example/artigo", "topic": "Outro tema completamente diferente"}]

    def extractor(topic: str, sources: list[Any]) -> list[tuple[str, str]]:
        return [("afirmação sustentada", "confirmed fact")]

    context = _context(tmp_path)
    result = ResearchStage(
        source_discovery=discovery, extractor=extractor,
    ).run(context, StageInputs.load("research", {}, context.project_dir))
    assert context.request.topic == "Tema informado"
    assert queries == ["Tema informado"]
    assert any(item.type == "trend_mismatch" for item in result.observations)
    assert result.stage == "research"
    assert result.artifacts["bundle"].path.endswith("research_bundle.json")


def test_evidence_comes_from_content_and_divergence_is_preserved(tmp_path: Path) -> None:
    def transport(url: str) -> str:
        if "a.example" in url:
            return "Texto real longo o suficiente. A grows steadily in the source material."
        return "Texto real longo o suficiente. A decreases in the second source material."

    def production_extractor(topic: str, contents: list[Any], *, identity: Any = None) -> list[Extraction]:
        result = []
        for content in contents:
            quote = "A grows steadily" if "a.example" in content.url else "A decreases"
            result.append(Extraction(
                claim=f"Fato extraído de {content.url}: {quote}",
                quote=quote,
                classification="confirmed fact",
            ))
        return result

    context = _context(tmp_path, urls=["https://a.example/a", "https://b.example/b"])
    result = ResearchStage(
        transport=transport, production_extractor=production_extractor,
    ).run(context, StageInputs.load("research", {}, context.project_dir))
    bundle = result.artifacts["bundle"].read_json(context.project_dir)
    assert len(bundle["claims"]) == 2
    assert all(item["evidence"] for item in bundle["claims"])
    assert bundle["contradictions"]
    assert all(not item["verified"] for item in bundle["claims"])
    assert any(item.type == "source_contradiction" for item in result.observations)
    assert bundle["sources"][0]["content_hash"]


def test_missing_content_blocks_verification(tmp_path: Path) -> None:
    context = _context(tmp_path, urls=["https://a.example/a"])
    stage = ResearchStage(transport=lambda url: "curto", production_extractor=lambda topic, contents: [])
    with pytest.raises(ResearchStageError):
        stage.run(context, StageInputs.load("research", {}, context.project_dir))
