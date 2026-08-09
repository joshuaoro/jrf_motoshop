"""
Unit tests for InventoryService and SupplierService.
"""

from decimal import Decimal

import pytest

from app.models import Part, StockEntry, Supplier
from app.services.inventory import InventoryService, SupplierService


class TestCreatePart:
    def test_generates_sku_when_omitted(self, db, factories):
        user = factories.user()
        part = InventoryService.create_part({"name": "Chain", "price": Decimal("100.00")}, user.id)
        assert part.sku.startswith("PRT-")

    def test_records_opening_stock_entry(self, db, factories):
        user = factories.user()
        part = InventoryService.create_part(
            {"name": "Chain", "price": Decimal("100.00"), "stock_quantity": 12},
            user.id,
        )

        entry = StockEntry.query.filter_by(part_id=part.id).one()
        assert entry.quantity == 12
        assert entry.reference_type == "initial"

    def test_no_stock_entry_when_opening_stock_is_zero(self, db, factories):
        user = factories.user()
        InventoryService.create_part(
            {"name": "Chain", "price": Decimal("100.00"), "stock_quantity": 0}, user.id
        )
        assert StockEntry.query.count() == 0

    def test_rejects_duplicate_sku(self, db, factories):
        user = factories.user()
        factories.part(sku="DUP-1")

        with pytest.raises(ValueError, match="already in use"):
            InventoryService.create_part(
                {"name": "Other", "price": Decimal("1.00"), "sku": "DUP-1"}, user.id
            )

    def test_rejects_duplicate_barcode(self, db, factories):
        user = factories.user()
        InventoryService.create_part(
            {"name": "A", "price": Decimal("1.00"), "sku": "A-1", "barcode": "123"},
            user.id,
        )

        with pytest.raises(ValueError, match="already in use"):
            InventoryService.create_part(
                {"name": "B", "price": Decimal("1.00"), "sku": "B-1", "barcode": "123"},
                user.id,
            )

    def test_does_not_leave_a_partial_row_after_a_failure(self, db, factories):
        user = factories.user()
        factories.part(sku="DUP-1")

        with pytest.raises(ValueError):
            InventoryService.create_part(
                {"name": "Other", "price": Decimal("1.00"), "sku": "DUP-1"}, user.id
            )

        assert Part.query.filter_by(name="Other").count() == 0

    def test_links_suppliers(self, db, factories):
        user = factories.user()
        supplier = factories.supplier()

        part = InventoryService.create_part(
            {
                "name": "Chain",
                "price": Decimal("100.00"),
                "supplier_ids": [supplier.id],
            },
            user.id,
        )
        assert [s.id for s in part.suppliers] == [supplier.id]


class TestUpdatePart:
    def test_logs_a_stock_entry_when_quantity_changes(self, db, factories):
        user = factories.user()
        part = factories.part(stock=10)

        InventoryService.update_part(part.id, {"stock_quantity": 4}, user.id)

        entry = StockEntry.query.filter_by(reference_type="manual").one()
        assert entry.quantity == -6

    def test_no_stock_entry_when_quantity_unchanged(self, db, factories):
        user = factories.user()
        part = factories.part(stock=10)

        InventoryService.update_part(part.id, {"name": "Renamed"}, user.id)

        assert StockEntry.query.filter_by(reference_type="manual").count() == 0
        assert part.name == "Renamed"

    def test_allows_keeping_its_own_sku(self, db, factories):
        user = factories.user()
        part = factories.part(sku="KEEP-1")

        updated = InventoryService.update_part(
            part.id, {"sku": "KEEP-1", "name": "Same SKU"}, user.id
        )
        assert updated.name == "Same SKU"

    def test_rejects_taking_another_parts_sku(self, db, factories):
        user = factories.user()
        factories.part(name="First", sku="TAKEN")
        second = factories.part(name="Second", sku="FREE")

        with pytest.raises(ValueError, match="already in use"):
            InventoryService.update_part(second.id, {"sku": "TAKEN"}, user.id)

    def test_missing_part_returns_none(self, db, factories):
        user = factories.user()
        assert InventoryService.update_part(9999, {"name": "x"}, user.id) is None


