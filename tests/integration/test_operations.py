"""
Tests for expenses, purchase orders and maintenance logs.

These three models previously had no way in: the expenses report could only
report zeros, and purchase orders existed only as a foreign key.
"""

from app.models import Part, PurchaseOrder


def po_payload(supplier, part, quantity=10, unit_price="40.00", **kwargs):
    payload = {
        "supplier_id": supplier.id,
        "items": [{"part_id": part.id, "quantity": quantity, "unit_price": unit_price}],
    }
    payload.update(kwargs)
    return payload


class TestExpenses:
    def test_create_and_list(self, manager_client):
        response = manager_client.post(
            "/api/expenses",
            json={
                "category": "rent",
                "description": "Shop rent for August",
                "amount": "25000.00",
                "payment_method": "bank_transfer",
            },
        )
        assert response.status_code == 201
        assert response.get_json()["amount"] == 25000.0

        listed = manager_client.get("/api/expenses").get_json()
        assert listed["pagination"]["total"] == 1

    def test_expenses_report_reflects_recorded_expenses(self, manager_client):
        """Regression: the report existed with no way to populate it."""
        for amount, category in (("1000.00", "utilities"), ("500.00", "supplies")):
            manager_client.post(
                "/api/expenses",
                json={
                    "category": category,
                    "description": f"{category} bill",
                    "amount": amount,
                    "payment_method": "cash",
                },
            )

        report = manager_client.get("/api/reports/expenses").get_json()
        assert report["total_expenses"] == 1500.0
        assert {row["category"] for row in report["by_category"]} == {
            "utilities",
            "supplies",
        }

    def test_rejects_unknown_category(self, manager_client):
        response = manager_client.post(
            "/api/expenses",
            json={
                "category": "bribes",
                "description": "x",
                "amount": "1.00",
                "payment_method": "cash",
            },
        )
        assert response.status_code == 400
        assert "category" in response.get_json()["details"]

    def test_rejects_non_positive_amount(self, manager_client):
        response = manager_client.post(
            "/api/expenses",
            json={
                "category": "other",
                "description": "x",
                "amount": "0",
                "payment_method": "cash",
            },
        )
        assert response.status_code == 400

    def test_staff_cannot_touch_expenses(self, staff_client):
        assert staff_client.get("/api/expenses").status_code == 403
        assert (
            staff_client.post(
                "/api/expenses",
                json={
                    "category": "other",
                    "description": "x",
                    "amount": "1.00",
                    "payment_method": "cash",
                },
            ).status_code
            == 403
        )

    def test_update_and_delete(self, manager_client):
        expense_id = manager_client.post(
            "/api/expenses",
            json={
                "category": "other",
                "description": "Typo",
                "amount": "10.00",
                "payment_method": "cash",
            },
        ).get_json()["id"]

        updated = manager_client.put(
            f"/api/expenses/{expense_id}", json={"description": "Corrected"}
        )
        assert updated.get_json()["description"] == "Corrected"

        assert manager_client.delete(f"/api/expenses/{expense_id}").status_code == 200
        assert manager_client.get(f"/api/expenses/{expense_id}").status_code == 404


