"""Sequential, resumable coordination of the six production stages.

The existing ``RunStore`` remains canonical for execution history; SQLite holds
profile identity and learning. A crash between the two is reconciled on the next
start from the persisted stage result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Mapping
from uuid import uuid4

from ai_video_factory.profiles.context import build_memory_context, stage_settings_digest
from ai_video_factory.profiles.models import Observation, StageName
from ai_video_factory.models import StageStatus
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.run_store import RunStore
from ai_video_factory.workflow.contracts import StageContext, StageRunner
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    STAGE_ORDER,
    ArtifactRef,
    ProductionRequest,
    ProductionResult,
    StageInputs,
    StageResult,
    StructuredError,
)

# Input keys that belong to a stage, including editorial aliases used by the
# review stage when rerouting corrections.
_STAGE_KEYS: dict[str, StageName] = {
    "research": "research",
    "script": "script",
    "narration": "narration",
    "media": "media",
    "editing": "editing",
    "review": "review",
}
_SPECIAL_KEYS: dict[str, tuple[StageName, ...]] = {
    "script.fact": ("script", "narration", "media", "editing", "review"),
    "script.speech": ("narration", "media", "editing", "review"),
    "script.narration": ("narration", "media", "editing", "review"),
    "script.visual": ("media", "editing", "review"),
}
_DOWNSTREAM: dict[StageName, tuple[StageName, ...]] = {
    "research": ("script", "narration", "media", "editing", "review"),
    "script": ("narration", "media", "editing", "review"),
    "narration": ("media", "editing", "review"),
    "media": ("editing", "review"),
    "editing": ("review",),
    "review": (),
}


def plan_invalidation(changed_inputs: set[str]) -> list[StageName]:
    """Stages whose outputs depend on the changed inputs, in execution order."""
    affected: set[StageName] = set()
    for key in sorted(changed_inputs):
        if key in _SPECIAL_KEYS:
            stages = set(_SPECIAL_KEYS[key])
        else:
            base = key.split(".", 1)[0]
            stage = _STAGE_KEYS.get(base)
            if stage is None:
                continue
            stages = {stage, *_DOWNSTREAM[stage]}
        affected.update(stages)
    return [stage for stage in STAGE_ORDER if stage in affected]


class StageExecutionError(RuntimeError):
    """A stage failed and its successors were not started."""


def run_production(
    request: ProductionRequest,
    *,
    store: ProfileStore,
    runners: Mapping[StageName, StageRunner],
    through: StageName = "review",
    resume: bool = True,
    dry_run: bool = False,
    run_store: RunStore | None = None,
    learning_reviewer: Callable | None = None,
    candidate_evaluator: object | None = None,
) -> ProductionResult:
    """Run the stages up to ``through``, reusing valid deliveries on resume."""
    if through not in STAGE_ORDER:
        raise ValueError(f"unknown stage {through}")
    snapshot = store.get_snapshot(request.profile_id, revision=request.profile_revision)
    resolved = request.model_copy(update={
        "language": request.language or snapshot.language,
        "tools": request.tools or dict(snapshot.settings.get("tools", {})),
        "budget": request.budget or snapshot.operation_budget,
        "profile_revision": snapshot.revision,
    })

    project_dir = resolved.project_dir
    artifacts_root = project_dir / "artifacts"
    state_dir = project_dir / "state"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "production.json").write_text(
        resolved.model_dump_json(indent=2), encoding="utf-8"
    )
    (project_dir / "profile_snapshot.json").write_text(
        snapshot.model_dump_json(indent=2), encoding="utf-8"
    )
    store.record_production(resolved.production_id, resolved.profile_id, "state/run_ids.json")

    runs = run_store or RunStore(state_dir, artifact_root=artifacts_root)
    refs_path = state_dir / "refs.json"
    run_ids_path = state_dir / "run_ids.json"
    refs: dict[StageName, ArtifactRef] = _load_refs(refs_path)
    results: dict[StageName, StageResult] = {}
    learning_ids: list[str] = []
    all_artifacts: dict[str, ArtifactRef] = {}

    _reconcile(state_dir, runs, store, resolved)

    if dry_run:
        return ProductionResult(
            production_id=resolved.production_id,
            profile_id=resolved.profile_id,
            status="pending",
            final_stage=through,
            project_dir=str(project_dir),
            learning_revision_ids=[],
        )

    budget = resolved.budget
    external_calls = 0
    for stage in STAGE_ORDER:
        if STAGE_ORDER.index(stage) > STAGE_ORDER.index(through):
            break
        runner = runners.get(stage)
        if runner is None:
            raise StageExecutionError(f"no runner configured for stage {stage}")
        memory = build_memory_context(
            store, snapshot, stage, resolved.topic,
            exclude_production_id=resolved.production_id,
        )
        artifact_dir = artifacts_root / f"{STAGE_ORDER.index(stage) + 1:02d}_{stage}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        context = StageContext(
            request=resolved,
            snapshot=snapshot,
            stage=stage,
            attempt=1,
            artifacts_dir=artifact_dir,
            memory=memory,
            effective_settings=memory.settings,
            tool_versions=resolved.tools,
            project_dir=project_dir,
        )
        inputs_payload = {
            "schema_version": 1,
            "production_id": resolved.production_id,
            "topic": resolved.topic,
            "angle": resolved.angle,
            "target_minutes": resolved.target_minutes,
            "seed_source_urls": list(resolved.seed_source_urls),
            "profile_id": resolved.profile_id,
            "profile_revision": snapshot.revision,
            "stage_settings_digest": stage_settings_digest(snapshot, stage),
            "memory_digest": memory.digest,
            "tools": resolved.tools,
            "predecessors": {
                name: ref.sha256 for name, ref in refs.items()
                if name in _predecessors(stage)
            },
        }
        result_path = state_dir / f"{stage}_result.json"
        cached = None
        if resume:
            cached = runs.completed_read_only(stage, inputs_payload)
            if cached is not None and result_path.is_file():
                candidate = StageResult.model_validate(json.loads(result_path.read_text(encoding="utf-8")))
                if candidate.stage == stage and candidate.status == "completed":
                    results[stage] = candidate
                    for key, ref in candidate.artifacts.items():
                        all_artifacts[f"{stage}.{key}"] = ref
                    bundle_ref = candidate.artifacts.get("bundle")
                    if bundle_ref is not None:
                        refs[stage] = bundle_ref
                    continue
        stage_inputs = StageInputs.load(stage, refs, project_dir)
        if getattr(runner, "external", False):
            if budget is None or not budget.configured:
                failure = StructuredError(
                    code="budget_not_configured",
                    message=f"stage {stage} needs an explicit operation budget before external calls",
                )
                return _failed_result(resolved, stage, results, all_artifacts, failure)
            if budget.max_external_calls is not None and external_calls >= budget.max_external_calls:
                failure = StructuredError(
                    code="budget_exhausted",
                    message="operation budget exhausted before stage " + stage,
                )
                return _failed_result(resolved, stage, results, all_artifacts, failure)
            external_calls += 1

        manifest = runs.start(stage, inputs_payload)
        run_ids = _load_json(run_ids_path)
        run_ids[stage] = manifest.run_id
        _write_json(run_ids_path, run_ids)
        try:
            result = runner.run(context, stage_inputs)
        except Exception as error:  # noqa: BLE001 - stage errors are structured at the boundary
            failure = StructuredError(
                code=type(error).__name__,
                message=str(error),
                retryable=False,
            )
            runs.fail(manifest.run_id, failure.message)
            _record_observations(
                store, resolved, stage, manifest.run_id,
                [{"type": "stage_failure", "source": "runner", "summary": failure.message,
                  "evidence_refs": [], "event_key": f"{resolved.production_id}:{stage}:failed"}],
                context.effective_settings, context.tool_versions,
            )
            return _failed_result(resolved, stage, results, all_artifacts, failure)

        # Persistence and integrity checks happen after the runner returns. A
        # failure here must become a structured production result, never an
        # unhandled exception that hides what the stage actually delivered.
        try:
            expected = {
                key: ref.resolve(project_dir) for key, ref in result.artifacts.items()
            }
            if "bundle" not in expected:
                raise StageExecutionError(f"stage {stage} did not declare a bundle artifact")
            runs.complete(manifest.run_id, {key: str(path) for key, path in expected.items()},
                          expected_artifacts=expected)
            _record_observations(
                store, resolved, stage, manifest.run_id,
                [seed.model_dump() for seed in result.observations],
                context.effective_settings, context.tool_versions,
            )
            result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        except Exception as error:  # noqa: BLE001 - boundary: persist, then report
            failure = StructuredError(
                code=type(error).__name__, message=str(error),
                details={"stage": stage, "phase": "after_runner"},
            )
            if runs._load_run(manifest.run_id).status is StageStatus.running:
                runs.fail(manifest.run_id, failure.message)
            return _failed_result(resolved, stage, results, all_artifacts, failure)

        results[stage] = result
        for key, ref in result.artifacts.items():
            all_artifacts[f"{stage}.{key}"] = ref

        if result.status != "completed":
            failure = result.error or StructuredError(
                code="stage_rejected",
                message=f"stage {stage} ended with status {result.status}",
                details={"stage": stage},
            )
            # The bundle and diagnostics are already persisted with integrity;
            # mark the run failed so resume cannot reuse a rejected delivery.
            runs.invalidate_completed(manifest.run_id, inputs_payload, failure.message)
            return _failed_result(resolved, stage, results, all_artifacts, failure)

        refs[stage] = result.artifacts["bundle"]
        _write_json(refs_path, {name: ref.model_dump() for name, ref in refs.items()})

        if learning_reviewer is not None and not dry_run:
            learning_ids.extend(
                _apply_learning(
                    store, context, stage, resolved.production_id,
                    learning_reviewer, candidate_evaluator,
                )
            )

    review = results.get("review")
    package_ref = review.artifacts.get("package") if review else None
    # The registered artifact is the manifest; the deliverable is its directory.
    package_dir = package_ref.resolve(project_dir).parent if package_ref else None
    return ProductionResult(
        production_id=resolved.production_id,
        profile_id=resolved.profile_id,
        status="completed",
        final_stage=through,
        project_dir=str(project_dir),
        artifacts=all_artifacts,
        package_path=str(package_dir) if package_dir else None,
        learning_revision_ids=learning_ids,
    )


def _predecessors(stage: StageName) -> tuple[StageName, ...]:
    from ai_video_factory.workflow.models import REQUIRED_PREDECESSORS

    return REQUIRED_PREDECESSORS[stage]


def _failed_result(
    request: ProductionRequest,
    stage: StageName,
    results: dict[StageName, StageResult],
    artifacts: dict[str, ArtifactRef],
    failure: StructuredError,
) -> ProductionResult:
    return ProductionResult(
        production_id=request.production_id,
        profile_id=request.profile_id,
        status="failed",
        final_stage=stage,
        project_dir=str(request.project_dir),
        artifacts=artifacts,
        failures=[failure],
    )


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_refs(path: Path) -> dict[StageName, ArtifactRef]:
    return {
        name: ArtifactRef.model_validate(ref)
        for name, ref in _load_json(path).items()
    }


def _reconcile(
    state_dir: Path,
    runs: RunStore,
    store: ProfileStore,
    request: ProductionRequest,
) -> None:
    """Replay persisted results whose observation was lost before SQLite commit."""
    run_ids = _load_json(state_dir / "run_ids.json")
    for stage in STAGE_ORDER:
        path = state_dir / f"{stage}_result.json"
        run_id = run_ids.get(stage)
        if not path.is_file() or not run_id:
            continue
        try:
            result = StageResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
            runs._load_run(str(run_id))  # verify the RunStore side still exists
        except Exception:  # noqa: BLE001 - reconciliation must never abort startup
            continue
        _record_observations(
            store, request, stage, str(run_id),
            [seed.model_dump() for seed in result.observations],
            result.effective_config, request.tools,
        )


def _record_observations(
    store: ProfileStore,
    request: ProductionRequest,
    stage: StageName,
    run_id: str,
    seeds: list[dict],
    effective_config: dict,
    tool_versions: dict[str, str],
) -> None:
    for seed in seeds:
        store.record_observation(
            Observation(
                observation_id=uuid4().hex,
                profile_id=request.profile_id,
                production_id=request.production_id,
                stage=stage,
                attempt=1,
                type=seed.get("type", "stage_result"),
                source=seed.get("source", "stage"),
                summary=str(seed.get("summary", "")),
                evidence_refs=list(seed.get("evidence_refs", [])),
                effective_config=dict(effective_config),
                tool_versions=dict(tool_versions),
                event_key=str(seed.get("event_key", f"{request.production_id}:{stage}:{run_id}")),
            )
        )


def _apply_learning(
    store: ProfileStore,
    context: StageContext,
    stage: StageName,
    production_id: str,
    reviewer: Callable,
    evaluator: object | None,
) -> list[str]:
    from ai_video_factory.profiles.learning import evaluate_and_apply, review_observations

    observations = store.list_observations(context.snapshot.profile_id, stage=stage)
    candidates = review_observations(context, observations, reviewer)
    activated: list[str] = []
    for candidate in candidates:
        result = evaluate_and_apply(
            context, candidate, evaluator, store,
            production_id=production_id,
        )
        if result.get("learning_id"):
            activated.append(str(result["learning_id"]))
    return activated
