import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def call(base, path, body=None, *, simulate=None, expected=200):
    headers = {}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    if simulate is not None:
        headers["X-Simulate-Failure"] = simulate
    request = Request(base.rstrip("/") + path, data=data, headers=headers)
    try:
        response = urlopen(request, timeout=75)
    except HTTPError as error:
        response = error
    with response:
        if response.status != expected:
            raise RuntimeError(f"{path} returned HTTP {response.status}, expected {expected}")
        return json.load(response)


def chat(base, session_id, message, *, simulate=None, system_prompt=None):
    body = {"session_id": session_id, "message": message}
    if system_prompt is not None:
        body["system_prompt"] = system_prompt
    reply = call(base, "/chat", body, simulate=simulate)
    assert set(reply) == {"session_id", "reply", "metadata"}
    assert reply["session_id"] == session_id
    assert reply["reply"].strip()
    metadata = reply["metadata"]
    assert set(metadata) == {
        "resolution_source", "model", "latency_ms", "input_tokens",
        "output_tokens", "key_id", "fallback_attempts",
    }
    assert metadata["model"]
    for name in ("latency_ms", "input_tokens", "output_tokens", "fallback_attempts"):
        assert type(metadata[name]) is int and metadata[name] >= 0
    assert metadata["input_tokens"] > 0 and metadata["output_tokens"] > 0
    return reply


def verify(base, extended):
    health = call(base, "/health")
    assert health["status"] == "ok" and health["cache_enabled"]
    assert health["keys_configured"] >= 2
    print(f"Health: {health['keys_configured']} keys loaded, cache on.")

    stamp = uuid4().hex[:12]
    prompt = f"In one sentence, explain why caching saves time. Reference {stamp}."
    live = chat(base, f"{stamp}-live", prompt)
    assert live["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert live["metadata"]["key_id"] == "key_1" and live["metadata"]["fallback_attempts"] == 0
    cached = chat(base, f"{stamp}-cached", prompt)
    assert cached["metadata"]["resolution_source"] == "LLM_CACHE"
    assert cached["metadata"]["key_id"] is None and cached["metadata"]["fallback_attempts"] == 0
    assert cached["reply"] == live["reply"]
    for name in ("input_tokens", "output_tokens", "model"):
        assert cached["metadata"][name] == live["metadata"][name]
    assert cached["metadata"]["latency_ms"] < live["metadata"]["latency_ms"]
    print(f"Inference and cache: {live['metadata']['latency_ms']} ms live, {cached['metadata']['latency_ms']} ms cached.")

    for status in ([429, 500, 502, 503] if extended else [429]):
        fallback = chat(base, f"{stamp}-fallback-{status}", prompt, simulate=f"key_1={status}")
        assert fallback["metadata"]["resolution_source"] == "LIVE_INFERENCE"
        assert fallback["metadata"]["key_id"] == "key_2" and fallback["metadata"]["fallback_attempts"] == 1
        print(f"Simulated {status}: key_2 returned a live reply.")

    failure_id = f"{stamp}-failed"
    failures = ["*=429"]
    if health["keys_configured"] == 2:
        failures.append("key_1=429,key_2=500")
    for simulation in failures:
        body = call(base, "/chat", {"session_id": failure_id, "message": prompt}, simulate=simulation, expected=503)
        assert body == {"detail": "all providers unavailable"}
        missing = call(base, f"/sessions/{failure_id}/messages", expected=404)
        assert missing == {"detail": "session not found"}
    for payload in (b'{"message":', {"message": "Missing session"}, {"session_id": stamp, "message": "   "}):
        assert "detail" in call(base, "/chat", payload, expected=422)
    print("503, 404, and 422 responses match the contract.")

    memory = f"{stamp}-memory"
    codename = f"Riverstone-{stamp}"
    first_message = f"Remember my fictional project codename {codename}. Reply only with 'Noted'."
    question = "What exact fictional project codename did I give you? Reply with the codename only."
    first = chat(base, memory, first_message)
    follow_up = chat(base, memory, question)
    isolated = chat(base, f"{stamp}-isolated", question)
    assert codename.lower() in follow_up["reply"].lower()
    assert codename.lower() not in isolated["reply"].lower()
    assert follow_up["metadata"]["input_tokens"] > isolated["metadata"]["input_tokens"]
    history = call(base, f"/sessions/{memory}/messages")
    assert history == {
        "session_id": memory,
        "messages": [
            {"role": "user", "content": first_message},
            {"role": "assistant", "content": first["reply"], "metadata": first["metadata"]},
            {"role": "user", "content": question},
            {"role": "assistant", "content": follow_up["reply"], "metadata": follow_up["metadata"]},
        ],
    }
    print(f"Multi-turn context, isolation, token accounting, and history verified ({memory}).")
    return history


def main():
    parser = argparse.ArgumentParser(description="Verify Lyftr Chat against a running backend using real inference.")
    parser.add_argument("base_url")
    parser.add_argument("--extended", action="store_true", help="Exercise all four simulated status codes.")
    snapshots = parser.add_mutually_exclusive_group()
    snapshots.add_argument("--write-history", type=Path)
    snapshots.add_argument("--check-history", type=Path)
    args = parser.parse_args()

    if args.check_history:
        saved = json.loads(args.check_history.read_text())
        current = call(args.base_url, f"/sessions/{saved['session_id']}/messages")
        assert saved == current
        print(f"History survived restart ({saved['session_id']}).")
        return
    history = verify(args.base_url, args.extended)
    if args.write_history:
        args.write_history.write_text(json.dumps(history, indent=2) + "\n")


if __name__ == "__main__":
    main()
