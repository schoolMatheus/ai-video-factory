"""Stage 2 — source-linked narration script with visual direction."""

from __future__ import annotations

from typing import Callable

from pydantic import ValidationError

from ai_video_factory.workflow.contracts import StageContext, StageInputs
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    ArtifactRef,
    Chapter,
    ObservationSeed,
    Pause,
    Scene,
    ScriptBundle,
    Shot,
    StageResult,
)

ScriptGenerator = Callable[[StageContext, object], ScriptBundle]


class ScriptStageError(RuntimeError):
    """Raised when the script cannot be grounded in the research dossier."""


class ScriptStage:
    external = False

    def __init__(self, *, generator: ScriptGenerator | None = None) -> None:
        self.generator = generator

    def run(self, context: StageContext, inputs: StageInputs) -> StageResult:
        research = inputs.research
        bundle = self.generator(context, research) if self.generator else self._build(context, research)
        known_claims = {claim.claim_id for claim in research.claims}
        for scene in bundle.scenes:
            for shot in scene.shots:
                if any(ref not in known_claims for ref in shot.claim_refs):
                    raise ScriptStageError(
                        f"shot {shot.shot_id} references a claim absent from the research bundle"
                    )
        if not bundle.scenes or any(not scene.narration_text.strip() for scene in bundle.scenes):
            raise ScriptStageError("script has no spoken content; refusing to pad duration with invention")
        if bundle.language != context.language:
            raise ScriptStageError(
                f"script language {bundle.language} does not match profile language {context.language}"
            )

        artifact_dir = context.artifacts_dir
        bundle_path = artifact_dir / BUNDLE_FILENAMES["script"]
        bundle.save(bundle_path)
        markdown_path = _write_markdown(bundle, artifact_dir / "script.md")
        artifacts = {
            "bundle": ArtifactRef.from_path(bundle_path, context.project_dir, "application/json"),
            "script": ArtifactRef.from_path(markdown_path, context.project_dir, "text/markdown"),
        }
        return StageResult(
            stage=context.stage,
            attempt=context.attempt,
            artifacts=artifacts,
            observations=[ObservationSeed(
                type="script_bundle", source="stage",
                summary=f"roteiro com {len(bundle.scenes)} cenas e {len(known_claims)} afirmações disponíveis",
                event_key=f"{context.request.production_id}:script:bundle",
            )],
            effective_config=dict(context.effective_settings),
        )

    @staticmethod
    def _build(context: StageContext, research: object) -> ScriptBundle:
        claims = list(research.claims)  # type: ignore[attr-defined]
        if not claims:
            raise ScriptStageError("no claims available from research; cannot write a grounded script")
        title = context.request.topic
        scenes: list[Scene] = []
        chapters: list[Chapter] = []
        for index, claim in enumerate(claims, start=1):
            scene_id = f"scene-{index:02d}"
            shot_id = f"{scene_id}-shot-1"
            detail_id = f"{scene_id}-shot-2"
            narration = f"{claim.text}."
            scenes.append(Scene(
                scene_id=scene_id,
                title=f"Capítulo {index}: {claim.text[:60]}",
                narration_text=narration,
                estimated_seconds=max(4.0, min(60.0, len(narration.split()) / 2.5)),
                pauses=[Pause(after_shot_id=shot_id, seconds=0.3)],
                shots=[
                    Shot(
                        shot_id=shot_id,
                        visual=f"Plano de abertura: {claim.text}",
                        intent="contextualizar a afirmação com o material pesquisado",
                        on_screen_text=claim.claim_id,
                        transition="cut",
                        claim_refs=[claim.claim_id],
                    ),
                    Shot(
                        shot_id=detail_id,
                        visual=f"Plano de detalhe: {claim.text}",
                        intent="aprofundar o mesmo ponto com outra imagem",
                        on_screen_text=claim.text[:60],
                        transition="dissolve",
                        overlap_seconds=0.4,
                        claim_refs=[claim.claim_id],
                    ),
                ],
            ))
            chapters.append(Chapter(chapter_id=f"chapter-{index:02d}", title=f"Capítulo {index}", scene_ids=[scene_id]))
        return ScriptBundle(
            title=title,
            logline=context.request.angle,
            language=context.language,
            chapters=chapters,
            scenes=scenes,
            estimated_duration_seconds=sum(scene.estimated_seconds for scene in scenes),
        )


def _write_markdown(bundle: ScriptBundle, path: object) -> Path:
    from pathlib import Path

    path = Path(path)
    lines = [f"# {bundle.title}", "", f"Idioma: {bundle.language}", ""]
    if bundle.logline:
        lines += [f"* {bundle.logline}", ""]
    for chapter in bundle.chapters:
        lines += [f"## {chapter.title}", ""]
        for scene_id in chapter.scene_ids:
            scene = next((item for item in bundle.scenes if item.scene_id == scene_id), None)
            if scene is None:
                continue
            lines += [f"### {scene.title}", "", "**Fala exata:**", scene.narration_text, ""]
            for shot in scene.shots:
                lines.append(
                    f"- `{shot.shot_id}` ({shot.transition}, sobreposição {shot.overlap_seconds}s): "
                    f"{shot.visual} — intenção: {shot.intent} — texto: {shot.on_screen_text or '—'} "
                    f"— fontes: {', '.join(shot.claim_refs) or '—'}"
                )
            for pause in scene.pauses:
                lines.append(f"- pausa de {pause.seconds}s após `{pause.after_shot_id}`")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
