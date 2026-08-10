"""
Shared helpers for the JSON API blueprints.

These exist to remove three bugs that were repeated across every endpoint:

* ``except Exception as e: ... e.messages`` - only ``ValidationError`` carries
  ``.messages``, so any other error raised a second ``AttributeError`` inside
  the handler and turned a 400 into a 500.
* ``datetime.fromisoformat(request.args[...])`` with no guard - a malformed
  ``?start_date=`` produced an unhandled ``ValueError`` (500 instead of 400).
* Ad-hoc pagination maths duplicated in a dozen places, with
  ``(total + per_page - 1) // per_page`` recomputed from the request instead of
  taken from the paginator.
"""

from datetime import datetime, time
from functools import wraps

from flask import current_app, jsonify, request
from flask_login import current_user
from marshmallow import ValidationError


class ApiError(Exception):
    """Raised to return a specific status code from anywhere in a view."""

    def __init__(self, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details

    def to_response(self):
        payload = {"error": self.message, "message": self.message, "success": False}
        if self.details:
            payload["details"] = self.details
        return jsonify(payload), self.status


def error(message: str, status: int = 400, **extra):
    """Build a consistent JSON error response.

    The text is repeated under ``message`` as well as ``error``: several
    front-end handlers read ``data.message``, and without it they fell back to
    a generic string and threw away the specific reason.
    """
    payload = {"error": message, "message": message, "success": False}
    payload.update(extra)
    return jsonify(payload), status


def load_json(schema, *, partial: bool = False):
    """Validate the request body against ``schema``.

    Raises ``ApiError`` (400/415) instead of leaking a marshmallow exception,
    and never assumes the caught exception has ``.messages``.
    """
    if not request.is_json:
        raise ApiError("Content-Type must be application/json", 415)

    try:
        payload = request.get_json(silent=False)
    except Exception:
        raise ApiError("Request body is not valid JSON", 400)

    if payload is None:
        raise ApiError("Request body is required", 400)

    try:
        return schema.load(payload, partial=partial)
    except ValidationError as exc:
        raise ApiError("Validation failed", 400, details=exc.messages)


def load_form(schema, form, *, partial: bool = False):
    """Validate an HTML form submission against ``schema``.

    Multi-value fields (``<select multiple>``, checkbox groups) are collapsed
    correctly: a plain ``dict(form)`` would keep only the first value.
    """
    data = {}
    for key in form:
        values = form.getlist(key)
        data[key] = values if len(values) > 1 else values[0]

    # A List field posted with a single selection still needs to be a list.
    for name, field in schema.fields.items():
        key = field.data_key or name
        if key in data and _is_list_field(field) and not isinstance(data[key], list):
            data[key] = [data[key]] if data[key] not in ("", None) else []

    return schema.load(data, partial=partial)


def _is_list_field(field):
    from marshmallow import fields as mm_fields

    return isinstance(field, mm_fields.List)


def parse_date_arg(name: str, *, end_of_day: bool = False):
    """Read an ISO-8601 date/datetime query argument.

    Returns ``None`` when absent. Raises ``ApiError`` (400) when malformed,
    rather than letting ``ValueError`` escape as a 500.

    A bare date used as an upper bound is widened to the end of that day, so
    ``?end_date=2026-08-09`` includes sales made during 2026-08-09.
    """
    raw = request.args.get(name)
    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise ApiError(
            f"Invalid '{name}': expected ISO-8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
            400,
        )

    if end_of_day and len(raw) == 10:
        parsed = datetime.combine(parsed.date(), time.max)
    return parsed


def pagination_args(default_per_page: int = 20):
    """Read and clamp ``?page=`` / ``?per_page=``."""
    max_per_page = current_app.config.get("MAX_PAGE_SIZE", 100)
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = request.args.get("per_page", default_per_page, type=int) or default_per_page
    per_page = max(1, min(per_page, max_per_page))
    return page, per_page


def pagination_meta(page: int, per_page: int, total: int) -> dict:
    """Uniform pagination block for list responses."""
    pages = (total + per_page - 1) // per_page if per_page else 0
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


# ============================================================
# AUTHORISATION DECORATORS
# ============================================================
def permission_required(*checks: str):
    """Require that ``current_user`` passes at least one named permission.

    ``checks`` are method names on the user model, e.g.
    ``@permission_required('can_manage_inventory')``.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return error("Authentication required", 401)
            for check in checks:
                method = getattr(current_user, check, None)
                if callable(method) and method():
                    return view(*args, **kwargs)
            return error("Insufficient permissions", 403)

        return wrapper

    return decorator


def admin_required(view):
    """Restrict a view to administrators."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return error("Authentication required", 401)
        if not current_user.is_admin():
            return error("Administrator access required", 403)
        return view(*args, **kwargs)

    return wrapper


def register_api_error_handler(blueprint):
    """Translate ``ApiError`` into a JSON response for one blueprint."""

    @blueprint.errorhandler(ApiError)
    def _handle(exc):
        return exc.to_response()
