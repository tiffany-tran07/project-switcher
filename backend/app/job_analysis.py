"""Optional local-only Ollama extraction; deterministic extraction lives in jobs.py."""

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.local_ai import ollama_json
from app.schemas import RequirementData


class ExtractedItem(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    supporting_span: str = Field(min_length=2, max_length=1000)
    kind: str
    priority: str


class ExtractedResponse(BaseModel):
    requirements: list[ExtractedItem]


def extract_with_ollama(description: str) -> list[RequirementData]:
    if not settings.ollama_chat_model:
        raise ValueError("Set OLLAMA_CHAT_MODEL to an installed local model")
    payload: dict[str, object] = {
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
    body = ollama_json("/api/chat", payload)
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
