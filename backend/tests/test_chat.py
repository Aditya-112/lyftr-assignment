import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def chat(client, session="a", message="First message", *, simulate=None, **options):
    headers = {} if simulate is None else {"X-Simulate-Failure": simulate}
    return client.post("/chat", json={"session_id": session, "message": message, **options}, headers=headers)


def history(client, session="a"):
    return client.get(f"/sessions/{session}/messages")


@pytest.mark.parametrize("body", [
    {"message": "hello"},
    {"session_id": "", "message": "hello"},
    {"session_id": "x" * 129, "message": "hello"},
    {"session_id": "a"},
    {"session_id": "a", "message": ""},
    {"session_id": "a", "message": " \t\n "},
    {"session_id": "a", "message": "x" * 4001},
    {"session_id": 42, "message": "hello"},
    {"session_id": "a", "message": 99},
    {"session_id": "a", "message": "hello", "system_prompt": []},
    {"session_id": "a", "message": "hello", "system_prompt": None},
])
def test_invalid_chat(client, provider, body):
    result = client.post("/chat", json=body)
    assert result.status_code == 422
    assert "detail" in result.json()
    assert provider.calls == []
    assert history(client).status_code == 404


def test_malformed_json(client, provider):
    result = client.post("/chat", content='{"message":', headers={"Content-Type": "application/json"})
    assert result.status_code == 422
    assert "detail" in result.json()
    assert provider.calls == []


