"""FilmCraft MCP client behaviour (plan task 11)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_video_factory.integrations.filmcraft import (
    DEFAULT_TIMEBASE,
    FilmCraftConfig,
    FilmCraftClientError,
    FilmCraftMcpClient,
    McpTimeout,
    load_filmcraft_config,
    redact,
)
from ai_video_factory.preflight import check_filmcraft_bridge


class FakeTransport:
    def __init__(self, *, fail_next: str | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self.closed = False
        self.fail_next = fail_next

    def request(self, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        self.requests.append(payload)
        method = payload["method"]
        if self.fail_next == method:
            self.fail_next = None
            raise McpTimeout("tempo esgotado")
        if method == "initialize":
            result: dict[str, Any] = {
                "serverInfo": {"version": "0.1-alpha"},
                "timebaseTicksPerSecond": DEFAULT_TIMEBASE,
            }
        elif method == "tools/list":
            result = {"tools": [{"name": name} for name in (
                "inspect_project", "insert_item", "save_project", "export_project")]}
        elif method == "tools/call":
            name = payload["params"]["name"]
            if name == "insert_item":
                result = {"structuredContent": {"status": "applied", "state": {"item": "i1"}}}
            elif name == "inspect_project":
                result = {"structuredContent": {
                    "status": "applied",
                    "state": {"project_path": "p.fcproj", "items": [], "offline_media": []},
                }}
            else:
                result = {"isError": True, "content": [{"text": "token=abc123 falhou"}]}
        else:
            result = {}
        return {"jsonrpc": "2.0", "id": payload["id"], "result": result}

    def close(self) -> None:
        self.closed = True


def _client(transport: FakeTransport) -> FilmCraftMcpClient:
    return FilmCraftMcpClient(FilmCraftConfig(mode="bridge"), transport=transport)


def test_negotiation_exposes_real_catalog_and_timebase() -> None:
    transport = FakeTransport()
    client = _client(transport)
    capabilities = client.connect()
    assert capabilities.version == "0.1-alpha"
    assert "insert_item" in capabilities.commands
    assert capabilities.timebase_ticks_per_second == DEFAULT_TIMEBASE
    assert capabilities.mode == "bridge"
    assert [item["method"] for item in transport.requests] == ["initialize", "tools/list"]


def test_unavailable_command_and_structured_error() -> None:
    client = _client(FakeTransport())
    client.connect()
    rejected = client.execute("delete_everything", {})
    assert rejected.status == "rejected"
    assert rejected.error is not None and rejected.error.code == "command_unavailable"
    error = client.execute("save_project", {})
    assert error.status == "rejected"
    assert error.error is not None and "abc123" not in error.error.message


def test_mutation_timeout_requires_inspection() -> None:
    transport = FakeTransport(fail_next="tools/call")
    client = _client(transport)
    client.connect()
    result = client.execute("insert_item", {"shot_id": "sh1"})
    assert result.status == "indeterminate"
    assert result.requires_inspection is True


def test_inspect_returns_typed_snapshot() -> None:
    client = _client(FakeTransport())
    client.connect()
    snapshot = client.inspect()
    assert snapshot.project_path == "p.fcproj"
    assert snapshot.offline_media == []


def test_reconnect_and_close() -> None:
    first = FakeTransport()
    client = _client(first)
    client.connect()
    client.close()
    assert first.closed
    try:
        client.inspect()
    except FilmCraftClientError:
        pass
    else:
        raise AssertionError("closed client must require reconnect")
    second = FakeTransport()
    client._transport = second
    client.connect()
    assert client.inspect().project_path == "p.fcproj"
    client.close()
    assert second.closed


def test_config_example_has_no_secret_and_preflight_is_read_only(tmp_path: Path) -> None:
    example = Path("config/filmcraft.example.toml")
    text = example.read_text(encoding="utf-8")
    assert "FILMCRAFT_BRIDGE_SECRET" in text
    assert "command = \"\"" in text
    config = load_filmcraft_config(example)
    assert config is not None and config.mode == "bridge"
    assert check_filmcraft_bridge(tmp_path / "missing.toml").status == "warn"
    assert "<redacted>" in redact("password=abc123")
