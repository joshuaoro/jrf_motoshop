"""
Security middleware, rate limiting and error handling.
"""

import logging
import time
from functools import wraps

from flask import g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix


class SecurityHeadersMiddleware:
    """Add security headers to all responses."""

    # Headers we own. Any value already set by the app is replaced rather than
    # duplicated - appending blindly produced two X-Frame-Options headers,
    # which some proxies reject outright.
    STATIC_HEADERS = (
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
        ("Permissions-Policy", "geolocation=(), microphone=(), camera=()"),
        ("Cross-Origin-Opener-Policy", "same-origin"),
        ("Cross-Origin-Resource-Policy", "same-origin"),
    )

    def __init__(self, flask_app, wsgi_app=None):
        self.flask_app = flask_app
        self.wsgi_app = wsgi_app or flask_app.wsgi_app
        csp = flask_app.config.get("CONTENT_SECURITY_POLICY", {})
        self.csp_header = "; ".join(f"{k} {v}" for k, v in csp.items()) if csp else None
        self.hsts = not flask_app.debug and not flask_app.testing

    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            managed = {name.lower() for name, _ in self.STATIC_HEADERS}
            managed.add("server")
            if self.csp_header:
                managed.add("content-security-policy")
            if self.hsts:
                managed.add("strict-transport-security")

            # Drop any pre-existing copies of the headers we manage.
            #
            # "server" is in that set, but note the limit: gunicorn and the
            # werkzeug dev server emit `Server:` at the HTTP layer, *after*
            # WSGI, so a middleware cannot remove it. Suppressing the banner in
            # production is the reverse proxy's job - nginx.conf sets
            # `server_tokens off` and `proxy_hide_header Server`.
            headers = [(k, v) for k, v in headers if k.lower() not in managed]
            headers.extend(self.STATIC_HEADERS)

            if self.csp_header:
                headers.append(("Content-Security-Policy", self.csp_header))
            if self.hsts:
                headers.append(
                    (
                        "Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains",
                    )
                )

            return start_response(status, headers, exc_info)

        return self.wsgi_app(environ, custom_start_response)


class RequestLoggingMiddleware:
    """Log all requests with timing."""

    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger("request")

    def __call__(self, environ, start_response):
        start_time = time.perf_counter()
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "")

        def custom_start_response(status, headers, exc_info=None):
            duration = time.perf_counter() - start_time
            status_code = status.split(" ")[0]
            self.logger.info(
                "%s %s %s %.3fs",
                method,
                path,
                status_code,
                duration,
                extra={
                    "method": method,
                    "path": path,
                    "status": status_code,
                    "duration": duration,
                },
            )
            return start_response(status, headers, exc_info)

        return self.app(environ, custom_start_response)


def init_security_middleware(app):
    """Initialize all security middleware."""
    # Trust one layer of reverse proxy (nginx / the platform load balancer) so
    # request.remote_addr - which the rate limiter keys on - is the real client
    # IP rather than the proxy's.
    if app.config.get("TRUST_PROXY_HEADERS", True):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    app.wsgi_app = SecurityHeadersMiddleware(app, app.wsgi_app)

    if not app.debug and not app.testing:
        app.wsgi_app = RequestLoggingMiddleware(app.wsgi_app)


# ============================================================
# RATE LIMITING
# ============================================================
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[],
        storage_uri="memory://",
        strategy="fixed-window",
    )

    def init_limiter(app):
        storage_uri = app.config.get("RATELIMIT_STORAGE_URI", "memory://")
        limiter.storage_uri = storage_uri
        limiter.enabled = app.config.get("RATELIMIT_ENABLED", True)

        # Apply the API-wide default to every /api/ route. Per-view limits
        # (e.g. the tighter one on login) still take precedence.
        limiter.init_app(app)
        app.extensions["limiter"] = limiter

        if storage_uri == "memory://" and not app.debug and not app.testing:
            app.logger.warning(
                "Rate limiting uses in-process memory storage. With more than "
                "one worker each process keeps its own counters - set "
                "RATELIMIT_STORAGE_URI to a shared Redis URL in production."
            )

except ImportError:  # pragma: no cover - exercised only without flask_limiter
    limiter = None

    def init_limiter(app):
        app.logger.warning(
            "flask_limiter is not installed - rate limiting is DISABLED. "
            "Install it before deploying: pip install Flask-Limiter"
        )


# ============================================================
# REQUEST HELPERS
# ============================================================
def require_json(f):
    """Ensure request has JSON content type."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415
        return f(*args, **kwargs)

    return decorated


def validate_json(schema_class):
    """Validate the JSON body against a marshmallow schema into ``g``."""
    from marshmallow import ValidationError

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 415
            try:
                g.validated_data = schema_class().load(request.get_json())
            except ValidationError as exc:
                return (
                    jsonify(
                        {
                            "error": "Validation failed",
                            "details": exc.messages,
                        }
                    ),
                    400,
                )
            return f(*args, **kwargs)

        return decorated

    return decorator


# ============================================================
# ERROR HANDLERS
# ============================================================
def wants_json() -> bool:
    """Decide between a JSON body and an HTML error page.

    Keyed on the request path first: everything under /api/ is JSON no matter
    what the client sent. Browsers send ``Accept: text/html``, while fetch()
    and curl send ``*/*`` - so testing ``accept_mimetypes.accept_html`` alone
    (the previous behaviour) served HTML error pages to API clients.
    """
    if request.path.startswith("/api/"):
        return True
    if request.is_json:
        return True
    return not request.accept_mimetypes.accept_html


def register_error_handlers(app):
    """Register consistent error handlers for both HTML and JSON clients."""
    from app.api.utils import ApiError
    from app.core.extensions import db

    def respond(status: int, message: str, template: str = None, details=None):
        if wants_json():
            payload = {"error": message, "status": status}
            if details:
                payload["details"] = details
            if g.get("request_id"):
                payload["request_id"] = g.request_id
            return jsonify(payload), status

        try:
            return (
                render_template(template or "errors/500.html", status=status, message=message),
                status,
            )
        except Exception:
            # Never let a missing/broken error template mask the real error.
            return f"{status} - {message}", status

    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        return exc.to_response()

    @app.errorhandler(400)
    def bad_request(e):
        return respond(400, getattr(e, "description", "Bad request"))

    @app.errorhandler(401)
    def unauthorized(e):
        return respond(401, "Authentication required")

    @app.errorhandler(403)
    def forbidden(e):
        return respond(403, "Insufficient permissions", "errors/403.html")

    @app.errorhandler(404)
    def not_found(e):
        return respond(404, "Resource not found", "errors/404.html")

    @app.errorhandler(405)
    def method_not_allowed(e):
        return respond(405, "Method not allowed")

    @app.errorhandler(413)
    def payload_too_large(e):
        return respond(413, "Request payload too large")

    @app.errorhandler(415)
    def unsupported_media_type(e):
        return respond(415, "Unsupported media type")

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return respond(429, "Too many requests, please try again later")

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        app.logger.exception("Internal server error")
        return respond(500, "Internal server error", "errors/500.html")

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        # Let werkzeug's own HTTP errors fall through to the handlers above.
        if isinstance(e, HTTPException):
            return e

        db.session.rollback()
        app.logger.exception("Unhandled exception on %s %s", request.method, request.path)

        if app.debug or app.testing:
            raise e
        return respond(500, "Internal server error", "errors/500.html")
