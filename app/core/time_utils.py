"""
Timezone helper.

The application stores every timestamp as **naive UTC** — Python naive
``datetime`` objects written to plain ``db.DateTime`` columns. Serialized API
values are naive ISO strings; some sites manually append ``"Z"``, and the
``time_ago`` template filter deliberately strips tzinfo before comparing. The
whole codebase is built on naive-vs-naive comparison, so it must stay that way.

``datetime.utcnow()`` produced a naive UTC timestamp but is deprecated
(emits a ``DeprecationWarning`` on Python 3.12, which this project's pytest
``filterwarnings`` turns into an error). ``now_utc`` is its exact-equivalent
replacement: it still yields a naive UTC ``datetime``, so no comparison,
column, serializer or filter changes are required anywhere.
"""

from datetime import UTC, datetime


def now_utc() -> datetime:
    """The current time as a naive UTC ``datetime``.

    Equivalent to the deprecated ``datetime.utcnow()``: same naive value,
    no tzinfo attached. Use everywhere a "now" UTC timestamp is needed.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def time_ago(moment: datetime | None) -> str:
    """Human-readable relative time, e.g. "5 minutes ago".

    Shared by the ``time_ago`` template filter and ``Notification.to_dict()``
    so the header dropdown (server-rendered) and the notifications page
    (rendered from the JSON API) always agree.
    """
    if moment is None:
        return ""

    # Compare naive-to-naive; model timestamps are stored as naive UTC.
    if moment.tzinfo is not None:
        moment = moment.replace(tzinfo=None)

    seconds = (now_utc() - moment).total_seconds()
    if seconds < 0:
        return "just now"

    for limit, divisor, unit in (
        (60, 1, "second"),
        (3600, 60, "minute"),
        (86400, 3600, "hour"),
        (2592000, 86400, "day"),
        (31536000, 2592000, "month"),
    ):
        if seconds < limit:
            count = int(seconds // divisor)
            if count <= 0:
                return "just now"
            return f"{count} {unit}{'s' if count != 1 else ''} ago"

    years = int(seconds // 31536000)
    return f"{years} year{'s' if years != 1 else ''} ago"
