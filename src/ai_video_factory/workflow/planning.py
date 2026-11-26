"""Editor-independent assembly planning from measured narration and shots."""

from __future__ import annotations

from fractions import Fraction

from ai_video_factory.profiles.models import ProfileSnapshot
from ai_video_factory.profiles.models import canonical_digest
from ai_video_factory.workflow.models import (
    AssemblyItem,
    AssemblyPlan,
    AssemblyTrack,
    MediaBundle,
    NarrationBundle,
    ScriptBundle,
)

DEFAULT_TIMEBASE = 254_016_000_000


def _ticks(seconds: float, timebase: int) -> int:
    """Exact decimal-to-tick conversion; no accumulated floating-point drift."""
    return int(Fraction(str(seconds)) * timebase)


def build_assembly(
    script: ScriptBundle,
    narration: NarrationBundle,
    media: MediaBundle,
    snapshot: ProfileSnapshot,
) -> AssemblyPlan:
    settings = snapshot.settings
    width = int(settings.get("editing.width", 1920))
    height = int(settings.get("editing.height", 1080))
    fps = int(settings.get("editing.fps", 30))
    timebase = int(settings.get("editing.timebase_ticks_per_second", DEFAULT_TIMEBASE))
    if width <= 0 or height <= 0 or fps <= 0 or timebase <= 0:
        raise ValueError("invalid resolution, fps or timebase in profile settings")

    selections = {item.shot_id: item for item in media.selected}
    segments = {segment.shot_id: segment for segment in narration.segments}
    video_items: list[AssemblyItem] = []
    narration_items: list[AssemblyItem] = []
    text_items: list[AssemblyItem] = []
    cursor = 0
    for scene in script.scenes:
        for shot in scene.shots:
            segment = segments.get(shot.shot_id)
            selection = selections.get(shot.shot_id)
            duration_seconds = segment.duration_seconds if segment else shot.target_seconds or 1.0
            duration_ticks = _ticks(duration_seconds, timebase)
            if duration_ticks <= 0:
                raise ValueError(f"shot {shot.shot_id} has no positive duration")
            overlap_ticks = _ticks(shot.overlap_seconds, timebase)
            video_items.append(AssemblyItem(
                item_id=f"video-{shot.shot_id}",
                scene_id=scene.scene_id,
                shot_id=shot.shot_id,
                start_ticks=cursor,
                duration_ticks=duration_ticks,
                source_in_ticks=_ticks(selection.source_in_seconds, timebase) if selection else 0,
                source_duration_ticks=_ticks(selection.source_duration_seconds, timebase) if selection and selection.source_duration_seconds else duration_ticks,
                overlap_ticks=overlap_ticks,
                media_ref=selection.file if selection else None,
            ))
            if segment is not None:
                narration_items.append(AssemblyItem(
                    item_id=f"narration-{segment.segment_id}",
                    scene_id=scene.scene_id,
                    shot_id=shot.shot_id,
                    start_ticks=_ticks(segment.start_seconds, timebase),
                    duration_ticks=_ticks(segment.duration_seconds, timebase),
                    source_in_ticks=0,
                    media_ref=segment.audio,
                ))
            if shot.on_screen_text:
                text_items.append(AssemblyItem(
                    item_id=f"text-{shot.shot_id}",
                    scene_id=scene.scene_id,
                    shot_id=shot.shot_id,
                    start_ticks=cursor,
                    duration_ticks=duration_ticks,
                    source_in_ticks=0,
                    text=shot.on_screen_text,
                ))
            cursor += duration_ticks - min(overlap_ticks, duration_ticks)

    tracks = [
        AssemblyTrack(track_id="video", kind="video", items=video_items),
        AssemblyTrack(track_id="narration", kind="narration", items=narration_items),
        AssemblyTrack(track_id="text", kind="text", items=text_items),
        AssemblyTrack(track_id="caption", kind="caption", items=[]),
        AssemblyTrack(track_id="music", kind="music", items=[]),
    ]
    plan = AssemblyPlan(
        width=width,
        height=height,
        fps=fps,
        timebase_ticks_per_second=timebase,
        tracks=tracks,
        audio_intent=str(settings.get("editing.audio_intent", "narration only; no music mixed in this stage")),
        plan_digest="pending",
    )
    payload = plan.model_dump()
    payload["plan_digest"] = ""
    return plan.model_copy(update={"plan_digest": canonical_digest(payload)})
