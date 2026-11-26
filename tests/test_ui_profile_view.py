from types import SimpleNamespace

from ai_video_factory.ui_backend.profile_adapter import _profile_view


def test_profile_view_expoe_nicho_do_snapshot():
    snapshot = SimpleNamespace(
        profile_id="canal-a",
        name="Canal A",
        revision=1,
        settings={},
        explicit_fields=[],
        niche="astronomia",
    )
    assert _profile_view(snapshot).niche == "astronomia"
