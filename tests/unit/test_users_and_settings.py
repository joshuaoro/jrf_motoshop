"""
Unit tests for UserService, SettingsService and the schema layer.
"""

from decimal import Decimal

import pytest
from marshmallow import ValidationError
from werkzeug.datastructures import MultiDict

from app.models import Settings, User
from app.schemas import CustomerSchema, PartSchema, SaleSchema, UserSchema
from app.services.system import NotificationService, SettingsService
from app.services.users import UserService


class TestUserService:
    def test_creates_user_with_hashed_password(self, db):
        user = UserService.create_user(
            {
                "name": "Alice",
                "email": "alice@example.com",
                "username": "alice",
                "password": "secret123",
                "role": "manager",
            }
        )

        assert user.password_hash != "secret123"
        assert user.check_password("secret123") is True
        assert user.role == "manager"

    def test_requires_a_password(self, db):
        with pytest.raises(ValueError, match="password is required"):
            UserService.create_user(
                {
                    "name": "Bob",
                    "email": "bob@example.com",
                    "username": "bob",
                }
            )

    def test_rejects_invalid_role(self, db):
        with pytest.raises(ValueError, match="Role must be one of"):
            UserService.create_user(
                {
                    "name": "Eve",
                    "email": "eve@example.com",
                    "username": "eve",
                    "password": "secret123",
                    "role": "superuser",
                }
            )

    def test_rejects_duplicate_email_and_username(self, db, factories):
        factories.user(username="taken", email="taken@example.com")

        with pytest.raises(ValueError, match="Email already registered"):
            UserService.create_user(
                {
                    "name": "X",
                    "email": "taken@example.com",
                    "username": "other",
                    "password": "secret123",
                }
            )

        with pytest.raises(ValueError, match="Username already taken"):
            UserService.create_user(
                {
                    "name": "X",
                    "email": "other@example.com",
                    "username": "taken",
                    "password": "secret123",
                }
            )

    def test_self_edit_cannot_escalate_role(self, db, factories):
        user = factories.user(username="lowly", role="staff")

        UserService.update_user(
            user.id,
            {"name": "New Name", "role": "admin", "is_active": False},
            editor=user,
        )

        assert user.name == "New Name"
        assert user.role == "staff", "role must not be self-assignable"
        assert user.is_active is True

    def test_non_admin_cannot_edit_someone_else(self, db, factories):
        actor = factories.user(username="actor", role="staff")
        victim = factories.user(username="victim", role="staff")

        with pytest.raises(PermissionError):
            UserService.update_user(victim.id, {"name": "Hacked"}, editor=actor)

    def test_admin_can_change_a_role(self, db, factories):
        admin = factories.user(username="admin", role="admin")
        other = factories.user(username="other", role="staff")

        UserService.update_user(other.id, {"role": "manager"}, editor=admin)
        assert other.role == "manager"

    def test_cannot_demote_the_last_admin(self, db, factories):
        admin = factories.user(username="onlyadmin", role="admin")

        with pytest.raises(ValueError, match="last active administrator"):
            UserService.update_user(admin.id, {"role": "staff"}, editor=admin)

    def test_cannot_disable_the_last_admin(self, db, factories):
        admin = factories.user(username="onlyadmin", role="admin")

        with pytest.raises(ValueError, match="last active administrator"):
            UserService.update_user(admin.id, {"is_active": False}, editor=admin)

    def test_can_demote_an_admin_when_another_remains(self, db, factories):
        first = factories.user(username="admin1", role="admin")
        second = factories.user(username="admin2", role="admin")

        UserService.update_user(second.id, {"role": "staff"}, editor=first)
        assert second.role == "staff"

    def test_cannot_delete_own_account(self, db, factories):
        admin = factories.user(username="admin", role="admin")

        with pytest.raises(ValueError, match="your own account"):
            UserService.delete_user(admin.id, editor=admin)

    def test_cannot_delete_the_last_admin(self, db, factories):
        admin = factories.user(username="admin", role="admin")
        other = factories.user(username="other", role="admin")
        # Demote `other` so only one admin remains, then have it try to delete.
        UserService.update_user(other.id, {"role": "staff"}, editor=admin)

        with pytest.raises(ValueError, match="last active administrator"):
            UserService.delete_user(admin.id, editor=other)

    def test_deactivates_a_user_with_sales_history(self, db, factories):
        from app.services.sales import SalesService

        admin = factories.user(username="admin", role="admin")
        seller = factories.user(username="seller")
        part = factories.part(stock=5)
        SalesService.create_sale(
            {
                "payment_method": "cash",
                "details": [{"part_id": part.id, "quantity": 1}],
            },
            seller.id,
        )

        found, message = UserService.delete_user(seller.id, editor=admin)
        assert found is True
        assert "deactivated" in message
        assert db.session.get(User, seller.id).is_active is False

    def test_hard_deletes_a_user_with_no_history(self, db, factories):
        admin = factories.user(username="admin", role="admin")
        temp = factories.user(username="temp")

        found, message = UserService.delete_user(temp.id, editor=admin)
        assert found is True
        assert "deleted" in message
        assert db.session.get(User, temp.id) is None