def test_health_routes_and_cors(client):
    assert client.get("/health").json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}
    for endpoint in ["/", "/docs", "/redoc", "/openapi.json"]:
        assert client.get(endpoint).status_code == 404
    response = client.options("/chat", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-simulate-failure",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_metadata_and_trimmed_boundaries(client, provider, settings):
    message = "a" * 4000
    session = "s" * 128
    response = chat(client, session, f" \n{message}  ")
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {"session_id", "reply", "metadata"}
    assert data["session_id"] == session
    assert data["reply"]
    metadata = data["metadata"]
    assert metadata == {
        "resolution_source": "LIVE_INFERENCE", "key_id": "key_1", "fallback_attempts": 0,
        "model": settings.model, "latency_ms": metadata["latency_ms"],
        "input_tokens": 28, "output_tokens": 6,
    }
    assert type(metadata["latency_ms"]) is int and metadata["latency_ms"] >= 0
    assert provider.calls[0][0] == settings.keys[0]
    assert all(key not in response.text for key in settings.keys)
    assert history(client, session).json()["messages"] == [
        {"role": "user", "content": message},
        {"role": "assistant", "content": data["reply"], "metadata": metadata},
    ]


def test_history_isolation_context_and_prompt_persistence(client, provider):
    missing = history(client)
    assert missing.status_code == 404 and missing.json() == {"detail": "session not found"}
    first = chat(client, "a", "My favorite language is Python.", system_prompt="Keep it brief.").json()
    second = chat(client, "a", "What is my favorite language?").json()
    other = chat(client, "b", "What is my favorite language?").json()
    first_payload, second_payload, other_payload = [payload for _, payload in provider.calls]

    assert second_payload["system_instruction"] == first_payload["system_instruction"]
    assert other_payload["system_instruction"] != first_payload["system_instruction"]
    assert [entry["parts"][0]["text"] for entry in second_payload["contents"]] == [
        "My favorite language is Python.", first["reply"], "What is my favorite language?",
    ]
    assert [entry["parts"][0]["text"] for entry in other_payload["contents"]] == ["What is my favorite language?"]
    assert second["metadata"]["input_tokens"] == 44
    assert first["metadata"]["input_tokens"] == other["metadata"]["input_tokens"] == 28
    assert [item["role"] for item in history(client, "a").json()["messages"]] == [
        "user", "assistant", "user", "assistant",
    ]
    assert len(history(client, "b").json()["messages"]) == 2
    assert "Keep it brief." not in history(client, "a").text


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_simulated_primary_failure(client, provider, settings, status):
    result = chat(client, simulate=f"key_1={status}")
    assert result.status_code == 200, result.text
    assert result.json()["metadata"]["key_id"] == "key_2"
    assert result.json()["metadata"]["fallback_attempts"] == 1
    assert [key for key, _ in provider.calls] == [settings.keys[1]]
    next_result = chat(client, session="next")
    assert next_result.json()["metadata"]["key_id"] == "key_1"
    assert len(provider.calls) == 2


@pytest.mark.parametrize("status, reason", [(429, "Rate limit"), (400, "Quota exceeded"), (502, "Bad gateway")])
def test_provider_errors_fail_over(client, provider, settings, status, reason):
    provider.failures[settings.keys[0]] = (status, reason)
    result = chat(client)
    assert result.status_code == 200, result.text
    assert result.json()["metadata"]["key_id"] == "key_2"
    assert result.json()["metadata"]["fallback_attempts"] == 1
    assert [key for key, _ in provider.calls] == list(settings.keys)


@pytest.mark.parametrize("header", ["*=429", "key_1=429,key_2=500"])
def test_total_simulated_failure_leaves_history_untouched(client, provider, header):
    assert chat(client, system_prompt="Persistent prompt").status_code == 200
    previous = history(client).json()
    for session in ["a", "new"]:
        result = chat(client, session, "Never persisted", simulate=header, system_prompt="Discard me")
        assert result.status_code == 503
        assert result.json() == {"detail": "all providers unavailable"}
    assert history(client).json() == previous
    assert history(client, "new").status_code == 404
    assert len(provider.calls) == 1
    assert chat(client, "a", "Follow-up").status_code == 200
    assert provider.calls[1][1]["system_instruction"] == provider.calls[0][1]["system_instruction"]


def test_total_provider_failure(client, provider, settings):
    provider.failures.update({key: (503, f"Could not serve {key}") for key in settings.keys})
    result = chat(client)
    assert result.status_code == 503
    assert result.json() == {"detail": "all providers unavailable"}
    assert history(client).status_code == 404
    assert len(provider.calls) == 2


def test_simulation_flag(settings, provider):
    with TestClient(create_app(replace(settings, simulate_failures=False))) as client:
        result = chat(client, simulate="*=429")
        assert result.status_code == 200
        assert result.json()["metadata"]["key_id"] == "key_1"
        assert len(provider.calls) == 1


def test_cache_shares_exact_prompt_and_usage_without_provider_call(client, provider):
    first = chat(client, "first").json()
    second = chat(client, "second").json()
    assert first["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert first["reply"] == second["reply"]
    cached = second["metadata"]
    assert cached["resolution_source"] == "LLM_CACHE"
    assert cached["key_id"] is None and cached["fallback_attempts"] == 0
    assert cached["input_tokens"] == first["metadata"]["input_tokens"]
    assert cached["output_tokens"] == first["metadata"]["output_tokens"]
    assert cached["latency_ms"] < first["metadata"]["latency_ms"]
    assert len(provider.calls) == 1
    assert history(client, "second").json()["messages"][-1]["metadata"] == cached


def test_cache_varies_with_messages_system_prompt_and_history(client, provider):
    assert chat(client, "a").json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert chat(client, "b", "Different message").json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert chat(client, "c", system_prompt="A different system prompt").json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert chat(client, "a", "Common follow-up").json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert chat(client, "b", "Common follow-up").json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert len(provider.calls) == 5


def test_simulation_bypasses_warm_cache_without_overwriting_it(client, provider):
    first = chat(client, "warm").json()
    fallback = chat(client, "fallback", simulate="key_1=429").json()
    assert fallback["metadata"]["key_id"] == "key_2"
    assert fallback["reply"] != first["reply"]
    unavailable = chat(client, "failed", simulate="*=429")
    assert unavailable.status_code == 503
    cached = chat(client, "cached").json()
    assert cached["metadata"]["resolution_source"] == "LLM_CACHE"
    assert cached["reply"] == first["reply"]
    assert len(provider.calls) == 2


def test_restart_preserves_sqlite_history_but_clears_cache(settings, provider):
    with TestClient(create_app(settings)) as client:
        assert chat(client).status_code == 200
        expected = history(client).json()
    with TestClient(create_app(settings)) as client:
        assert history(client).json() == expected
        assert chat(client, "new").json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_session_turns_are_serialized(client, provider):
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(chat, client, "a", "One")
        second = executor.submit(chat, client, "a", "Two")
        assert [first.result().status_code, second.result().status_code] == [200, 200]
    assert [len(payload["contents"]) for _, payload in provider.calls] == [1, 3]
    assert [item["role"] for item in history(client).json()["messages"]] == [
        "user", "assistant", "user", "assistant",
    ]


def test_database_rolls_back_if_second_insert_fails(client, settings):
    with sqlite3.connect(settings.database) as database:
        database.executescript("""
            CREATE TRIGGER reject_assistant BEFORE INSERT ON messages
            WHEN NEW.role = 'assistant'
            BEGIN SELECT RAISE(ABORT, 'test rollback'); END;
        """)
    result = chat(client)
    assert result.status_code == 500
    assert result.json() == {"detail": "internal server error"}
    assert history(client).status_code == 404
    with sqlite3.connect(settings.database) as database:
        assert database.execute("SELECT count(*) FROM sessions").fetchone() == (0,)


def test_health_fails_when_schema_is_unavailable(client, settings):
    with sqlite3.connect(settings.database) as database:
        database.execute("DROP TABLE messages")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
