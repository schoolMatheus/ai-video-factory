"""Stage 4 — shot-matched media acquisition with documented rights."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Callable

from ai_video_factory.asset_memory import AssetMemory, score_relevance, scoped_memory_path
from ai_video_factory.workflow.contracts import StageContext, StageInputs
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    ArtifactRef,
    MediaBundle,
    MediaCandidate,
    MediaGap,
    MediaSelection,
    ObservationSeed,
    RightsRecord,
    StageResult,
)

def _safe_media_path(directory: Path, identity: str, suffix: str) -> Path:
    """Contained, cross-platform filename derived from a candidate identity."""
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    tail = identity.split("?", 1)[0].rsplit("/", 1)[-1]
    stem = re.sub(r"[^A-Za-z0-9_-]", "-", tail)[:32] or "media"
    safe_suffix = re.sub(r"[^A-Za-z0-9.]", "", suffix) or ".bin"
    destination = (directory / f"{stem}-{digest}{safe_suffix}").resolve()
    if directory.resolve() not in destination.parents:
        raise ValueError("media destination escapes the production directory")
    return destination


CandidateSearch = Callable[[str, int], list[dict[str, Any]]]
AssetFetch = Callable[[dict[str, Any], Path], Path | None]
TechnicalQc = Callable[[Path], bool]


class MediaStage:
    external = True

    def __init__(
        self,
        *,
        search: CandidateSearch | None = None,
        fetch: AssetFetch | None = None,
        technical_qc: TechnicalQc | None = None,
        memory: AssetMemory | None = None,
        data_dir: str | Path = "data",
    ) -> None:
        self.search = search
        self.fetch = fetch
        self.technical_qc = technical_qc
        self.memory = memory
        self.data_dir = Path(data_dir)

    def run(self, context: StageContext, inputs: StageInputs) -> StageResult:
        memory = self.memory or AssetMemory(
            scoped_memory_path(context.snapshot.profile_id, data_dir=self.data_dir),
            profile_id=context.snapshot.profile_id,
        )
        candidates: list[MediaCandidate] = []
        selected: list[MediaSelection] = []
        rights: list[RightsRecord] = []
        gaps: list[MediaGap] = []
        observations: list[ObservationSeed] = []
        files_dir = context.artifacts_dir / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        limit = max(1, int(context.setting("media.candidates_per_shot", 3)))
        seen_ids: set[str] = set()

        for scene in inputs.script.scenes:
            for shot in scene.shots:
                query = self._query(context, scene.title, shot.visual)
                found = self.search(query, limit) if self.search else []
                useful: list[dict[str, Any]] = []
                for raw in found:
                    candidate_id = str(raw.get("id") or raw.get("url") or "")
                    if not candidate_id or candidate_id in seen_ids:
                        continue
                    seen_ids.add(candidate_id)
                    title = str(raw.get("title", ""))
                    relevance = score_relevance(title, shot.visual)
                    license_name = raw.get("license")
                    file_ref = None
                    technical_ok = True
                    if memory.is_blocked(candidate_id):
                        memory.record_rejection(
                            candidate_id, "rejeição editorial do canal", "profile_memory",
                            classification="editorial",
                        )
                        continue
                    source_path = raw.get("path")
                    if source_path is not None and Path(source_path).is_file():
                        technical_ok = self.technical_qc(Path(source_path)) if self.technical_qc else True
                        if not technical_ok:
                            memory.record_rejection(
                                candidate_id, "falha técnica no arquivo", "asset_qc",
                                classification="technical",
                            )
                    if relevance <= 0:
                        memory.record_rejection(
                            candidate_id, "sem correspondência com o plano", "relevance",
                            classification="editorial",
                        )
                        continue
                    if license_name is None:
                        gaps.append(MediaGap(
                            scene_id=scene.scene_id, shot_id=shot.shot_id,
                            reason="licença ausente; plano bloqueado para entrega final",
                            strategy="buscar alternativa com licença explícita",
                        ))
                        continue
                    if not technical_ok:
                        continue
                    if self.fetch is not None:
                        source = self.fetch(raw, files_dir)
                        if source is not None and source.is_file():
                            # A URL is not a Windows filename. Keep the provider
                            # id and URL as metadata; derive a safe, stable name
                            # from a digest of the candidate identity.
                            destination = _safe_media_path(files_dir, candidate_id, source.suffix)
                            if source.resolve() != destination.resolve():
                                destination.write_bytes(source.read_bytes())
                            file_ref = ArtifactRef.from_path(
                                destination, context.project_dir, "video/mp4"
                            )
                    candidate = MediaCandidate(
                        candidate_id=candidate_id,
                        scene_id=scene.scene_id,
                        shot_id=shot.shot_id,
                        query=query,
                        url=str(raw.get("url", "")),
                        title=title,
                        license=str(license_name),
                        attribution=str(raw.get("attribution", "")),
                        file=file_ref,
                        relevance=relevance,
                        technical_ok=True,
                    )
                    candidates.append(candidate)
                    useful.append(raw)
                if useful:
                    best = max(useful, key=lambda raw: score_relevance(str(raw.get("title", "")), shot.visual))
                    best_id = str(best.get("id") or best.get("url") or "")
                    candidate = next(item for item in candidates if item.candidate_id == best_id)
                    selected.append(MediaSelection(
                        scene_id=scene.scene_id,
                        shot_id=shot.shot_id,
                        candidate_id=best_id,
                        file=candidate.file,
                        strategy=None if candidate.file else f"compor plano com base em: {shot.visual}",
                        source_duration_seconds=self._shot_duration(inputs, shot.shot_id),
                        movement=str(best.get("movement", "static")),
                    ))
                    rights.append(RightsRecord(
                        candidate_id=best_id,
                        license=candidate.license or "unknown",
                        attribution=candidate.attribution,
                        source_url=candidate.url,
                    ))
                else:
                    gaps.append(MediaGap(
                        scene_id=scene.scene_id,
                        shot_id=shot.shot_id,
                        reason="nenhum candidato com direitos e relevância verificados",
                        strategy=f"compor plano explicitamente: {shot.visual}",
                    ))

        if gaps:
            observations.append(ObservationSeed(
                type="media_gaps", source="stage",
                summary=f"{len(gaps)} planos sem mídia verificada",
                event_key=f"{context.request.production_id}:media:gaps",
            ))
        bundle = MediaBundle(
            candidates=candidates,
            selected=selected,
            rights=rights,
            gaps=gaps,
            rights_complete=not any("licença ausente" in gap.reason for gap in gaps),
        )
        bundle_path = context.artifacts_dir / BUNDLE_FILENAMES["media"]
        bundle.save(bundle_path)
        rights_path = context.artifacts_dir / "rights.json"
        rights_path.write_text(
            "\n".join(f"{item.candidate_id}: {item.license} — {item.attribution}" for item in rights),
            encoding="utf-8",
        )
        gaps_path = context.artifacts_dir / "gaps.json"
        gaps_path.write_text(
            __import__("json").dumps([item.model_dump() for item in gaps], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return StageResult(
            stage=context.stage,
            attempt=context.attempt,
            artifacts={
                "bundle": ArtifactRef.from_path(bundle_path, context.project_dir, "application/json"),
                "rights": ArtifactRef.from_path(rights_path, context.project_dir, "text/plain"),
                "gaps": ArtifactRef.from_path(gaps_path, context.project_dir, "application/json"),
                **{item.candidate_id: item.file for item in candidates if item.file is not None},
            },
            observations=observations,
            effective_config=dict(context.effective_settings),
        )

    @staticmethod
    def _query(context: StageContext, title: str, visual: str) -> str:
        parts = [context.request.topic, title, visual]
        extra = context.setting("media.query_suffix", "")
        if extra:
            parts.append(str(extra))
        return " | ".join(part for part in parts if part)

    @staticmethod
    def _shot_duration(inputs: StageInputs, shot_id: str) -> float | None:
        for segment in inputs.narration.segments:
            if segment.shot_id == shot_id:
                return segment.duration_seconds
        return None
