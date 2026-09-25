import httpx
import pytest

from camino_mcp.canvas import CaminoError, CanvasClient, _safe_download_url
from camino_mcp.service import CaminoService


def service(handler):
    return CaminoService(CanvasClient("FAKE_TEST_TOKEN", transport=httpx.MockTransport(handler)))


def test_assignment_detail_includes_description_but_excludes_arbitrary_fields():
    def handler(request):
        assert request.url.path == "/api/v1/courses/2/assignments/3"
        return httpx.Response(
            200,
            json={
                "id": 3,
                "name": "Essay",
                "description": "<p>Write it</p>",
                "submission_types": ["online_upload"],
                "private_field": "no",
            },
        )

    result = service(handler).get_assignment("2", "3")
    assert result["assignment"]["description"] == "<p>Write it</p>"
    assert "private_field" not in result["assignment"]


def test_pages_list_and_detail():
    def handler(request):
        if request.url.path.endswith("/pages"):
            return httpx.Response(
                200, json=[{"url": "syllabus", "title": "Syllabus", "body": "not listed"}]
            )
        assert request.url.path.endswith("/pages/syllabus")
        return httpx.Response(
            200, json={"url": "syllabus", "title": "Syllabus", "body": "<p>Read</p>"}
        )

    client = service(handler)
    assert "body" not in client.list_pages("2")["pages"][0]
    assert client.get_page("2", "syllabus")["page"]["body"] == "<p>Read</p>"


@pytest.mark.parametrize("slug", ["../secret", "a/b", "a%2fb", "a?b", "", "..", "a\\b"])
def test_invalid_slug_rejected_before_network(slug):
    def forbidden(_):
        raise AssertionError("network requested")

    with pytest.raises(ValueError):
        service(forbidden).get_page("2", slug)


def test_discussion_topics_list_and_detail():
    def handler(request):
        assert request.method == "GET"
        if request.url.path.endswith("/discussion_topics"):
            return httpx.Response(
                200, json=[{"id": 4, "title": "Week 1", "message": "<p>Hello</p>"}]
            )
        assert request.url.path.endswith("/discussion_topics/4")
        return httpx.Response(200, json={"id": 4, "title": "Week 1", "message": "<p>Hello</p>"})

    client = service(handler)
    assert client.list_discussions("2")["discussions"][0]["title"] == "Week 1"
    assert client.get_discussion("2", "4")["discussion"]["message"] == "<p>Hello</p>"


def test_course_announcements_and_inbox_conversations():
    def handler(request):
        if request.url.path.endswith("/announcements"):
            assert request.url.params.get("context_codes[]") == "course_2"
            return httpx.Response(200, json=[{"id": 8, "title": "Update", "message": "<p>Hi</p>"}])
        if request.url.path.endswith("/conversations/9"):
            return httpx.Response(
                200,
                json={
                    "id": 9,
                    "subject": "Question",
                    "messages": [{"id": 10, "body": "Reply", "author_id": 5}],
                },
            )
        assert request.url.params.get("filter[]") == "course_2"
        return httpx.Response(
            200, json=[{"id": 9, "subject": "Question", "last_message": "Preview"}]
        )

    client = service(handler)
    assert client.list_announcements("2")["announcements"][0]["message"] == "<p>Hi</p>"
    assert client.list_conversations("2")["conversations"][0]["subject"] == "Question"
    assert client.get_conversation("9")["conversation"]["messages"][0]["body"] == "Reply"


def test_file_listing_and_download_to_explicit_folder(tmp_path):
    def handler(request):
        assert request.headers["Authorization"] == "Bearer FAKE_TEST_TOKEN"
        if request.url.path.endswith("/files"):
            return httpx.Response(
                200,
                json=[
                    {"id": 7, "display_name": "course.pdf", "size": 5, "url": "https://evil.test"}
                ],
            )
        if request.url.path.endswith("/files/7"):
            return httpx.Response(
                200, json={"id": 7, "display_name": "course.pdf", "size": 5, "folder_id": 1}
            )
        assert request.url.path == "/courses/2/files/7/download"
        return httpx.Response(200, content=b"hello")

    client = service(handler)
    assert "url" not in client.list_files("2")["files"][0]
    path = client.download_file("2", "7", str(tmp_path))["path"]
    assert (tmp_path / "course.pdf").read_bytes() == b"hello"
    assert path == str(tmp_path / "course.pdf")


