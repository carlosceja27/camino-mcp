import httpx

from camino_mcp import server
from camino_mcp.canvas import CanvasClient


def test_server_tools_return_explicit_safe_errors_without_token(monkeypatch):
    monkeypatch.delenv("CAMINO_API_TOKEN", raising=False)
    results = [
        server.list_courses(),
        server.list_assignments("1"),
        server.upcoming(),
        server.overdue(),
        server.grades(),
    ]
    assert all(
        result["complete"] is False
        and result["error"].startswith("CAMINO_API_TOKEN is not set.")
        and "Approved Integrations" in result["error"]
        for result in results
    )


def test_server_can_return_synthetic_course_data(monkeypatch):
    def fake_client():
        return CanvasClient(
            "FAKE_TEST_TOKEN",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json=[{"id": 42, "name": "Example"}]
                    if request.url.params.get("enrollment_state") == "active"
                    else [],
                )
            ),
        )

    monkeypatch.setattr(server, "CanvasClient", fake_client)
    result = server.list_courses()
    assert result["complete"] is True
    assert result["courses"] == [
        {"id": 42, "name": "Example", "enrollment_state": None, "favorite": False}
    ]
