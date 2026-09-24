import httpx
import pytest

from camino_mcp.canvas import CanvasClient
from camino_mcp.service import CaminoService


@pytest.mark.parametrize("bucket", ["graded", "submitted"])
def test_unsupported_canvas_bucket_is_rejected_without_network(bucket):
    client = CanvasClient(
        "FAKE_TEST_TOKEN", transport=httpx.MockTransport(lambda _: pytest.fail("network requested"))
    )
    with pytest.raises(ValueError, match="bucket"):
        CaminoService(client).list_assignments(1, bucket)
