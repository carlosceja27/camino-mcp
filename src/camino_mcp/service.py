"""Safe allowlisted projections of Camino coursework."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .canvas import AccessDenied, CaminoError

# Submission types that cannot be turned in through Camino (paper, in class, no submission).
OFFLINE_TYPES = {"none", "on_paper", "not_graded", "wiki_page"}
SUBMITTED_STATES = {"submitted", "graded", "pending_review", "complete"}

BUCKETS = {
    "future",
    "past",
    "overdue",
    "upcoming",
    "unsubmitted",
    "ungraded",
    "undated",
}


def positive_id(value, name):
    if isinstance(value, str):
        value = value.strip()
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value), flags=re.ASCII):
        raise ValueError(
            f"{name} must be a positive whole number (for example 12345); "
            "use list_courses or the list tools to find IDs"
        )
    return int(value)


def course_id(value):
    return positive_id(value, "course_id")


def page_slug(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value.strip()):
        raise ValueError("page_url must be a page slug from list_pages (for example 'syllabus')")
    value = value.strip()
    return value


def select(raw, keys):
    return {key: raw[key] for key in keys if key in raw} if isinstance(raw, dict) else None


def safe_filename(value):
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or value.startswith(".")
        or any(char in value for char in ("/", "\\", "\x00", ":"))
        or any(ord(char) < 32 for char in value)
    ):
        raise CaminoError("Unsafe file filename rejected.")
    return value


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
    types = raw.get("submission_types")
    if isinstance(types, list) and all(isinstance(t, str) for t in types):
        view["submission_types"] = types
    submission = raw.get("submission")
    if isinstance(submission, dict):
        view["submission"] = {k: submission.get(k) for k in ("workflow_state", "submitted_at")}
        for key in ("missing", "late", "excused"):
            if isinstance(submission.get(key), bool):
                view["submission"][key] = submission[key]
    return view


def _enrollment(raw):
    enrollments = raw.get("enrollments")
    if not isinstance(enrollments, list):
        return {}
    rows = [e for e in enrollments if isinstance(e, dict)]
    students = [e for e in rows if e.get("type") in {"student", "StudentEnrollment"}]
    return (students or rows or [{}])[0]


class CaminoService:
    def __init__(self, client):
        self.client = client

    def list_courses(self):
        include = ["total_scores", "term"]
        active = self.client.get_pages(
            "/courses", {"enrollment_state": "active", "per_page": 100, "include[]": include}
        )
        pending = self.client.get_pages(
            "/courses",
            {"enrollment_state": "invited_or_pending", "per_page": 100, "include[]": include},
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
            enrollment = _enrollment(raw)
            view = {
                "id": cid,
                "name": raw.get("name"),
                "enrollment_state": enrollment.get("enrollment_state"),
                "favorite": cid in favorite_ids,
            }
            term = raw.get("term")
            if isinstance(term, dict) and isinstance(term.get("name"), str):
                view["term"] = term["name"]
            if isinstance(raw.get("end_at"), str):
                view["end_at"] = raw["end_at"]
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

    def get_assignment(self, cid, assignment_id):
        cid = course_id(cid)
        aid = positive_id(assignment_id, "assignment_id")
        raw = self.client.get_object(f"/courses/{cid}/assignments/{aid}")
        view = assignment_view(raw, cid)
        if view is None:
            raise CaminoError("Camino returned an unexpected assignment.")
        for key in ("description", "submission_types", "unlock_at", "lock_at", "grading_type"):
            if key in raw:
                view[key] = raw[key]
        return {"complete": True, "assignment": view}

    def list_pages(self, cid):
        cid = course_id(cid)
        rows = self.client.get_pages(f"/courses/{cid}/pages", {"per_page": 100})
        return {
            "complete": True,
            "pages": [
                v
                for r in rows
                if (
                    v := select(
                        r, ("page_id", "url", "title", "updated_at", "published", "locked_for_user")
                    )
                )
                is not None
            ],
        }

    def get_page(self, cid, page_url):
        cid = course_id(cid)
        slug = page_slug(page_url)
        raw = self.client.get_object(f"/courses/{cid}/pages/{slug}")
        return {
            "complete": True,
            "page": select(
                raw,
                ("page_id", "url", "title", "body", "updated_at", "published", "locked_for_user"),
            ),
        }

    def list_discussions(self, cid):
        cid = course_id(cid)
        rows = self.client.get_pages(f"/courses/{cid}/discussion_topics", {"per_page": 100})
        return {
            "complete": True,
            "discussions": [
                v
                for r in rows
                if (
                    v := select(
                        r,
                        (
                            "id",
                            "title",
                            "posted_at",
                            "last_reply_at",
                            "published",
                            "locked_for_user",
                        ),
                    )
                )
                is not None
            ],
        }

    def get_discussion(self, cid, topic_id):
        cid = course_id(cid)
        tid = positive_id(topic_id, "topic_id")
        raw = self.client.get_object(f"/courses/{cid}/discussion_topics/{tid}")
        return {
            "complete": True,
            "discussion": select(
                raw,
                (
                    "id",
                    "title",
                    "message",
                    "posted_at",
                    "last_reply_at",
                    "published",
                    "locked_for_user",
                ),
            ),
        }

    def list_announcements(self, cid):
        cid = course_id(cid)
        rows = self.client.get_pages(
            "/announcements", {"context_codes[]": f"course_{cid}", "per_page": 100}
        )
        return {
            "complete": True,
            "announcements": [
                v
                for r in rows
                if (v := select(r, ("id", "title", "message", "posted_at", "html_url"))) is not None
            ],
        }

    def list_conversations(self, cid):
        cid = course_id(cid)
        rows = self.client.get_pages(
            "/conversations", {"filter[]": f"course_{cid}", "per_page": 100}
        )
        return {
            "complete": True,
            "conversations": [
                v
                for r in rows
                if (
                    v := select(
                        r,
                        (
                            "id",
                            "subject",
                            "last_message",
                            "last_message_at",
                            "workflow_state",
                            "context_name",
                            "message_count",
                        ),
                    )
                )
                is not None
            ],
        }

    def get_conversation(self, conversation_id):
        mid = positive_id(conversation_id, "conversation_id")
        raw = self.client.get_object(f"/conversations/{mid}")
        view = select(raw, ("id", "subject", "workflow_state", "context_name"))
        messages = raw.get("messages")
        view["messages"] = [
            v
            for r in (messages if isinstance(messages, list) else [])
            if (v := select(r, ("id", "body", "created_at", "author_id"))) is not None
        ]
        return {"complete": True, "conversation": view}

    def list_files(self, cid):
        cid = course_id(cid)
        rows = self.client.get_pages(f"/courses/{cid}/files", {"per_page": 100})
        return {
            "complete": True,
            "files": [
                v
                for r in rows
                if (
                    v := select(
                        r,
                        (
                            "id",
                            "display_name",
                            "filename",
                            "size",
                            "content-type",
                            "folder_id",
                            "locked_for_user",
                            "hidden_for_user",
                        ),
                    )
                )
                is not None
            ],
        }

    def download_file(self, cid, file_id, destination_dir):
        cid = course_id(cid)
        fid = positive_id(file_id, "file_id")
        if isinstance(destination_dir, str) and destination_dir.strip().startswith("~"):
            destination_dir = str(Path(destination_dir.strip()).expanduser())
        if (
            not isinstance(destination_dir, str)
            or not destination_dir
            or not Path(destination_dir).is_absolute()
        ):
            raise ValueError(
                "destination_dir must be an existing folder given as a full path, "
                "for example /Users/you/Downloads or ~/Downloads"
            )
        directory = Path(destination_dir)
        if not directory.is_dir():
            raise ValueError("destination_dir must be an existing absolute directory")
        raw = self.client.get_object(f"/courses/{cid}/files/{fid}")
        if raw.get("id") != fid:
            raise CaminoError("Camino returned an unexpected file ID.")
        if raw.get("locked_for_user") or raw.get("hidden_for_user"):
            raise CaminoError("File is not available to this user.")
        filename = safe_filename(raw.get("display_name") or raw.get("filename"))
        size = raw.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0 or size > 20_000_000:
            raise CaminoError("File size unknown or exceeds 20 MB limit.")
        path = directory / filename
        if path.exists() or path.is_symlink():
            raise CaminoError("Destination file already exists.")
        try:
            downloaded = self.client.download(cid, fid, path)
        except FileExistsError:
            raise CaminoError("Destination file already exists.") from None
        except OSError:
            raise CaminoError("Cannot write file in destination directory.") from None
        if downloaded != size:
            path.unlink(missing_ok=True)
            raise CaminoError("Downloaded file size did not match Canvas metadata.")
        return {"complete": True, "path": str(path), "size": downloaded, "file_id": fid}

    def check_setup(self):
        me = self.client.get_object("/users/self")
        return {
            "complete": True,
            "connected": True,
            "name": me.get("short_name") or me.get("name"),
            "message": "Camino is connected. Try list_courses, upcoming, or overdue.",
        }

    def _cross_course(self, predicate, now, *, include_ended=True):
        now = now or datetime.now().astimezone()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        results, skipped = [], []
        for course in self.list_courses()["courses"]:
            cid = course["id"]
            if course.get("enrollment_state") not in (None, "active"):
                continue  # invited/pending courses have no readable assignments yet
            if not include_ended and _ended(course, now):
                continue
            try:
                assignments = self.list_assignments(cid)["assignments"]
            except AccessDenied:
                skipped.append({"course_id": cid, "course_name": course.get("name")})
                continue
            for assignment in assignments:
                parsed = _parse_due(assignment.get("due_at"))
                if parsed is not None and predicate(parsed, now, assignment):
                    assignment["course_name"] = course.get("name")
                    results.append(assignment)
        results.sort(key=lambda row: _parse_due(row["due_at"]).astimezone(UTC))
        out = {"complete": not skipped, "as_of": now.isoformat(), "assignments": results}
        if skipped:
            out["skipped_courses"] = skipped
            out["warning"] = (
                "Some courses could not be read (no access or not published yet); "
                "results do not include them."
            )
        return out

    def upcoming(self, days=7, *, now=None):
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 31:
            raise ValueError("days must be a whole number between 1 and 31")
        return self._cross_course(
            lambda due, current, item: (
                current <= due <= current + timedelta(days=days) and not _done(item)
            ),
            now,
        )

    def overdue(self, include_ended_courses=False, *, now=None):
        if not isinstance(include_ended_courses, bool):
            raise ValueError("include_ended_courses must be true or false")  # noqa: TRY004
        result = self._cross_course(
            lambda due, current, item: due < current and not _done(item) and _turn_in_online(item),
            now,
            include_ended=include_ended_courses,
        )
        result["note"] = (
            "Only work that is turned in on Camino and has no submission is listed. "
            "Paper/in-class items and excused work are left out"
            + ("." if include_ended_courses else ", as are courses whose end date has passed.")
        )
        return result


def _parse_due(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _ended(course, now):
    end = _parse_due(course.get("end_at"))
    return end is not None and end < now


def _done(item):
    submission = item.get("submission")
    if not isinstance(submission, dict):
        return False
    return (
        submission.get("workflow_state") in SUBMITTED_STATES
        or bool(submission.get("submitted_at"))
        or submission.get("excused") is True
    )


def _turn_in_online(item):
    if (item.get("submission") or {}).get("missing") is True:
        return True
    types = item.get("submission_types")
    if not isinstance(types, list) or not types:
        return True  # unknown: keep rather than hide possible missing work
    return not set(types) <= OFFLINE_TYPES
