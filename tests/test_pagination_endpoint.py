import httpx
import pytest

from camino_mcp.canvas import CaminoError, CanvasClient


def test_pagination_cannot_switch_to_a_different_api_endpoint():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json=[],
            headers={
                "Link": '<https://camino.instructure.com/api/v1/conversations?page=2>; rel="next"'
            },
        )

    with pytest.raises(CaminoError, match="pagination"):
        CanvasClient("FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler)).get_pages(
            "/courses"
        )
    assert calls == ["/api/v1/courses"]
