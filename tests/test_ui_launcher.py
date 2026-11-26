"""Launcher, static build and tool diagnostics."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_video_factory.ui_backend.app import UiSettings, create_app
from ai_video_factory.ui_backend.session import BootstrapService
import ai_video_factory.ui_cli as ui_cli
from ai_video_factory.ui_cli import build_ui_parser, prepare_launch, require_ui_extra
from scripts.build_ui import build_ui


def test_ui_extra_missing_shows_clear_instruction(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_import() -> tuple[object, object]:
        raise ImportError("missing")

    monkeypatch.setattr(ui_cli, "import_ui_modules", fail_import)

    with pytest.raises(SystemExit) as error:
        require_ui_extra()

    assert "uv sync --extra ui" in str(error.value)


def test_port_in_use_does_not_kill_another_process(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    class BusySocket:
        def __enter__(self):
            raise OSError("address in use")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: BusySocket())

    with pytest.raises(SystemExit) as error:
        prepare_launch(Path.cwd(), port=8765)

    assert "8765" in str(error.value)


def test_parser_supports_no_browser_and_port() -> None:
    args = build_ui_parser().parse_args(["--no-browser", "--port", "9000"])

    assert args.no_browser is True
    assert args.port == 9000


def test_static_build_writes_manifest(tmp_path: Path) -> None:
    source = tmp_path / "dist"
    source.mkdir()
    (source / "index.html").write_text("<html></html>", encoding="utf-8")
    assets = source / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    target = tmp_path / "ui_static"

    manifest = build_ui(source, target)

    assert (target / "index.html").is_file()
    assert "app.js" in json.dumps(manifest)
    assert (target / "manifest.json").is_file()


def test_tools_do_not_run_checks_on_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_video_factory.ui_backend import domain

    calls: list[str] = []
    monkeypatch.setattr(domain, "check_tool", lambda tool_id: calls.append(tool_id))
    bootstrap = BootstrapService(tmp_path / "bootstrap.token")
    token = bootstrap.issue()
    app = create_app(UiSettings(project_root=tmp_path), bootstrap=bootstrap)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.post("/api/v1/session/bootstrap", json={"token": token}).status_code == 204
        response = client.get("/api/v1/tools")

    assert response.status_code == 200
    assert calls == []
    assert all("secret" not in item.get("id", "").lower() for item in response.json()["items"])


def test_tool_check_is_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_video_factory.ui_backend import domain

    monkeypatch.setattr(
        domain,
        "check_tool",
        lambda tool_id: {
            "id": tool_id,
            "state": "validated",
            "observed": "ffmpeg -version respondeu",
        },
    )
    bootstrap = BootstrapService(tmp_path / "bootstrap.token")
    token = bootstrap.issue()
    app = create_app(UiSettings(project_root=tmp_path), bootstrap=bootstrap)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.post("/api/v1/session/bootstrap", json={"token": token}).status_code == 204
        csrf = client.cookies.get("avf_session_csrf")
        response = client.post(
            "/api/v1/tools/ffmpeg/check",
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 200
    assert response.json()["state"] == "validated"
