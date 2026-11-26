"""Platform-specific locations for locally installed tools and fonts.

This module is the single public boundary for platform-sensitive paths and
locks. Consumers must not import ``fcntl`` or ``msvcrt`` directly.
"""

import os
from pathlib import Path
import shutil

from ai_video_factory.file_lock import exclusive_file_lock

WINDOWS = os.name == "nt"

__all__ = [
    "WINDOWS",
    "browser_candidates",
    "exclusive_file_lock",
    "font_candidates",
    "remotion_commands",
    "resolve_font",
    "resolve_venv_executable",
    "venv_program",
    "windows_file_version",
]


def venv_program(root: Path, name: str) -> Path:
    return Path(root) / ("Scripts" if WINDOWS else "bin") / (f"{name}.exe" if WINDOWS else name)


def resolve_venv_executable(venv: Path, name: str) -> Path:
    """Resolve a program inside a virtual environment on the current platform."""
    return venv_program(venv, name)


def resolve_font() -> Path | None:
    """First available caption font, or ``None`` when the host has none."""
    for candidate in font_candidates():
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def font_candidates() -> tuple[str, ...]:
    paths: list[str] = []
    if WINDOWS:
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        paths.extend(str(fonts / name) for name in ("arialbd.ttf", "segoeuib.ttf", "arial.ttf", "segoeui.ttf"))
    paths.extend((
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ))
    return tuple(paths)


def browser_candidates() -> list[Path]:
    paths = []
    names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
    if WINDOWS:
        names.extend(("chrome.exe", "msedge.exe"))
    for name in names:
        located = shutil.which(name)
        if located:
            paths.append(Path(located))
    if WINDOWS:
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if root:
                paths.extend((
                    Path(root) / "Google/Chrome/Application/chrome.exe",
                    Path(root) / "Microsoft/Edge/Application/msedge.exe",
                ))
    return paths


def remotion_commands(
    root: Path, fixture: Path, output: Path, browser: Path, npm: Path | None,
) -> list[tuple[str, ...]]:
    """Bypass Windows npm/cmd argument rewriting for paths and JSON props."""
    directory = Path(root) / "remotion"
    if WINDOWS:
        directory = directory.resolve()
        fixture, output, browser = (Path(path).resolve() for path in (fixture, output, browser))
        node = shutil.which("node") or "node"
        return [
            (node, str(directory / "node_modules/typescript/bin/tsc"), "-p", "tsconfig.json"),
            (node, str(directory / "dist/render.js"), "--props", str(fixture), str(output),
             "--browser-executable", str(browser)),
        ]
    return [(str(npm) if npm else "npm", "run", "render", "--", "--props",
             os.path.relpath(fixture, directory), os.path.relpath(output, directory),
             "--browser-executable", str(browser))]


def windows_file_version(path: Path) -> str | None:
    """Read PE version metadata without launching a browser window."""
    if not WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes

    version = ctypes.WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD))
    version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    version.GetFileVersionInfoW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
    version.GetFileVersionInfoW.restype = wintypes.BOOL
    if not version.GetFileVersionInfoW(str(path), 0, size, data):
        return None
    pointer = ctypes.c_void_p()
    length = wintypes.UINT()
    version.VerQueryValueW.argtypes = (
        ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT),
    )
    version.VerQueryValueW.restype = wintypes.BOOL
    if not version.VerQueryValueW(data, "\\", ctypes.byref(pointer), ctypes.byref(length)):
        return None
    # VS_FIXEDFILEINFO: signature, structure version, file version MS/LS, ...
    if length.value < 16:
        return None
    fixed = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD * 4)).contents
    if fixed[0] != 0xFEEF04BD:
        return None
    return f"{fixed[2] >> 16}.{fixed[2] & 0xffff}.{fixed[3] >> 16}.{fixed[3] & 0xffff}"
