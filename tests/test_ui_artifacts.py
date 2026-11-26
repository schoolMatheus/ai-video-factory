"""Artifact resolution, Range delivery and scoped uploads."""

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_video_factory.run_store import RunStore
from ai_video_factory.ui_backend.app import UiSettings, create_app
from ai_video_factory.ui_backend.artifacts import ArtifactService
from ai_video_factory.ui_backend.read_models import ProductionReadModels
from ai_video_factory.ui_backend.session import BootstrapService


@pytest.fixture
def layout(tmp_path: Path):
    root = tmp_path / "projeto com espaços"
    state_root = root / "state"
    artifact_root = root / "runs"
    store = RunStore(state_root, artifact_root=artifact_root)
    run = store.start("research", {"topic": "tema"})
    media = artifact_root / run.run_id / "clipe longo.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"0123456789ABCDEF")
    store.complete(run.run_id, {"video": str(media)}, expected_artifacts={"video": media})
    models = ProductionReadModels(state_root, artifact_root)
    service = ArtifactService(models, artifact_root)
    artifact_id = models.list_artifacts(run.run_id)[0].id
    return root, state_root, artifact_root, run, media, service, artifact_id


def test_resolve_keeps_id_and_hash(layout) -> None:
    _, _, _, run, media, service, artifact_id = layout

    resolved = service.resolve(artifact_id, production_id=run.run_id)

    assert resolved.path == media.resolve()
    assert resolved.sha256 == hashlib.sha256(media.read_bytes()).hexdigest()
    assert resolved.size_bytes == media.stat().st_size


def test_resolve_rejects_another_production(layout) -> None:
    from ai_video_factory.ui_backend.models import NotFoundError

    _, _, _, _, _, service, artifact_id = layout

    with pytest.raises(NotFoundError):
        service.resolve(artifact_id, production_id="0" * 32)


def test_symlink_outside_root_is_rejected(
    layout, make_symlink, tmp_path: Path
) -> None:
    from ai_video_factory.ui_backend.models import NotFoundError

    _, state_root, artifact_root, run, media, service, _ = layout
    outside = tmp_path / "fora.txt"
    outside.write_text("segredo", encoding="utf-8")
    link = media.parent / "link.mp4"
    make_symlink(link, outside)
    run_dir = state_root / "research" / run.run_id
    manifest_path = run_dir / "manifest.json"
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_integrity"]["video"]["path"] = (
        f"{run.run_id}/link.mp4"
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(NotFoundError):
        service.resolve(service.artifact_id(run.run_id, "video"), production_id=run.run_id)


def test_range_returns_partial_content(layout) -> None:
    root, _, _, run, _, _, artifact_id = layout
    bootstrap = BootstrapService(root / "data" / "ui" / "bootstrap.token")
    app = create_app(
        UiSettings(project_root=root, data_root=root / "data"), bootstrap=bootstrap
    )
    token = bootstrap.issue()
    with TestClient(app, base_url="http://127.0.0.1:8787") as client:
        assert client.post("/api/v1/session/bootstrap", json={"token": token}).status_code == 204
        response = client.get(
            f"/api/v1/artifacts/{artifact_id}/content",
            headers={"Range": "bytes=4-9"},
        )

    assert response.status_code == 206
    assert response.content == b"456789"
    assert response.headers["content-range"] == "bytes 4-9/16"
    assert response.headers["accept-ranges"] == "bytes"


def test_invalid_range_is_rejected(layout) -> None:
    from ai_video_factory.ui_backend.models import InvalidRequestError

    _, _, _, run, _, service, artifact_id = layout

    with pytest.raises(InvalidRequestError):
        service.parse_range("bytes=abc-def", 16)


def test_upload_records_hash_and_rejects_bad_type(layout) -> None:
    from ai_video_factory.ui_backend.models import InvalidRequestError

    root, _, _, run, _, service, _ = layout
    content = b"upload de imagem"
    upload = service.store_upload(
        run.run_id,
        filename="minha imagem.png",
        content=content,
        media_type="image/png",
        max_bytes=1024,
    )

    assert upload.name.endswith("minha_imagem.png")
    assert upload.sha256 == hashlib.sha256(content).hexdigest()
    assert upload.path.is_file()

    with pytest.raises(InvalidRequestError):
        service.store_upload(
            run.run_id,
            filename="malware.exe",
            content=b"x",
            media_type="application/octet-stream",
            max_bytes=1024,
        )


def test_interrupted_upload_removes_only_its_partial(layout) -> None:
    root, _, _, run, _, service, _ = layout
    target = service.upload_directory(run.run_id) / "parcial.tmp"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"partial")

    service.discard_partial(run.run_id, "parcial.tmp")

    assert not target.exists()
