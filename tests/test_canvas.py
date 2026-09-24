import httpx
import pytest

from camino_mcp.canvas import CaminoError, CanvasClient
from camino_mcp.service import CaminoService


def mock_client(handler):
    return CanvasClient("FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler))


def response(request, data, headers=None, status=200):
    return httpx.Response(status, json=data, headers=headers, request=request)


def test_courses_merge_active_pending_and_favorites_without_omission():
    def handler(request):
        path = request.url.path
        if path.endswith("favorites/courses"):
            return response(request, [{"id": 3, "name": "Starred", "enrollments": []}])
        state = request.url.params.get("enrollment_state")
        if state == "active":
            return response(
                request,
                [
                    {"id": 1, "name": "Active", "enrollments": [{"enrollment_state": "active"}]},
                    {"id": 3, "name": "Starred", "enrollments": []},
                ],
            )
        return response(
            request,
            [{"id": 2, "name": "Pending", "enrollments": [{"enrollment_state": "invited"}]}],
        )

    result = CaminoService(mock_client(handler)).list_courses()
    assert [c["id"] for c in result["courses"]] == [1, 2, 3]
    assert result["courses"][2]["favorite"] is True
    assert result["courses"][1]["enrollment_state"] == "invited"
    assert result["complete"] is True


def test_assignments_allowlist_and_submission_metadata():
    def handler(request):
        assert request.url.params.get("include[]") == "submission"
        assert request.url.params.get("bucket") == "future"
        return response(
            request,
            [
                {
                    "id": 10,
                    "name": "Essay",
                    "description": "secret HTML",
                    "html_url": "https://evil.test/hijack",
                    "due_at": "2026-09-28T16:00:00Z",
                    "points_possible": 12,
                    "submission": {
                        "workflow_state": "submitted",
                        "submitted_at": "2026-09-27T16:00:00Z",
                        "body": "secret",
                    },
                }
            ],
        )

    result = CaminoService(mock_client(handler)).list_assignments("123", "future")
    assert result["assignments"] == [
        {
            "id": 10,
            "course_id": 123,
            "name": "Essay",
            "due_at": "2026-09-28T16:00:00Z",
            "points_possible": 12,
            "submission": {"workflow_state": "submitted", "submitted_at": "2026-09-27T16:00:00Z"},
        }
    ]


@pytest.mark.parametrize("course_id", ["../2", "1/assignments", "-1", "1?x=2", "0", True, "１２"])
def test_invalid_course_id_rejected_before_network(course_id):
    def forbidden(_):
        raise AssertionError("network requested")

    with pytest.raises(ValueError, match="course_id"):
        CaminoService(mock_client(forbidden)).list_assignments(course_id)


def test_pagination_rejects_off_origin_next():
    def handler(request):
        return response(
            request, [{"id": 1}], {"Link": '<https://evil.test/api/v1/courses>; rel="next"'}
        )

    with pytest.raises(CaminoError, match="pagination"):
        mock_client(handler).get_pages("/courses")


def test_pagination_follows_safe_next_and_stops_loop():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return response(
                request,
                [{"id": 1}],
                {"Link": '<https://camino.instructure.com/api/v1/courses?page=2>; rel="next"'},
            )
        return response(request, [{"id": 2}])

    assert mock_client(handler).get_pages("/courses") == [{"id": 1}, {"id": 2}]
    assert len(calls) == 2

    def looping(request):
        return response(request, [], {"Link": f'<{request.url}>; rel="next"'})

    with pytest.raises(CaminoError, match="pagination"):
        mock_client(looping).get_pages("/courses")