@pytest.mark.parametrize("name", ["../../evil", "../evil", "/tmp/evil", "\\evil", "a/b", "a\\b"])
def test_download_unsafe_filename_rejected(tmp_path, name):
    def handler(request):
        return httpx.Response(200, json={"id": 7, "display_name": name, "size": 5})

    with pytest.raises(CaminoError, match="filename"):
        service(handler).download_file("2", "7", str(tmp_path))


def test_download_rejects_redirect_without_following(tmp_path):
    def handler(request):
        if request.url.path.startswith("/api/v1"):
            return httpx.Response(200, json={"id": 7, "display_name": "x.pdf", "size": 5})
        return httpx.Response(302, headers={"location": "https://evil.test/secret"})

    with pytest.raises(CaminoError, match="redirect"):
        service(handler).download_file("2", "7", str(tmp_path))
    assert not list(tmp_path.iterdir())


def test_download_limit_and_no_overwrite(tmp_path):
    (tmp_path / "x.pdf").write_bytes(b"old")

    def handler(request):
        if request.url.path.startswith("/api/v1"):
            return httpx.Response(200, json={"id": 7, "display_name": "x.pdf", "size": 5})
        raise AssertionError("download should not start")

    with pytest.raises(CaminoError, match="exists"):
        service(handler).download_file("2", "7", str(tmp_path))
    assert (tmp_path / "x.pdf").read_bytes() == b"old"


def test_cdn_redirect_without_bearer(tmp_path):
    def handler(request):
        if request.url.host == "camino.instructure.com":
            if request.url.path.startswith("/api/v1"):
                return httpx.Response(200, json={"id": 7, "display_name": "file.pdf", "size": 3})
            return httpx.Response(
                302,
                headers={"location": "https://abc.canvas-user-content.com/file.pdf?signature=x"},
            )
        assert request.url.host == "abc.canvas-user-content.com"
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"pdf")

    result = service(handler).download_file(2, 7, str(tmp_path))
    assert result["size"] == 3
    assert (tmp_path / "file.pdf").read_bytes() == b"pdf"


@pytest.mark.parametrize(
    "url",
    [
        "http://abc.canvas-user-content.com/file",
        "https://abc.canvas-user-content.com.evil.test/file",
        "https://canvas-user-content.com/file",
        "https://user@abc.canvas-user-content.com/file",
        "https://abc.canvas-user-content.com:444/file",
        "https://abc.canvas-user-content.com/file#fragment",
    ],
)
def test_unsafe_cdn_urls(url):
    assert not _safe_download_url(url)


def test_mismatched_download_size_is_removed(tmp_path):
    def handler(request):
        if request.url.path.startswith("/api/v1"):
            return httpx.Response(200, json={"id": 7, "display_name": "file.pdf", "size": 10})
        return httpx.Response(200, content=b"short")

    with pytest.raises(CaminoError, match="size did not match"):
        service(handler).download_file(2, 7, str(tmp_path))
    assert not (tmp_path / "file.pdf").exists()


def test_locked_file_rejected(tmp_path):
    def handler(request):
        assert request.url.path.startswith("/api/v1")
        return httpx.Response(
            200, json={"id": 7, "display_name": "file.pdf", "size": 3, "locked_for_user": True}
        )

    with pytest.raises(CaminoError, match="not available"):
        service(handler).download_file(2, 7, str(tmp_path))


def test_download_rejects_oversize_before_fetch(tmp_path):
    def handler(request):
        if request.url.path.startswith("/api/v1"):
            return httpx.Response(200, json={"id": 7, "display_name": "x.pdf", "size": 21_000_000})
        raise AssertionError("oversize download should not start")

    with pytest.raises(CaminoError, match="size"):
        service(handler).download_file("2", "7", str(tmp_path))
