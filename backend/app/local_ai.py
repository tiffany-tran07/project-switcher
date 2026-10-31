"""Local Ollama transport: no environment proxies, redirects, or non-loopback URLs."""

import json
from email.message import Message
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/v1/local-ai", tags=["local AI"])
MAX_RESPONSE_BYTES = 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> None:
        raise ValueError("Local Ollama redirects are disabled")


def local_endpoint() -> str:
    value = settings.ollama_base_url
    parsed = urlsplit(value)
    if (
        value != value.strip()
        or any(ord(char) < 32 for char in value)
        or parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Ollama requires a plain localhost HTTP base URL without credentials or paths"
        )
    if parsed.port is not None and parsed.port < 1:
        raise ValueError("Ollama port is invalid")
    return value.rstrip("/")


def ollama_json(
    path: str, payload: dict[str, object] | None = None, timeout: float = 20
) -> dict[str, Any]:
    if path not in {"/api/chat", "/api/tags"}:
        raise ValueError("Unsupported local Ollama operation")
    endpoint = urlsplit(local_endpoint())
    # Pin even the name "localhost" to numeric IPv4 loopback; never rely on DNS.
    address = "http://127.0.0.1" + (f":{endpoint.port}" if endpoint.port is not None else "")
    request = Request(
        address + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Local Ollama response exceeds the size limit")
    try:
        result = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise ValueError("Local Ollama returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("Local Ollama response must be an object")
    return result


class LocalAIConfig(BaseModel):
    endpoint: str | None
    model: str
    allowed: bool
    message: str


class LocalAICheck(BaseModel):
    runtime_available: bool
    model_available: bool | None
    message: str


@router.get("/config", response_model=LocalAIConfig)
def local_ai_config() -> LocalAIConfig:
    try:
        endpoint = local_endpoint()
    except ValueError:
        return LocalAIConfig(
            endpoint=None,
            model=settings.ollama_chat_model,
            allowed=False,
            message="Ollama URL is blocked. Use http://127.0.0.1:11434 or a localhost HTTP port.",
        )
    return LocalAIConfig(
        endpoint=endpoint,
        model=settings.ollama_chat_model,
        allowed=True,
        message="Local AI is optional. Proxy settings and redirects are disabled.",
    )


@router.post("/check", response_model=LocalAICheck)
def check_local_ai() -> LocalAICheck:
    try:
        result = ollama_json("/api/tags", timeout=3)
        models = result.get("models")
        if not isinstance(models, list):
            raise ValueError("Invalid model inventory")
        names = {
            item.get("name")
            for item in models
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
    except (OSError, ValueError, TypeError):
        return LocalAICheck(
            runtime_available=False,
            model_available=None,
            message="Local runtime is unavailable or blocked. Deterministic features still work.",
        )
    model = settings.ollama_chat_model
    available = model in names or (":" not in model and f"{model}:latest" in names)
    return LocalAICheck(
        runtime_available=True,
        model_available=available if model else None,
        message="Configured model is installed."
        if model and available
        else "Runtime is running, but the configured model is not installed."
        if model
        else "Runtime is running. Set OLLAMA_CHAT_MODEL in .env to enable model extraction.",
    )
