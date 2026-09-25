from datetime import datetime

import httpx
import pytest

from camino_mcp.canvas import CaminoError, CanvasClient
from camino_mcp.service import CaminoService


def make_service(handler):
    return CaminoService(CanvasClient("FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler)))


def test_upcoming_filters_local_aware_window_and_unsubmitted():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/courses"):
            return httpx.Response(
                200,
                json=[{"id": 7, "name": "A"}]
                if request.url.params.get("enrollment_state") == "active"
                else [],
            )
        if "favorites" in request.url.path:
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "name": "Relevant",
                    "due_at": "2026-09-25T06:00:00Z",
                    "submission": {"workflow_state": "unsubmitted"},
                },
                {
                    "id": 2,
                    "name": "Done",
                    "due_at": "2026-09-25T06:00:00Z",
                    "submission": {"workflow_state": "submitted"},
                },
                {"id": 3, "name": "Too late", "due_at": "2026-10-03T00:00:00Z"},
                {"id": 4, "name": "Undated", "due_at": None},
            ],
        )

    result = make_service(handler).upcoming(
        1, now=datetime.fromisoformat("2026-09-24T12:00:00-07:00")
    )
    assert [a["id"] for a in result["assignments"]] == [1]
    assert result["complete"] is True
    assert any("/courses/7/assignments" in path for path in calls)


def test_overdue_ignores_submitted_and_future_items():
    def handler(request):
        if request.url.path.endswith("/courses"):
            return httpx.Response(
                200,
                json=[{"id": 9}]
                if request.url.params.get("enrollment_state") == "invited_or_pending"
                else [],
            )
        if "favorites" in request.url.path:
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "due_at": "2026-09-23T00:00:00Z",
                    "submission": {"workflow_state": "unsubmitted"},
                },
                {
                    "id": 2,
                    "due_at": "2026-09-23T00:00:00Z",
                    "submission": {"workflow_state": "submitted"},
                },
            ],
        )

    result = make_service(handler).overdue(now=datetime.fromisoformat("2026-09-24T12:00:00-07:00"))
    assert [a["id"] for a in result["assignments"]] == [1]


def test_inaccessible_course_is_skipped_and_flagged_not_fatal():
    def handler(request):
        if request.url.path.endswith("/courses"):
            return httpx.Response(
                200,
                json=[{"id": 1, "name": "Open"}, {"id": 2, "name": "Locked"}]
                if request.url.params.get("enrollment_state") == "active"
                else [],
            )
        if "favorites" in request.url.path:
            return httpx.Response(200, json=[])
        if "/courses/2/" in request.url.path:
            return httpx.Response(403, json={"errors": [{"message": "unauthorized"}]})
        return httpx.Response(200, json=[])

    result = make_service(handler).upcoming(
        7, now=datetime.fromisoformat("2026-09-24T12:00:00-07:00")
    )
    assert result["complete"] is False
    assert result["skipped_courses"] == [{"course_id": 2, "course_name": "Locked"}]
    assert "warning" in result


def test_cross_course_server_failure_is_explicit_not_silent_partial_success():
    def handler(request):
        if request.url.path.endswith("/courses"):
            return httpx.Response(
                200,
                json=[{"id": 1}, {"id": 2}]
                if request.url.params.get("enrollment_state") == "active"
                else [],
            )
        if "favorites" in request.url.path:
            return httpx.Response(200, json=[])
        return httpx.Response(500 if "/courses/2/" in request.url.path else 200, json=[])

    with pytest.raises(CaminoError, match="HTTP 500"):
        make_service(handler).upcoming(7, now=datetime.fromisoformat("2026-09-24T12:00:00-07:00"))


def test_window_rejects_out_of_bounds():
    def forbidden(_):
        raise AssertionError("network requested")

    for value in (0, -1, 32, True):
        with pytest.raises(ValueError, match="days"):
            make_service(forbidden).upcoming(value)


def test_missing_token_never_sends_network_request():
    with pytest.raises(CaminoError, match="CAMINO_API_TOKEN"):
        CanvasClient("", transport=httpx.MockTransport(lambda _: pytest.fail("network"))).get_pages(
            "/courses"
        )
