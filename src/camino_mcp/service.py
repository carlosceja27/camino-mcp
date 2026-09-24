"""Safe allowlisted projections of Camino coursework."""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from .canvas import CaminoError

BUCKETS = {
    "future",
    "past",
    "overdue",
    "upcoming",
    "unsubmitted",
    "ungraded",
    "undated",
}


def course_id(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value), flags=re.ASCII):
        raise ValueError("course_id must be a positive ASCII integer")
    return int(value)


def safe_link(value):
    if not isinstance(value, str):
        return None
    p = urlsplit(value)
    if p.scheme == "https" and p.netloc == "camino.instructure.com" and not p.fragment:
        return value
    return None


def assignment_view(raw, cid):
    if not isinstance(raw, dict):
        return None
    view = {
        "id": raw.get("id"),
        "course_id": cid,
        "name": raw.get("name"),
        "due_at": raw.get("due_at"),
        "points_possible": raw.get("points_possible"),
    }
    link = safe_link(raw.get("html_url"))
    if link:
        view["html_url"] = link
    submission = raw.get("submission")
    if isinstance(submission, dict):
        view["submission"] = {k: submission.get(k) for k in ("workflow_state", "submitted_at")}
    return view


class CaminoService:
    def __init__(self, client):
        self.client = client

    def list_courses(self):
        active = self.client.get_pages(
            "/courses", {"enrollment_state": "active", "per_page": 100, "include[]": "total_scores"}
        )
        pending = self.client.get_pages(
            "/courses",
            {
                "enrollment_state": "invited_or_pending",
                "per_page": 100,
                "include[]": "total_scores",
            },
        )
        favorites = self.client.get_pages("/users/self/favorites/courses", {"per_page": 100})
        favorite_ids = {c.get("id") for c in favorites if isinstance(c, dict)}
        merged = {}
        for raw in active + pending + favorites:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), int):
                continue
            cid = raw["id"]
            if cid in merged:
                continue
            enrollments = raw.get("enrollments") or []
            enrollment = enrollments[0] if enrollments and isinstance(enrollments[0], dict) else {}
            view = {
                "id": cid,
                "name": raw.get("name"),
                "enrollment_state": enrollment.get("enrollment_state"),
                "favorite": cid in favorite_ids,
            }
            for key in ("computed_current_grade", "computed_current_score"):
                if enrollment.get(key) is not None:
                    view[key] = enrollment[key]
            merged[cid] = view
        return {"complete": True, "courses": sorted(merged.values(), key=lambda c: c["id"])}

    def grades(self):
        grades = []
        for course in self.list_courses()["courses"]:
            row = {"course_id": course["id"], "course_name": course.get("name")}
            for key in ("computed_current_grade", "computed_current_score"):
                if key in course:
                    row[key] = course[key]
            grades.append(row)
        return {"complete": True, "grades": grades}

    def list_assignments(self, cid, bucket=None):
        cid = course_id(cid)
        if bucket is not None and bucket not in BUCKETS:
            raise ValueError("bucket is not a supported Canvas assignment bucket")
        params = {"per_page": 100, "order_by": "due_at", "include[]": "submission"}
        if bucket:
            params["bucket"] = bucket
        rows = self.client.get_pages(f"/courses/{cid}/assignments", params)
        return {
            "complete": True,
            "assignments": [v for row in rows if (v := assignment_view(row, cid)) is not None],
        }

    def _cross_course(self, predicate, now):
        now = now or datetime.now().astimezone()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        results = []
        for course in self.list_courses()["courses"]:
            cid = course["id"]
            try:
                assignments = self.list_assignments(cid)["assignments"]
            except CaminoError as exc:
                raise CaminoError(
                    f"Could not read course {cid}; cross-course results are incomplete: {exc}"
                ) from None
            for assignment in assignments:
                due = assignment.get("due_at")
                if not isinstance(due, str):
                    continue
                try:
                    parsed = datetime.fromisoformat(due)
                except ValueError:
                    continue
                if parsed.tzinfo is None:
                    continue
                if predicate(parsed, now, assignment):
                    assignment["course_name"] = course.get("name")
                    results.append(assignment)
        results.sort(key=lambda row: datetime.fromisoformat(row["due_at"]).astimezone(UTC))
        return {"complete": True, "as_of": now.isoformat(), "assignments": results}

    def upcoming(self, days=7, *, now=None):
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 31:
            raise ValueError("days must be an integer between 1 and 31")
        return self._cross_course(
            lambda due, current, item: (
                current <= due <= current + timedelta(days=days) and not _submitted(item)
            ),
            now,
        )

    def overdue(self, *, now=None):
        return self._cross_course(
            lambda due, current, item: due < current and not _submitted(item), now
        )


def _submitted(item):
    state = item.get("submission", {}).get("workflow_state")
    return state in {"submitted", "graded", "pending_review"} or bool(
        item.get("submission", {}).get("submitted_at")
    )
