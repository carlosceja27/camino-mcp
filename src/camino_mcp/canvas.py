"""Bounded, same-origin Canvas API reader. No token or response body in errors."""

import os
import re
import time
from urllib.parse import urlsplit

import httpx

BASE = "https://camino.instructure.com/api/v1"
SETUP_HINT = (
    "See the README section 'Getting your Camino API token': Camino -> Account -> Settings -> "
    "Approved Integrations -> + New Access Token. Never paste the token into an AI chat."
)
MISSING_TOKEN = f"CAMINO_API_TOKEN is not set. {SETUP_HINT}"
BAD_TOKEN = (
    "Camino rejected the API token (invalid, expired, or revoked). Generate a new token and "
    f"restart your AI app. {SETUP_HINT}"
)
RETRIES = 3


class CaminoError(Exception):
    """Safe, user-displayable error without provider details."""


class AccessDenied(CaminoError):
    """The token is valid, but this particular resource is not available to the user."""


class CanvasClient:
    def __init__(self, token=None, *, transport=None, max_pages=20, sleep=None):
        raw = token if token is not None else os.environ.get("CAMINO_API_TOKEN", "")
        self.token = raw.strip()
        self.max_pages = max_pages
        self._sleep = sleep
        self._transport = transport
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {self.token}"} if self.token else {},
            transport=transport,
            timeout=15,
            follow_redirects=False,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _require_token(self):
        if not self.token:
            raise CaminoError(MISSING_TOKEN)

    def _get(self, url, params=None):
        for attempt in range(RETRIES):
            try:
                result = self._client.get(url, params=params)
            except httpx.TimeoutException:
                raise CaminoError(
                    "Camino took too long to respond. Try again in a minute."
                ) from None
            except httpx.RequestError:
                raise CaminoError(
                    "Could not reach Camino. Check your internet connection and try again."
                ) from None
            if _is_throttled(result) and attempt < RETRIES - 1:
                (self._sleep or time.sleep)(1 + attempt)
                continue
            return result
        raise AssertionError("unreachable")  # pragma: no cover

    def get_object(self, path, params=None):
        """Read a single JSON object from the same-origin Canvas API."""
        self._require_token()
        if not _safe_path(path):
            raise CaminoError("Invalid API path.")
        result = self._get(BASE + path, params)
        _check_response(result)
        try:
            item = result.json()
        except ValueError:
            raise CaminoError("Camino returned an invalid JSON response.") from None
        if not isinstance(item, dict):
            raise CaminoError("Camino returned an unexpected response shape.")
        return item

    def download(self, course_id, file_id, destination, limit=20_000_000):
        """Stream a course file without accepting redirects or overwriting files."""
        self._require_token()
        url = f"https://camino.instructure.com/courses/{course_id}/files/{file_id}/download"
        try:
            with self._client.stream("GET", url) as response:
                if response.status_code == 302:
                    target = response.headers.get("location", "")
                    # Follow only the Canvas-managed CDN chain, without the bearer token.
                    with httpx.Client(
                        transport=self._transport, timeout=30, follow_redirects=False
                    ) as cdn:
                        for _ in range(3):
                            if not _safe_download_url(target):
                                raise CaminoError("Unsafe file download redirect rejected.")
                            with cdn.stream("GET", target) as file_response:
                                if file_response.status_code in (301, 302, 303, 307, 308):
                                    target = file_response.headers.get("location", "")
                                    continue
                                return _write_download(file_response, destination, limit)
                        raise CaminoError("File download redirect limit reached.")
                return _write_download(response, destination, limit)
        except httpx.RequestError:
            raise CaminoError(
                "Could not download the file from Camino. Check your connection and try again."
            ) from None

    def get_pages(self, path, params=None):
        self._require_token()
        if not _safe_path(path):
            raise CaminoError("Invalid API path.")
        url = BASE + path
        requested_path = urlsplit(url).path
        seen = set()
        items = []
        for _ in range(self.max_pages):
            if not _safe_api_url(url) or urlsplit(url).path != requested_path or url in seen:
                raise CaminoError("Unsafe or looping pagination link.")
            seen.add(url)
            result = self._get(url, params if len(seen) == 1 else None)
            _check_response(result)
            try:
                page = result.json()
            except ValueError:
                raise CaminoError("Camino returned an invalid JSON response.") from None
            if not isinstance(page, list):
                raise CaminoError("Camino returned an unexpected response shape.")
            items.extend(page)
            url = _next_url(result.headers.get("Link", ""))
            if url is None:
                return items
            if not _safe_api_url(url) or urlsplit(url).path != requested_path:
                raise CaminoError("Unsafe pagination link rejected.")
        raise CaminoError("Pagination page limit reached; results may be incomplete.")


