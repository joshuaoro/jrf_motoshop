"""
Flask extensions initialization
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
import logging

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

# The rate limiter lives in app.core.security (it owns the init logic and the
# no-flask_limiter fallback). Re-exported here so callers can import every
# extension from one place without two Limiter instances existing - the
# previous duplicate meant `@limiter.limit` decorators registered against an
# object that was never init_app'd, and so never actually limited anything.
from app.core.security import limiter  # noqa: E402,F401  (re-export)

# Login manager config
login_manager.login_view = "dashboard_web.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"
login_manager.session_protection = "strong"


@login_manager.user_loader
def load_user(user_id):
    """Resolve the session's user id to a User row."""
    from app.models import User

    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


@login_manager.unauthorized_handler
def handle_unauthorized():
    """Send API callers JSON and browsers the login page."""
    from flask import redirect, request, url_for, jsonify
    from flask import flash

    if request.path.startswith("/api/"):
        return jsonify({"error": "Authentication required", "status": 401}), 401

    flash(login_manager.login_message, login_manager.login_message_category)
    return redirect(
        url_for(
            "dashboard_web.login",
            next=request.full_path if request.query_string else request.path,
        )
    )


def init_extensions(app):
    """Initialize all Flask extensions"""
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # CSRF protection. API blueprints are exempted in the factory once they
    # are registered; browser form posts still require a token.
    csrf.init_app(app)

    configure_logging(app)


def configure_logging(app):
    """Configure console and rotating-file logging."""
    import sys
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    log_level = getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)

    app.logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    app.logger.addHandler(console_handler)

    # File logging is opt-out. Previously this ran whenever debug was off and
    # wrote to a hard-coded relative 'logs/app.log' - which crashed at startup
    # with FileNotFoundError if the directory did not exist, and wrote to a
    # different place depending on the working directory.
    if app.config.get("LOG_TO_FILE", True) and not app.testing:
        log_dir = Path(app.config.get("LOG_DIR", "logs"))
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_dir / "app.log",
                maxBytes=10_000_000,
                backupCount=10,
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)-8s %(name)s %(funcName)s:%(lineno)d %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            app.logger.addHandler(file_handler)
        except OSError as exc:
            # A read-only or missing volume must not stop the app booting;
            # console logging still works.
            app.logger.warning("File logging disabled (%s): %s", log_dir, exc)

    app.logger.setLevel(log_level)
    app.logger.propagate = False

    # Route the module-level loggers used across the app through the same
    # handlers, otherwise service/API log lines vanish entirely.
    root = logging.getLogger("app")
    root.handlers.clear()
    for handler in app.logger.handlers:
        root.addHandler(handler)
    root.setLevel(log_level)
    root.propagate = False

    # Reduce noise from libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
