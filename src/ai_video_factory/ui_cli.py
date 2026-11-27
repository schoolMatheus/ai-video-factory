"""Local launcher for the compiled dashboard (no browser Node process)."""

from __future__ import annotations

import argparse
import os
import socket
import webbrowser
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_ui_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Abre o painel local do AI Video Factory.")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    return parser


def import_ui_modules() -> tuple[object, object]:
    import fastapi
    import uvicorn

    return fastapi, uvicorn


def require_ui_extra() -> None:
    try:
        import_ui_modules()
    except ImportError as error:
        raise SystemExit(
            "A interface exige o extra ui. Instale com: uv sync --extra ui"
        ) from error


def prepare_launch(project_root: Path, *, port: int, host: str = "127.0.0.1"):  # type: ignore[no-untyped-def]
    from ai_video_factory.ui_backend.app import UiSettings

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, port))
    except OSError as error:
        raise SystemExit(
            f"A porta {port} já está em uso. Escolha outra com --port; "
            "nenhum processo foi encerrado."
        ) from error

    root = Path(project_root).resolve()
    data_root = root / "data"
    packaged = Path(__file__).resolve().parent / "ui_static"
    static_dir = packaged if (packaged / "index.html").is_file() else root / "web" / "dist"
    if not (static_dir / "index.html").is_file():
        static_dir = None
    profiles_db = data_root / "profiles" / "profiles.sqlite3"
    return UiSettings(
        project_root=root,
        data_root=data_root,
        control_db=data_root / "ui" / "control.sqlite3",
        # A clean install must be able to create the first profile: the store
        # creates the database on first use.
        profiles_db=profiles_db,
        static_dir=static_dir,
        bind_host=host,
        port=port,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_ui_parser().parse_args(argv)
    require_ui_extra()
    settings = prepare_launch(_PROJECT_ROOT, port=args.port, host=args.host)

    from ai_video_factory.ui_backend.app import create_app
    from ai_video_factory.ui_backend.session import BootstrapService

    data_root = Path(settings.data_root or Path(settings.project_root) / "data")
    bootstrap_token_path = data_root / "ui" / "bootstrap.token"
    token = BootstrapService(bootstrap_token_path).issue()
    os.environ["AVF_CONTROL_DB"] = str(settings.control_db)
    app = create_app(settings)
    url = f"http://{settings.bind_host}:{settings.port}/#token={token}"
    print("Abra o painel local neste endereço (token de uso único):")
    print(url)
    if not args.no_browser:
        webbrowser.open(url)
    import uvicorn

    uvicorn.run(app, host=settings.bind_host, port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
