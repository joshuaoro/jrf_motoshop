"""
Tests for the expenses, purchase order and maintenance pages.

These render real templates, so they catch the class of bug that only shows up
at render time: a missing context variable, a bad url_for(), or a filter that
does not exist.
"""

import pytest


def make_expense(client, **overrides):
    payload = {
        "category": "utilities",
        "description": "Electricity bill",
        "amount": "3200.00",
        "payment_method": "cash",
    }
    payload.update(overrides)
    return client.post("/api/expenses", json=payload)


def make_order(client, supplier, part, **overrides):
    payload = {
        "supplier_id": supplier.id,
        "items": [{"part_id": part.id, "quantity": 10, "unit_price": "40.00"}],
    }
    payload.update(overrides)
    return client.post("/api/purchase-orders", json=payload)


def make_log(client, **overrides):
    payload = {
        "equipment_name": "Hydraulic lift",
        "maintenance_type": "preventive",
        "description": "Annual service",
        "cost": "2500.00",
    }
    payload.update(overrides)
    return client.post("/api/maintenance", json=payload)


class TestExpensesPage:
    def test_renders_empty(self, manager_client, seeded_settings):
        response = manager_client.get("/expenses/")
        assert response.status_code == 200
        assert b"No expenses recorded" in response.data

    def test_renders_with_data_and_totals(self, manager_client, seeded_settings):
        make_expense(manager_client, amount="1000.00", category="rent")
        make_expense(manager_client, amount="250.50", category="supplies")

        body = manager_client.get("/expenses/").get_data(as_text=True)
        assert "Electricity bill" in body
        # Totals are formatted through the peso filter.
        assert "1,250.50" in body

    def test_category_filter(self, manager_client, seeded_settings):
        make_expense(manager_client, description="Rent payment", category="rent")
        make_expense(manager_client, description="Bolts and nuts", category="supplies")

        body = manager_client.get("/expenses/?category=rent").get_data(as_text=True)
        assert "Rent payment" in body
        assert "Bolts and nuts" not in body

    def test_search_filter(self, manager_client, seeded_settings):
        make_expense(manager_client, description="Findable thing", vendor="Meralco")
        make_expense(manager_client, description="Other thing")

        body = manager_client.get("/expenses/?search=Findable").get_data(as_text=True)
        assert "Findable thing" in body
        assert "Other thing" not in body

    def test_invalid_date_is_ignored_not_a_500(self, manager_client, seeded_settings):
        response = manager_client.get("/expenses/?start_date=not-a-date")
        assert response.status_code == 200
        assert b"Ignoring invalid date" in response.data

    def test_pagination_renders(self, manager_client, seeded_settings):
        for i in range(25):
            make_expense(manager_client, description=f"Expense {i}")

        body = manager_client.get("/expenses/").get_data(as_text=True)
        assert "Page 1 of 2" in body
        assert manager_client.get("/expenses/?page=2").status_code == 200

    def test_staff_cannot_open_expenses(self, staff_client, seeded_settings):
        response = staff_client.get("/expenses/")
        assert response.status_code == 302

    def test_expense_names_are_escaped(self, manager_client, seeded_settings):
        make_expense(manager_client, description='<img src=x onerror="alert(1)">')

        body = manager_client.get("/expenses/").get_data(as_text=True)
        assert 'onerror="alert(1)"' not in body