class TestSettingsService:
    def test_init_defaults_is_idempotent(self, db):
        SettingsService.init_defaults()
        first = Settings.query.count()
        SettingsService.init_defaults()
        assert Settings.query.count() == first

    def test_returns_typed_values(self, db, seeded_settings):
        assert SettingsService.get_setting("inventory", "low_stock_threshold") == 5
        assert SettingsService.get_setting("inventory", "low_stock_alert") is True
        assert SettingsService.get_setting("sales", "tax_rate") == 0.12

    def test_default_is_used_for_a_missing_setting(self, db):
        assert SettingsService.get_setting("nope", "missing", "fallback") == "fallback"
        assert SettingsService.get_setting("nope", "missing") is None

    def test_update_reports_unknown_keys(self, db, seeded_settings, factories):
        user = factories.user()
        result = SettingsService.update_settings(
            {"inventory": {"low_stock_threshold": 12, "not_a_setting": "x"}}, user.id
        )

        assert len(result["updated"]) == 1
        assert len(result["errors"]) == 1
        assert SettingsService.get_setting("inventory", "low_stock_threshold") == 12

    def test_reset_restores_defaults(self, db, seeded_settings, factories):
        user = factories.user()
        SettingsService.update_settings({"inventory": {"low_stock_threshold": 99}}, user.id)
        assert SettingsService.get_setting("inventory", "low_stock_threshold") == 99

        SettingsService.reset_to_defaults("inventory")
        assert SettingsService.get_setting("inventory", "low_stock_threshold") == 5

    def test_secret_values_are_masked_unless_requested(self, db):
        db.session.add(
            Settings(
                category="security",
                setting_key="api_key",
                setting_value="super-secret",
                setting_type="password",
            )
        )
        db.session.commit()

        masked = SettingsService.get_all_settings(include_sensitive=False)
        revealed = SettingsService.get_all_settings(include_sensitive=True)

        assert masked["security"]["api_key"]["value"] == "********"
        assert revealed["security"]["api_key"]["value"] == "super-secret"


class TestNotificationService:
    def test_mark_read_is_idempotent(self, db, factories):
        user = factories.user()
        note = NotificationService.create_notification(user.id, "Hi", "Body")

        assert NotificationService.mark_read(note.id, user.id) is True
        assert NotificationService.mark_read(note.id, user.id) is True
        assert NotificationService.get_unread_count(user.id) == 0

    def test_cannot_read_another_users_notification(self, db, factories):
        owner = factories.user(username="owner")
        other = factories.user(username="other")
        note = NotificationService.create_notification(owner.id, "Hi", "Body")

        assert NotificationService.mark_read(note.id, other.id) is False
        assert NotificationService.get_unread_count(owner.id) == 1


class TestSchemas:
    def test_load_returns_a_plain_dict(self, db):
        """The service layer does Model(**data) - load must not return a model."""
        data = CustomerSchema().load({"name": "Bob"})
        assert isinstance(data, dict)

    def test_form_strings_are_coerced_and_blanks_nulled(self, db):
        form = MultiDict(
            [
                ("name", "  Brake Pad  "),
                ("price", "450.50"),
                ("stock_quantity", "10"),
                ("brand", ""),
                ("csrf_token", "ignored"),
            ]
        )
        data = PartSchema().load(form)

        assert data["name"] == "Brake Pad"
        assert data["price"] == Decimal("450.50")
        assert data["stock_quantity"] == 10
        assert data["brand"] is None
        assert "csrf_token" not in data

    def test_server_computed_fields_are_stripped_from_input(self, db):
        data = SaleSchema().load(
            {
                "payment_method": "cash",
                "total_amount": "0.01",
                "receipt_number": "FAKE",
                "details": [{"part_id": 1, "quantity": 1}],
            }
        )
        assert "total_amount" not in data
        assert "receipt_number" not in data

    def test_duplicate_parts_in_one_sale_are_rejected(self, db):
        with pytest.raises(ValidationError, match="only appear once"):
            SaleSchema().load(
                {
                    "payment_method": "cash",
                    "details": [
                        {"part_id": 1, "quantity": 1},
                        {"part_id": 1, "quantity": 2},
                    ],
                }
            )

    def test_invalid_enum_values_are_rejected(self, db):
        with pytest.raises(ValidationError):
            SaleSchema().load(
                {
                    "payment_method": "crypto",
                    "details": [{"part_id": 1, "quantity": 1}],
                }
            )

    def test_negative_quantity_is_rejected(self, db):
        with pytest.raises(ValidationError):
            SaleSchema().load(
                {
                    "payment_method": "cash",
                    "details": [{"part_id": 1, "quantity": -5}],
                }
            )

    def test_password_is_never_dumped(self, db, factories):
        user = factories.user()
        dumped = UserSchema().dump(user)
        assert "password" not in dumped
        assert "password_hash" not in dumped
