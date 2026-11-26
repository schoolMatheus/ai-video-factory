"""Copy the Vite build into the Python package with an integrity manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def build_ui(source: Path, target: Path) -> dict[str, object]:
    source = Path(source).resolve()
    target = Path(target).resolve()
    if not (source / "index.html").is_file():
        raise FileNotFoundError(f"Build do frontend ausente em {source}")

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    files: dict[str, dict[str, object]] = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        files[relative] = {
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    manifest = {"schema_version": 1, "files": files}
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--source", type=Path, default=root / "web" / "dist")
    parser.add_argument(
        "--target", type=Path, default=root / "src" / "ai_video_factory" / "ui_static"
    )
    args = parser.parse_args()
    manifest = build_ui(args.source, args.target)
    print(f"UI copiada: {len(manifest['files'])} arquivos")


if __name__ == "__main__":
    main()
