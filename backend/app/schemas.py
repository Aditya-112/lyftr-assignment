from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, StrictStr, StringConstraints, field_validator


class ModelMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    session_id: Annotated[StrictStr, StringConstraints(min_length=1, max_length=128)]
    message: Annotated[StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    system_prompt: Annotated[StrictStr, StringConstraints(strip_whitespace=True)] | None = None

    @field_validator("system_prompt", mode="before")
    @classmethod
    def require_string_when_provided(cls, value: object) -> object:
        if value is None:
            raise ValueError("System prompt must be a string")
        return value


class Metadata(BaseModel):
    resolution_source: Literal["LIVE_INFERENCE", "LLM_CACHE"]
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: Metadata


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    metadata: Metadata | None


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[UserMessage | AssistantMessage]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    keys_configured: int
    cache_enabled: bool
