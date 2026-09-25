"""Regressions for bugs found in review: student-facing correctness and resilience."""

import asyncio
import json
from datetime import datetime

import httpx
import pytest

from camino_mcp import server
from camino_mcp.canvas import BAD_TOKEN, AccessDenied, CaminoError, CanvasClient
from camino_mcp.service import CaminoService

NOW = datetime.fromisoformat("2026-09-25T12:00:00-07:00")


def client(handler, **kw):
    return CanvasClient(
        "FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler), sleep=lambda _: None, **kw
    )


def courses_handler(courses, assignments):
    def handler(request):
        path = request.url.path
        if path.endswith("/courses"):
            active = request.url.params.get("enrollment_state") == "active"
            return httpx.Response(200, json=courses if active else [])
        if "favorites" in path:
            return httpx.Response(200, json=[])
        cid = int(path.split("/courses/")[1].split("/")[0])
        return httpx.Response(200, json=assignments.get(cid, []))

    return handler


def test_numeric_ids_from_ai_clients_are_accepted_by_mcp_schema(monkeypatch):
    seen = []
    monkeypatch.setattr(
        server, "_call", lambda method, *a, **k: seen.append((method, a)) or {"complete": True}
    )
    asyncio.run(server.mcp.call_tool("get_assignment", {"course_id": 120415, "assignment_id": 5}))
    asyncio.run(server.mcp.call_tool("list_assignments", {"course_id": "120415"}))
    assert seen[0] == ("get_assignment", (120415, 5))
    assert seen[1][1][0] == "120415"


def test_whitespace_around_ids_is_tolerated():
    def handler(request):
        assert request.url.path == "/api/v1/courses/12/assignments"
        return httpx.Response(200, json=[])

    assert CaminoService(client(handler)).list_assignments(" 12 ")["complete"] is True


def test_overdue_skips_paper_excused_and_ended_courses_but_keeps_real_missing_work():
    courses = [
        {
            "id": 1,
            "name": "Now",
            "end_at": "2026-12-18T08:00:00Z",
            "enrollments": [{"type": "student", "enrollment_state": "active"}],
        },
        {
            "id": 2,
            "name": "Old",
            "end_at": "2026-03-13T07:00:00Z",
            "enrollments": [{"type": "student", "enrollment_state": "active"}],
        },
    ]
    past = "2026-09-20T00:00:00Z"
    unsub = {"workflow_state": "unsubmitted", "submitted_at": None}
    assignments = {
        1: [
            {
                "id": 10,
                "name": "Upload",
                "due_at": past,
                "submission_types": ["online_upload"],
                "submission": unsub,
            },
            {
                "id": 11,
                "name": "Paper",
                "due_at": past,
                "submission_types": ["on_paper"],
                "submission": unsub,
            },
            {
                "id": 12,
                "name": "None",
                "due_at": past,
                "submission_types": ["none"],
                "submission": unsub,
            },
            {
                "id": 13,
                "name": "Excused",
                "due_at": past,
                "submission_types": ["online_upload"],
                "submission": {**unsub, "excused": True},
            },
            {
                "id": 14,
                "name": "Marked missing",
                "due_at": past,
                "submission_types": ["on_paper"],
                "submission": {**unsub, "missing": True},
            },
            {
                "id": 15,
                "name": "Quiz",
                "due_at": past,
                "submission_types": ["online_quiz"],
                "submission": {"workflow_state": "complete"},
            },
        ],
        2: [
            {
                "id": 20,
                "name": "Ancient",
                "due_at": "2026-02-01T00:00:00Z",
                "submission_types": ["online_upload"],
                "submission": unsub,
            }
        ],
    }
    service = CaminoService(client(courses_handler(courses, assignments)))
    assert [a["id"] for a in service.overdue(now=NOW)["assignments"]] == [10, 14]
    with_ended = service.overdue(True, now=NOW)["assignments"]
    assert [a["id"] for a in with_ended] == [20, 10, 14]


def test_upcoming_excludes_excused_work():
    courses = [{"id": 1, "name": "A"}]
    soon = "2026-09-27T00:00:00Z"
    assignments = {
        1: [
            {
                "id": 1,
                "due_at": soon,
                "submission": {"workflow_state": "unsubmitted", "excused": True},
            },
            {"id": 2, "due_at": soon, "submission": {"workflow_state": "unsubmitted"}},
        ]
    }
    result = CaminoService(client(courses_handler(courses, assignments))).upcoming(7, now=NOW)
    assert [a["id"] for a in result["assignments"]] == [2]


