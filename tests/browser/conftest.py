"""
Fixtures for the Playwright browser tests.

These run the real application in a background thread against a temporary
SQLite file, then drive it with Chromium. They exist to catch what the
server-side suite structurally cannot: JavaScript that throws, a modal that
never opens, a payload the API rejects, a button wired to a function that
does not exist.

Requires a one-off browser download:  python -m playwright install chromium
"""

import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="playwright is not installed")

from werkzeug.serving import make_server  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LiveServer:
    """The application, served on a real socket for the browser to hit."""

    def __init__(self, app, port):
        self.app = app
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self._server = make_server("127.0.0.1", port, app, threaded=True)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.25):
                    return self
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("live server did not start in time")

    def stop(self):
        self._server.shutdown()
        self._thread.join(timeout=5)


def assert_disposable(app):
    """Refuse to touch anything that is not a throwaway SQLite file.

    These fixtures call drop_all(). Setting os.environ["DATABASE_URL"] is NOT
    enough to redirect the database - the config classes resolve that value
    when app.core.config is first imported, which the root conftest has
    already triggered by then, so a stale real URL survives. That mistake
    once pointed this suite at a live Supabase database and dropped it.
    Overrides are now passed explicitly, and this is the seatbelt.
    """
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite"):
        pytest.exit(
            f"REFUSING TO RUN: browser tests drop tables and this app is "
            f"pointed at a non-SQLite database ({uri.rsplit('@', 1)[-1]}).",
            returncode=1,
        )


@pytest.fixture(scope="session")
def live_server():
    """A real HTTP server backed by a temporary SQLite database.

    A file database rather than :memory: - the server runs on its own threads,
    and an in-memory SQLite database is not reliably shared across them.
    """
    tmpdir = tempfile.mkdtemp(prefix="jrf-browser-")
    db_path = Path(tmpdir) / "browser.db"
    database_url = f"sqlite:///{db_path.as_posix()}"

    from app import create_app
    from app.core.extensions import db

    # Passed as explicit overrides, not through os.environ: by the time this
    # runs the config classes have already been imported and frozen.
    app = create_app(
        "development",
        overrides={
            "SQLALCHEMY_DATABASE_URI": database_url,
            "SQLALCHEMY_ENGINE_OPTIONS": {"connect_args": {"check_same_thread": False}},
            "SECRET_KEY": "browser-tests-secret-key-not-used-anywhere-real",
            "RATELIMIT_ENABLED": False,
            "LOG_TO_FILE": False,
            "WTF_CSRF_ENABLED": True,
            "TESTING": False,
            "SQLALCHEMY_ECHO": False,
        },
    )

    assert_disposable(app)

    with app.app_context():
        db.create_all()

    server = LiveServer(app, _free_port()).start()
    try:
        yield server
    finally:
        server.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture()
def seeded(live_server):
    """A clean database with settings, an admin, and a small catalogue."""
    from app.core.extensions import db
    from app.models import Customer, Part, Supplier, User
    from app.services.system import SettingsService

    assert_disposable(live_server.app)

    with live_server.app.app_context():
        db.drop_all()
        db.create_all()
        SettingsService.init_defaults()

        admin = User(
            name="Browser Admin",
            email="browser@example.com",
            username="browseradmin",
            role="admin",
        )
        admin.set_password("BrowserPass123!")
        db.session.add(admin)

        supplier = Supplier(name="Playwright Supplies", email="pw@example.com")
        db.session.add(supplier)

        db.session.add_all(
            [
                Part(
                    name="Brake Pad Set",
                    sku="BP-100",
                    part_type="Brakes",
                    brand="Brembo",
                    price=1200,
                    cost_price=800,
                    stock_quantity=25,
                    min_stock_level=5,
                ),
                Part(
                    name="Spark Plug",
                    sku="SP-200",
                    part_type="Electrical",
                    brand="NGK",
                    price=85,
                    cost_price=52,
                    stock_quantity=100,
                    min_stock_level=20,
                ),
            ]
        )
        db.session.add(Customer(name="Regular Customer", email="regular@example.com"))
        db.session.commit()

    return {
        "email": "browser@example.com",
        "password": "BrowserPass123!",
        "url": live_server.url,
    }


def _new_instrumented_page(browser, *, ignore_csp: bool):
    """Shared setup for ``page`` and ``strict_page``.

    ``ignore_csp`` controls whether a real Content-Security-Policy violation
    is treated as noise (the normal suite, which runs under the development
    policy and should never see one) or as a hard failure (the strict-CSP
    suite, whose entire point is to catch exactly that).
    """
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    # Keep the tests hermetic and fast: never reach out to a CDN. Whether the
    # CSP actually allows those hosts is asserted statically instead, in
    # tests/integration/test_security.py, which needs no network at all.
    context.route(
        "**/*",
        lambda route: (
            route.abort()
            if "127.0.0.1" not in route.request.url and "localhost" not in route.request.url
            else route.continue_()
        ),
    )

    errors = []

    def is_local(url: str) -> bool:
        return "127.0.0.1" in url or "localhost" in url

    # Noise produced by the deliberate CDN blocking above, not real defects.
    ignored_console = ["Failed to load resource", "net::ERR_FAILED"]
    if ignore_csp:
        ignored_console.append("Content Security Policy")

    page.on("pageerror", lambda exc: errors.append(f"JS error: {exc}"))
    page.on(
        "console",
        lambda message: (
            errors.append(f"console.error: {message.text}")
            if message.type == "error"
            and not any(noise in message.text for noise in ignored_console)
            else None
        ),
    )
    page.on(
        "requestfailed",
        lambda request: (
            errors.append(f"request failed: {request.method} {request.url}")
            if is_local(request.url)
            else None
        ),
    )

    page.js_errors = errors
    return page, context


