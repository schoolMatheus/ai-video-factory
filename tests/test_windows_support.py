"""Native startup and cross-process portability regressions."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_cli_help_starts_without_posix_dependencies():
    result = subprocess.run(
        [sys.executable, "-m", "ai_video_factory.cli", "--help"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "NO_COLOR": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert "video-pipeline" in result.stdout


def _try_lock(path: Path):
    return subprocess.run(
        [sys.executable, "-c", """
import sys
from pathlib import Path
from ai_video_factory.file_lock import exclusive_file_lock
try:
    with exclusive_file_lock(Path(sys.argv[1]), blocking=False):
        print('acquired')
except BlockingIOError:
    sys.exit(3)
""", str(path)],
        capture_output=True, text=True, timeout=15,
    )


def test_file_lock_excludes_another_process_and_releases_on_error(tmp_path):
    from ai_video_factory.file_lock import exclusive_file_lock

    path = tmp_path / "locks with spaces" / "render.lock"
    with pytest.raises(RuntimeError, match="render failed"):
        with exclusive_file_lock(path):
            contender = _try_lock(path)
            assert contender.returncode == 3, contender.stderr
            raise RuntimeError("render failed")
    retry = _try_lock(path)
    assert retry.returncode == 0, retry.stderr
    assert retry.stdout.strip() == "acquired"


def test_windows_browser_discovery_without_path_or_gui(monkeypatch, tmp_path):
    from ai_video_factory import platform_support, pipeline, video_pipeline

    browser = tmp_path / "Program Files" / "Google/Chrome/Application/chrome.exe"
    browser.parent.mkdir(parents=True)
    browser.write_bytes(b"browser")
    monkeypatch.setattr(platform_support, "WINDOWS", True)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.delenv("REMOTION_CHROME_EXECUTABLE", raising=False)
    monkeypatch.setattr(platform_support.shutil, "which", lambda _: None)
    assert pipeline._find_local_browser() == browser.resolve()
    assert video_pipeline._find_local_browser() == browser.resolve()


def test_windows_font_and_virtualenv_paths(monkeypatch, tmp_path):
    from ai_video_factory import platform_support

    monkeypatch.setattr(platform_support, "WINDOWS", True)
    monkeypatch.setenv("WINDIR", str(tmp_path / "Windows"))
    assert platform_support.venv_program(tmp_path / ".tts-venv", "piper") == (
        tmp_path / ".tts-venv/Scripts/piper.exe"
    )
    assert str(tmp_path / "Windows/Fonts/arialbd.ttf") in platform_support.font_candidates()


@pytest.mark.skipif(os.name != "nt", reason="Windows command shim resolution")
def test_doctor_resolves_npm_cmd_on_windows(monkeypatch, tmp_path):
    from ai_video_factory.doctor import _subprocess_runner

    tools = tmp_path / "tools with spaces"
    tools.mkdir()
    (tools / "npm.cmd").write_text("@echo off\necho 11.0.0\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ["PATH"])
    code, stdout, stderr = _subprocess_runner(("npm", "--version"))
    assert code == 0, stderr
    assert stdout.strip() == "11.0.0"


def test_windows_render_avoids_shell_shims_and_preserves_spaces(monkeypatch, tmp_path):
    from ai_video_factory import platform_support

    monkeypatch.setattr(platform_support, "WINDOWS", True)
    monkeypatch.setattr(platform_support.shutil, "which", lambda _: "C:/Program Files/nodejs/node.exe")
    fixture = tmp_path / "edit with & spaces.json"
    browser = tmp_path / "Program Files/chrome.exe"
    output = tmp_path / "output video.mp4"
    commands = platform_support.remotion_commands(tmp_path, fixture, output, browser, None)
    assert len(commands) == 2
    assert commands[0][0] == commands[1][0] == "C:/Program Files/nodejs/node.exe"
    assert commands[1][2:] == ("--props", str(fixture), str(output), "--browser-executable", str(browser))


def test_windows_relative_render_paths_survive_child_working_directory(monkeypatch, tmp_path):
    from ai_video_factory import platform_support

    monkeypatch.setattr(platform_support, "WINDOWS", True)
    monkeypatch.chdir(tmp_path)
    commands = platform_support.remotion_commands(
        Path("project"), Path("fixtures/edit.json"), Path("data/master.mp4"),
        Path("tools/chrome.exe"), None,
    )
    assert commands[0][1] == str(tmp_path / "project/remotion/node_modules/typescript/bin/tsc")
    assert commands[1][2:] == (
        "--props", str(tmp_path / "fixtures/edit.json"), str(tmp_path / "data/master.mp4"),
        "--browser-executable", str(tmp_path / "tools/chrome.exe"),
    )


@pytest.mark.parametrize("module_name", ["pipeline", "video_pipeline"])
def test_render_failure_preserves_utf8_diagnostic(module_name, tmp_path):
    from importlib import import_module

    module = import_module(f"ai_video_factory.{module_name}")
    with pytest.raises(module.PipelineCommandError, match="falha 🏭"):
        module._run_command(
            (sys.executable, "-c", "import sys; sys.stderr.buffer.write('falha \\U0001f3ed'.encode('utf-8')); sys.exit(1)"),
            cwd=tmp_path, name="renderer",
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows PE file version API")
def test_windows_executable_version_does_not_launch_the_program():
    from ai_video_factory.platform_support import windows_file_version

    version = windows_file_version(Path(sys.executable))
    assert version is not None
    assert version.startswith(f"{sys.version_info.major}.{sys.version_info.minor}.")
