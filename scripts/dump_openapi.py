"""Dump the local API OpenAPI schema without credentials, workers or network."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from ai_video_factory.ui_backend.app import UiSettings, create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "web" / "openapi.json",
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        app = create_app(
            UiSettings(
                project_root=root,
                data_root=root / "data",
                static_dir=None,
            )
        )
        schema = app.openapi()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