class TestPurchaseOrders:
    def test_create_computes_totals_from_line_items(self, manager_client, factories):
        supplier = factories.supplier()
        part = factories.part()

        response = manager_client.post(
            "/api/purchase-orders",
            json=po_payload(
                supplier, part, quantity=10, unit_price="40.00", shipping_cost="150.00"
            ),
        )
        body = response.get_json()

        assert response.status_code == 201
        assert body["order_number"].startswith("PO-")
        assert body["subtotal"] == 400.0
        assert body["total_amount"] == 550.0  # 400 + 150 shipping
        assert body["status"] == "pending"

    def test_client_cannot_dictate_the_total(self, manager_client, factories):
        supplier = factories.supplier()
        part = factories.part()

        body = manager_client.post(
            "/api/purchase-orders",
            json={**po_payload(supplier, part), "total_amount": "1.00"},
        ).get_json()

        assert body["total_amount"] == 400.0

    def test_rejects_duplicate_parts(self, manager_client, factories):
        supplier = factories.supplier()
        part = factories.part()

        response = manager_client.post(
            "/api/purchase-orders",
            json={
                "supplier_id": supplier.id,
                "items": [
                    {"part_id": part.id, "quantity": 1, "unit_price": "1.00"},
                    {"part_id": part.id, "quantity": 2, "unit_price": "1.00"},
                ],
            },
        )
        assert response.status_code == 400

    def test_rejects_unknown_supplier(self, manager_client, factories):
        part = factories.part()
        response = manager_client.post(
            "/api/purchase-orders",
            json={
                "supplier_id": 9999,
                "items": [{"part_id": part.id, "quantity": 1, "unit_price": "1.00"}],
            },
        )
        assert response.status_code == 400
        assert "Supplier 9999 not found" in response.get_json()["error"]

    def test_receiving_increases_stock_and_records_a_movement(self, manager_client, db, factories):
        supplier = factories.supplier()
        part = factories.part(stock=5, cost_price="30.00")

        order_id = manager_client.post(
            "/api/purchase-orders",
            json=po_payload(supplier, part, quantity=10, unit_price="40.00"),
        ).get_json()["id"]

        response = manager_client.post(
            f"/api/purchase-orders/{order_id}/receive",
            json={"items": [{"part_id": part.id, "quantity": 10}]},
        )
        assert response.status_code == 200
        assert response.get_json()["status"] == "received"

        db.session.refresh(part)
        assert part.stock_quantity == 15
        # Cost price tracks what was actually paid.
        assert float(part.cost_price) == 40.0

        from app.models import StockEntry

        entry = StockEntry.query.filter_by(
            reference_type="purchase_order", reference_id=order_id
        ).one()
        assert entry.quantity == 10

    def test_partial_receipt_marks_the_order_partial(self, manager_client, db, factories):
        supplier = factories.supplier()
        part = factories.part(stock=0)

        order_id = manager_client.post(
            "/api/purchase-orders",
            json=po_payload(supplier, part, quantity=10),
        ).get_json()["id"]

        body = manager_client.post(
            f"/api/purchase-orders/{order_id}/receive",
            json={"items": [{"part_id": part.id, "quantity": 4}]},
        ).get_json()

        assert body["status"] == "partial"
        db.session.refresh(part)
        assert part.stock_quantity == 4

        # The rest arrives later.
        body = manager_client.post(
            f"/api/purchase-orders/{order_id}/receive",
            json={"items": [{"part_id": part.id, "quantity": 6}]},
        ).get_json()
        assert body["status"] == "received"
        db.session.refresh(part)
        assert part.stock_quantity == 10

    def test_cannot_over_receive(self, manager_client, factories):
        supplier = factories.supplier()
        part = factories.part(stock=0)

        order_id = manager_client.post(
            "/api/purchase-orders", json=po_payload(supplier, part, quantity=5)
        ).get_json()["id"]

        response = manager_client.post(
            f"/api/purchase-orders/{order_id}/receive",
            json={"items": [{"part_id": part.id, "quantity": 6}]},
        )
        assert response.status_code == 400
        assert "only 5 outstanding" in response.get_json()["error"]

    def test_cannot_receive_a_part_not_on_the_order(self, manager_client, factories):
        supplier = factories.supplier()
        ordered = factories.part(name="Ordered", sku="ORD-1")
        other = factories.part(name="Other", sku="OTH-1")

        order_id = manager_client.post(
            "/api/purchase-orders", json=po_payload(supplier, ordered)
        ).get_json()["id"]

        response = manager_client.post(
            f"/api/purchase-orders/{order_id}/receive",
            json={"items": [{"part_id": other.id, "quantity": 1}]},
        )
        assert response.status_code == 400
        assert "not on this purchase order" in response.get_json()["error"]

    def test_receipt_is_atomic(self, manager_client, db, factories):
        """A bad second line must not leave the first line's stock applied."""
        supplier = factories.supplier()
        good = factories.part(name="Good", sku="G-1", stock=0)
        other = factories.part(name="NotOrdered", sku="N-1", stock=0)

        order_id = manager_client.post(
            "/api/purchase-orders", json=po_payload(supplier, good, quantity=5)
        ).get_json()["id"]

        response = manager_client.post(
            f"/api/purchase-orders/{order_id}/receive",
            json={
                "items": [
                    {"part_id": good.id, "quantity": 5},
                    {"part_id": other.id, "quantity": 1},
                ]
            },
        )
        assert response.status_code == 400

        db.session.expire_all()
        assert db.session.get(Part, good.id).stock_quantity == 0
        assert db.session.get(PurchaseOrder, order_id).status == "pending"

    def test_invalid_status_transition_is_rejected(self, manager_client, factories):
        supplier = factories.supplier()
        part = factories.part()

        order_id = manager_client.post(
            "/api/purchase-orders", json=po_payload(supplier, part)
        ).get_json()["id"]

        # pending -> received is not allowed; it must be ordered first.
        response = manager_client.post(
            f"/api/purchase-orders/{order_id}/status", json={"status": "received"}
        )
        assert response.status_code == 400
        assert "Cannot change status" in response.get_json()["error"]

        assert (
            manager_client.post(
                f"/api/purchase-orders/{order_id}/status", json={"status": "ordered"}
            ).status_code
            == 200
        )

    def test_cannot_receive_against_a_cancelled_order(self, manager_client, factories):
        supplier = factories.supplier()
        part = factories.part()

        order_id = manager_client.post(
            "/api/purchase-orders", json=po_payload(supplier, part)
        ).get_json()["id"]
        manager_client.post(f"/api/purchase-orders/{order_id}/status", json={"status": "cancelled"})

        response = manager_client.post(
            f"/api/purchase-orders/{order_id}/receive",
            json={"items": [{"part_id": part.id, "quantity": 1}]},
        )
        assert response.status_code == 400

    def test_cannot_delete_an_order_with_received_stock(self, manager_client, factories):
        supplier = factories.supplier()
        part = factories.part(stock=0)

        order_id = manager_client.post(
            "/api/purchase-orders", json=po_payload(supplier, part, quantity=5)
        ).get_json()["id"]
        manager_client.post(
            f"/api/purchase-orders/{order_id}/receive",
            json={"items": [{"part_id": part.id, "quantity": 2}]},
        )

        response = manager_client.delete(f"/api/purchase-orders/{order_id}")
        assert response.status_code == 400
        assert "cancel it instead" in response.get_json()["error"]

    def test_supplier_with_orders_is_deactivated_not_deleted(self, manager_client, db, factories):
        """Regression: this branch existed but nothing could ever reach it."""
        supplier = factories.supplier()
        part = factories.part()

        manager_client.post("/api/purchase-orders", json=po_payload(supplier, part))

        assert manager_client.delete(f"/api/suppliers/{supplier.id}").status_code == 200
        db.session.refresh(supplier)
        assert supplier.is_active is False

    def test_staff_cannot_raise_purchase_orders(self, staff_client, factories):
        supplier = factories.supplier()
        part = factories.part()
        response = staff_client.post("/api/purchase-orders", json=po_payload(supplier, part))
        assert response.status_code == 403


