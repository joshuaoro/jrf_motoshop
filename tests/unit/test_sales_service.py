"""
Unit tests for SalesService - the sale lifecycle, stock effects and money maths.
"""

from decimal import Decimal

import pytest

from app.models import Notification, Sale, SaleDetail, StockEntry
from app.services.sales import CustomerService, SalesService


def line(part, quantity=1, **kwargs):
    payload = {"part_id": part.id, "quantity": quantity}
    payload.update(kwargs)
    return payload


class TestCreateSale:
    def test_creates_sale_and_deducts_stock(self, db, factories):
        user = factories.user()
        part = factories.part(stock=10, price="100.00")

        sale = SalesService.create_sale(
            {"payment_method": "cash", "details": [line(part, 3)]}, user.id
        )

        assert sale.id is not None
        assert sale.receipt_number.startswith("RCP-")
        assert part.stock_quantity == 7
        assert sale.total_amount == Decimal("300.00")

    def test_totals_are_computed_not_taken_from_the_client(self, db, factories):
        """A client must not be able to dictate what it pays."""
        user = factories.user()
        part = factories.part(stock=10, price="100.00")

        sale = SalesService.create_sale(
            {
                "payment_method": "cash",
                # These are dump_only in the schema and ignored by the service.
                "total_amount": Decimal("0.01"),
                "details": [line(part, 2)],
            },
            user.id,
        )

        assert sale.total_amount == Decimal("200.00")

    def test_falls_back_to_catalogue_price_when_unit_price_omitted(self, db, factories):
        user = factories.user()
        part = factories.part(stock=5, price="249.99")

        sale = SalesService.create_sale(
            {"payment_method": "cash", "details": [line(part, 2)]}, user.id
        )

        detail = SaleDetail.query.filter_by(sale_id=sale.id).one()
        assert detail.unit_price == Decimal("249.99")
        assert sale.total_amount == Decimal("499.98")

    def test_snapshots_unit_cost_for_margin_reporting(self, db, factories):
        user = factories.user()
        part = factories.part(stock=5, price="500.00", cost_price="320.00")

        sale = SalesService.create_sale(
            {"payment_method": "cash", "details": [line(part, 2)]}, user.id
        )

        detail = SaleDetail.query.filter_by(sale_id=sale.id).one()
        assert detail.unit_cost == Decimal("320.00")

        # A later cost change must not rewrite history.
        part.cost_price = Decimal("999.00")
        db.session.commit()
        assert SaleDetail.query.filter_by(sale_id=sale.id).one().unit_cost == Decimal("320.00")

    def test_applies_discount_then_tax(self, db, factories):
        user = factories.user()
        part = factories.part(stock=10, price="1000.00")

        sale = SalesService.create_sale(
            {
                "payment_method": "cash",
                "details": [
                    line(
                        part,
                        1,
                        discount_percent=Decimal("10"),
                        tax_percent=Decimal("12"),
                    )
                ],
            },
            user.id,
        )

        # 1000 - 100 discount = 900 taxable; 12% = 108; total 1008.
        assert sale.discount_amount == Decimal("100.00")
        assert sale.tax_amount == Decimal("108.00")
        assert sale.total_amount == Decimal("1008.00")

    def test_records_a_stock_movement_per_line(self, db, factories):
        user = factories.user()
        part = factories.part(stock=10)

        sale = SalesService.create_sale(
            {"payment_method": "cash", "details": [line(part, 4)]}, user.id
        )

        entry = StockEntry.query.filter_by(reference_type="sale", reference_id=sale.id).one()
        assert entry.quantity == -4
        assert entry.movement_type == "sale"

    def test_rejects_insufficient_stock(self, db, factories):
        user = factories.user()
        part = factories.part(stock=2)

        with pytest.raises(ValueError, match="Insufficient stock"):
            SalesService.create_sale(
                {"payment_method": "cash", "details": [line(part, 3)]}, user.id
            )

    def test_rolls_back_entirely_when_a_later_line_fails(self, db, factories):
        """Stock must never be partially deducted by a failed sale."""
        user = factories.user()
        ok_part = factories.part(name="Good", sku="OK-1", stock=10)
        short_part = factories.part(name="Short", sku="SHORT-1", stock=1)

        with pytest.raises(ValueError):
            SalesService.create_sale(
                {
                    "payment_method": "cash",
                    "details": [line(ok_part, 5), line(short_part, 99)],
                },
                user.id,
            )

        db.session.expire_all()
        assert ok_part.stock_quantity == 10, "first line should have been rolled back"
        assert Sale.query.count() == 0
        assert StockEntry.query.count() == 0

    def test_rejects_inactive_part(self, db, factories):
        user = factories.user()
        part = factories.part(is_active=False)

        with pytest.raises(ValueError, match="not active"):
            SalesService.create_sale(
                {"payment_method": "cash", "details": [line(part, 1)]}, user.id
            )

    def test_rejects_unknown_part(self, db, factories):
        user = factories.user()

        with pytest.raises(ValueError, match="not found"):
            SalesService.create_sale(
                {
                    "payment_method": "cash",
                    "details": [{"part_id": 9999, "quantity": 1}],
                },
                user.id,
            )

    def test_rejects_unknown_customer(self, db, factories):
        user = factories.user()
        part = factories.part()

        with pytest.raises(ValueError, match="Customer 4242 not found"):
            SalesService.create_sale(
                {
                    "payment_method": "cash",
                    "customer_id": 4242,
                    "details": [line(part, 1)],
                },
                user.id,
            )

    def test_requires_at_least_one_line(self, db, factories):
        user = factories.user()

        with pytest.raises(ValueError, match="at least one item"):
            SalesService.create_sale({"payment_method": "cash", "details": []}, user.id)


