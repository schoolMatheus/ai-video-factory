"""Cross-platform lock, executable and font boundary tests (plan task 1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ai_video_factory import platform_support
from ai_video_factory.platform_support import (
    exclusive_file_lock,
    resolve_font,
    resolve_venv_executable,
)


def test_exclusive_lock_blocks_a_second_holder(tmp_path: Path) -> None:
    lock_path = tmp_path / "production.lock"
    with exclusive_file_lock(lock_path):
        with pytest.raises(BlockingIOError):
            with exclusive_file_lock(lock_path, blocking=False):
                pass


def test_lock_is_released_after_an_error(tmp_path: Path) -> None:
    lock_path = tmp_path / "production.lock"
    with pytest.raises(RuntimeError, match="boom"):
        with exclusive_file_lock(lock_path):
            raise RuntimeError("boom")
    with exclusive_file_lock(lock_path, blocking=False):
        pass


def test_lock_file_survives_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "nested" / "production.lock"
    with exclusive_file_lock(lock_path):
        pass
    assert lock_path.is_file()


def test_venv_executable_uses_scripts_on_windows_and_bin_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform_support, "WINDOWS", True)
    assert resolve_venv_executable(tmp_path, "python") == tmp_path / "Scripts" / "python.exe"
    monkeypatch.setattr(platform_support, "WINDOWS", False)
    assert resolve_venv_executable(tmp_path, "ffmpeg") == tmp_path / "bin" / "ffmpeg"


def test_venv_executable_tolerates_spaces(tmp_path: Path) -> None:
    root = tmp_path / "venv with spaces"
    result = resolve_venv_executable(root, "piper")
    assert "venv with spaces" in str(result)
    assert result.name in {"piper.exe", "piper"}


def test_resolve_font_prefers_existing_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    font = tmp_path / "caption font.ttf"
    font.write_bytes(b"font")
    monkeypatch.setattr(platform_support, "font_candidates", lambda: (str(font),))
    assert resolve_font() == font


def test_resolve_font_returns_none_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform_support, "font_candidates", lambda: ())
    assert resolve_font() is None


def test_cli_imports_without_fcntl_on_windows() -> None:
    """Importing the CLI must not require a POSIX-only module."""
    code = (
        "import sys; sys.modules['fcntl'] = None; "
        "import ai_video_factory.cli; print('ok')"
    )
    from subprocess import run

    completed = run([sys.executable, "-c", code], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert "ok" in completed.stdout
