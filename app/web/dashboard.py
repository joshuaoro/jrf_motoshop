"""
Web dashboard blueprint - login, dashboard and notifications pages.
"""

import logging
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.core.extensions import db, limiter
from app.core.time_utils import now_utc
from app.models import User
from app.services.dashboard import DashboardService
from app.services.system import NotificationService

dashboard_web_bp = Blueprint("dashboard_web", __name__, template_folder="../../templates")
logger = logging.getLogger(__name__)


def _config_limit(key: str):
    """Rate-limit a view with a limit string read from config per request."""
    if limiter is None:
        return lambda view: view
    return limiter.limit(lambda: current_app.config[key])


def _safe_next_url(candidate: str) -> str | None:
    """Validate a ?next= redirect target.

    Only same-origin, path-only targets are accepted. The previous check was
    ``next_page.startswith('/')``, which allows ``//evil.example.com`` - a
    protocol-relative URL that browsers treat as an absolute off-site link,
    making the login page an open redirect.
    """
    if not candidate:
        return None

    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return None
    if not candidate.startswith("/") or candidate.startswith("//"):
        return None
    return candidate


@dashboard_web_bp.route("/")
@dashboard_web_bp.route("/dashboard")
@login_required
def index():
    """Dashboard home page"""
    stats = DashboardService.get_stats()

    return render_template(
        "dashboard.html",
        recent_activities=DashboardService.get_activities(limit=10),
        unread_notifications=NotificationService.get_unread_count(current_user.id),
        **stats,
    )


@dashboard_web_bp.route("/login", methods=["GET", "POST"])
@_config_limit("RATELIMIT_LOGIN")
def login():
    """Web login page"""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_web.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") in ("on", "true", "1")

        if not email or not password:
            flash("Email and password are required", "error")
            return render_template("login.html"), 400

        user = User.query.filter(User.email == email).first()

        # One message for both "unknown email" and "wrong password" so the
        # form cannot be used to discover which addresses are registered.
        if not user or not user.check_password(password):
            logger.warning("Failed web login for %s from %s", email, request.remote_addr)
            flash("Invalid email or password", "error")
            return render_template("login.html"), 401

        if not user.is_active:
            flash("Account is disabled. Contact an administrator.", "error")
            return render_template("login.html"), 403

        login_user(user, remember=remember)
        user.last_login = now_utc()
        db.session.commit()

        logger.info("Web login: %s (%s)", user.email, user.role)
        flash(f"Welcome back, {user.name}!", "success")

        return redirect(_safe_next_url(request.args.get("next")) or url_for("dashboard_web.index"))

    return render_template("login.html")


@dashboard_web_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Web logout.

    POST only: a GET logout can be triggered by any third-party page embedding
    an <img src="/logout">, which is a cross-site request forgery even though
    the impact is only a nuisance.
    """
    logout_user()
    flash("You have been logged out", "success")
    return redirect(url_for("dashboard_web.login"))


@dashboard_web_bp.route("/notifications")
@login_required
def notifications():
    """Notifications page"""
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = 20

    paginated = NotificationService.get_user_notifications(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        unread_only=request.args.get("unread_only", "false").lower() == "true",
    )

    return render_template(
        "notifications.html",
        notifications=[n.to_dict() for n in paginated.items],
        pagination={
            "page": paginated.page,
            "per_page": paginated.per_page,
            "total": paginated.total,
            "pages": paginated.pages,
        },
        unread_count=NotificationService.get_unread_count(current_user.id),
    )
