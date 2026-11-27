"""Multi-shot scene timing must follow measured audio, not a single fallback."""

from __future__ import annotations

from fractions import Fraction

from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.workflow.models import (
    ArtifactRef,
    MediaBundle,
    NarrationBundle,
    ScriptBundle,
)
from ai_video_factory.workflow.planning import DEFAULT_TIMEBASE, build_assembly


def _snapshot(tmp_path):
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    return store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
        "settings": {"editing.width": 1920, "editing.height": 1080, "editing.fps": 30},
    }))


def _bundles(tmp_path):
    script = ScriptBundle(
        title="Episódio", language="pt-BR", estimated_duration_seconds=15.0,
        scenes=[{
            "scene_id": "s1", "title": "Cena longa", "narration_text": "Fala longa.",
            "estimated_seconds": 15.0,
            "pauses": [{"after_shot_id": "sh1", "seconds": 0.5},
                       {"after_shot_id": "sh2", "seconds": 1.0}],
            "shots": [
                {"shot_id": "sh1", "visual": "abertura", "target_seconds": 3.0,
                 "on_screen_text": "Título", "overlap_seconds": 0.2},
                {"shot_id": "sh2", "visual": "detalhe", "target_seconds": 4.0},
                {"shot_id": "sh3", "visual": "fechamento", "target_seconds": 5.0},
            ],
        }],
    )
    refs = []
    segments = []
    for index, seconds in enumerate((2.0, 3.0, 5.0), start=1):
        path = tmp_path / f"seg{index}.wav"
        path.write_bytes(b"RIFF")
        ref = ArtifactRef.from_path(path, tmp_path, "audio/wav")
        refs.append(ref)
        segments.append({
            "segment_id": f"n{index}", "scene_id": "s1", "shot_id": f"sh{index}",
            "text": f"Fala {index}", "audio": ref.model_dump(),
            "start_seconds": sum((2.0, 3.0, 5.0)[:index - 1]) + (0.5 if index > 1 else 0)
            + (1.0 if index > 2 else 0),
            "duration_seconds": seconds,
        })
    narration = NarrationBundle(
        provider="fake", voice="v", language="pt-BR", segments=segments,
        spoken_text="Fala 1 Fala 2 Fala 3", total_duration_seconds=11.5,
    )
    selected = []
    for index in (1, 2, 3):
        path = tmp_path / f"shot{index}.mp4"
        path.write_bytes(b"media")
        selected.append({
            "scene_id": "s1", "shot_id": f"sh{index}", "candidate_id": f"m{index}",
            "file": ArtifactRef.from_path(path, tmp_path, "video/mp4").model_dump(),
        })
    media = MediaBundle(
        candidates=[{
            "candidate_id": f"m{i}", "scene_id": "s1", "shot_id": f"sh{i}",
            "license": "CC0", "file": item["file"],
        } for i, item in enumerate(selected, start=1)],
        selected=selected,
    )
    return script, narration, media


def test_shots_are_distributed_within_measured_audio_and_pauses(tmp_path) -> None:
    script, narration, media = _bundles(tmp_path)
    plan = build_assembly(script, narration, media, _snapshot(tmp_path))

    video = next(track for track in plan.tracks if track.kind == "video")
    narration_track = next(track for track in plan.tracks if track.kind == "narration")
    text_track = next(track for track in plan.tracks if track.kind == "text")
    assert [item.shot_id for item in video.items] == ["sh1", "sh2", "sh3"]
    assert len(narration_track.items) == 3
    assert len(text_track.items) == 1
    assert all(item.duration_ticks > 0 for item in video.items)
    assert video.items[0].start_ticks == 0
    for previous, current in zip(video.items, video.items[1:]):
        assert current.start_ticks >= previous.start_ticks
    audio_end = max(
        int((Fraction(str(item.start_seconds or 0)) + Fraction(str(item.duration_seconds)))
            * DEFAULT_TIMEBASE)
        for item in narration.segments
    )
    video_end = max(item.start_ticks + item.duration_ticks for item in video.items)
    # Pauses belong to the scene but must not be added twice on top of speech.
    tolerance = int(Fraction("1.5") * DEFAULT_TIMEBASE)
    assert abs(video_end - audio_end) <= tolerance


def test_overlap_never_exceeds_the_shot_itself(tmp_path) -> None:
    script, narration, media = _bundles(tmp_path)
    plan = build_assembly(script, narration, media, _snapshot(tmp_path))
    video = next(track for track in plan.tracks if track.kind == "video")
    for item in video.items:
        assert 0 <= item.overlap_ticks < item.duration_ticks
