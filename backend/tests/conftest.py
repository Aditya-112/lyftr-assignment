import asyncio
import json as jsonlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_API_KEYS", "fixture-primary,fixture-secondary")
    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-3.1-flash-lite")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'chat.db'}")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("DEFAULT_SYSTEM_PROMPT", "Default instructions")
    monkeypatch.setenv("ENABLE_FAILURE_SIMULATION", "true")
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "5")
    monkeypatch.setenv("CACHE_TTL", "3600")
    return Settings.from_env()


@pytest.fixture
def provider(monkeypatch):
    class Provider:
        calls = []
        failures = {}

        @staticmethod
        async def post(_client, url, *, headers, json=None, data=None, **_kwargs):
            assert "generativelanguage.googleapis.com" in url
            assert "gemini-3.1-flash-lite:generateContent" in url
            params = httpx.URL(url).params
            key = httpx.Headers(headers).get("x-goog-api-key") or params.get("key")
            payload = json if json is not None else jsonlib.loads(data)
            Provider.calls.append((key, payload))
            await asyncio.sleep(0.02)
            request = httpx.Request("POST", url)
            if key in Provider.failures:
                status, message = Provider.failures[key]
                return httpx.Response(
                    status,
                    json={"error": {"code": status, "message": message}},
                    request=request,
                )
            prompt_tokens = 20 + 8 * len(payload["contents"])
            return httpx.Response(
                200,
                json={
                    "candidates": [{
                        "content": {"role": "model", "parts": [{"text": f"Provider fixture reply {len(Provider.calls)}."}]},
                        "finishReason": "STOP",
                        "index": 0,
                    }],
                    "usageMetadata": {
                        "promptTokenCount": prompt_tokens,
                        "candidatesTokenCount": 6,
                        "totalTokenCount": prompt_tokens + 6,
                    },
                    "modelVersion": "gemini-3.1-flash-lite",
                },
                request=request,
            )

    monkeypatch.setattr(AsyncHTTPHandler, "post", Provider.post)
    return Provider


@pytest.fixture
def client(settings, provider):
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client
