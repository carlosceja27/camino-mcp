import httpx

from camino_mcp.canvas import CanvasClient
from camino_mcp.service import CaminoService


def test_grades_keep_score_even_when_letter_grade_missing():
    def handler(request):
        if request.url.path.endswith("favorites/courses"):
            return httpx.Response(200, json=[])
        if request.url.params.get("enrollment_state") == "active":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 42,
                        "name": "Course",
                        "enrollments": [
                            {"computed_current_score": 88.5, "computed_current_grade": None}
                        ],
                    }
                ],
            )
        return httpx.Response(200, json=[])

    service = CaminoService(CanvasClient("FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler)))
    assert service.grades() == {
        "complete": True,
        "grades": [{"course_id": 42, "course_name": "Course", "computed_current_score": 88.5}],
    }
