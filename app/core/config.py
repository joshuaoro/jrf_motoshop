"""
Application configuration.

**Everything environment-dependent is resolved when the app is created, not
when this module is imported.**

That distinction has bitten this project twice. Class bodies that call
``os.environ.get(...)`` freeze their value at import time, so anything that
adjusts the environment afterwards is silently ignored — which is how a test
harness that set ``DATABASE_URL`` to a temporary SQLite file ended up running
``drop_all()`` against a live PostgreSQL database. The rule now:

* class bodies hold **static** defaults only;
* every value read from the environment lives in ``resolve()``;
* ``validate()`` inspects the resolved mapping, never class attributes.

To override settings deliberately (tests, embedding), pass ``overrides`` to
``create_app`` rather than mutating ``os.environ``.
"""

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import dotenv_values
from sqlalchemy.pool import StaticPool

BASE_DIR = Path(__file__).resolve().parent.parent.parent

_environment_loaded = False


def load_environment(force: bool = False) -> None:
    """Populate os.environ from the project's dotenv files.

    Precedence, highest first:

    1. variables genuinely exported in the shell / CI
    2. ``.env.local`` - developer-specific, git-ignored
    3. ``.env``       - shared/deployment defaults

    The obvious implementation - ``load_dotenv(".env.local", override=False)``
    - does not work, and the reason is subtle: **Flask's CLI loads ``.env``
    into os.environ itself, before it imports the application.** By the time
    this function runs under ``flask ...``, DATABASE_URL is already set from
    ``.env``, so a non-overriding load of ``.env.local`` is a no-op and every
    CLI command still talks to the deployment database.

    So rather than trusting "already present" to mean "exported by the user",
    the files are read into dicts and compared: a variable may be overridden
    by ``.env.local`` when it is absent, or when it still holds exactly what
    ``.env`` specifies. Anything else was set deliberately and is left alone.
    """
    global _environment_loaded
    if _environment_loaded and not force:
        return

    base = dotenv_values(BASE_DIR / ".env") if (BASE_DIR / ".env").exists() else {}
    local = dotenv_values(BASE_DIR / ".env.local") if (BASE_DIR / ".env.local").exists() else {}

    for key, value in {**base, **local}.items():
        if value is None:
            continue
        current = os.environ.get(key)
        if current is None or current == base.get(key):
            os.environ[key] = value

    _environment_loaded = True


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def build_database_url() -> str | None:
    """Assemble the SQLAlchemy URL from the environment.

    Prefers ``DATABASE_URL``; otherwise composes one from the discrete
    PG*/SUPABASE_DB_* variables. Returns None when nothing is configured so
    the caller can raise a useful error at the right moment.
    """
    url = os.environ.get("DATABASE_URL")

    if not url:
        host = os.environ.get("PGHOST") or os.environ.get("SUPABASE_DB_HOST")
        port = os.environ.get("PGPORT") or os.environ.get("SUPABASE_DB_PORT", "5432")
        user = os.environ.get("PGUSER") or os.environ.get("SUPABASE_DB_USER")
        password = os.environ.get("PGPASSWORD") or os.environ.get("SUPABASE_DB_PASSWORD")
        database = os.environ.get("PGDATABASE") or os.environ.get("SUPABASE_DB_NAME", "postgres")

        if host and user and password and database:
            # Passwords routinely contain '@', ':' and '/'; without quoting
            # those silently corrupt the URL into an unreachable host.
            url = (
                f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
                f"@{host}:{port}/{database}"
            )

    if not url:
        return None

    # SQLAlchemy 2 dropped the bare "postgres://" scheme that some hosting
    # providers still hand out.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


def describe_database(url: str | None) -> str:
    """Host and database name only - never the credentials.

    Logged at startup so it is always obvious which database an app instance
    is about to talk to.
    """
    if not url:
        return "not configured"
    if url.startswith("sqlite"):
        return f"sqlite ({url.split('///')[-1] or ':memory:'})"
    return url.rsplit("@", 1)[-1]


def is_local_database(url: str | None) -> bool:
    """True for SQLite or a database on this machine."""
    if not url:
        return False
    if url.startswith("sqlite"):
        return True
    host = describe_database(url)
    return host.startswith(("localhost", "127.0.0.1", "[::1]", "postgres:", "db:"))


