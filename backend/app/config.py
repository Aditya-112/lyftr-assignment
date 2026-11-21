import os
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlsplit


Number = TypeVar("Number", int, float)


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def positive_number(name: str, default: str, parse: type[Number]) -> Number:
    try:
        value = parse(os.getenv(name, default))
        if not isfinite(value) or value <= 0:
            raise ValueError
    except (ValueError, OverflowError):
        raise ValueError(f"{name} must be a positive number") from None
    return value


@dataclass(frozen=True)
class Settings:
    keys: tuple[str, ...] = field(repr=False)
    database: Path
    origins: tuple[str, ...]
    simulate_failures: bool
    model: str
    default_prompt: str
    timeout: float
    cache_ttl: int

    @classmethod
    def from_env(cls) -> "Settings":
        keys = tuple(key.strip() for key in required("LLM_API_KEYS").split(","))
        if len(set(keys)) != len(keys) or len(keys) < 2 or any(
            not key or key.startswith("replace_with_") for key in keys
        ):
            raise ValueError("LLM_API_KEYS must contain at least two distinct provider keys")

        prefix = "sqlite:///"
        database_url = required("DATABASE_URL")
        if not database_url.startswith(prefix):
            raise ValueError("DATABASE_URL must use sqlite:/// and point to a file")
        path = database_url[len(prefix):]
        if not path or path in {":memory:", "/"} or any(char in path for char in "?#\x00"):
            raise ValueError("DATABASE_URL must point to a SQLite file")

        origins = tuple(origin.strip() for origin in required("ALLOWED_ORIGINS").split(","))
        for origin in origins:
            try:
                parts = urlsplit(origin)
                port = parts.port
                if (
                    parts.scheme not in {"http", "https"} or not parts.hostname
                    or parts.username is not None or parts.path or parts.query or parts.fragment
                    or port == 0 or any(char.isspace() for char in origin)
                ):
                    raise ValueError
            except ValueError:
                raise ValueError("ALLOWED_ORIGINS must list HTTP(S) origins without paths") from None

        simulation = os.getenv("ENABLE_FAILURE_SIMULATION", "false").strip().lower()
        if simulation not in {"true", "false"}:
            raise ValueError("ENABLE_FAILURE_SIMULATION must be true or false")

        model = os.getenv("LLM_MODEL", "gemini/gemini-3.1-flash-lite").strip()
        provider, _, model_name = model.partition("/")
        if not provider or not model_name or any(char.isspace() for char in model):
            raise ValueError("LLM_MODEL must be a provider-qualified LiteLLM model")

        return cls(
            keys=keys,
            database=Path(path).resolve(),
            origins=origins,
            simulate_failures=simulation == "true",
            model=model,
            default_prompt=os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful, concise assistant.").strip(),
            timeout=positive_number("LLM_REQUEST_TIMEOUT", "25", float),
            cache_ttl=positive_number("CACHE_TTL", "3600", int),
        )
