"""Stage 5 — FilmCraft assembly with reconciliation and observable checkpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from ai_video_factory.profiles.models import canonical_digest
from ai_video_factory.workflow.contracts import FilmCraftClient, StageContext, StageInputs
from ai_video_factory.workflow.models import (
    BUNDLE_FILENAMES,
    ArtifactRef,
    EditingBundle,
    EditorCommandResult,
    EditorSnapshot,
    ObservationSeed,
    StageResult,
)
from ai_video_factory.workflow.planning import build_assembly


class EditingStageError(RuntimeError):
    """The editor state cannot be trusted as a final delivery."""


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
    result = json.loads(completed.stdout or "{}")
    stream = next((item for item in result.get("streams", []) if item.get("width")), {})
    return {
        "width": stream.get("width"),
        "height": stream.get("height"),
        "duration": float((result.get("format") or {}).get("duration", 0) or 0),
    }


class EditingStage:
    external = True

    def __init__(self, client: FilmCraftClient, *, probe: Probe | None = None) -> None:
        self.client = client
        self.probe = probe or _probe_with_ffprobe
        self._last_export_state: dict[str, Any] = {}

    def run(self, context: StageContext, inputs: StageInputs) -> StageResult:
        artifacts_dir = context.artifacts_dir
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        capabilities = self.client.connect()
        plan = build_assembly(inputs.script, inputs.narration, inputs.media, context.snapshot)
        plan_path = artifacts_dir / "assembly_plan.json"
        plan.save(plan_path)
        commands = self._commands(capabilities.commands)

        previous_path = artifacts_dir / "previous_snapshot.json"
        previous = self._load_snapshot(previous_path)
        observed = self.client.inspect()
        item_map = self._item_map(observed)
        warnings: list[str] = []
        observations: list[ObservationSeed] = []
        if previous is not None and _snapshot_digest(previous) != _snapshot_digest(observed):
            warnings.append("projeto alterado manualmente desde a última inspeção; alterações preservadas")
            observations.append(ObservationSeed(
                type="manual_edit_observed", source="filmcraft",
                summary="estado observado difere do checkpoint anterior; intenção não inferida",
                evidence_refs=[previous_path.as_posix()],
                event_key=f"{context.request.production_id}:editing:manual:{_snapshot_digest(observed)[:12]}",
            ))

        log_path = artifacts_dir / "operations.jsonl"
        for track in plan.tracks:
            if track.kind != "video":
                continue
            for item in track.items:
                if item.shot_id in item_map:
                    continue  # reconciled from an observed project after a crash
                params = {
                    "shot_id": item.shot_id,
                    "scene_id": item.scene_id,
                    "item_id": item.item_id,
                    "start_ticks": item.start_ticks,
                    "duration_ticks": item.duration_ticks,
                    "source_in_ticks": item.source_in_ticks,
                    "overlap_ticks": item.overlap_ticks,
                    "timebase_ticks_per_second": plan.timebase_ticks_per_second,
                    "media_path": item.media_ref.path if item.media_ref else None,
                }
                result = self.client.execute(commands.get("insert", "insert_item"), params)
                self._log(log_path, commands.get("insert", "insert_item"), params, result)
                if result.requires_inspection:
                    observed = self.client.inspect()
                    item_map = self._item_map(observed)
                    if item.shot_id in item_map:
                        continue
                    raise EditingStageError(
                        f"mutation for {item.shot_id} is indeterminate and was not observed; refusing blind retry"
                    )
                if result.status == "rejected":
                    raise EditingStageError(self._error_text(result, commands["insert"]))
                item_map[item.shot_id] = str(result.state.get("item_id", item.item_id))

        media_refs = [item.media_ref for item in plan.tracks[0].items if item.media_ref]
        media_refs += [item.media_ref for track in plan.tracks if track.kind == "narration" for item in track.items if item.media_ref]
        manifest_path = artifacts_dir / "media_manifest.json"
        manifest_path.write_text(json.dumps(
            [ref.model_dump() for ref in media_refs], indent=2, ensure_ascii=False
        ), encoding="utf-8")
        missing = [ref.path for ref in media_refs if not ref.resolve(context.project_dir).is_file()]
        if missing:
            warnings.append(f"mídia ausente no disco: {', '.join(missing)}")

        for alias in ("save", "preview", "export"):
            command = commands.get(alias)
            if command is None:
                continue
            params = {"project_path": observed.project_path or f"{context.project_dir}/project.fcproj"}
            if alias == "export":
                params["width"] = plan.width
                params["height"] = plan.height
                params["output"] = str(artifacts_dir / "master.mp4")
            result = self.client.execute(command, params)
            self._log(log_path, command, params, result)
            warnings.extend(result.warnings)
            if result.requires_inspection:
                observed = self.client.inspect()
            if result.status == "rejected":
                raise EditingStageError(self._error_text(result, command))

        final_snapshot = self.client.inspect()
        if final_snapshot.offline_media:
            raise EditingStageError(
                "export finished with offline media; not a valid final delivery: "
                + ", ".join(final_snapshot.offline_media)
            )
        _save_snapshot(previous_path, final_snapshot)
        export_state = self._last_export_state or {}
        output_value = export_state.get("output") or export_state.get("master_path")
        output_path = Path(str(output_value)) if output_value else artifacts_dir / "master.mp4"
        if not output_path.is_file():
            raise EditingStageError(f"export did not produce an inspectable file at {output_path}")
        probe = self.probe(output_path)
        if probe.get("width") != plan.width or probe.get("height") != plan.height:
            warnings.append(
                f"resolução inspecionada {probe.get('width')}x{probe.get('height')} "
                f"differ da planejada {plan.width}x{plan.height}"
            )
        observed_artifacts = {
            "bundle": ArtifactRef.from_path(
                _save_bundle(context, capabilities.version, commands, item_map, plan, final_snapshot,
                             output_path, manifest_path, warnings, artifacts_dir),
                context.project_dir, "application/json",
            ),
            "plan": ArtifactRef.from_path(plan_path, context.project_dir, "application/json"),
            "master": ArtifactRef.from_path(output_path, context.project_dir, "video/mp4"),
            "manifest": ArtifactRef.from_path(manifest_path, context.project_dir, "application/json"),
            "log": ArtifactRef.from_path(log_path, context.project_dir, "text/plain"),
        }
        return StageResult(
            stage=context.stage,
            attempt=context.attempt,
            artifacts=observed_artifacts,
            observations=observations,
            effective_config=dict(context.effective_settings),
        )

    @staticmethod
    def _commands(available: list[str]) -> dict[str, str]:
        candidates = {
            "insert": ("insert_item", "insert_clip", "add_item"),
            "save": ("save_project", "project.save"),
            "preview": ("render_preview", "preview"),
            "export": ("export_project", "export"),
            "inspect": ("inspect_project", "get_project"),
        }
        found: dict[str, str] = {}
        for alias, options in candidates.items():
            match = next((option for option in options if option in available), None)
            if match is not None:
                found[alias] = match
        return found

    @staticmethod
    def _item_map(snapshot: EditorSnapshot) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in snapshot.items:
            shot_id = item.get("shot_id")
            item_id = item.get("item_id") or item.get("id")
            if shot_id and item_id:
                result[str(shot_id)] = str(item_id)
        return result

    @staticmethod
    def _load_snapshot(path: Path) -> EditorSnapshot | None:
        if not path.is_file():
            return None
        return EditorSnapshot.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def _log(self, path: Path, command: str, params: dict[str, Any], result: EditorCommandResult) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "command": command, "params": params, "status": result.status,
                "warnings": result.warnings,
            }, ensure_ascii=False) + "\n")
        if result.status == "applied" and command in {"export_project", "export"}:
            self._last_export_state = dict(result.state)

    @staticmethod
    def _error_text(result: EditorCommandResult, command: str) -> str:
        if result.error is not None:
            return f"editor command {command} failed: {result.error.message}"
        return f"editor command {command} was not applied ({result.status})"


def _snapshot_digest(snapshot: EditorSnapshot) -> str:
    return canonical_digest(snapshot.model_dump())


def _save_snapshot(path: Path, snapshot: EditorSnapshot) -> None:
    path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def _save_bundle(
    context: StageContext,
    version: str,
    commands: Mapping[str, str],
    item_map: dict[str, str],
    plan: Any,
    snapshot: EditorSnapshot,
    master: Path,
    manifest: Path,
    warnings: list[str],
    artifacts_dir: Path,
) -> Path:
    bundle = EditingBundle(
        filmcraft_version=version,
        mode=str(context.setting("editing.mode", "bridge")),
        project_path=snapshot.project_path or str(context.project_dir / "project.fcproj"),
        item_map=dict(item_map),
        applied_plan_digest=plan.plan_digest,
        observed_state=snapshot.model_dump(),
        previews=[],
        master=ArtifactRef.from_path(master, context.project_dir, "video/mp4"),
        media_manifest=ArtifactRef.from_path(manifest, context.project_dir, "application/json"),
        warnings=list(dict.fromkeys(warnings)),
    )
    path = artifacts_dir / BUNDLE_FILENAMES["editing"]
    bundle.save(path)
    return path
