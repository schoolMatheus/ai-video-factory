"""Contained artifact resolution, Range delivery and scoped uploads."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_video_factory.ui_backend.control_store import ControlStore
from ai_video_factory.ui_backend.models import InvalidRequestError, NotFoundError
from ai_video_factory.ui_backend.read_models import ProductionReadModels

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_ALLOWED_UPLOAD_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "video/mp4", "audio/wav", "audio/mpeg", "text/markdown"}
)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ResolvedArtifact:
    path: Path
    name: str
    media_type: str
    size_bytes: int
    sha256: str
    production_id: str


@dataclass(frozen=True)
class UploadRecord:
    id: str
    production_id: str
    name: str
    path: Path
    media_type: str
    size_bytes: int
    sha256: str


class ArtifactService:
    def __init__(self, read_models: ProductionReadModels, artifact_root: Path) -> None:
        self.read_models = read_models
        self.artifact_root = Path(artifact_root).resolve()
        self.store = ControlStore(read_models.state_root.parent / "data" / "ui" / "control.sqlite3")

    @staticmethod
    def artifact_id(production_id: str, key: str) -> str:
        return ProductionReadModels._artifact_id(production_id, key)  # noqa: SLF001

    def resolve(
        self, artifact_id: str, *, production_id: str | None = None
    ) -> ResolvedArtifact:
        found = self.read_models.find_artifact(artifact_id)
        if found is None:
            raise NotFoundError("Artefato não encontrado.")
        found_production, key, integrity = found
        if production_id is not None and found_production != production_id:
            raise NotFoundError("Artefato não pertence a esta produção.")

        candidate = self.artifact_root / integrity.path
        try:
            path = candidate.resolve()
            path.relative_to(self.artifact_root)
        except (ValueError, OSError) as error:
            raise NotFoundError("Artefato fora da raiz permitida.") from error
        if not path.is_file():
            raise NotFoundError("Artefato não está mais disponível.")
        return ResolvedArtifact(
            path=path,
            name=key if "." not in Path(integrity.path).name else Path(integrity.path).name,
            media_type=_media_type(integrity.path),
            size_bytes=path.stat().st_size,
            sha256=integrity.sha256,
            production_id=found_production,
        )

    @staticmethod
    def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
        if header is None:
            return None
        match = _RANGE.fullmatch(header.strip())
        if match is None:
            raise InvalidRequestError("Intervalo de bytes inválido.")
        start_text, end_text = match.groups()
        if not start_text and not end_text:
            raise InvalidRequestError("Intervalo de bytes inválido.")
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                raise InvalidRequestError("Intervalo de bytes inválido.")
            return max(0, size - suffix), size - 1
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
        if start > end or start >= size or start < 0:
            raise InvalidRequestError("Intervalo de bytes fora do arquivo.")
        return start, min(end, size - 1)

    def upload_directory(self, production_id: str) -> Path:
        return self.artifact_root / "uploads" / production_id

    def store_upload(
        self,
        production_id: str,
        *,
        filename: str,
        content: bytes,
        media_type: str,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> UploadRecord:
        if media_type not in _ALLOWED_UPLOAD_TYPES:
            raise InvalidRequestError("Tipo de arquivo não permitido.")
        if not content or len(content) > max_bytes:
            raise InvalidRequestError("Tamanho de arquivo inválido.")
        if not re.fullmatch(r"[0-9a-f]{32}", production_id):
            raise NotFoundError("Produção não encontrada.")

        safe = _SAFE_NAME.sub("_", Path(filename).name).strip("._")[:80] or "arquivo"
        upload_id = uuid.uuid4().hex
        directory = self.upload_directory(production_id)
        directory.mkdir(parents=True, exist_ok=True)
        partial = directory / f"{upload_id}.part"
        final = directory / f"{upload_id}_{safe}"
        try:
            partial.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            partial.replace(final)
        finally:
            if partial.exists():
                partial.unlink()
        with self.store._connect() as connection:  # noqa: SLF001
            connection.execute(
                """
                INSERT INTO uploads
                    (id, production_id, name, path, media_type, size_bytes, sha256, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    production_id,
                    safe,
                    str(final.relative_to(self.artifact_root)).replace("\\", "/"),
                    media_type,
                    len(content),
                    digest,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return UploadRecord(
            id=upload_id,
            production_id=production_id,
            name=safe,
            path=final,
            media_type=media_type,
            size_bytes=len(content),
            sha256=digest,
        )

    def discard_partial(self, production_id: str, name: str) -> None:
        if Path(name).name != name or name in {".", ".."}:
            raise InvalidRequestError("Nome de arquivo parcial inválido.")
        partial = self.upload_directory(production_id) / name
        if partial.is_file():
            partial.unlink()

    def list_uploads(self, production_id: str) -> list[UploadRecord]:
        with self.store._connect() as connection:  # noqa: SLF001
            rows = connection.execute(
                "SELECT * FROM uploads WHERE production_id = ? ORDER BY created_at",
                (production_id,),
            ).fetchall()
        return [
            UploadRecord(
                id=str(row["id"]),
                production_id=production_id,
                name=str(row["name"]),
                path=self.artifact_root / str(row["path"]),
                media_type=str(row["media_type"]),
                size_bytes=int(row["size_bytes"]),
                sha256=str(row["sha256"]),
            )
            for row in rows
        ]

    def control_db_path(self) -> Path:
        return Path(self.store.db_path)


def _media_type(path: str) -> str:
    suffix = Path(path).suffix.casefold()
    return {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".json": "application/json",
        ".md": "text/markdown",
    }.get(suffix, "application/octet-stream")