class TestPurchaseOrderPages:
    def test_list_renders_empty(self, manager_client, seeded_settings):
        response = manager_client.get("/purchase-orders/")
        assert response.status_code == 200
        assert b"No purchase orders yet" in response.data

    def test_list_renders_with_data(self, manager_client, seeded_settings, factories):
        supplier = factories.supplier(name="Acme Supply")
        part = factories.part()
        make_order(manager_client, supplier, part)

        body = manager_client.get("/purchase-orders/").get_data(as_text=True)
        assert "Acme Supply" in body
        assert "PO-" in body

    def test_detail_renders(self, manager_client, seeded_settings, factories):
        supplier = factories.supplier()
        part = factories.part(name="Brake Disc", sku="BD-9")
        order_id = make_order(manager_client, supplier, part).get_json()["id"]

        body = manager_client.get(f"/purchase-orders/{order_id}").get_data(as_text=True)
        assert "Brake Disc" in body
        assert "BD-9" in body
        # Pending orders cannot be received yet.
        assert "Mark this order" in body

    def test_detail_shows_receive_form_once_ordered(
        self, manager_client, seeded_settings, factories
    ):
        supplier = factories.supplier()
        part = factories.part()
        order_id = make_order(manager_client, supplier, part).get_json()["id"]
        manager_client.post(f"/api/purchase-orders/{order_id}/status", json={"status": "ordered"})

        body = manager_client.get(f"/purchase-orders/{order_id}").get_data(as_text=True)
        assert "Receive items" in body
        assert "receive-qty" in body

    def test_detail_offers_only_valid_next_statuses(
        self, manager_client, seeded_settings, factories
    ):
        supplier = factories.supplier()
        part = factories.part()
        order_id = make_order(manager_client, supplier, part).get_json()["id"]

        body = manager_client.get(f"/purchase-orders/{order_id}").get_data(as_text=True)
        # pending -> {ordered, cancelled} only.
        assert "Mark ordered" in body
        assert "Mark cancelled" in body
        assert "Mark received" not in body

    def test_received_order_shows_no_transitions(self, manager_client, seeded_settings, factories):
        supplier = factories.supplier()
        part = factories.part(stock=0)
        order_id = make_order(manager_client, supplier, part).get_json()["id"]
        manager_client.post(f"/api/purchase-orders/{order_id}/status", json={"status": "ordered"})
        manager_client.post(
            f"/api/purchase-orders/{order_id}/receive",
            json={"items": [{"part_id": part.id, "quantity": 10}]},
        )

        body = manager_client.get(f"/purchase-orders/{order_id}").get_data(as_text=True)
        assert "Mark ordered" not in body
        assert "Receive items" not in body

    def test_missing_order_redirects(self, manager_client, seeded_settings):
        response = manager_client.get("/purchase-orders/9999")
        assert response.status_code == 302

    def test_status_filter(self, manager_client, seeded_settings, factories):
        supplier = factories.supplier()
        part = factories.part()
        order_id = make_order(manager_client, supplier, part).get_json()["id"]
        manager_client.post(f"/api/purchase-orders/{order_id}/status", json={"status": "cancelled"})

        assert manager_client.get("/purchase-orders/?status=cancelled").status_code == 200
        body = manager_client.get("/purchase-orders/?status=pending").get_data(as_text=True)
        assert "No purchase orders yet" in body

    def test_staff_cannot_open_purchase_orders(self, staff_client, seeded_settings):
        assert staff_client.get("/purchase-orders/").status_code == 302

    def test_part_names_are_escaped_in_the_picker(self, manager_client, seeded_settings, factories):
        factories.part(name='<img src=x onerror="alert(1)">', sku="XSS-2")

        body = manager_client.get("/purchase-orders/").get_data(as_text=True)
        assert 'onerror="alert(1)"' not in body


class TestMaintenancePage:
    def test_renders_empty(self, manager_client, seeded_settings):
        response = manager_client.get("/maintenance/")
        assert response.status_code == 200
        assert b"No maintenance records" in response.data

    def test_renders_with_data(self, manager_client, seeded_settings):
        make_log(manager_client, equipment_name="Air compressor")

        body = manager_client.get("/maintenance/").get_data(as_text=True)
        assert "Air compressor" in body
        assert "2,500.00" in body

    def test_overdue_is_highlighted_and_counted(self, manager_client, seeded_settings):
        make_log(
            manager_client,
            equipment_name="Overdue rig",
            next_maintenance="2020-01-01T00:00:00",
        )

        body = manager_client.get("/maintenance/").get_data(as_text=True)
        assert "Overdue rig" in body
        assert "bg-red-50" in body

        filtered = manager_client.get("/maintenance/?overdue=true").get_data(as_text=True)
        assert "Overdue rig" in filtered

    def test_type_filter(self, manager_client, seeded_settings):
        make_log(
            manager_client,
            equipment_name="Preventive job",
            maintenance_type="preventive",
        )
        make_log(manager_client, equipment_name="Emergency job", maintenance_type="emergency")

        body = manager_client.get("/maintenance/?type=emergency").get_data(as_text=True)
        assert "Emergency job" in body
        assert "Preventive job" not in body

    def test_summary_counts(self, manager_client, seeded_settings):
        make_log(manager_client, next_maintenance="2020-01-01T00:00:00")
        make_log(manager_client, next_maintenance="2099-01-01T00:00:00")

        body = manager_client.get("/maintenance/").get_data(as_text=True)
        assert "Overdue" in body
        assert "Spend (12 months)" in body

    def test_staff_cannot_open_maintenance(self, staff_client, seeded_settings):
        assert staff_client.get("/maintenance/").status_code == 302

    def test_equipment_names_are_escaped(self, manager_client, seeded_settings):
        make_log(manager_client, equipment_name='<img src=x onerror="alert(1)">')

        body = manager_client.get("/maintenance/").get_data(as_text=True)
        assert 'onerror="alert(1)"' not in body


class TestNavigation:
    @pytest.mark.parametrize("path", ["/expenses/", "/purchase-orders/", "/maintenance/"])
    def test_admin_sees_links_to_the_new_pages(self, admin_client, seeded_settings, path):
        body = admin_client.get("/dashboard").get_data(as_text=True)
        assert path in body

    def test_staff_sidebar_hides_restricted_pages(self, staff_client, seeded_settings):
        body = staff_client.get("/dashboard").get_data(as_text=True)
        assert "/expenses/" not in body
        assert "/purchase-orders/" not in body
        assert "/maintenance/" not in body
        # But staff still get the pages they are allowed to use.
        assert "/customers/" in body
        assert "/inventory/" in body
