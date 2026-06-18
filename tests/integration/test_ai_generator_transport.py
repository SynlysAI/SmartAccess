from __future__ import annotations

import socket
import ssl
from http.client import RemoteDisconnected
from urllib.error import URLError

from smartaccess.runtime.adapters import ai_generator
from smartaccess.runtime.adapters.ai_generator import SmartAccessAiGenerator


class _JsonResponse:
    def __enter__(self) -> "_JsonResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @staticmethod
    def read() -> bytes:
        return b'{"ok": true}'


def test_post_uses_explicit_https_context(monkeypatch) -> None:
    generator = SmartAccessAiGenerator(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        provider="codex",
    )
    calls: list[ssl.SSLContext | None] = []

    def fake_urlopen(_request, *, timeout, context=None):  # noqa: ANN001
        calls.append(context)
        return _JsonResponse()

    monkeypatch.setattr(ai_generator, "urlopen", fake_urlopen)

    assert generator._post("/responses", {"input": []}) == {"ok": True}
    assert len(calls) == 1
    assert isinstance(calls[0], ssl.SSLContext)


def test_post_formats_ssl_asn1_error_after_retry(monkeypatch) -> None:
    generator = SmartAccessAiGenerator(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        provider="codex",
    )

    def fake_urlopen(_request, **_kwargs):  # noqa: ANN001
        raise URLError(
            ssl.SSLError("[ASN1: NOT_ENOUGH_DATA] not enough data (_ssl.c:4057)")
        )

    monkeypatch.setattr(ai_generator, "urlopen", fake_urlopen)

    try:
        generator._post("/responses", {"input": []})
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive
        message = ""

    assert "TLS/SSL" in message
    assert "ASN1: NOT_ENOUGH_DATA" in message


def test_post_formats_direct_ssLError(monkeypatch) -> None:
    generator = SmartAccessAiGenerator(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        provider="codex",
    )

    def fake_urlopen(_request, **_kwargs):  # noqa: ANN001
        raise ssl.SSLError("[ASN1: NOT_ENOUGH_DATA] not enough data (_ssl.c:4057)")

    monkeypatch.setattr(ai_generator, "urlopen", fake_urlopen)

    try:
        generator._post("/responses", {"input": []})
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive
        message = ""

    assert "TLS/SSL" in message


def test_post_formats_read_timeout(monkeypatch) -> None:
    generator = SmartAccessAiGenerator(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        provider="codex",
        timeout_seconds=60,
    )

    class SlowResponse:
        def __enter__(self) -> "SlowResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            raise socket.timeout("The read operation timed out")

    def fake_urlopen(_request, **_kwargs):  # noqa: ANN001
        return SlowResponse()

    monkeypatch.setattr(ai_generator, "urlopen", fake_urlopen)

    try:
        generator._post("/responses", {"input": []})
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive
        message = ""

    assert message == "AI request timed out after 60s"


def test_post_retries_transient_connection_reset(monkeypatch) -> None:
    generator = SmartAccessAiGenerator(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        provider="codex",
    )
    calls = 0

    def fake_urlopen(_request, **_kwargs):  # noqa: ANN001
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError(ConnectionResetError(10054, "connection reset by peer"))
        return _JsonResponse()

    monkeypatch.setattr(ai_generator, "urlopen", fake_urlopen)

    assert generator._post("/responses", {"input": []}) == {"ok": True}
    assert calls == 2


def test_post_retries_remote_disconnected(monkeypatch) -> None:
    generator = SmartAccessAiGenerator(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        provider="codex",
    )
    calls = 0

    def fake_urlopen(_request, **_kwargs):  # noqa: ANN001
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RemoteDisconnected("remote end closed connection")
        return _JsonResponse()

    monkeypatch.setattr(ai_generator, "urlopen", fake_urlopen)

    assert generator._post("/responses", {"input": []}) == {"ok": True}
    assert calls == 2


def test_draft_instrument_profile_extends_timeout_for_images(monkeypatch) -> None:
    generator = SmartAccessAiGenerator(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        provider="codex",
        timeout_seconds=60,
    )
    seen: list[float | None] = []

    def fake_post(_path, _payload, *, timeout_seconds=None):  # noqa: ANN001
        seen.append(timeout_seconds)
        return {"output_text": '{"profile_id":"d1","anchors":[],"views":[]}'}

    monkeypatch.setattr(generator, "_post", fake_post)

    generator.draft_instrument_profile(
        "generate anchors",
        {"screenshot": {"data": "abcd", "mime_type": "image/png"}},
    )

    assert seen == [120.0]


def test_draft_workflow_extends_timeout_for_codex(monkeypatch) -> None:
    generator = SmartAccessAiGenerator(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        provider="codex",
        timeout_seconds=60,
    )
    seen: list[float | None] = []

    def fake_send(_payload, *, timeout_seconds=None):  # noqa: ANN001
        seen.append(timeout_seconds)
        return '{"metadata":{"workflow_id":"wf1","anchor_profile":"device_1","author":"ai-assistant","lifecycle_state":"Draft"},"preconditions":[],"steps":[],"retry_policy":{"max_attempts":2}}'

    monkeypatch.setattr(generator, "_send", fake_send)

    generator.draft_workflow("generate workflow", {})

    assert seen == [120.0]


def test_draft_workflow_accepts_legacy_exact_match_mode(monkeypatch) -> None:
    generator = SmartAccessAiGenerator(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="test-model",
        provider="codex",
    )

    monkeypatch.setattr(
        generator,
        "_send",
        lambda _payload, **_kwargs: """
        {
          "metadata": {
            "workflow_id": "wf_exact",
            "anchor_profile": "device_1",
            "author": "ai-assistant",
            "lifecycle_state": "Draft"
          },
          "steps": [
            {
              "id": "click_status",
              "action": "click",
              "anchor_id": "status",
              "match_mode": "exact",
              "expected_text": "Running",
              "timeout_seconds": 5
            }
          ]
        }
        """,
    )

    workflow = generator.draft_workflow("wait until status is Running", {})

    assert workflow.steps[0].match_mode == "equals"
