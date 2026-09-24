from datetime import datetime

import httpx

from camino_mcp.canvas import CanvasClient
from camino_mcp.service import CaminoService


def test_upcoming_sort_is_chronological_across_timezone_offsets():
    def handler(request):
        if request.url.path.endswith("/courses"):
            return httpx.Response(
                200,
                json=[{"id": 1}] if request.url.params.get("enrollment_state") == "active" else [],
            )
        if "favorites" in request.url.path:
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json=[
                {"id": 1, "due_at": "2026-09-25T01:00:00-07:00"},
                {"id": 2, "due_at": "2026-09-25T07:00:00+00:00"},
            ],
        )

    service = CaminoService(CanvasClient("FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler)))
    result = service.upcoming(2, now=datetime.fromisoformat("2026-09-24T12:00:00-07:00"))
    assert [item["id"] for item in result["assignments"]] == [2, 1]