class TestLowStockNotifications:
    def test_notifies_managers_only_about_parts_in_this_sale(self, db, factories, seeded_settings):
        admin = factories.user(username="admin", role="admin")
        seller = factories.user(username="seller", role="staff")
        sold = factories.part(name="Sold", sku="S-1", stock=6, min_stock=5)
        # Already low, but not part of this sale - must not be reported.
        factories.part(name="Untouched", sku="U-1", stock=1)

        SalesService.create_sale({"payment_method": "cash", "details": [line(sold, 5)]}, seller.id)

        notes = Notification.query.filter_by(user_id=admin.id).all()
        assert len(notes) == 1
        assert "Sold" in notes[0].message
        assert "Untouched" not in notes[0].message

    def test_silent_when_alerts_disabled(self, db, factories, seeded_settings):
        from app.services.system import SettingsService

        factories.user(username="admin", role="admin")
        seller = factories.user(username="seller")
        part = factories.part(stock=6, min_stock=5)

        SettingsService.update_settings({"inventory": {"low_stock_alert": False}}, seller.id)

        SalesService.create_sale({"payment_method": "cash", "details": [line(part, 5)]}, seller.id)

        assert Notification.query.count() == 0


class TestPayments:
    def test_partial_then_full_payment_updates_status(self, db, factories):
        user = factories.user()
        part = factories.part(stock=10, price="100.00")
        sale = SalesService.create_sale(
            {
                "payment_method": "cash",
                "payment_status": "pending",
                "details": [line(part, 2)],
            },
            user.id,
        )

        SalesService.process_payment(sale.id, Decimal("50.00"), "cash", user_id=user.id)
        assert sale.payment_status == "partial"

        SalesService.process_payment(sale.id, Decimal("150.00"), "cash", user_id=user.id)
        assert sale.payment_status == "paid"
        assert SalesService.get_amount_paid(sale) == Decimal("200.00")

    def test_rejects_overpayment(self, db, factories):
        user = factories.user()
        part = factories.part(stock=10, price="100.00")
        sale = SalesService.create_sale(
            {"payment_method": "cash", "details": [line(part, 1)]}, user.id
        )

        with pytest.raises(ValueError, match="exceeds the outstanding balance"):
            SalesService.process_payment(sale.id, Decimal("500.00"), "cash", user_id=user.id)

    def test_rejects_non_positive_amount(self, db, factories):
        user = factories.user()
        part = factories.part(stock=10, price="100.00")
        sale = SalesService.create_sale(
            {"payment_method": "cash", "details": [line(part, 1)]}, user.id
        )

        with pytest.raises(ValueError, match="greater than zero"):
            SalesService.process_payment(sale.id, Decimal("0"), "cash", user_id=user.id)


