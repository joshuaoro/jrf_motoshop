"""
Main application factory
"""

import json
import uuid
from datetime import datetime

from flask import Flask, g, jsonify, request
from flask_login import current_user

from app.core.config import config, describe_database, get_config, is_local_database
from app.core.extensions import csrf, db, init_extensions
from app.core.security import (
    init_limiter,
    init_security_middleware,
    register_error_handlers,
)
from app.core.time_utils import now_utc, time_ago


def create_app(config_name=None, overrides=None):
    """Application factory pattern.

    ``overrides`` is a dict applied on top of the selected config class,
    before any extension is initialised. It exists because the config classes
    resolve values (notably the database URL) at *import* time: mutating
    ``os.environ`` after ``app.core.config`` has been imported has no effect,
    which makes "just set DATABASE_URL first" an unreliable way for a test
    harness to redirect the database. Pass it explicitly instead.
    """
    app = Flask(
        __name__,
        template_folder="../../templates",
        static_folder="../../static",
    )

    # Static defaults from the class, then everything environment-derived,
    # then explicit overrides. Validation runs last so it inspects exactly
    # what the app will actually use.
    config_class = config[config_name] if config_name in config else get_config()
    app.config.from_object(config_class)
    app.config.update(config_class.resolve())

    if overrides:
        app.config.update(overrides)

    config_class.validate(app.config)

    # Initialize extensions
    init_extensions(app)

    # Security middleware
    init_security_middleware(app)
    init_limiter(app)

    # Register blueprints before the error handlers so blueprint-scoped
    # handlers are already in place.
    register_blueprints(app)

    register_error_handlers(app)
    register_request_context(app)
    register_shell_and_cli(app)
    register_template_context(app)
    register_core_routes(app)

    # Always say which database this instance is about to talk to. An app
    # silently pointing at the wrong one - production from a dev shell, say -
    # is the kind of thing that should never be a surprise.
    database = describe_database(app.config.get("SQLALCHEMY_DATABASE_URI"))
    app.logger.info(
        "JRF Motoshop starting (env=%s, debug=%s, database=%s)",
        app.config.get("FLASK_ENV"),
        app.debug,
        database,
    )
    if app.debug and not is_local_database(app.config.get("SQLALCHEMY_DATABASE_URI")):
        app.logger.warning(
            "Development mode is pointed at a REMOTE database (%s). "
            "Put a local DATABASE_URL in .env.local to avoid touching it.",
            database,
        )

    return app


# ============================================================
# ROUTES OWNED BY THE APP ITSELF
# ============================================================
def register_core_routes(app):
    """Health and readiness endpoints.

    Note there is deliberately no ``/`` route here: the dashboard blueprint
    already owns ``/``. Registering a second rule for the same path only ever
    shadowed itself - the blueprint rule was matched first and the redirect
    defined here was dead code.
    """

    @app.route("/health")
    def health_check():
        """Liveness + database connectivity, for load balancers and Docker."""
        try:
            db.session.execute(db.text("SELECT 1"))
            return (
                jsonify(
                    {
                        "status": "healthy",
                        "database": "connected",
                        "version": app.config.get("APP_VERSION", "2.0.3"),
                        "timestamp": now_utc().isoformat() + "Z",
                    }
                ),
                200,
            )
        except Exception as exc:
            app.logger.error("Health check failed: %s", exc)
            return (
                jsonify(
                    {
                        "status": "unhealthy",
                        "database": "disconnected",
                        "timestamp": now_utc().isoformat() + "Z",
                    }
                ),
                503,
            )


# ============================================================
# REQUEST CONTEXT
# ============================================================
def register_request_context(app):
    """Attach a correlation id to every request and echo it back."""

    @app.before_request
    def _assign_request_id():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex

    @app.after_request
    def _return_request_id(response):
        response.headers["X-Request-ID"] = g.get("request_id", "")
        return response

    @app.after_request
    def _stamp_api_success(response):
        """Add a `success` boolean to every JSON object the API returns.

        The front-end branches on `data.success`. Most endpoints return the
        saved resource, which has no such key, so a successful create or edit
        read as a failure and the page never refreshed. Stamping it centrally
        keeps the contract uniform instead of relying on each endpoint to
        remember, and never overwrites a value a view set deliberately.
        """
        if not request.path.startswith("/api/"):
            return response
        if not response.is_json or response.direct_passthrough:
            return response

        payload = response.get_json(silent=True)
        if isinstance(payload, dict) and "success" not in payload:
            payload["success"] = response.status_code < 400
            response.set_data(json.dumps(payload, default=str))

        return response

    @app.teardown_request
    def _rollback_failed_session(exc):
        """Never let a failed request leave a dirty session for the next one.

        Connections are pooled and the session is scoped to the app context,
        so an uncommitted failure could otherwise surface inside an unrelated
        later request.
        """
        if exc is not None:
            db.session.rollback()


