import json
import socket
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import local_ai
from app.config import settings

pytest_plugins = ("test_library",)


@contextmanager
def server(
    body: bytes, location: str | None = None
) -> Generator[tuple[str, list[tuple[str, str, bytes]]], None, None]:
    calls: list[tuple[str, str, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self) -> None:
            data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append((self.command, self.path, data))
            self.send_response(302 if location else 200)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            self.respond()

        def do_GET(self) -> None:
            self.respond()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}", calls
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=3)


def test_local_requests_bypass_environment_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    with server(b'{"models": []}') as (endpoint, calls), server(b"{}") as (proxy, proxy_calls):
        monkeypatch.setattr(settings, "ollama_base_url", endpoint)
        monkeypatch.setenv("HTTP_PROXY", proxy)
        monkeypatch.setenv("http_proxy", proxy)
        monkeypatch.setenv("ALL_PROXY", proxy)
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setenv("no_proxy", "")
        assert local_ai.ollama_json("/api/tags") == {"models": []}
        assert local_ai.ollama_json("/api/chat", {"message": "Private fixture text"}) == {
            "models": []
        }
        assert proxy_calls == []
        assert calls[0] == ("GET", "/api/tags", b"")
        assert calls[1][0:2] == ("POST", "/api/chat")
        assert json.loads(calls[1][2]) == {"message": "Private fixture text"}


def test_localhost_is_pinned_to_numeric_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    original = socket.getaddrinfo

    def numeric_only(host: str, *args: Any, **kwargs: Any) -> Any:
        assert host == "127.0.0.1"
        return original(host, *args, **kwargs)

    with server(b'{"models": []}') as (endpoint, calls):
        monkeypatch.setattr(settings, "ollama_base_url", endpoint.replace("127.0.0.1", "localhost"))
        monkeypatch.setattr(socket, "getaddrinfo", numeric_only)
        assert local_ai.ollama_json("/api/tags") == {"models": []}
        assert len(calls) == 1


def test_local_redirects_are_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    with server(b"{}") as (target, target_calls):
        with server(b"{}", location=f"{target}/api/chat") as (endpoint, calls):
            monkeypatch.setattr(settings, "ollama_base_url", endpoint)
            with pytest.raises(ValueError, match="redirects are disabled"):
                local_ai.ollama_json("/api/chat", {"message": "Private fixture text"})
            assert len(calls) == 1
            assert target_calls == []


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://localhost:11434",
        "http://example.invalid:11434",
        "http://localhost.evil.invalid",
        "http://192.168.1.2:11434",
        "http://user:secret@localhost:11434",
        "http://localhost:11434/api",
        "http://localhost:11434?secret=1",
        "http://localhost:11434#fragment",
        " http://localhost:11434",
        "http://localhost:99999",
        "http://localhost:0",
        "http://local\thost:11434",
    ],
)
def test_nonlocal_or_ambiguous_endpoints_are_blocked(
    monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    monkeypatch.setattr(settings, "ollama_base_url", endpoint)
    monkeypatch.setattr(
        local_ai, "build_opener", lambda *_: pytest.fail("Blocked URL opened a network connection")
    )
    with pytest.raises(ValueError):
        local_ai.ollama_json("/api/chat", {"message": "Private fixture text"})
    config = local_ai.local_ai_config()
    assert config.allowed is False
    assert config.endpoint is None
    assert "secret" not in config.message


@pytest.mark.parametrize("body", [b"not JSON", b"[]", b"null"])
def test_invalid_json_is_rejected(monkeypatch: pytest.MonkeyPatch, body: bytes) -> None:
    with server(body) as (endpoint, _):
        monkeypatch.setattr(settings, "ollama_base_url", endpoint)
        with pytest.raises(ValueError):
            local_ai.ollama_json("/api/tags")


def test_response_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    with server(b'{"large": "1234567890"}') as (endpoint, _):
        monkeypatch.setattr(settings, "ollama_base_url", endpoint)
        monkeypatch.setattr(local_ai, "MAX_RESPONSE_BYTES", 10)
        with pytest.raises(ValueError, match="size limit"):
            local_ai.ollama_json("/api/tags")


def test_configuration_is_read_only_and_diagnostics_send_no_career_data(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with server(b'{"models": [{"name": "fixture:latest"}]}') as (endpoint, calls):
        monkeypatch.setattr(settings, "ollama_base_url", endpoint)
        monkeypatch.setattr(settings, "ollama_chat_model", "fixture")
        config = client.get("/api/v1/local-ai/config").json()
        assert config["endpoint"] == endpoint
        assert config["model"] == "fixture"
        assert calls == []
        result = client.post("/api/v1/local-ai/check").json()
        assert result["runtime_available"] is True
        assert result["model_available"] is True
        assert calls == [("GET", "/api/tags", b"")]
        monkeypatch.setattr(settings, "ollama_chat_model", "missing")
        assert client.post("/api/v1/local-ai/check").json()["model_available"] is False
        monkeypatch.setattr(settings, "ollama_chat_model", "")
        assert client.post("/api/v1/local-ai/check").json()["model_available"] is None


def test_failed_check_still_keeps_offline_workflow_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def offline(*_: object, **__: object) -> dict[str, object]:
        raise OSError("Private exception details must not be returned")

    monkeypatch.setattr(local_ai, "ollama_json", offline)
    result = client.post("/api/v1/local-ai/check")
    assert result.status_code == 200
    assert result.json()["runtime_available"] is False
    assert "Private exception" not in result.json()["message"]
    assert client.get("/api/v1/jobs").status_code == 200