def test_pending_invitations_are_not_queried_for_assignments():
    courses = [
        {
            "id": 1,
            "name": "Invite",
            "enrollments": [{"type": "student", "enrollment_state": "invited"}],
        }
    ]

    def handler(request):
        assert "/assignments" not in request.url.path
        return courses_handler(courses, {})(request)

    assert CaminoService(client(handler)).upcoming(7, now=NOW)["complete"] is True


@pytest.mark.parametrize(
    "enrollments",
    [
        {"type": "student"},
        "x",
        [None, 3],
        [
            {"type": "teacher"},
            {"type": "student", "enrollment_state": "active", "computed_current_score": 90},
        ],
    ],
)
def test_list_courses_tolerates_unusual_enrollment_shapes(enrollments):
    handler = courses_handler(
        [{"id": 5, "name": "C", "enrollments": enrollments, "term": {"name": "Fall"}}], {}
    )
    course = CaminoService(client(handler)).list_courses()["courses"][0]
    assert course["id"] == 5 and course["term"] == "Fall"


def test_student_enrollment_preferred_for_grade():
    enr = [
        {"type": "ta", "enrollment_state": "active"},
        {"type": "student", "enrollment_state": "active", "computed_current_score": 90},
    ]
    course = CaminoService(
        client(courses_handler([{"id": 5, "enrollments": enr}], {}))
    ).list_courses()["courses"][0]
    assert course["computed_current_score"] == 90


def test_canvas_403_rate_limit_is_retried_not_reported_as_access_denied():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(403, text="403 Forbidden (Rate Limit Exceeded)")
        return httpx.Response(200, json=[])

    assert client(handler).get_pages("/courses") == []
    assert len(calls) == 3


def test_persistent_rate_limit_has_clear_message():
    handler = lambda _: httpx.Response(403, text="403 Forbidden (Rate Limit Exceeded)")
    with pytest.raises(CaminoError, match="rate-limiting"):
        client(handler).get_pages("/courses")


def test_invalid_token_vs_resource_unauthorized_are_distinguished():
    bad = lambda _: httpx.Response(
        401,
        headers={"WWW-Authenticate": 'Bearer realm="canvas-lms"'},
        json={"errors": [{"message": "Invalid access token."}]},
    )
    with pytest.raises(CaminoError) as exc:
        client(bad).get_pages("/courses")
    assert str(exc.value) == BAD_TOKEN and not isinstance(exc.value, AccessDenied)

    unauth = lambda _: httpx.Response(
        401,
        json={
            "status": "unauthorized",
            "errors": [{"message": "user not authorized to perform that action"}],
        },
    )
    with pytest.raises(AccessDenied):
        client(unauth).get_pages("/courses/1/assignments")


def test_network_failure_is_friendly():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(CaminoError, match="internet connection"):
        client(handler).get_pages("/courses")


def test_token_whitespace_from_copy_paste_is_stripped():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer FAKE"
        return httpx.Response(200, json=[])

    CanvasClient("  FAKE\n", transport=httpx.MockTransport(handler)).get_pages("/courses")


def test_check_setup_reports_connected_user():
    handler = lambda r: httpx.Response(
        200, json={"id": 1, "short_name": "Sam", "login_id": "secret"}
    )
    result = CaminoService(client(handler)).check_setup()
    assert (
        result["connected"] is True
        and result["name"] == "Sam"
        and "secret" not in json.dumps(result)
    )


def test_unexpected_exception_returns_safe_error(monkeypatch):
    monkeypatch.setenv("CAMINO_API_TOKEN", "FAKE_TEST_TOKEN")

    def boom(self):
        raise RuntimeError("FAKE_TEST_TOKEN internal detail")

    monkeypatch.setattr(CaminoService, "list_courses", boom)
    result = server.list_courses()
    assert result["complete"] is False and "FAKE_TEST_TOKEN" not in result["error"]


def test_conversation_with_malformed_messages_does_not_crash():
    handler = lambda r: httpx.Response(200, json={"id": 3, "subject": "Hi", "messages": None})
    assert CaminoService(client(handler)).get_conversation(3)["conversation"]["messages"] == []


def test_download_accepts_home_relative_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    def handler(request):
        if request.url.path.endswith("/files/9"):
            return httpx.Response(200, json={"id": 9, "display_name": "a.txt", "size": 2})
        return httpx.Response(200, content=b"hi", headers={"content-type": "text/plain"})

    result = CaminoService(client(handler)).download_file(1, 9, "~")
    assert result["complete"] is True and (tmp_path / "a.txt").read_bytes() == b"hi"


def test_all_tools_have_annotations_and_descriptions():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} >= {
        "check_setup",
        "list_courses",
        "upcoming",
        "overdue",
        "grades",
    }
    for tool in tools:
        assert tool.description and tool.annotations is not None
        assert tool.annotations.readOnlyHint is (tool.name != "download_file")
