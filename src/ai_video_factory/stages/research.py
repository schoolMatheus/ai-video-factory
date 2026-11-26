"""Stage 1 — topic-driven deep research with traceable evidence."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from ai_video_factory.profiles.models import StageName
from ai_video_factory.research_pipeline import (
    Extraction,
    ResearchError,
    SourceContent,
    persist_source_content,
    run_research,
    write_research_artifacts,
)
from ai_video_factory.workflow.contracts import StageContext, StageInputs
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    ArtifactRef,
    ClaimEntry,
    ContradictionEntry,
    EvidenceEntry,
    ObservationSeed,
    ResearchBundle,
    SourceEntry,
    StageResult,
)

SourceDiscovery = Callable[[str], Sequence[dict[str, Any] | str]]
Extractor = Callable[[str, list[Any]], list[tuple[str, str]]]
ProductionExtractor = Callable[[str, list[SourceContent]], list[Extraction]]


class ResearchStageError(RuntimeError):
    """Raised when no supported material can back a research delivery."""


class ResearchStage:
    external = True

    def __init__(
        self,
        *,
        source_discovery: SourceDiscovery | None = None,
        transport: Callable[[str], str | bytes] | None = None,
        extractor: Extractor | None = None,
        production_extractor: ProductionExtractor | None = None,
    ) -> None:
        self.source_discovery = source_discovery
        self.transport = transport
        self.extractor = extractor
        self.production_extractor = production_extractor

    def run(self, context: StageContext, inputs: StageInputs) -> StageResult:
        topic = context.request.topic  # never silently replaced by a trend
        observations: list[ObservationSeed] = []
        discovered = self._discover(topic, context, observations)
        urls = list(dict.fromkeys([*context.request.seed_source_urls, *discovered]))
        if not urls:
            raise ResearchStageError(
                f"no seed or discovered sources for topic {topic!r}; refusing to invent material"
            )

        limits = context.request.budget
        if limits is not None and limits.max_external_calls is not None:
            urls = urls[: max(1, limits.max_external_calls)]

        production_mode = self.transport is not None or self.production_extractor is not None
        try:
            result = run_research(
                topic,
                urls,
                extractor=self.extractor if not production_mode else None,
                production_extractor=self.production_extractor,
                content_fetcher=self.transport,
            )
        except ResearchError as error:
            raise ResearchStageError(str(error)) from error

        verified_ids = {claim.claim_id for claim in result.verified_facts}
        claims = [
            ClaimEntry(
                claim_id=claim.claim_id,
                text=claim.text,
                classification=claim.provisional_classification,
                source_ids=list(claim.source_ids),
                evidence=[
                    EvidenceEntry(
                        source_url=str(item.get("url", "")),
                        quote=str(item.get("quote", "")),
                        chunk_id=str(item.get("chunk_id", "")),
                    )
                    for item in claim.evidence
                ],
                verified=claim.claim_id in verified_ids,
            )
            for claim in result.claims
        ]
        contradictions = [
            ContradictionEntry(
                contradiction_id=item.contradiction_id,
                claim_ids=list(item.claim_ids),
                nature=item.nature,
                resolution=item.resolution,
            )
            for item in result.contradictions
        ]
        if contradictions:
            observations.append(ObservationSeed(
                type="source_contradiction", source="research_pipeline",
                summary=f"fontes divergentes: {contradictions[0].nature}",
                event_key=f"{context.request.production_id}:research:contradictions",
            ))

        artifact_dir = context.artifacts_dir
        paths = write_research_artifacts(result, artifact_dir)
        sources: list[SourceEntry] = []
        for source in result.sources:
            content = result.source_contents.get(source.url)
            content_ref = None
            if content is not None:
                content_path = persist_source_content(content, artifact_dir)
                content_ref = ArtifactRef.from_path(content_path, context.project_dir, "text/plain")
            sources.append(SourceEntry(
                url=source.url,
                title=source.title,
                quality=source.quality,
                content_hash=content.content_hash if content else "",
                content_ref=content_ref,
            ))
        bundle = ResearchBundle(
            topic=topic,
            angle=context.request.angle,
            sources=sources,
            claims=claims,
            contradictions=contradictions,
            uncertainties=list(result.flag_reasons),
            synthesis=result.research_brief,
            brief_ref=ArtifactRef.from_path(paths["research_brief"], context.project_dir, "text/markdown"),
        )
        bundle_path = artifact_dir / BUNDLE_FILENAMES["research"]
        bundle.save(bundle_path)
        observations.append(ObservationSeed(
            type="research_bundle", source="stage",
            summary=f"dossiê de {topic}: {len(sources)} fontes, {len(claims)} afirmações",
            evidence_refs=[paths["claims"].as_posix()],
            event_key=f"{context.request.production_id}:research:bundle",
        ))
        artifacts = {key: ArtifactRef.from_path(path, context.project_dir, "application/json")
                     for key, path in paths.items() if path.suffix == ".json"}
        artifacts["bundle"] = ArtifactRef.from_path(bundle_path, context.project_dir, "application/json")
        return StageResult(
            stage=context.stage,
            attempt=context.attempt,
            artifacts=artifacts,
            observations=observations,
            effective_config=dict(context.effective_settings),
        )

    def _discover(
        self,
        topic: str,
        context: StageContext,
        observations: list[ObservationSeed],
    ) -> list[str]:
        if self.source_discovery is None:
            return []
        found = self.source_discovery(topic)
        urls: list[str] = []
        for item in found:
            if isinstance(item, str):
                urls.append(item)
                continue
            url = str(item.get("url", ""))
            if url:
                urls.append(url)
            candidate_topic = str(item.get("topic", topic))
            if candidate_topic != topic:
                observations.append(ObservationSeed(
                    type="trend_mismatch", source="discovery",
                    summary=f"tendência descoberta ({candidate_topic}) divergente; tema preservado: {topic}",
                    event_key=f"{context.request.production_id}:research:trend:{url}",
                ))
        return urls
