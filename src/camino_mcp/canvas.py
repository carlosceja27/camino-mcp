"""Bounded, same-origin Canvas API reader. No token or response body in errors."""

import os
import re
import time
from urllib.parse import urlsplit

import httpx

BASE = "https://camino.instructure.com/api/v1"


class CaminoError(Exception):
    """Safe, user-displayable error without provider details."""


class CanvasClient:
    def __init__(self, token=None, *, transport=None, max_pages=20):
        self.token = token if token is not None else os.environ.get("CAMINO_API_TOKEN", "")
        self.max_pages = max_pages
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {self.token}"} if self.token else {},
            transport=transport,
            timeout=15,
            follow_redirects=False,
        )

    def get_pages(self, path, params=None):
        if not self.token:
            raise CaminoError("CAMINO_API_TOKEN is not set.")
        if (
            not path.startswith("/")
            or path.startswith("//")
            or "%" in path
            or "\\" in path
            or any(segment in {".", ".."} for segment in path.split("/"))
        ):
            raise CaminoError("Invalid API path.")
        url = BASE + path
        requested_path = urlsplit(url).path
        seen = set()
        items = []
        for _ in range(self.max_pages):
            if not _safe_api_url(url) or urlsplit(url).path != requested_path or url in seen:
                raise CaminoError("Unsafe or looping pagination link.")
            seen.add(url)
            for attempt in range(3):
                try:
                    result = self._client.get(url, params=params if len(seen) == 1 else None)
                except httpx.RequestError:
                    raise CaminoError("Camino network request failed.") from None
                if result.status_code == 429 and attempt < 2:
                    time.sleep(min(1 + attempt, 2))
                    continue
                break
            if result.status_code == 401:
                raise CaminoError("Camino authentication failed; check or renew the API token.")
            if result.status_code == 403:
                raise CaminoError("Camino denied access to this resource.")
            if result.status_code == 429:
                raise CaminoError("Camino rate limit reached; retry later.")
            if result.status_code >= 300:
                raise CaminoError(f"Camino API request failed (HTTP {result.status_code}).")
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


def _safe_api_url(url):
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.netloc == "camino.instructure.com"
        and (parts.path == "/api/v1" or parts.path.startswith("/api/v1/"))
        and not parts.username
        and not parts.password
        and not parts.fragment
    )


def _next_url(header):
    for part in header.split(","):
        match = re.match(r"\s*<([^>]+)>\s*;(.*)", part)
        if match and re.search(r'\brel\s*=\s*"?next"?(?:\s*;|\s*$)', match.group(2)):
            return match.group(1)
    return None
