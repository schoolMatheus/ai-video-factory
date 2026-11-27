"""Stage 6 — measured review, correction routing and final package."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from ai_video_factory.publisher import build_package
from ai_video_factory.workflow.contracts import StageContext, StageInputs
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    ArtifactRef,
    ObservationSeed,
    ReviewBundle,
    ReviewCheck,
    Reroute,
    StageResult,
    StructuredError,
)

Probe = Callable[[Path], dict[str, Any]]


def _probe_with_ffprobe(path: Path) -> dict[str, Any]:
    import subprocess

    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    if completed.returncode != 0:
        return {}
    payload = json.loads(completed.stdout or "{}")
    stream = next((item for item in payload.get("streams", []) if item.get("width")), {})
    return {
        "width": stream.get("width"),
        "height": stream.get("height"),
        "duration": float((payload.get("format") or {}).get("duration", 0) or 0),
    }


class ReviewStage:
    external = False

    def __init__(self, *, probe: Probe | None = None, packager: Callable | None = None) -> None:
        self.probe = probe or _probe_with_ffprobe
        self.packager = packager or build_package

    def run(self, context: StageContext, inputs: StageInputs) -> StageResult:
        editing = inputs.editing
        media = inputs.media
        script = inputs.script
        narration = inputs.narration
        research = inputs.research
        checks: list[ReviewCheck] = []
        failures: list[str] = []
        reroutes: list[Reroute] = []

        def check(name: str, category: str, passed: bool, detail: str, *, stage: str | None = None,
                  invalidation: str | None = None) -> None:
            checks.append(ReviewCheck(
                name=name, category=category,  # type: ignore[arg-type]
                passed=passed, detail=detail,
            ))
            if not passed:
                failures.append(f"{name}: {detail}")
                if stage:
                    reroutes.append(Reroute(
                        stage=stage,  # type: ignore[arg-type]
                        reason=detail,
                        invalidation_keys=[invalidation] if invalidation else [],
                    ))

        observed = editing.observed_state
        offline = list(observed.get("offline_media", []))
        check("offline_media", "technical", not offline,
              "mídia offline no projeto" if offline else "nenhuma mídia offline",
              stage="editing", invalidation="editing.media")

        master = editing.master
        master_path = master.resolve(context.project_dir) if master else None
        probe: dict[str, Any] = self.probe(master_path) if master_path and master_path.is_file() else {}
        expected_width = int(context.setting("editing.width", 1920))
        expected_height = int(context.setting("editing.height", 1080))
        resolution_ok = probe.get("width") == expected_width and probe.get("height") == expected_height
        check("resolution", "technical", resolution_ok,
              f"observado {probe.get('width')}x{probe.get('height')}, esperado {expected_width}x{expected_height}",
              stage="editing", invalidation="editing.resolution")

        measured_duration = float(probe.get("duration", 0) or 0)
        expected_duration = narration.total_duration_seconds
        tolerance = float(context.setting("review.duration_tolerance_seconds", 1.0))
        duration_ok = measured_duration > 0 and abs(measured_duration - expected_duration) <= tolerance
        check("duration", "technical", duration_ok,
              f"vídeo {measured_duration}s x narração {expected_duration}s",
              stage="narration", invalidation="narration.duration")

        known_claims = {claim.claim_id for claim in research.claims}
        broken_refs = [
            ref
            for scene in script.scenes
            for shot in scene.shots
            for ref in shot.claim_refs
            if ref not in known_claims
        ]
        check("claim_refs", "content", not broken_refs,
              f"referências quebradas: {', '.join(broken_refs)}" if broken_refs else "todas as afirmações existem no dossiê",
              stage="script", invalidation="script.fact")

        spoken_ok = _normalized(script.canonical_narration) == _normalized(narration.spoken_text)
        check("spoken_text", "editorial", spoken_ok,
              "fala efetiva diverge do roteiro canônico" if not spoken_ok else "fala corresponde ao roteiro",
              stage="narration", invalidation="narration.text")

        missing_rights = [selection.shot_id for selection in media.selected
                          if not any(record.candidate_id == selection.candidate_id for record in media.rights)]
        rights_ok = media.rights_complete and not missing_rights
        check("rights", "rights", rights_ok,
              f"lacunas de direitos: {', '.join(missing_rights)}" if missing_rights else "direitos documentados",
              stage="media", invalidation="media.rights")

        missing_credits = [record.candidate_id for record in media.rights if not record.attribution]
        check("credits", "rights", not missing_credits,
              f"créditos ausentes: {', '.join(missing_credits)}" if missing_credits else "créditos presentes",
              stage="media", invalidation="media.credits")

        essential_gaps = [gap for gap in media.gaps if "compor plano" not in gap.strategy]
        check("media_gaps", "editorial", not essential_gaps,
              f"{len(essential_gaps)} lacunas essenciais" if essential_gaps else "sem lacunas essenciais",
              stage="media", invalidation="media.gaps")

        package_path: Path | None = None
        if not failures and master_path is not None:
            # The package is a delivery of this stage: it must live inside the
            # RunStore integrity root (<production>/artifacts), never at the
            # production root where containment checks reject it after the run.
            package_root = context.artifacts_dir / "package"
            package = self.packager(
                package_root,
                master_mp4=master_path,
                rights_manifest=_write_rights(context, media.rights),
                research_brief=_write_brief(context, research.synthesis),
                qc_reports=[_write_checks(context, checks)],
                title_candidates=[script.title],
                description=f"{script.title}\n\n{script.logline}".strip(),
            )
            approval = Path(package.approval_path)
            if json.loads(approval.read_text(encoding="utf-8"))["status"] != "pending":
                raise RuntimeError("new package must start with pending approval")
            package_path = package_root
        elif failures:
            failures.append("pacote não gerado: correções obrigatórias pendentes")

        bundle = ReviewBundle(
            checks=checks,
            editorial_review="; ".join(item.detail for item in checks if item.category == "editorial"),
            rights_review="; ".join(item.detail for item in checks if item.category == "rights"),
            failures=failures,
            reroutes=reroutes,
            status="passed" if not failures else "failed",
            package_path=str(package_path) if package_path else None,
        )
        bundle_path = context.artifacts_dir / BUNDLE_FILENAMES["review"]
        bundle.save(bundle_path)
        artifacts: dict[str, ArtifactRef] = {
            "bundle": ArtifactRef.from_path(bundle_path, context.project_dir, "application/json"),
        }
        if package_path is not None:
            artifacts["package"] = ArtifactRef.from_path(
                _write_package_manifest(package_path, bundle), context.project_dir, "application/json"
            )
        return StageResult(
            stage=context.stage,
            status="failed" if bundle.status == "failed" else "completed",
            attempt=context.attempt,
            artifacts=artifacts,
            observations=[ObservationSeed(
                type="review_completed", source="stage",
                summary=f"revisão {bundle.status} com {len(failures)} falha(s)",
                event_key=f"{context.request.production_id}:review:result",
            )],
            effective_config=dict(context.effective_settings),
            error=StructuredError(
                code="review_failed",
                message="; ".join(failures) or "revisão reprovada",
                details={
                    "bundle_status": bundle.status,
                    "reroutes": [route.model_dump() for route in reroutes],
                },
            ) if bundle.status == "failed" else None,
        )


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _write_rights(context: StageContext, records: list[Any]) -> Path:
    path = context.artifacts_dir / "rights_manifest.json"
    path.write_text(json.dumps([record.model_dump() for record in records], ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_brief(context: StageContext, synthesis: str) -> Path:
    path = context.artifacts_dir / "review_brief.md"
    path.write_text(synthesis or "# Síntese\n", encoding="utf-8")
    return path


def _write_checks(context: StageContext, checks: list[ReviewCheck]) -> Path:
    path = context.artifacts_dir / "review_checks.json"
    path.write_text(json.dumps([item.model_dump() for item in checks], ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_package_manifest(package_root: Path, bundle: ReviewBundle) -> Path:
    path = package_root / "review_manifest.json"
    path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
    return path
