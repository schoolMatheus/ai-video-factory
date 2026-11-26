"""Loopback-only test server with controlled seeds for Playwright E2E."""

from __future__ import annotations

import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from ai_video_factory.run_store import RunStore
from ai_video_factory.ui_backend.app import UiSettings, create_app
from ai_video_factory.ui_backend.session import BootstrapService

ROOT = Path(__file__).resolve().parents[1]
PORT = 8766


def build_test_app() -> FastAPI:
    temporary = Path(tempfile.mkdtemp(prefix="avf-e2e-"))
    data_root = temporary / "data"
    bootstrap = BootstrapService(data_root / "ui" / "bootstrap.token")
    settings = UiSettings(
        project_root=temporary,
        data_root=data_root,
        profiles_db=data_root / "profiles" / "profiles.sqlite3",
        static_dir=ROOT / "web" / "dist",
        port=PORT,
    )
    app = create_app(settings, bootstrap=bootstrap)

    @app.get("/__e2e/ping", include_in_schema=False)
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/__e2e/token", include_in_schema=False)
    def token() -> dict[str, str]:
        return {"token": bootstrap.issue()}

    @app.post("/__e2e/seed", include_in_schema=False)
    def seed() -> dict[str, str]:
        store = RunStore(temporary / "state", artifact_root=temporary / "runs")
        run = store.start("research", {"topic": "Episódio E2E"})
        store.event(run.run_id, "source_found", {"url": "https://example.test/fonte"})
        return {"production_id": run.run_id}

    @app.post("/__e2e/seed-profiles", include_in_schema=False)
    def seed_profiles() -> dict[str, str]:
        from ai_video_factory.profiles.models import Observation, ProfileSpec
        from ai_video_factory.profiles.store import ProfileStore

        db = data_root / "profiles" / "profiles.sqlite3"
        db.parent.mkdir(parents=True, exist_ok=True)
        store = ProfileStore(db)
        for identifier in ("canal-a", "canal-b"):
            try:
                store.create_profile(
                    ProfileSpec(
                        profile_id=identifier,
                        name=f"Canal {identifier}",
                        language="pt-BR",
                    )
                )
            except Exception:
                pass
        try:
            store.record_observation(
                Observation(
                    observation_id="e2e-observation",
                    profile_id="canal-a",
                    stage="script",
                    attempt=1,
                    type="user_feedback",
                    source="e2e",
                    summary="Abertura longa demais",
                    event_key="e2e:abertura",
                )
            )
        except Exception:
            pass
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    uvicorn.run(build_test_app(), host="127.0.0.1", port=PORT, log_level="warning")
