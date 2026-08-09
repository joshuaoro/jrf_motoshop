"""
Shared pytest fixtures.

Tests run against an in-memory SQLite database created from the models, so the
suite needs no external services and cannot touch a real deployment.
"""

import os
from decimal import Decimal

import pytest

# Set before importing the app so config picks the test database rather than
# whatever DATABASE_URL happens to be in the developer's .env.
os.environ["FLASK_ENV"] = "testing"
os.environ.pop("DATABASE_URL", None)

from app import create_app  # noqa: E402
from app.core.extensions import db as _db  # noqa: E402
from app.models import Customer, Part, Supplier, User  # noqa: E402
from app.services.system import SettingsService  # noqa: E402


@pytest.fixture(scope="session")
def app():
    """Application configured for testing.

    Built once per session, but deliberately without pushing an application
    context here: `g` lives on the app context, and Flask-Login caches the
    signed-in user in `g._login_user`. A session-wide context would leak that
    cached user (and its now-dropped database rows) into later tests.
    """
    return create_app("testing")


@pytest.fixture()
def db(app):
    """A clean schema, and a fresh application context, for every test."""
    with app.app_context():
        _db.create_all()
        try:
            yield _db
        finally:
            _db.session.rollback()
            _db.session.remove()
            _db.drop_all()


@pytest.fixture()
def client(app, db):
    """Anonymous test client."""
    return app.test_client()


# ============================================================
# MODEL FACTORIES
# ============================================================
def make_user(
    db,
    *,
    username="tester",
    email=None,
    role="staff",
    password="password123",
    is_active=True,
    name=None,
):
    user = User(
        name=name or username.title(),
        email=email or f"{username}@example.com",
        username=username,
        role=role,
        is_active=is_active,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def make_part(
    db,
    *,
    name="Brake Pad",
    sku="BP-001",
    price="500.00",
    cost_price="300.00",
    stock=25,
    min_stock=5,
    is_active=True,
    part_type="Brakes",
    brand="Brembo",
):
    part = Part(
        name=name,
        sku=sku,
        part_type=part_type,
        brand=brand,
        price=Decimal(price),
        cost_price=Decimal(cost_price),
        stock_quantity=stock,
        min_stock_level=min_stock,
        is_active=is_active,
    )
    db.session.add(part)
    db.session.commit()
    return part


def make_supplier(db, *, name="Acme Parts", email=None):
    supplier = Supplier(name=name, email=email)
    db.session.add(supplier)
    db.session.commit()
    return supplier


def make_customer(db, *, name="Walk In", email=None):
    customer = Customer(name=name, email=email)
    db.session.add(customer)
    db.session.commit()
    return customer


@pytest.fixture()
def factories(db):
    """Bundle of factory callables bound to the test session."""

    class _Factories:
        user = staticmethod(lambda **kw: make_user(db, **kw))
        part = staticmethod(lambda **kw: make_part(db, **kw))
        supplier = staticmethod(lambda **kw: make_supplier(db, **kw))
        customer = staticmethod(lambda **kw: make_customer(db, **kw))

    return _Factories()


# ============================================================
# USERS AND AUTHENTICATED CLIENTS
# ============================================================
@pytest.fixture()
def admin(db):
    return make_user(db, username="admin", role="admin")


@pytest.fixture()
def manager(db):
    return make_user(db, username="manager", role="manager")


@pytest.fixture()
def staff(db):
    return make_user(db, username="staff", role="staff")


def _login(client, user, password="password123"):
    response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 200, response.get_json()
    return client


@pytest.fixture()
def admin_client(app, db, admin):
    return _login(app.test_client(), admin)


@pytest.fixture()
def manager_client(app, db, manager):
    return _login(app.test_client(), manager)


@pytest.fixture()
def staff_client(app, db, staff):
    return _login(app.test_client(), staff)


@pytest.fixture()
def seeded_settings(db):
    """Default application settings, as `flask init-db` would create them."""
    SettingsService.init_defaults()
    return SettingsService
