"""FilmCraft native-MCP client with typed capabilities and results.

Transport is injected so tests never launch an editor. The default stdio
transport speaks line-delimited JSON-RPC to the MCP server that ships with
FilmCraft; bridge secrets are inherited from the environment and redacted.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ai_video_factory.workflow.models import (
    EditorCapabilities,
    EditorCommandResult,
    EditorSnapshot,
    StructuredError,
)

DEFAULT_TIMEBASE = 254_016_000_000
_SECRET_RE = re.compile(r"(?i)\b(token|secret|password|api[_-]?key|credential)\b\s*[:=]\s*\S+")


class FilmCraftClientError(RuntimeError):
    """Base error for the FilmCraft adapter."""


class McpTimeout(FilmCraftClientError):
    """A request exceeded its deadline; a mutation may or may not have applied."""


class McpTransportError(FilmCraftClientError):
    """The transport failed or returned a malformed response."""


def redact(text: str) -> str:
    """Remove secrets from anything that could be logged or archived."""
    return _SECRET_RE.sub(r"\1=<redacted>", text)


@dataclass
class FilmCraftConfig:
    mode: str = "bridge"
    command: str = ""
    args: list[str] = field(default_factory=list)
    timeout_seconds: float = 30.0
    secret_env: str = "FILMCRAFT_BRIDGE_SECRET"
    commands: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FilmCraftConfig:
        filmcraft = payload.get("filmcraft", payload)
        if not isinstance(filmcraft, dict):
            raise FilmCraftClientError("filmcraft configuration must be a table")
        mode = str(filmcraft.get("mode", "bridge"))
        if mode not in {"bridge", "headless"}:
            raise FilmCraftClientError(f"unknown FilmCraft mode {mode!r}")
        timeout = float(filmcraft.get("timeout_seconds", 30.0))
        if timeout <= 0:
            raise FilmCraftClientError("timeout_seconds must be positive")
        return cls(
            mode=mode,
            command=str(filmcraft.get("command", "")),
            args=[str(item) for item in filmcraft.get("args", [])],
            timeout_seconds=timeout,
            secret_env=str(filmcraft.get("secret_env", "FILMCRAFT_BRIDGE_SECRET")),
            commands={str(key): str(value) for key, value in filmcraft.get("commands", {}).items()},
        )


def load_filmcraft_config(path: str | Path | None = None) -> FilmCraftConfig | None:
    """Read an example-free config; ``None`` means FilmCraft is not configured."""
    if path is None:
        path = Path("config") / "filmcraft.toml"
    path = Path(path)
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    return FilmCraftConfig.from_dict(payload)


class McpTransport(Protocol):
    def request(self, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]: ...

    def close(self) -> None: ...


class StdioMcpTransport:
    """Line-delimited JSON-RPC over the MCP server's stdin/stdout."""

    def __init__(self, command: str, args: list[str], *, env: dict[str, str] | None = None) -> None:
        if not command:
            raise FilmCraftClientError("FilmCraft MCP command is not configured")
        environment = dict(os.environ)
        environment.update(env or {})
        self._process = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        self._queue: queue.Queue[str] = queue.Queue()
        self._reader = threading.Thread(target=self._read_lines, daemon=True)
        self._reader.start()
        self._counter = 0

    def _read_lines(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._queue.put(line)
        self._queue.put("")

    def request(self, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        assert self._process.stdin is not None
        try:
            self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
        except OSError as error:
            raise McpTransportError(f"failed to send MCP request: {error}") from error
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpTimeout("MCP request timed out; project state is indeterminate")
            try:
                line = self._queue.get(timeout=remaining)
            except queue.Empty as error:
                raise McpTimeout("MCP request timed out; project state is indeterminate") from error
            if not line:
                raise McpTransportError("MCP server closed the connection")
            try:
                response = json.loads(line)
            except json.JSONDecodeError as error:
                raise McpTransportError("MCP server returned malformed JSON") from error
            if response.get("id") == payload.get("id"):
                return response

    def close(self) -> None:
        try:
            if self._process.stdin is not None:
                self._process.stdin.close()
            self._process.terminate()
        except OSError:
            pass
        finally:
            self._process.wait(timeout=5)


class FilmCraftMcpClient:
    """Small client that follows the MCP tools/call contract of FilmCraft."""

    def __init__(
        self,
        config: FilmCraftConfig,
        *,
        transport: McpTransport | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.config = config
        self._transport = transport
        self._env = env
        self._id = 0
        self._capabilities: EditorCapabilities | None = None
        self._connected = False

    def connect(self) -> EditorCapabilities:
        if self._transport is None:
            self._transport = StdioMcpTransport(
                self.config.command, self.config.args, env=self._env
            )
        result = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ai-video-factory", "version": "1"},
        })
        info = result.get("serverInfo", {}) if isinstance(result, dict) else {}
        version = str(info.get("version", "unknown"))
        catalog = self._send("tools/list", {})
        tools = catalog.get("tools", []) if isinstance(catalog, dict) else []
        commands = sorted(str(tool.get("name")) for tool in tools if isinstance(tool, dict))
        confirmed = {
            str(key): value for key, value in result.items()
            if key in {"timebaseTicksPerSecond", "modes", "bridge"}
        }
        self._capabilities = EditorCapabilities(
            version=version,
            mode=self.config.mode,
            commands=commands,
            timebase_ticks_per_second=int(confirmed.get("timebaseTicksPerSecond", DEFAULT_TIMEBASE)),
            confirmed=confirmed,
        )
        self._connected = True
        return self._capabilities

    def inspect(self) -> EditorSnapshot:
        capabilities = self._require_connection()
        result = self.execute(self._command("inspect", "inspect_project"), {})
        payload = result.state
        return EditorSnapshot(
            project_path=str(payload.get("project_path", "")),
            items=list(payload.get("items", [])),
            dirty=bool(payload.get("dirty", False)),
            offline_media=[str(item) for item in payload.get("offline_media", [])],
            raw_digest=str(payload.get("raw_digest", "")),
        )

    def execute(self, command_id: str, params: dict[str, Any]) -> EditorCommandResult:
        capabilities = self._require_connection()
        tool = self.config.commands.get(command_id, command_id)
        if tool not in capabilities.commands:
            return EditorCommandResult(
                command_id=command_id,
                status="rejected",
                error=StructuredError(
                    code="command_unavailable",
                    message=f"FilmCraft {capabilities.version} does not expose {tool!r}",
                ),
            )
        try:
            response = self._send("tools/call", {"name": tool, "arguments": params})
        except McpTimeout:
            return EditorCommandResult(command_id=command_id, status="indeterminate")
        except McpTransportError as error:
            return EditorCommandResult(
                command_id=command_id,
                status="rejected",
                error=StructuredError(code="transport_error", message=redact(str(error))),
            )
        if response.get("isError"):
            detail = _response_text(response)
            return EditorCommandResult(
                command_id=command_id,
                status="rejected",
                error=StructuredError(code="editor_error", message=redact(detail)),
            )
        payload = _response_payload(response)
        return EditorCommandResult(
            command_id=command_id,
            status=str(payload.get("status", "applied")),
            warnings=[str(item) for item in payload.get("warnings", [])],
            job_id=payload.get("job_id"),
            state=payload.get("state", {}) if isinstance(payload.get("state", {}), dict) else {},
        )

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self._connected = False

    def _require_connection(self) -> EditorCapabilities:
        if self._capabilities is None or not self._connected:
            raise FilmCraftClientError("client is not connected; call connect() first")
        return self._capabilities

    def _command(self, alias: str, default: str) -> str:
        return self.config.commands.get(alias, default)

    def _send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        assert self._transport is not None
        self._id += 1
        response = self._transport.request(
            {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params},
            timeout_seconds=self.config.timeout_seconds,
        )
        if not isinstance(response, dict):
            raise McpTransportError("MCP response is not an object")
        error = response.get("error")
        if error:
            message = str(error.get("message", "unknown MCP error"))
            raise McpTransportError(redact(message))
        result = response.get("result", {})
        return result if isinstance(result, dict) else {}


def _response_text(response: dict[str, Any]) -> str:
    parts = []
    for item in response.get("content", []):
        if isinstance(item, dict) and "text" in item:
            parts.append(str(item["text"]))
    return " | ".join(parts) or "editor reported an error"


def _response_payload(response: dict[str, Any]) -> dict[str, Any]:
    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    text = _response_text(response)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"state": {"raw": text}}
    return parsed if isinstance(parsed, dict) else {"state": {"raw": text}}
