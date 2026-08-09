"""
Tests for configuration resolution.

These exist because of a real incident: the config classes used to read
``os.environ`` in their class bodies, which froze every value at import time.
A test harness set ``DATABASE_URL`` to a temporary SQLite path *after* the
module had been imported, the change was silently ignored, and the suite ran
``drop_all()`` against a live PostgreSQL database.
"""

import os

import pytest

from app import create_app
from app.core.config import (
    Config,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    build_database_url,
    describe_database,
    engine_options,
    is_local_database,
)


@pytest.fixture()
def clean_env(monkeypatch):
    """Isolate the environment variables config reads."""
    for name in (
        "DATABASE_URL",
        "SECRET_KEY",
        "PGHOST",
        "PGUSER",
        "PGPASSWORD",
        "PGDATABASE",
        "SUPABASE_DB_HOST",
        "SUPABASE_DB_USER",
        "SUPABASE_DB_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class TestLateBinding:
    """The environment must be read at create_app(), not at import."""

    def test_database_url_set_after_import_is_honoured(self, clean_env):
        clean_env.setenv("DATABASE_URL", "sqlite:///late_one.db")
        first = create_app("development")
        assert first.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///late_one.db"

        # Change it again - a second app must see the new value.
        clean_env.setenv("DATABASE_URL", "sqlite:///late_two.db")
        second = create_app("development")
        assert second.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///late_two.db"

    def test_class_body_holds_no_database_url(self):
        """A stale class attribute is exactly what caused the incident."""
        for cls in (Config, DevelopmentConfig, ProductionConfig, TestingConfig):
            assert not hasattr(cls, "SQLALCHEMY_DATABASE_URI"), (
                f"{cls.__name__} resolves the database URL at import time; "
                "move it into resolve()"
            )

    def test_engine_options_track_the_resolved_driver(self, clean_env):
        clean_env.setenv("DATABASE_URL", "sqlite:///driver.db")
        app = create_app("development")
        # libpq-only arguments must not leak onto a SQLite engine.
        assert "connect_timeout" not in app.config["SQLALCHEMY_ENGINE_OPTIONS"].get(
            "connect_args", {}
        )


class TestOverrides:
    """create_app(overrides=...) is the supported way to redirect config."""

    def test_overrides_win_over_the_environment(self, clean_env):
        clean_env.setenv("DATABASE_URL", "postgresql://u:p@example.com:5432/real")

        app = create_app(
            "development",
            overrides={"SQLALCHEMY_DATABASE_URI": "sqlite:///override.db"},
        )
        assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///override.db"

    def test_validation_sees_the_overridden_values(self, clean_env):
        """Production validation must inspect the final config, not the class."""
        clean_env.setenv("SECRET_KEY", "x" * 40)
        clean_env.setenv("DATABASE_URL", "postgresql://u:p@example.com:5432/real")

        # Overriding to SQLite must now fail production validation.
        with pytest.raises(RuntimeError, match="PostgreSQL is required"):
            create_app(
                "production",
                overrides={"SQLALCHEMY_DATABASE_URI": "sqlite:///nope.db"},
            )


class TestTestingConfigIsSealed:
    def test_testing_ignores_database_url_entirely(self, clean_env):
        """The last line of defence: tests never reach a real database."""
        clean_env.setenv("DATABASE_URL", "postgresql://u:p@production.example.com:5432/live")

        app = create_app("testing")
        assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite")
        assert "production.example.com" not in app.config["SQLALCHEMY_DATABASE_URI"]

    def test_testing_disables_rate_limiting_and_file_logs(self):
        app = create_app("testing")
        assert app.config["RATELIMIT_ENABLED"] is False
        assert app.config["LOG_TO_FILE"] is False


class TestProductionValidation:
    def test_requires_a_secret_key(self, clean_env):
        clean_env.setenv("DATABASE_URL", "postgresql://u:p@example.com:5432/real")
        with pytest.raises(RuntimeError, match="SECRET_KEY must be set"):
            create_app("production")

    def test_rejects_a_short_secret_key(self, clean_env):
        clean_env.setenv("SECRET_KEY", "too-short")
        clean_env.setenv("DATABASE_URL", "postgresql://u:p@example.com:5432/real")
        with pytest.raises(RuntimeError, match="at least 32 characters"):
            create_app("production")

    def test_requires_a_database(self, clean_env):
        clean_env.setenv("SECRET_KEY", "x" * 40)
        with pytest.raises(RuntimeError, match="No database configured"):
            create_app("production", overrides={"SQLALCHEMY_DATABASE_URI": None})


class TestDatabaseUrlBuilding:
    def test_credentials_are_url_quoted(self, clean_env):
        clean_env.setenv("PGHOST", "db.example.com")
        clean_env.setenv("PGUSER", "user@corp")
        clean_env.setenv("PGPASSWORD", "p@ss:w/rd")
        clean_env.setenv("PGDATABASE", "shop")

        url = build_database_url()
        # The real host must survive; the '@' in the password must not split it.
        assert url.endswith("@db.example.com:5432/shop")
        assert "p%40ss%3Aw%2Frd" in url

    def test_legacy_postgres_scheme_is_upgraded(self, clean_env):
        clean_env.setenv("DATABASE_URL", "postgres://u:p@example.com:5432/db")
        assert build_database_url().startswith("postgresql://")

    def test_returns_none_when_nothing_is_configured(self, clean_env):
        assert build_database_url() is None


class TestDatabaseDescription:
    def test_never_reveals_credentials(self):
        described = describe_database("postgresql://user:hunter2@db.example.com:5432/shop")
        assert "hunter2" not in described
        assert "user" not in described
        assert described == "db.example.com:5432/shop"

    def test_handles_sqlite_and_missing_urls(self):
        assert "sqlite" in describe_database("sqlite:///local.db")
        assert describe_database(None) == "not configured"

    @pytest.mark.parametrize(
        "url,local",
        [
            ("sqlite:///x.db", True),
            ("postgresql://u:p@localhost:5432/db", True),
            ("postgresql://u:p@127.0.0.1:5432/db", True),
            ("postgresql://u:p@postgres:5432/db", True),  # docker-compose service
            ("postgresql://u:p@aws-0.pooler.supabase.com:6543/postgres", False),
            (None, False),
        ],
    )
    def test_recognises_local_databases(self, url, local):
        assert is_local_database(url) is local


class TestEngineOptions:
    def test_sqlite_memory_uses_a_static_pool(self):
        options = engine_options("sqlite+pysqlite:///:memory:")
        assert "poolclass" in options

    def test_sqlite_file_needs_no_pool_class(self):
        assert "poolclass" not in engine_options("sqlite:///file.db")

    def test_postgres_gets_pooling_and_libpq_args(self):
        options = engine_options("postgresql://u:p@host:5432/db")
        assert options["pool_pre_ping"] is True
        assert options["connect_args"]["application_name"] == "jrf-motoshop"


class TestEnvironmentFilePrecedence:
    """shell > .env.local > .env

    The tricky case is the middle one. Flask's CLI loads ``.env`` into
    os.environ before importing the app, so "the variable is already set" is
    not evidence that a human set it - and a naive non-overriding load of
    ``.env.local`` silently does nothing under ``flask ...``.
    """

    @staticmethod
    def _reload(monkeypatch, tmp_path, base: str, local: str | None):
        """Run load_environment() against throwaway dotenv files."""
        from app.core import config as config_module

        (tmp_path / ".env").write_text(base, encoding="utf-8")
        if local is not None:
            (tmp_path / ".env.local").write_text(local, encoding="utf-8")

        monkeypatch.setattr(config_module, "BASE_DIR", tmp_path)
        config_module.load_environment(force=True)

    def test_dotenv_local_overrides_dotenv(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        self._reload(
            monkeypatch,
            tmp_path,
            base="DATABASE_URL=postgresql://u:p@production:5432/live\n",
            local="DATABASE_URL=sqlite:///local.db\n",
        )
        assert os.environ["DATABASE_URL"] == "sqlite:///local.db"

    def test_dotenv_local_still_wins_when_the_cli_preloaded_dotenv(self, monkeypatch, tmp_path):
        """Reproduces the Flask-CLI case that made the first attempt useless."""
        production = "postgresql://u:p@production:5432/live"
        # Simulate flask.cli having already loaded .env into the environment.
        monkeypatch.setenv("DATABASE_URL", production)

        self._reload(
            monkeypatch,
            tmp_path,
            base=f"DATABASE_URL={production}\n",
            local="DATABASE_URL=sqlite:///local.db\n",
        )
        assert os.environ["DATABASE_URL"] == "sqlite:///local.db"

    def test_a_deliberately_exported_variable_beats_both_files(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///exported.db")
        self._reload(
            monkeypatch,
            tmp_path,
            base="DATABASE_URL=postgresql://u:p@production:5432/live\n",
            local="DATABASE_URL=sqlite:///local.db\n",
        )
        assert os.environ["DATABASE_URL"] == "sqlite:///exported.db"

    def test_dotenv_is_used_when_there_is_no_local_override(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        self._reload(
            monkeypatch,
            tmp_path,
            base="DATABASE_URL=postgresql://u:p@production:5432/live\n",
            local=None,
        )
        assert os.environ["DATABASE_URL"].endswith("/live")

    def test_dotenv_local_example_is_tracked_but_dotenv_local_is_not(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        assert (root / ".env.local.example").exists()

        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        assert ".env.*" in gitignore
        assert "!.env.local.example" in gitignore