@pytest.fixture()
def page(live_server, seeded, browser):
    """A browser page that fails the test on any JS error or failed request.

    A page can look fine while its console is full of TypeErrors; asserting on
    a clean console is what makes these tests worth running.
    """
    page, context = _new_instrumented_page(browser, ignore_csp=True)
    yield page
    context.close()


@pytest.fixture()
def logged_in(page, seeded):
    """A page already signed in as the administrator."""
    page.goto(f"{seeded['url']}/login")
    page.fill("#email", seeded["email"])
    page.fill("#password", seeded["password"])
    page.click("button[type=submit]")
    page.wait_for_url(lambda url: "/login" not in url, timeout=10_000)
    return page


@pytest.fixture(scope="session")
def strict_csp_live_server():
    """Same live server, but under the *production* Content-Security-Policy.

    ``config_name`` stays ``"development"`` so ``validate()`` does not demand
    Postgres or a 32-char SECRET_KEY - only ``CONTENT_SECURITY_POLICY`` is
    overridden, to exactly the policy ``ProductionConfig`` ships. Production's
    CSP can otherwise never be exercised by any test or local run, which is
    exactly how a set of inline onclick= handlers across every template went
    unnoticed: they work fine under the development policy that every other
    fixture here uses, and are silently dead under the one that actually
    reaches users.
    """
    from app.core.config import ProductionConfig

    tmpdir = tempfile.mkdtemp(prefix="jrf-browser-strict-csp-")
    db_path = Path(tmpdir) / "browser.db"
    database_url = f"sqlite:///{db_path.as_posix()}"

    from app import create_app
    from app.core.extensions import db

    app = create_app(
        "development",
        overrides={
            "SQLALCHEMY_DATABASE_URI": database_url,
            "SQLALCHEMY_ENGINE_OPTIONS": {"connect_args": {"check_same_thread": False}},
            "SECRET_KEY": "browser-tests-secret-key-not-used-anywhere-real",
            "RATELIMIT_ENABLED": False,
            "LOG_TO_FILE": False,
            "WTF_CSRF_ENABLED": True,
            "TESTING": False,
            "SQLALCHEMY_ECHO": False,
            "CONTENT_SECURITY_POLICY": ProductionConfig.CONTENT_SECURITY_POLICY,
        },
    )

    assert_disposable(app)

    with app.app_context():
        db.create_all()

    server = LiveServer(app, _free_port()).start()
    try:
        yield server
    finally:
        server.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture()
def strict_csp_seeded(strict_csp_live_server):
    """The same seed data as ``seeded``, against the strict-CSP server."""
    from app.core.extensions import db
    from app.models import Customer, Part, Supplier, User
    from app.services.system import SettingsService

    assert_disposable(strict_csp_live_server.app)

    with strict_csp_live_server.app.app_context():
        db.drop_all()
        db.create_all()
        SettingsService.init_defaults()

        admin = User(
            name="Browser Admin",
            email="browser@example.com",
            username="browseradmin",
            role="admin",
        )
        admin.set_password("BrowserPass123!")
        db.session.add(admin)

        supplier = Supplier(name="Playwright Supplies", email="pw@example.com")
        db.session.add(supplier)

        db.session.add_all(
            [
                Part(
                    name="Brake Pad Set",
                    sku="BP-100",
                    part_type="Brakes",
                    brand="Brembo",
                    price=1200,
                    cost_price=800,
                    stock_quantity=25,
                    min_stock_level=5,
                ),
                Part(
                    name="Spark Plug",
                    sku="SP-200",
                    part_type="Electrical",
                    brand="NGK",
                    price=85,
                    cost_price=52,
                    stock_quantity=100,
                    min_stock_level=20,
                ),
            ]
        )
        db.session.add(Customer(name="Regular Customer", email="regular@example.com"))
        db.session.commit()

    return {
        "email": "browser@example.com",
        "password": "BrowserPass123!",
        "url": strict_csp_live_server.url,
    }


@pytest.fixture()
def strict_page(strict_csp_live_server, strict_csp_seeded, browser):
    """A page under the real production CSP where a violation fails the test."""
    page, context = _new_instrumented_page(browser, ignore_csp=False)
    yield page
    context.close()


@pytest.fixture()
def strict_logged_in(strict_page, strict_csp_seeded):
    """A page signed in as the administrator, under the strict production CSP."""
    strict_page.goto(f"{strict_csp_seeded['url']}/login")
    strict_page.fill("#email", strict_csp_seeded["email"])
    strict_page.fill("#password", strict_csp_seeded["password"])
    strict_page.click("button[type=submit]")
    strict_page.wait_for_url(lambda url: "/login" not in url, timeout=10_000)
    return strict_page
