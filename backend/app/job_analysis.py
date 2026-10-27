"""Optional local-only Ollama extraction; deterministic extraction lives in jobs.py."""

import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.schemas import RequirementData


class ExtractedItem(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    supporting_span: str = Field(min_length=2, max_length=1000)
    kind: str
    priority: str


class ExtractedResponse(BaseModel):
    requirements: list[ExtractedItem]


def extract_with_ollama(description: str) -> list[RequirementData]:
    endpoint = urlparse(settings.ollama_base_url)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Ollama must use a localhost HTTP endpoint")
    if not settings.ollama_chat_model:
        raise ValueError("Set OLLAMA_CHAT_MODEL to an installed local model")
    payload = {
        "model": settings.ollama_chat_model,
        "stream": False,
        "format": ExtractedResponse.model_json_schema(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract stated job requirements. Give each exact supporting_span "
                    "from the posting, text, kind (skill, tool, responsibility, experience, "
                    "education, certification), and priority (required, preferred, unclear). "
                    "Do not infer unstated requirements. Return JSON only."
                ),
            },
            {"role": "user", "content": description},
        ],
    }
    request = Request(
        f"{settings.ollama_base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:  # noqa: S310 - localhost URL validated above
        body = json.load(response)
    parsed = ExtractedResponse.model_validate_json(body["message"]["content"])
    requirements: list[RequirementData] = []
    for item in parsed.requirements[:100]:
        if (
            item.supporting_span not in description
            or item.text.casefold() not in item.supporting_span.casefold()
        ):
            continue
        try:
            requirements.append(
                RequirementData(
                    text=item.text,
                    supporting_span=item.supporting_span,
                    normalized_term=item.text.casefold()[:200],
                    kind=item.kind,
                    priority=item.priority,
                )
            )
        except ValidationError:
            continue
    return requirements