class TestAdjustStock:
    def test_increases_and_logs(self, db, factories):
        user = factories.user()
        part = factories.part(stock=5)

        InventoryService.adjust_stock(part.id, 7, "purchase", user_id=user.id)

        assert part.stock_quantity == 12
        assert StockEntry.query.filter_by(movement_type="purchase").one().quantity == 7

    def test_refuses_to_go_negative(self, db, factories):
        user = factories.user()
        part = factories.part(stock=3)

        with pytest.raises(ValueError, match="Insufficient stock"):
            InventoryService.adjust_stock(part.id, -10, "adjustment", user_id=user.id)

        db.session.expire_all()
        assert part.stock_quantity == 3

    def test_missing_part_returns_none(self, db, factories):
        user = factories.user()
        assert InventoryService.adjust_stock(9999, 1, "adjustment", user_id=user.id) is None


class TestDeletePart:
    def test_hard_deletes_a_part_with_no_history(self, db, factories):
        part = factories.part()
        assert InventoryService.delete_part(part.id) is True
        assert InventoryService.get_part(part.id) is None

    def test_deactivates_a_part_that_has_been_sold(self, db, factories):
        from app.services.sales import SalesService

        user = factories.user()
        part = factories.part(stock=10)
        SalesService.create_sale(
            {
                "payment_method": "cash",
                "details": [{"part_id": part.id, "quantity": 1}],
            },
            user.id,
        )

        assert InventoryService.delete_part(part.id) is True
        assert InventoryService.get_part(part.id) is not None
        assert part.is_active is False


class TestQueries:
    def test_low_stock_uses_the_configured_threshold(self, db, factories, seeded_settings):
        factories.part(name="Low", sku="L-1", stock=2)
        factories.part(name="Fine", sku="F-1", stock=50)

        low = InventoryService.get_low_stock_parts()
        assert [p.name for p in low] == ["Low"]

    def test_explicit_threshold_overrides_the_setting(self, db, factories, seeded_settings):
        factories.part(name="Twenty", sku="T-1", stock=20)
        assert InventoryService.get_low_stock_parts(threshold=25)
        assert not InventoryService.get_low_stock_parts(threshold=10)

    def test_search_matches_name_and_sku(self, db, factories):
        factories.part(name="Front Brake Pad", sku="BRK-100")
        factories.part(name="Oil Filter", sku="OIL-200")

        by_name, _ = InventoryService.get_parts(search="brake")
        by_sku, _ = InventoryService.get_parts(search="OIL-2")
        assert [p.sku for p in by_name] == ["BRK-100"]
        assert [p.sku for p in by_sku] == ["OIL-200"]

    def test_inactive_parts_are_excluded_by_default(self, db, factories):
        factories.part(name="Gone", sku="G-1", is_active=False)
        parts, total = InventoryService.get_parts()
        assert total == 0


class TestSupplierService:
    def test_rejects_duplicate_email(self, db, factories):
        factories.supplier(name="First", email="dup@supply.com")

        with pytest.raises(ValueError, match="already exists"):
            SupplierService.create_supplier({"name": "Second", "email": "dup@supply.com"})

    def test_link_and_unlink_part(self, db, factories):
        supplier = factories.supplier()
        part = factories.part()

        assert (
            SupplierService.link_part(supplier.id, part.id, {"cost_price": Decimal("50.00")})
            is True
        )
        db.session.refresh(supplier)
        assert part in supplier.parts

        assert SupplierService.unlink_part(supplier.id, part.id) is True
        db.session.refresh(supplier)
        assert part not in supplier.parts

    def test_linking_twice_is_idempotent(self, db, factories):
        supplier = factories.supplier()
        part = factories.part()

        assert SupplierService.link_part(supplier.id, part.id) is True
        assert SupplierService.link_part(supplier.id, part.id) is True
        db.session.refresh(supplier)
        assert len(supplier.parts) == 1

    def test_link_with_unknown_ids_returns_false(self, db, factories):
        supplier = factories.supplier()
        assert SupplierService.link_part(supplier.id, 9999) is False
        assert SupplierService.link_part(9999, 1) is False

    def test_deleting_a_linked_supplier_clears_the_association(self, db, factories):
        supplier = factories.supplier()
        part = factories.part()
        SupplierService.link_part(supplier.id, part.id)

        assert SupplierService.delete_supplier(supplier.id) is True
        assert db.session.get(Supplier, supplier.id) is None
        # The part itself must survive.
        assert db.session.get(Part, part.id) is not None
