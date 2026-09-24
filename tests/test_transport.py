import httpx
import pytest

from camino_mcp.canvas import CaminoError, CanvasClient


def test_rate_limit_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("camino_mcp.canvas.time.sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429 if len(calls) == 1 else 200, json=[])

    result = CanvasClient("FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler)).get_pages(
        "/courses"
    )
    assert result == []
    assert len(calls) == 2


def test_paginated_non_list_response_is_explicit_failure():
    def handler(request):
        return httpx.Response(200, json={"errors": ["something"]})

    with pytest.raises(CaminoError, match="response shape"):
        CanvasClient("FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler)).get_pages(
            "/courses"
        )


def test_encoded_path_separator_rejected_before_http():
    with pytest.raises(CaminoError, match="Invalid API path"):
        CanvasClient(
            "FAKE_TEST_TOKEN", transport=httpx.MockTransport(lambda _: pytest.fail("network"))
        ).get_pages("/%2f%2fevil.test")