def _safe_path(path):
    return (
        isinstance(path, str)
        and path.startswith("/")
        and not path.startswith("//")
        and not any(character in path for character in ("%", "\\", "?", "#"))
        and not any(segment in {".", ".."} for segment in path.split("/"))
    )


def _body_text(result):
    try:
        return result.text[:2000].lower()
    except httpx.ResponseNotRead:  # streamed download bodies
        return ""


def _is_throttled(result):
    if result.status_code == 429:
        return True
    # Canvas signals throttling as 403 "Rate Limit Exceeded".
    return result.status_code == 403 and (
        "rate limit exceeded" in _body_text(result)
        or result.headers.get("X-Rate-Limit-Remaining", "").strip() in {"0", "0.0"}
    )


def _is_bad_token(result):
    # Canvas uses 401 both for bad tokens and for "user not authorized" on a resource.
    # Only an invalid/expired token carries WWW-Authenticate or an access-token message.
    body = _body_text(result)
    return (
        "www-authenticate" in result.headers
        or "invalid access token" in body
        or "expired" in body
        or not body.strip()
    )


def _check_response(result):
    status = result.status_code
    if _is_throttled(result):
        raise CaminoError("Camino is rate-limiting requests right now; wait a minute and retry.")
    if status == 401:
        if _is_bad_token(result):
            raise CaminoError(BAD_TOKEN)
        raise AccessDenied("You don't have access to this in Camino (it may be unpublished).")
    if status == 403:
        raise AccessDenied("You don't have access to this in Camino (it may be unpublished).")
    if status == 404:
        raise AccessDenied(
            "Not found in Camino. Check the ID, or the course may not use this feature."
        )
    if status >= 500:
        raise CaminoError(f"Camino is having problems (HTTP {status}); try again later.")
    if status >= 300:
        raise CaminoError(f"Camino API request failed (HTTP {status}).")


def _safe_download_url(url):
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        return (
            parts.scheme == "https"
            and parts.port in (None, 443)
            and (
                (host.endswith(".canvas-user-content.com") and host != "canvas-user-content.com")
                or host
                in {"inst-fs-iad-prod.inscloudgate.net", "cdn.inst-fs-iad-prod.inscloudgate.net"}
            )
            and parts.username is None
            and parts.password is None
            and not parts.fragment
        )
    except ValueError:
        return False


def _write_download(response, destination, limit):
    if response.status_code >= 300:
        response.read()
    _check_response(response)
    if response.headers.get("content-type", "").lower().startswith("text/html"):
        raise CaminoError("File download returned a web page instead of a file.")
    with open(destination, "xb") as output:
        try:
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise CaminoError("File size limit exceeded.")
                output.write(chunk)
        except BaseException:
            output.close()
            destination.unlink(missing_ok=True)
            raise
    return size


def _safe_api_url(url):
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.netloc == "camino.instructure.com"
        and (parts.path == "/api/v1" or parts.path.startswith("/api/v1/"))
        and not parts.username
        and not parts.password
        and not parts.fragment
        and "access_token" not in parts.query.lower()
    )


def _next_url(header):
    for part in header.split(","):
        match = re.match(r"\s*<([^>]+)>\s*;(.*)", part)
        if match and re.search(r'\brel\s*=\s*"?next"?(?:\s*;|\s*$)', match.group(2)):
            return match.group(1)
    return None