class TestMaintenance:
    def test_create_and_list(self, manager_client):
        response = manager_client.post(
            "/api/maintenance",
            json={
                "equipment_name": "Tyre changer",
                "maintenance_type": "preventive",
                "description": "Quarterly service",
                "cost": "1200.00",
            },
        )
        assert response.status_code == 201
        assert response.get_json()["equipment_name"] == "Tyre changer"

        listed = manager_client.get("/api/maintenance").get_json()
        assert listed["pagination"]["total"] == 1

    def test_rejects_unknown_type(self, manager_client):
        response = manager_client.post(
            "/api/maintenance",
            json={
                "equipment_name": "Lift",
                "maintenance_type": "vibes",
                "description": "x",
            },
        )
        assert response.status_code == 400

    def test_overdue_filter(self, manager_client):
        manager_client.post(
            "/api/maintenance",
            json={
                "equipment_name": "Overdue lift",
                "maintenance_type": "inspection",
                "description": "Annual",
                "next_maintenance": "2020-01-01T00:00:00",
            },
        )
        manager_client.post(
            "/api/maintenance",
            json={
                "equipment_name": "Future lift",
                "maintenance_type": "inspection",
                "description": "Annual",
                "next_maintenance": "2099-01-01T00:00:00",
            },
        )

        overdue = manager_client.get("/api/maintenance?overdue=true").get_json()
        assert overdue["pagination"]["total"] == 1
        assert overdue["maintenance_logs"][0]["equipment_name"] == "Overdue lift"
        assert overdue["maintenance_logs"][0]["is_overdue"] is True

    def test_rejects_unknown_part(self, manager_client):
        response = manager_client.post(
            "/api/maintenance",
            json={
                "equipment_name": "Lift",
                "maintenance_type": "corrective",
                "description": "x",
                "part_id": 9999,
            },
        )
        assert response.status_code == 400
