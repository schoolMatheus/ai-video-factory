"""Assembly plan math and editor-independent layout (plan task 12)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.workflow.models import (
    ArtifactRef,
    MediaBundle,
    NarrationBundle,
    ScriptBundle,
)
from ai_video_factory.workflow.planning import DEFAULT_TIMEBASE, build_assembly


def _bundles(tmp_path: Path, count: int, seconds: float, overlap: float = 0.0) -> tuple:
    media_file = tmp_path / "shot.mp4"
    media_file.write_bytes(b"video")
    media_ref = ArtifactRef.from_path(media_file, tmp_path, "video/mp4")
    scenes = []
    segments = []
    selections = []
    candidates = []
    for index in range(count):
        shot_id = f"sh{index}"
        scenes.append({
            "scene_id": f"s{index}", "title": "Cena", "narration_text": "fala",
            "estimated_seconds": seconds,
            "shots": [{
                "shot_id": shot_id, "visual": "v",
                "transition": "dissolve" if overlap else "cut",
                "overlap_seconds": overlap,
            }],
        })
        segments.append({
            "segment_id": f"n{index}", "scene_id": f"s{index}", "shot_id": shot_id,
            "text": "fala", "audio": media_ref.model_dump(),
            "start_seconds": index * seconds, "duration_seconds": seconds,
        })
        candidates.append({
            "candidate_id": f"m{index}", "scene_id": f"s{index}", "shot_id": shot_id,
            "license": "CC0", "file": media_ref.model_dump(),
        })
        selections.append({
            "scene_id": f"s{index}", "shot_id": shot_id, "candidate_id": f"m{index}",
            "file": media_ref.model_dump(), "source_in_seconds": 0.5,
        })
    script = ScriptBundle(
        title="T", language="pt-BR", estimated_duration_seconds=count * seconds,
        scenes=scenes,
    )
    narration = NarrationBundle(
        provider="p", voice="v", language="pt-BR",
        segments=segments, total_duration_seconds=count * seconds,
    )
    media = MediaBundle(candidates=candidates, selected=selections)
    return script, narration, media


def _snapshot(**settings: object) -> ProfileSpec:
    return ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
        "settings": settings,
    })


def test_real_narration_times_overlap_and_rational_ticks(tmp_path: Path) -> None:
    script, narration, media = _bundles(tmp_path, 2, 1.0, overlap=0.2)
    plan = build_assembly(script, narration, media, _snapshot())
    video = next(track for track in plan.tracks if track.kind == "video").items
    assert plan.width == 1920 and plan.height == 1080 and plan.fps == 30
    assert plan.timebase_ticks_per_second == DEFAULT_TIMEBASE
    assert video[0].duration_ticks == int(Fraction("1.0") * DEFAULT_TIMEBASE)
    assert video[0].source_in_ticks == int(Fraction("0.5") * DEFAULT_TIMEBASE)
    assert video[1].start_ticks == int(Fraction("0.8") * DEFAULT_TIMEBASE)
    assert video[1].overlap_ticks == int(Fraction("0.2") * DEFAULT_TIMEBASE)
    assert plan.plan_digest


def test_no_accumulated_float_drift(tmp_path: Path) -> None:
    script, narration, media = _bundles(tmp_path, 10, 0.1)
    plan = build_assembly(script, narration, media, _snapshot())
    video = next(track for track in plan.tracks if track.kind == "video").items
    assert video[-1].start_ticks == int(Fraction("0.9") * DEFAULT_TIMEBASE)
    assert all(item.duration_ticks == int(Fraction("0.1") * DEFAULT_TIMEBASE) for item in video)


def test_resolution_from_profile_without_legacy_crop(tmp_path: Path) -> None:
    script, narration, media = _bundles(tmp_path, 1, 1.0)
    plan = build_assembly(script, narration, media, _snapshot(**{
        "editing.width": 1920, "editing.height": 1080, "editing.fps": 30,
        "editing.postprocess_crop": False,
    }))
    assert (plan.width, plan.height) == (1920, 1080)
    assert not any("crop" in track.track_id for track in plan.tracks)