# ============================================================
# BLUEPRINTS
# ============================================================
def register_blueprints(app):
    """Register all blueprints"""
    from app.api.auth import auth_bp
    from app.api.customers import customers_bp
    from app.api.dashboard import dashboard_bp
    from app.api.notifications import notifications_bp
    from app.api.operations import expenses_bp, maintenance_bp, purchase_orders_bp
    from app.api.parts import parts_bp
    from app.api.realtime import realtime_bp
    from app.api.reports import reports_bp
    from app.api.sales import sales_bp
    from app.api.settings import settings_bp
    from app.api.staff import staff_bp
    from app.api.suppliers import suppliers_bp
    from app.api.system import system_bp

    api_blueprints = (
        (auth_bp, "/api/auth"),
        (parts_bp, "/api/parts"),
        (suppliers_bp, "/api/suppliers"),
        (sales_bp, "/api/sales"),
        (customers_bp, "/api/customers"),
        (expenses_bp, "/api/expenses"),
        (purchase_orders_bp, "/api/purchase-orders"),
        (maintenance_bp, "/api/maintenance"),
        (staff_bp, "/api/staff"),
        (settings_bp, "/api/settings"),
        (notifications_bp, "/api/notifications"),
        (reports_bp, "/api/reports"),
        (dashboard_bp, "/api/dashboard"),
        (realtime_bp, "/api/realtime"),
        (system_bp, "/api/system"),
    )

    for blueprint, prefix in api_blueprints:
        app.register_blueprint(blueprint, url_prefix=prefix)
        # The JSON API authenticates with the session cookie but is called via
        # fetch(); CSRF is enforced by SameSite=Lax plus an explicit token on
        # state-changing browser forms, so the token form check is exempted
        # here to keep the API usable by non-browser clients.
        csrf.exempt(blueprint)

    # Customers and suppliers used to be nested under /api/sales and
    # /api/parts. Mount the same blueprints at those prefixes too so existing
    # callers keep working while the flat paths become canonical.
    legacy_aliases = (
        (customers_bp, "/api/sales/customers", "sales_customers_legacy"),
        (suppliers_bp, "/api/parts/suppliers", "parts_suppliers_legacy"),
    )
    for blueprint, prefix, alias in legacy_aliases:
        app.register_blueprint(blueprint, url_prefix=prefix, name=alias)
        csrf.exempt(blueprint)

    from app.web.customers import customers_web_bp
    from app.web.dashboard import dashboard_web_bp
    from app.web.inventory import inventory_web_bp
    from app.web.operations import (
        expenses_web_bp,
        maintenance_web_bp,
        purchase_orders_web_bp,
    )
    from app.web.reports import reports_web_bp
    from app.web.sales import sales_web_bp
    from app.web.settings import settings_web_bp
    from app.web.staff import staff_web_bp
    from app.web.suppliers import suppliers_web_bp

    web_blueprints = (
        (dashboard_web_bp, None),
        (inventory_web_bp, "/inventory"),
        (suppliers_web_bp, "/suppliers"),
        (purchase_orders_web_bp, "/purchase-orders"),
        (customers_web_bp, "/customers"),
        (sales_web_bp, "/sales"),
        (expenses_web_bp, "/expenses"),
        (maintenance_web_bp, "/maintenance"),
        (reports_web_bp, "/reports"),
        (settings_web_bp, "/settings"),
        (staff_web_bp, "/staff"),
    )

    for blueprint, prefix in web_blueprints:
        if prefix:
            app.register_blueprint(blueprint, url_prefix=prefix)
        else:
            app.register_blueprint(blueprint)


# ============================================================
# CLI / SHELL
# ============================================================
def register_shell_and_cli(app):
    """Register CLI commands and the `flask shell` namespace."""
    from app.cli.commands import (
        backup_db_command,
        cleanup_command,
        create_admin_command,
        init_db_command,
        reindex_command,
        seed_data_command,
    )

    for command in (
        init_db_command,
        create_admin_command,
        seed_data_command,
        backup_db_command,
        cleanup_command,
        reindex_command,
    ):
        app.cli.add_command(command)

    @app.shell_context_processor
    def make_shell_context():
        from app import models

        namespace = {"db": db}
        namespace.update({name: getattr(models, name) for name in models.__all__})
        return namespace


# ============================================================
# TEMPLATE CONTEXT
# ============================================================
def register_template_context(app):
    """Values every template can rely on."""

    @app.context_processor
    def inject_globals():
        return {
            "app_name": "JRF Motorcycle Parts",
            "app_version": app.config.get("APP_VERSION", "2.0.3"),
            "current_year": now_utc().year,
        }

    @app.context_processor
    def inject_notifications():
        """Notification bell contents for the shared layout."""
        empty = {"unread_notifications": 0, "recent_notifications": []}

        if not current_user.is_authenticated:
            return empty

        from app.services.system import NotificationService

        try:
            page = NotificationService.get_user_notifications(current_user.id, page=1, per_page=10)
            return {
                "unread_notifications": NotificationService.get_unread_count(current_user.id),
                "recent_notifications": [n.to_dict() for n in page.items],
            }
        except Exception:
            # The layout renders on every page, including error pages - a
            # notification lookup failure must not cascade into a 500 loop.
            app.logger.exception("Failed to load notifications for layout")
            db.session.rollback()
            return empty

    @app.template_filter("peso")
    def peso(value):
        """Format a number as Philippine pesos."""
        try:
            return f"₱{float(value):,.2f}"
        except (TypeError, ValueError):
            return "₱0.00"

    def _coerce_datetime(value):
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return value if isinstance(value, datetime) else None

    @app.template_filter("localdt")
    def localdt(value, fmt="%Y-%m-%d %H:%M"):
        """Format a datetime, tolerating None and ISO strings."""
        moment = _coerce_datetime(value)
        return moment.strftime(fmt) if moment else "-"

    @app.template_filter("time_ago")
    def time_ago_filter(value):
        """Human-readable relative time, e.g. "5 minutes ago".

        Used by the dashboard activity feed and the notification dropdown.
        Delegates to ``time_utils.time_ago`` so ``Notification.to_dict()``
        (consumed by the notifications page's JS) computes the same string.
        """
        return time_ago(_coerce_datetime(value))