def engine_options(url: str | None) -> dict:
    """SQLAlchemy engine options appropriate to the configured driver."""
    if not url or url.startswith("sqlite"):
        # SQLite has no server to pool against; StaticPool keeps an in-memory
        # database alive across sessions.
        options: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in (url or ""):
            options["poolclass"] = StaticPool
        return options

    # PostgreSQL - tuned for the Supabase transaction pooler. connect_timeout
    # and application_name are libpq arguments and raise TypeError on SQLite,
    # which is why this is chosen per-scheme rather than applied blindly.
    return {
        "pool_size": _int("DB_POOL_SIZE", 5),
        "max_overflow": _int("DB_MAX_OVERFLOW", 10),
        "pool_timeout": _int("DB_POOL_TIMEOUT", 30),
        "pool_recycle": _int("DB_POOL_RECYCLE", 1800),
        "pool_pre_ping": True,
        "connect_args": {
            "connect_timeout": _int("DB_CONNECT_TIMEOUT", 10),
            "application_name": "jrf-motoshop",
        },
    }


class Config:
    """Static defaults. Anything from the environment belongs in resolve()."""

    APP_VERSION = "2.0.3"
    DEBUG = False
    TESTING = False

    # ============================================================
    # SECURITY (static parts)
    # ============================================================
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # Tie token lifetime to the session instead.

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RATELIMIT_HEADERS_ENABLED = True
    JSON_SORT_KEYS = False

    # ============================================================
    # SECURITY HEADERS
    # ============================================================
    # Keep in step with the CDNs the templates actually reference:
    #   cdn.tailwindcss.com  - Tailwind
    #   cdnjs.cloudflare.com - Font Awesome
    #   cdn.jsdelivr.net     - Alpine.js (base layout) and Chart.js (reports)
    # Omitting jsdelivr silently killed the notification bell, the user menu
    # and every report chart, because the browser blocked the scripts.
    CONTENT_SECURITY_POLICY = {
        "default-src": "'self'",
        "script-src": (
            "'self' 'unsafe-inline' https://cdn.tailwindcss.com "
            "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net"
        ),
        "style-src": (
            "'self' 'unsafe-inline' https://cdn.tailwindcss.com "
            "https://cdnjs.cloudflare.com https://fonts.googleapis.com"
        ),
        "font-src": "'self' data: https://cdnjs.cloudflare.com https://fonts.gstatic.com",
        "img-src": "'self' data: https:",
        "connect-src": "'self'",
        "frame-ancestors": "'none'",
        "form-action": "'self'",
        "base-uri": "'self'",
        "object-src": "'none'",
    }

    @classmethod
    def resolve(cls) -> dict:
        """Read the environment. Called once per create_app()."""
        load_environment()

        database_url = build_database_url()

        return {
            "FLASK_ENV": os.environ.get("FLASK_ENV", "development"),
            "SECRET_KEY": os.environ.get("SECRET_KEY") or "dev-secret-change-in-production",
            "PERMANENT_SESSION_LIFETIME": _int("SESSION_LIFETIME_SECONDS", 3600),
            "MAX_CONTENT_LENGTH": _int("MAX_CONTENT_LENGTH", 8 * 1024 * 1024),
            "TRUST_PROXY_HEADERS": _bool("TRUST_PROXY_HEADERS", True),
            # --- database ---
            "SQLALCHEMY_DATABASE_URI": database_url,
            "SQLALCHEMY_ENGINE_OPTIONS": engine_options(database_url),
            # --- rate limiting ---
            "RATELIMIT_ENABLED": _bool("RATELIMIT_ENABLED", True),
            "RATELIMIT_STORAGE_URI": (
                os.environ.get("RATELIMIT_STORAGE_URI")
                or os.environ.get("REDIS_URL")
                or "memory://"
            ),
            "RATELIMIT_DEFAULT": os.environ.get("RATELIMIT_DEFAULT", "600 per minute"),
            "RATELIMIT_LOGIN": os.environ.get("RATELIMIT_LOGIN", "10 per minute"),
            "RATELIMIT_API": os.environ.get("RATELIMIT_API", "120 per minute"),
            # --- background tasks ---
            "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            # --- email (optional) ---
            "MAIL_SERVER": os.environ.get("MAIL_SERVER"),
            "MAIL_PORT": _int("MAIL_PORT", 587),
            "MAIL_USE_TLS": _bool("MAIL_USE_TLS", True),
            "MAIL_USE_SSL": _bool("MAIL_USE_SSL", False),
            "MAIL_USERNAME": os.environ.get("MAIL_USERNAME"),
            "MAIL_PASSWORD": os.environ.get("MAIL_PASSWORD"),
            "MAIL_DEFAULT_SENDER": os.environ.get(
                "MAIL_DEFAULT_SENDER",
                "JRF Motorcycle Parts <no-reply@jrfmotorparts.com>",
            ),
            "MAIL_TIMEOUT": _int("MAIL_TIMEOUT", 30),
            # --- logging ---
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
            "LOG_DIR": os.environ.get("LOG_DIR", str(BASE_DIR / "logs")),
            "LOG_TO_FILE": _bool("LOG_TO_FILE", True),
            # --- application ---
            "BACKUP_DIR": os.environ.get("BACKUP_DIR", str(BASE_DIR / "backups")),
            "DEFAULT_PAGE_SIZE": _int("DEFAULT_PAGE_SIZE", 20),
            "MAX_PAGE_SIZE": _int("MAX_PAGE_SIZE", 100),
        }

    @classmethod
    def validate(cls, settings: dict) -> None:
        """Fail fast on a misconfigured environment.

        Runs against the *resolved* mapping (including any overrides), so what
        is checked is exactly what the app will use.
        """
        if not settings.get("SQLALCHEMY_DATABASE_URI"):
            raise RuntimeError(
                "No database configured. Set DATABASE_URL (or "
                "SUPABASE_DB_HOST / SUPABASE_DB_USER / SUPABASE_DB_PASSWORD) "
                "in .env.local, .env, or the environment."
            )


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False

    @classmethod
    def resolve(cls) -> dict:
        settings = super().resolve()
        settings["LOG_LEVEL"] = os.environ.get("LOG_LEVEL", "DEBUG")
        return settings


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

    # No inline scripts in production. The templates load Tailwind, Font
    # Awesome, Alpine and Chart.js from CDNs, which stay allow-listed.
    CONTENT_SECURITY_POLICY = {
        **Config.CONTENT_SECURITY_POLICY,
        "script-src": (
            "'self' https://cdn.tailwindcss.com "
            "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net"
        ),
    }

    @classmethod
    def validate(cls, settings: dict) -> None:
        super().validate(settings)

        secret = settings.get("SECRET_KEY") or ""
        if not os.environ.get("SECRET_KEY"):
            raise RuntimeError(
                "SECRET_KEY must be set in production. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if len(secret) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters long.")

        uri = settings.get("SQLALCHEMY_DATABASE_URI") or ""
        if not uri.startswith("postgresql"):
            raise RuntimeError(f"PostgreSQL is required in production, got: {uri.split('://')[0]}")


class TestingConfig(Config):
    TESTING = True
    DEBUG = False

    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False

    @classmethod
    def resolve(cls) -> dict:
        settings = super().resolve()
        # Tests always run against in-memory SQLite, whatever the environment
        # says. This is the last line of defence against a test run reaching a
        # real database, so it deliberately ignores DATABASE_URL.
        settings.update(
            {
                "SECRET_KEY": "testing-secret-key-not-used-in-any-real-deployment",
                "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
                "SQLALCHEMY_ENGINE_OPTIONS": engine_options("sqlite+pysqlite:///:memory:"),
                "RATELIMIT_ENABLED": False,
                "LOG_TO_FILE": False,
                "LOG_LEVEL": "WARNING",
            }
        )
        return settings

    @classmethod
    def validate(cls, settings: dict) -> None:
        return  # Nothing external to check.


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config():
    """Get the configuration class for the current environment."""
    load_environment()
    return config.get(os.environ.get("FLASK_ENV", "development"), config["default"])