class TestVoidSale:
    def test_restores_stock_and_marks_refunded(self, db, factories):
        user = factories.user()
        part = factories.part(stock=10)
        sale = SalesService.create_sale(
            {"payment_method": "cash", "details": [line(part, 4)]}, user.id
        )
        assert part.stock_quantity == 6

        assert SalesService.void_sale(sale.id, user.id, "customer returned") is True

        db.session.expire_all()
        assert part.stock_quantity == 10
        assert sale.payment_status == "refunded"
        assert "customer returned" in sale.notes

    def test_cannot_void_twice(self, db, factories):
        user = factories.user()
        part = factories.part(stock=10)
        sale = SalesService.create_sale(
            {"payment_method": "cash", "details": [line(part, 1)]}, user.id
        )

        assert SalesService.void_sale(sale.id, user.id, "first") is True
        assert SalesService.void_sale(sale.id, user.id, "second") is False
        db.session.expire_all()
        assert part.stock_quantity == 10, "stock must not be credited twice"

    def test_missing_sale_returns_false(self, db, factories):
        user = factories.user()
        assert SalesService.void_sale(9999, user.id, "nope") is False


class TestSummaries:
    def test_summary_excludes_voided_sales(self, db, factories):
        user = factories.user()
        part = factories.part(stock=50, price="100.00")

        SalesService.create_sale({"payment_method": "cash", "details": [line(part, 1)]}, user.id)
        voided = SalesService.create_sale(
            {"payment_method": "cash", "details": [line(part, 1)]}, user.id
        )
        SalesService.void_sale(voided.id, user.id, "test")

        summary = SalesService.get_sales_summary()
        assert summary["total_sales"] == 1
        assert summary["total_revenue"] == 100.0

    def test_summary_on_empty_database(self, db):
        summary = SalesService.get_sales_summary()
        assert summary == {
            "total_sales": 0,
            "total_revenue": 0.0,
            "total_tax": 0.0,
            "total_discount": 0.0,
            "avg_sale": 0.0,
        }

    def test_top_selling_parts_ranks_by_units(self, db, factories):
        user = factories.user()
        popular = factories.part(name="Popular", sku="P-1", stock=100, price="10.00")
        rare = factories.part(name="Rare", sku="R-1", stock=100, price="10.00")

        SalesService.create_sale(
            {"payment_method": "cash", "details": [line(popular, 10)]}, user.id
        )
        SalesService.create_sale({"payment_method": "cash", "details": [line(rare, 2)]}, user.id)

        top = SalesService.get_top_selling_parts()
        assert [t["name"] for t in top] == ["Popular", "Rare"]
        assert top[0]["total_sold"] == 10


class TestCustomerService:
    def test_rejects_duplicate_email(self, db, factories):
        factories.customer(name="First", email="dup@example.com")

        with pytest.raises(ValueError, match="already exists"):
            CustomerService.create_customer({"name": "Second", "email": "dup@example.com"})

    def test_delete_deactivates_customer_with_sales(self, db, factories):
        user = factories.user()
        customer = factories.customer(name="Regular")
        part = factories.part(stock=10)
        SalesService.create_sale(
            {
                "payment_method": "cash",
                "customer_id": customer.id,
                "details": [line(part, 1)],
            },
            user.id,
        )

        assert CustomerService.delete_customer(customer.id) is True
        assert CustomerService.get_customer(customer.id) is not None
        assert customer.is_active is False

    def test_delete_removes_customer_without_sales(self, db, factories):
        customer = factories.customer()
        assert CustomerService.delete_customer(customer.id) is True
        assert CustomerService.get_customer(customer.id) is None
