"""Cross-boundary review integration: honest failure state and contained package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from ai_video_factory.models import StageStatus
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.run_store import RunStore
from ai_video_factory.stages.review import ReviewStage
from ai_video_factory import workflow_cli
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    STAGE_ORDER,
    ArtifactRef,
    ClaimEntry,
    EditingBundle,
    EvidenceEntry,
    MediaBundle,
    NarrationBundle,
    ObservationSeed,
    ProductionRequest,
    ResearchBundle,
    ReviewBundle,
    ScriptBundle,
    StageResult,
)
from ai_video_factory.workflow.orchestrator import run_production

_PROBE = {"width": 1920, "height": 1080, "duration": 10.0}


def _probe(path: Path) -> dict[str, Any]:
    return dict(_PROBE)


def _store(tmp_path: Path) -> ProfileStore:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal",
        "name": "Canal",
        "language": "pt-BR",
        "operation_budget": {"max_external_calls": 10},
    }))
    return store


def _request(tmp_path: Path, production_id: str = "prod-review") -> ProductionRequest:
    return ProductionRequest.model_validate({
        "production_id": production_id,
        "profile_id": "canal",
        "topic": "Tema informado",
        "target_minutes": 1 / 60,
        "base_dir": str(tmp_path / "projects"),
    })


class _DeterministicRunner:
    """A real predecessor delivery, written where the coordinator expects it."""

    def __init__(self, *, offline: list[str] | None = None) -> None:
        self.offline = offline or []
        self.calls: list[str] = []

    def run(self, context: Any, inputs: Any) -> StageResult:
        self.calls.append(context.stage)
        directory = Path(context.artifacts_dir)
        directory.mkdir(parents=True, exist_ok=True)
        project = Path(context.project_dir)
        bundle: Any

        if context.stage == "research":
            bundle = ResearchBundle(
                topic=context.topic,
                claims=[ClaimEntry(
                    claim_id="c1", text="Fato", classification="confirmed fact",
                    source_ids=["https://a.example"],
                    evidence=[EvidenceEntry(source_url="https://a.example", quote="trecho")],
                    verified=True,
                )],
                synthesis="# Síntese real",
            )
        elif context.stage == "script":
            bundle = ScriptBundle(
                title="Episódio", logline="recorte", language="pt-BR",
                estimated_duration_seconds=10.0,
                scenes=[{
                    "scene_id": "s1", "title": "Cena", "narration_text": "Fala canônica.",
                    "estimated_seconds": 10.0,
                    "shots": [{"shot_id": "sh1", "visual": "v", "claim_refs": ["c1"]}],
                }],
            )
        elif context.stage == "narration":
            audio = directory / "segment.wav"
            audio.write_bytes(b"RIFFfake")
            audio_ref = ArtifactRef.from_path(audio, project, "audio/wav")
            bundle = NarrationBundle(
                provider="fake", voice="v", language="pt-BR",
                segments=[{
                    "segment_id": "n1", "scene_id": "s1", "shot_id": "sh1",
                    "text": "Fala canônica.", "audio": audio_ref.model_dump(),
                    "start_seconds": 0.0, "duration_seconds": 10.0,
                }],
                spoken_text="Fala canônica.",
                total_duration_seconds=10.0,
            )
        elif context.stage == "media":
            shot = directory / "shot.mp4"
            shot.write_bytes(b"media bytes")
            file_ref = ArtifactRef.from_path(shot, project, "video/mp4")
            bundle = MediaBundle(
                candidates=[{
                    "candidate_id": "m1", "scene_id": "s1", "shot_id": "sh1",
                    "license": "CC0", "attribution": "Autor", "file": file_ref.model_dump(),
                }],
                selected=[{
                    "scene_id": "s1", "shot_id": "sh1", "candidate_id": "m1",
                    "file": file_ref.model_dump(),
                }],
                rights=[{
                    "candidate_id": "m1", "license": "CC0", "attribution": "Autor",
                    "source_url": "https://a.example",
                }],
            )
        else:
            master = directory / "master.mp4"
            master.write_bytes(b"master")
            master_ref = ArtifactRef.from_path(master, project, "video/mp4")
            bundle = EditingBundle(
                filmcraft_version="test", mode="bridge", project_path="editing/project.fcproj",
                item_map={"sh1": "item-1"}, master=master_ref.model_dump(),
                observed_state={"offline_media": list(self.offline)},
            )

        path = directory / BUNDLE_FILENAMES[context.stage]
        bundle.save(path)
        return StageResult(
            stage=context.stage,
            attempt=context.attempt,
            artifacts={"bundle": ArtifactRef.from_path(path, project, "application/json")},
            observations=[ObservationSeed(
                type="stage_completed", source="deterministic-runner",
                summary=f"{context.stage} entregue",
                event_key=f"{context.request.production_id}:{context.stage}:completed",
            )],
            effective_config=dict(context.effective_settings),
        )


def _runners(*, offline: list[str] | None = None) -> dict[str, Any]:
    predecessor = _DeterministicRunner(offline=offline)
    return {stage: predecessor for stage in STAGE_ORDER if stage != "review"}


def _run(tmp_path: Path, *, offline: list[str] | None = None) -> Any:
    runners = _runners(offline=offline)
    runners["review"] = ReviewStage(probe=_probe)
    return run_production(_request(tmp_path), store=_store(tmp_path), runners=runners)


def _review_bundle(result: Any) -> ReviewBundle:
    ref: ArtifactRef = result.artifacts["review.bundle"]
    return ReviewBundle.load(ref.resolve(Path(result.project_dir)))


def test_real_review_failure_cannot_complete_production(tmp_path: Path) -> None:
    result = _run(tmp_path, offline=["missing.mp4"])

    assert result.status != "completed"
    assert result.final_stage == "review"
    assert result.package_path is None
    assert result.failures
    assert any("offline_media" in failure.message for failure in result.failures)

    bundle = _review_bundle(result)
    assert bundle.status == "failed"
    assert bundle.failures
    assert "editing" in {route.stage for route in bundle.reroutes}
    assert bundle.package_path is None

    state_dir = Path(result.project_dir) / "state"
    run_id = json.loads((state_dir / "run_ids.json").read_text(encoding="utf-8"))["review"]
    runs = RunStore(state_dir, artifact_root=Path(result.project_dir) / "artifacts")
    assert runs._load_run(run_id).status is StageStatus.failed


def test_real_review_package_is_contained_and_registered(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result.status == "completed"
    assert result.failures == []
    assert result.package_path

    package = Path(result.package_path).resolve()
    artifacts_root = (Path(result.project_dir) / "artifacts").resolve()
    assert artifacts_root in package.parents
    assert (package / "review_manifest.json").is_file()
    assert json.loads((package / "review_manifest.json").read_text(encoding="utf-8"))["status"] == "passed"
    assert (package / "master.mp4").is_file()

    state_dir = Path(result.project_dir) / "state"
    run_id = json.loads((state_dir / "run_ids.json").read_text(encoding="utf-8"))["review"]
    runs = RunStore(state_dir, artifact_root=artifacts_root)
    manifest = runs._load_run(run_id)
    assert manifest.status is StageStatus.completed
    assert "package" in manifest.artifact_integrity
    assert runs._artifact_integrity_error(manifest) is None


def test_cli_review_rejection_exits_nonzero(tmp_path: Path, monkeypatch: Any) -> None:
    store = _store(tmp_path)
    monkeypatch.setattr(workflow_cli, "open_store", lambda: store)
    monkeypatch.setattr(workflow_cli, "build_runners", lambda *_args: {
        **_runners(offline=["missing.mp4"]),
        "review": ReviewStage(probe=_probe),
    })

    result = CliRunner().invoke(workflow_cli.workflow_app, [
        "run", "--profile", "canal", "--topic", "Tema", "--production", "prod-cli",
        "--target-minutes", "0.0166667",
        "--base-dir", str(tmp_path / "projects"),
    ])

    assert result.exit_code == 2
    assert '"status": "failed"' in result.output


def test_cli_approved_review_produces_registered_package(tmp_path: Path, monkeypatch: Any) -> None:
    store = _store(tmp_path)
    monkeypatch.setattr(workflow_cli, "open_store", lambda: store)
    monkeypatch.setattr(workflow_cli, "build_runners", lambda *_args: {
        **_runners(),
        "review": ReviewStage(probe=_probe),
    })

    result = CliRunner().invoke(workflow_cli.workflow_app, [
        "run", "--profile", "canal", "--topic", "Tema", "--production", "prod-cli-ok",
        "--target-minutes", "0.0166667",
        "--base-dir", str(tmp_path / "projects"),
    ])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "completed"
    package = Path(payload["package_path"]).resolve()
    assert (package / "review_manifest.json").is_file()
