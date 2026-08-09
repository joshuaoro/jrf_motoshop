"""
Integration tests for the JSON API: auth, permissions, validation and errors.
"""

from app.models import Part


class TestAuth:
    def test_login_succeeds_and_sets_a_session(self, client, admin):
        response = client.post(
            "/api/auth/login",
            json={
                "email": admin.email,
                "password": "password123",
            },
        )
        assert response.status_code == 200
        assert response.get_json()["user"]["username"] == "admin"

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.get_json()["email"] == admin.email

    def test_wrong_password_is_401(self, client, admin):
        response = client.post(
            "/api/auth/login",
            json={
                "email": admin.email,
                "password": "wrong",
            },
        )
        assert response.status_code == 401

    def test_unknown_email_gives_the_same_message_as_a_wrong_password(self, client, admin):
        unknown = client.post(
            "/api/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "whatever",
            },
        )
        wrong = client.post(
            "/api/auth/login",
            json={
                "email": admin.email,
                "password": "wrong",
            },
        )
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.get_json()["error"] == wrong.get_json()["error"]

    def test_disabled_account_is_403(self, client, db, factories):
        factories.user(username="off", is_active=False)
        response = client.post(
            "/api/auth/login",
            json={
                "email": "off@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 403

    def test_login_requires_json(self, client, admin):
        response = client.post("/api/auth/login", data={"email": admin.email})
        assert response.status_code == 415

    def test_malformed_body_is_400_not_500(self, client, admin):
        response = client.post("/api/auth/login", data="{not json", content_type="application/json")
        assert response.status_code == 400

    def test_protected_endpoint_returns_json_401_when_anonymous(self, client):
        response = client.get("/api/parts/")
        assert response.status_code == 401
        assert response.get_json()["error"]

    def test_logout_ends_the_session(self, admin_client):
        assert admin_client.post("/api/auth/logout").status_code == 200
        assert admin_client.get("/api/auth/me").status_code == 401

    def test_change_password_requires_the_current_one(self, admin_client):
        response = admin_client.post(
            "/api/auth/change-password",
            json={
                "current_password": "wrong",
                "new_password": "newpassword123",
            },
        )
        assert response.status_code == 400

    def test_change_password_succeeds(self, admin_client, admin):
        response = admin_client.post(
            "/api/auth/change-password",
            json={
                "current_password": "password123",
                "new_password": "newpassword456",
            },
        )
        assert response.status_code == 200
        assert admin.check_password("newpassword456")


class TestPermissions:
    def test_staff_cannot_create_a_part(self, staff_client):
        response = staff_client.post(
            "/api/parts/",
            json={
                "name": "Sneaky",
                "price": "10.00",
            },
        )
        assert response.status_code == 403

    def test_manager_can_create_a_part(self, manager_client):
        response = manager_client.post(
            "/api/parts/",
            json={
                "name": "Legit",
                "price": "10.00",
                "sku": "LEG-1",
            },
        )
        assert response.status_code == 201

    def test_staff_cannot_list_users(self, staff_client):
        assert staff_client.get("/api/auth/users").status_code == 403

    def test_staff_cannot_read_system_logs(self, staff_client):
        assert staff_client.get("/api/system/logs").status_code == 403

    def test_staff_cannot_void_a_sale(self, staff_client, db, factories):
        from app.services.sales import SalesService

        part = factories.part(stock=10)
        seller = factories.user(username="seller2")
        sale = SalesService.create_sale(
            {
                "payment_method": "cash",
                "details": [{"part_id": part.id, "quantity": 1}],
            },
            seller.id,
        )

        response = staff_client.post(f"/api/sales/{sale.id}/void", json={"reason": "because"})
        assert response.status_code == 403


class TestPartsApi:
    def test_list_is_paginated(self, admin_client, factories):
        for i in range(5):
            factories.part(name=f"Part {i}", sku=f"SKU-{i}")

        response = admin_client.get("/api/parts/?per_page=2")
        body = response.get_json()

        assert response.status_code == 200
        assert len(body["parts"]) == 2
        assert body["pagination"]["total"] == 5
        assert body["pagination"]["pages"] == 3
        assert body["pagination"]["has_next"] is True

    def test_per_page_is_capped(self, admin_client, factories):
        factories.part()
        body = admin_client.get("/api/parts/?per_page=100000").get_json()
        assert body["pagination"]["per_page"] == 100

    def test_create_validates(self, admin_client):
        response = admin_client.post("/api/parts/", json={"price": "-5"})
        body = response.get_json()

        assert response.status_code == 400
        assert "name" in body["details"]
        assert "price" in body["details"]

    def test_duplicate_sku_is_400_not_500(self, admin_client, factories):
        factories.part(sku="DUPE")
        response = admin_client.post(
            "/api/parts/",
            json={
                "name": "Other",
                "price": "1.00",
                "sku": "DUPE",
            },
        )
        assert response.status_code == 400

    def test_get_missing_part_is_404(self, admin_client):
        assert admin_client.get("/api/parts/9999").status_code == 404

    def test_stock_adjustment(self, admin_client, db, factories):
        part = factories.part(stock=10)

        response = admin_client.post(
            f"/api/parts/{part.id}/stock",
            json={
                "quantity_change": -3,
                "movement_type": "adjustment",
            },
        )
        assert response.status_code == 200
        assert response.get_json()["stock_quantity"] == 7

    def test_stock_adjustment_rejects_zero(self, admin_client, factories):
        part = factories.part()
        response = admin_client.post(f"/api/parts/{part.id}/stock", json={"quantity_change": 0})
        assert response.status_code == 400

    def test_sales_metrics_endpoint_exists(self, admin_client, db, factories):
        from app.services.sales import SalesService

        part = factories.part(stock=10, price="100.00", cost_price="60.00")
        seller = factories.user(username="seller3")
        SalesService.create_sale(
            {
                "payment_method": "cash",
                "details": [{"part_id": part.id, "quantity": 2}],
            },
            seller.id,
        )

        body = admin_client.get(f"/api/parts/{part.id}/sales-metrics").get_json()
        assert body["total_sold"] == 2
        assert body["total_revenue"] == 200.0
        assert body["gross_profit"] == 80.0
        assert body["avg_price"] == 100.0


class TestSalesApi:
    def test_create_sale_end_to_end(self, admin_client, db, factories):
        part = factories.part(stock=10, price="150.00")

        response = admin_client.post(
            "/api/sales/",
            json={
                "payment_method": "cash",
                "details": [{"part_id": part.id, "quantity": 2}],
            },
        )
        body = response.get_json()

        assert response.status_code == 201
        assert body["total_amount"] == 300.0
        assert body["receipt_number"].startswith("RCP-")
        assert len(body["details"]) == 1
        assert body["details"][0]["part_name"] == part.name
        assert db.session.get(Part, part.id).stock_quantity == 8

    def test_client_cannot_set_the_total(self, admin_client, factories):
        part = factories.part(stock=10, price="150.00")

        body = admin_client.post(
            "/api/sales/",
            json={
                "payment_method": "cash",
                "total_amount": "0.01",
                "details": [{"part_id": part.id, "quantity": 1}],
            },
        ).get_json()

        assert body["total_amount"] == 150.0

    def test_overselling_is_400(self, admin_client, factories):
        part = factories.part(stock=1)
        response = admin_client.post(
            "/api/sales/",
            json={
                "payment_method": "cash",
                "details": [{"part_id": part.id, "quantity": 5}],
            },
        )
        assert response.status_code == 400
        assert "Insufficient stock" in response.get_json()["error"]

    def test_duplicate_line_items_are_rejected(self, admin_client, factories):
        part = factories.part(stock=10)
        response = admin_client.post(
            "/api/sales/",
            json={
                "payment_method": "cash",
                "details": [
                    {"part_id": part.id, "quantity": 1},
                    {"part_id": part.id, "quantity": 1},
                ],
            },
        )
        assert response.status_code == 400

    def test_void_restores_stock(self, admin_client, db, factories):
        part = factories.part(stock=10)
        sale_id = admin_client.post(
            "/api/sales/",
            json={
                "payment_method": "cash",
                "details": [{"part_id": part.id, "quantity": 4}],
            },
        ).get_json()["id"]

        response = admin_client.post(f"/api/sales/{sale_id}/void", json={"reason": "wrong item"})
        assert response.status_code == 200
        assert db.session.get(Part, part.id).stock_quantity == 10

    def test_void_requires_a_reason(self, admin_client, factories):
        part = factories.part(stock=10)
        sale_id = admin_client.post(
            "/api/sales/",
            json={
                "payment_method": "cash",
                "details": [{"part_id": part.id, "quantity": 1}],
            },
        ).get_json()["id"]

        assert admin_client.post(f"/api/sales/{sale_id}/void", json={}).status_code == 400

    def test_payments_report_the_balance(self, admin_client, factories):
        part = factories.part(stock=10, price="100.00")
        sale_id = admin_client.post(
            "/api/sales/",
            json={
                "payment_method": "cash",
                "payment_status": "pending",
                "details": [{"part_id": part.id, "quantity": 1}],
            },
        ).get_json()["id"]

        admin_client.post(
            f"/api/sales/{sale_id}/payments",
            json={"amount": "40.00", "payment_method": "cash"},
        )

        body = admin_client.get(f"/api/sales/{sale_id}/payments").get_json()
        assert body["amount_paid"] == 40.0
        assert body["balance"] == 60.0

    def test_bad_date_filter_is_400_not_500(self, admin_client):
        response = admin_client.get("/api/sales/?start_date=not-a-date")
        assert response.status_code == 400
        assert "start_date" in response.get_json()["error"]


class TestCustomersAndSuppliers:
    def test_flat_and_nested_customer_paths_both_work(self, admin_client, factories):
        factories.customer(name="Reachable")

        flat = admin_client.get("/api/customers")
        nested = admin_client.get("/api/sales/customers")

        assert flat.status_code == 200
        assert nested.status_code == 200
        assert flat.get_json()["customers"] == nested.get_json()["customers"]

    def test_flat_and_nested_supplier_paths_both_work(self, admin_client, factories):
        factories.supplier(name="Reachable")

        assert admin_client.get("/api/suppliers").status_code == 200
        assert admin_client.get("/api/parts/suppliers").status_code == 200

    def test_duplicate_customer_email_is_400(self, admin_client, factories):
        factories.customer(name="First", email="dup@example.com")
        response = admin_client.post(
            "/api/customers",
            json={
                "name": "Second",
                "email": "dup@example.com",
            },
        )
        assert response.status_code == 400

    def test_invalid_email_is_rejected(self, admin_client):
        response = admin_client.post("/api/customers", json={"name": "X", "email": "not-an-email"})
        assert response.status_code == 400
        assert "email" in response.get_json()["details"]


class TestReports:
    def test_profitability_uses_real_cost(self, admin_client, db, factories):
        part = factories.part(stock=10, price="100.00", cost_price="60.00")
        admin_client.post(
            "/api/sales/",
            json={
                "payment_method": "cash",
                "details": [{"part_id": part.id, "quantity": 5}],
            },
        )

        body = admin_client.get("/api/reports/profitability").get_json()

        assert body["revenue"] == 500.0
        assert body["cogs"] == 300.0
        assert body["gross_profit"] == 200.0
        assert body["margin_percent"] == 40.0

    def test_inventory_report_totals(self, admin_client, factories):
        factories.part(stock=10, price="100.00", cost_price="60.00")

        body = admin_client.get("/api/reports/inventory").get_json()
        assert body["total_value"] == 1000.0
        assert body["total_cost"] == 600.0
        assert body["potential_profit"] == 400.0

    def test_supplier_count_counts_suppliers(self, admin_client, factories):
        """Regression: this used to count part<->supplier association rows."""
        supplier = factories.supplier(name="One")
        part_a = factories.part(name="A", sku="A-1")
        part_b = factories.part(name="B", sku="B-1")

        from app.services.inventory import SupplierService

        SupplierService.link_part(supplier.id, part_a.id)
        SupplierService.link_part(supplier.id, part_b.id)

        body = admin_client.get("/api/reports/dashboard").get_json()
        assert body["total_suppliers"] == 1

    def test_sales_report_rejects_a_bad_group_by(self, admin_client):
        response = admin_client.get("/api/reports/sales?group_by=nonsense")
        assert response.status_code == 400

    def test_sales_report_groups_by_day(self, admin_client, factories):
        part = factories.part(stock=10, price="50.00")
        admin_client.post(
            "/api/sales/",
            json={
                "payment_method": "cash",
                "details": [{"part_id": part.id, "quantity": 1}],
            },
        )

        body = admin_client.get("/api/reports/sales?group_by=day").get_json()
        assert body["data"][0]["total"] == 50.0

    def test_staff_cannot_see_financial_reports(self, staff_client):
        assert staff_client.get("/api/reports/profitability").status_code == 403
        assert staff_client.get("/api/reports/expenses").status_code == 403


class TestResponseContract:
    """Every JSON API response carries a `success` flag.

    Regression: the front-end branches on `data.success`, but create/update
    endpoints return the saved resource. Without the flag a successful save
    read as a failure and the page never refreshed.
    """

    def test_create_response_reports_success(self, admin_client):
        response = admin_client.post(
            "/api/parts/", json={"name": "Contract", "price": "1.00", "sku": "CON-1"}
        )
        assert response.status_code == 201
        assert response.get_json()["success"] is True

    def test_update_response_reports_success(self, admin_client, factories):
        part = factories.part()
        body = admin_client.put(f"/api/parts/{part.id}", json={"name": "Renamed"}).get_json()
        assert body["success"] is True

    def test_list_response_reports_success(self, admin_client):
        assert admin_client.get("/api/parts/").get_json()["success"] is True

    def test_error_response_reports_failure_with_a_message(self, admin_client):
        response = admin_client.get("/api/parts/999999")
        body = response.get_json()

        assert response.status_code == 404
        assert body["success"] is False
        # Both keys carry the text; different handlers read different ones.
        assert body["error"] == body["message"]

    def test_validation_error_keeps_field_details(self, admin_client):
        body = admin_client.post("/api/parts/", json={"price": "-1"}).get_json()
        assert body["success"] is False
        assert "name" in body["details"]

    def test_web_pages_are_not_stamped(self, admin_client, seeded_settings):
        """The flag is for the JSON API only, not rendered HTML."""
        response = admin_client.get("/dashboard")
        assert response.status_code == 200
        assert not response.is_json


class TestDashboardOverviewContract:
    """The reports page reads these exact keys and throws without them.

    Regression: /api/dashboard/overview omitted low_stock_items,
    sales_by_day and revenue_by_category, so reports.html died on a
    TypeError and rendered nothing below the summary cards.
    """

    REQUIRED_KEYS = (
        "statistics",
        "top_parts",
        "low_stock_items",
        "sales_by_day",
        "revenue_by_category",
    )

    def test_every_key_the_reports_page_reads_is_present(self, admin_client, seeded_settings):
        body = admin_client.get("/api/dashboard/overview").get_json()

        missing = [key for key in self.REQUIRED_KEYS if key not in body]
        assert not missing, f"overview is missing {missing}"

        for key in (
            "top_parts",
            "low_stock_items",
            "sales_by_day",
            "revenue_by_category",
        ):
            assert isinstance(body[key], list), f"{key} must be a list"

    def test_statistics_carry_the_fields_the_cards_display(self, admin_client, seeded_settings):
        stats = admin_client.get("/api/dashboard/overview").get_json()["statistics"]
        for key in ("total_revenue", "total_sales", "low_stock_parts"):
            assert key in stats

    def test_low_stock_items_have_what_the_table_renders(
        self, admin_client, seeded_settings, factories
    ):
        factories.part(name="Nearly Out", sku="LOW-1", stock=1, min_stock=10)

        items = admin_client.get("/api/dashboard/overview").get_json()["low_stock_items"]
        assert items, "a part below the threshold should appear"
        for key in ("name", "stock_quantity", "price"):
            assert key in items[0]

    def test_todays_endpoint_shape(self, admin_client, seeded_settings):
        body = admin_client.get("/api/dashboard/today").get_json()
        assert "total_revenue" in body
        assert "total_sales" in body


class TestSystemAndErrors:
    def test_health_needs_no_auth(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json()["status"] == "healthy"

    def test_health_does_not_leak_connection_details(self, client):
        body = client.get("/api/system/health").get_json()
        assert body["database"] in ("connected", "disconnected")

    def test_unknown_api_path_returns_json_404(self, admin_client):
        response = admin_client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.is_json

    def test_unknown_page_returns_html_404(self, admin_client):
        response = admin_client.get("/definitely-not-a-page", headers={"Accept": "text/html"})
        assert response.status_code == 404
        assert b"<" in response.data

    def test_security_headers_are_present_and_unique(self, client):
        response = client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert len(response.headers.get_all("X-Frame-Options")) == 1
        assert "Content-Security-Policy" in response.headers

    def test_every_response_carries_a_request_id(self, client):
        assert client.get("/health").headers.get("X-Request-ID")

    def test_method_not_allowed_is_405(self, admin_client):
        assert admin_client.delete("/api/auth/login").status_code == 405


class TestNotifications:
    def test_marking_read_twice_is_not_an_error(self, admin_client, db, admin):
        from app.services.system import NotificationService

        note = NotificationService.create_notification(admin.id, "Hi", "Body")

        assert admin_client.post(f"/api/notifications/{note.id}/read").status_code == 200
        assert admin_client.post(f"/api/notifications/{note.id}/read").status_code == 200

    def test_unread_count(self, admin_client, db, admin):
        from app.services.system import NotificationService

        NotificationService.create_notification(admin.id, "A", "B")
        body = admin_client.get("/api/notifications/unread-count").get_json()
        assert body["unread_count"] == 1
