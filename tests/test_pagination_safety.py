import httpx
import pytest

from camino_mcp.canvas import CaminoError, CanvasClient


def test_pagination_rejects_credentials_in_url():
    def handler(request):
        return httpx.Response(
            200,
            json=[],
            headers={
                "Link": '<https://camino.instructure.com/api/v1/courses?access_token=leak>; rel="next"'
            },
        )

    with pytest.raises(CaminoError, match="pagination"):
        CanvasClient("FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler)).get_pages(
            "/courses"
        )


def test_pagination_rejects_encoded_path_traversal():
    def handler(request):
        return httpx.Response(
            200,
            json=[],
            headers={"Link": '<https://camino.instructure.com/api/v1/%2e%2e/private>; rel="next"'},
        )

    with pytest.raises(CaminoError, match="pagination"):
        CanvasClient("FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler)).get_pages(
            "/courses"
        )
