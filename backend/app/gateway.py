import asyncio
import os
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import import_module
from time import perf_counter

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault("LITELLM_LOG", "CRITICAL")

import litellm
from litellm.caching.caching import Cache
from openai import APIError, APIConnectionError

from .config import Settings
from .schemas import Metadata, ModelMessage


class ProvidersUnavailable(Exception):
    pass


def simulated_failures(header: str | None, key_ids: tuple[str, ...]) -> dict[str, int]:
    failures = {}
    for entry in (header or "").split(","):
        key_id, _, status = entry.strip().partition("=")
        key_id, status = key_id.strip(), status.strip()
        if status in {"429", "500", "502", "503"} and (key_id == "*" or key_id in key_ids):
            failures[key_id] = int(status)
    return failures


def can_fail_over(error: APIError) -> bool:
    status = getattr(error, "status_code", None)
    code = str(getattr(error, "code", "")).lower()
    return (
        status in {401, 403, 408, 429}
        or (isinstance(status, int) and 500 <= status <= 599)
        or code in {"insufficient_quota", "resource_exhausted", "quota_exceeded", "billing_hard_limit_reached"}
        or "quota" in str(error).lower()
    )


class Gateway:
    def __init__(self, settings: Settings):
        try:
            litellm.get_llm_provider(settings.model)
        except litellm.BadRequestError:
            raise ValueError("LLM_MODEL must use a supported LiteLLM provider") from None
        self.settings = settings
        self.key_ids = tuple(f"key_{number}" for number in range(1, len(settings.keys) + 1))
        self.cache = Cache(type="local", ttl=settings.cache_ttl, supported_call_types=["acompletion"])

    @contextmanager
    def enable(self) -> Iterator[None]:
        import_module("litellm.llms.anthropic.pass_through.messages.response_cache")
        previous_cache = litellm.cache
        litellm.cache = self.cache
        try:
            yield
        finally:
            litellm.cache = previous_cache

    @property
    def cache_enabled(self) -> bool:
        return litellm.cache is self.cache

    async def resolve(self, messages: list[ModelMessage], header: str | None) -> tuple[str, Metadata]:
        start = perf_counter()
        failures = simulated_failures(header, self.key_ids) if self.settings.simulate_failures else {}
        cache_control = {"no-cache": True, "no-store": True} if failures else {}
        for attempts, (key_id, key) in enumerate(zip(self.key_ids, self.settings.keys)):
            if key_id in failures or "*" in failures:
                continue
            try:
                async with asyncio.timeout(self.settings.timeout):
                    response = await litellm.acompletion(
                        model=self.settings.model,
                        messages=messages,
                        api_key=key,
                        timeout=self.settings.timeout,
                        num_retries=0,
                        cache=cache_control,
                    )
            except (TimeoutError, APIConnectionError, litellm.BudgetExceededError):
                continue
            except APIError as error:
                if can_fail_over(error):
                    continue
                raise ProvidersUnavailable from None

            reply = response.choices[0].message.content if response.choices else None
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", None)
            output_tokens = getattr(usage, "completion_tokens", None)
            if (
                not isinstance(reply, str) or not reply.strip()
                or not isinstance(input_tokens, int) or input_tokens <= 0
                or not isinstance(output_tokens, int) or output_tokens <= 0
            ):
                raise ProvidersUnavailable

            cached = response._hidden_params.get("cache_hit") is True
            return reply, Metadata(
                resolution_source="LLM_CACHE" if cached else "LIVE_INFERENCE",
                model=self.settings.model,
                latency_ms=int((perf_counter() - start) * 1000),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                key_id=None if cached else key_id,
                fallback_attempts=0 if cached else attempts,
            )
        raise ProvidersUnavailable
