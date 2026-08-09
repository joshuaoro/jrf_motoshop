"""
Integration tests for the server-rendered pages.

The point of the smoke tests here is that every template actually renders with
the context its view supplies - a missing variable or a bad url_for() only
shows up when the page is really rendered.
"""

import pytest
from werkzeug.datastructures import MultiDict

from app.models import Part, Supplier, User


def login_form(client, user, password="password123"):
    return client.post(
        "/login",
        data={"email": user.email, "password": password},
        follow_redirects=False,
    )


class TestWebAuth:
    def test_login_page_renders(self, client):
        response = client.get("/login")
        assert response.status_code == 200
        assert b"csrf_token" in response.data

    def test_login_succeeds_and_redirects(self, client, admin):
        response = login_form(client, admin)
        assert response.status_code == 302
        # dashboard_web.index serves both '/' and '/dashboard'.
        assert response.headers["Location"] in ("/", "/dashboard")

    def test_bad_credentials_re_render_with_401(self, client, admin):
        response = client.post(
            "/login",
            data={
                "email": admin.email,
                "password": "nope",
            },
        )
        assert response.status_code == 401

    def test_anonymous_visitor_is_redirected_to_login(self, client):
        response = client.get("/dashboard")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_open_redirect_is_refused(self, client, admin):
        """?next=//evil.example.com must not send the user off-site."""
        response = client.post(
            "/login?next=//evil.example.com",
            data={"email": admin.email, "password": "password123"},
        )
        assert response.status_code == 302
        assert "evil.example.com" not in response.headers["Location"]

    def test_relative_next_is_honoured(self, client, admin):
        response = client.post(
            "/login?next=/inventory/",
            data={"email": admin.email, "password": "password123"},
        )
        assert response.headers["Location"].endswith("/inventory/")

    def test_logout_rejects_get(self, admin_client):
        """A GET logout would be triggerable by any third-party page."""
        assert admin_client.get("/logout").status_code == 405

    def test_logout_via_post_works(self, admin_client):
        response = admin_client.post("/logout")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/dashboard",
        "/inventory/",
        "/inventory/create",
        "/inventory/suppliers",
        "/inventory/suppliers/create",
        "/suppliers/",
        "/customers/",
        "/sales/",
        "/sales/history",
        "/reports/",
        "/reports/sales",
        "/reports/inventory",
        "/reports/profitability",
        "/settings/",
        "/staff/",
        "/notifications",
    ],
)
def test_every_page_renders_for_an_admin(admin_client, seeded_settings, path):
    response = admin_client.get(path)
    assert (
        response.status_code == 200
    ), f"{path} returned {response.status_code}\n{response.data[:600]}"


def test_pages_render_with_data_present(admin_client, seeded_settings, factories):
    """Re-render the list pages with rows, exercising the row templates."""
    supplier = factories.supplier(name="Acme", email="acme@example.com")
    part = factories.part(name="Chain", sku="CH-1")
    factories.customer(name="Regular", email="regular@example.com")

    from app.services.inventory import SupplierService

    SupplierService.link_part(supplier.id, part.id)

    for path in ("/inventory/", "/suppliers/", "/customers/", "/staff/", "/sales/"):
        response = admin_client.get(path)
        assert response.status_code == 200, f"{path} broke with data present"


def test_sale_detail_page_renders(admin_client, factories):
    part = factories.part(stock=10, price="100.00")
    sale_id = admin_client.post(
        "/api/sales/",
        json={
            "payment_method": "cash",
            "details": [{"part_id": part.id, "quantity": 2}],
        },
    ).get_json()["id"]

    response = admin_client.get(f"/sales/{sale_id}")
    assert response.status_code == 200
    assert b"RCP-" in response.data


def test_edit_forms_render(admin_client, factories):
    part = factories.part()
    supplier = factories.supplier()

    assert admin_client.get(f"/inventory/{part.id}/edit").status_code == 200
    assert admin_client.get(f"/inventory/suppliers/{supplier.id}/edit").status_code == 200


class TestWebForms:
    def test_create_part_via_form(self, admin_client, db):
        response = admin_client.post(
            "/inventory/create",
            data={
                "name": "Web Part",
                "price": "199.50",
                "cost_price": "120.00",
                "stock_quantity": "7",
                "min_stock_level": "2",
                "sku": "WEB-1",
                "part_type": "Brakes",
                "brand": "Acme",
                "description": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        part = Part.query.filter_by(sku="WEB-1").one()
        assert part.stock_quantity == 7
        assert float(part.price) == 199.50
        assert part.brand == "Acme"

    def test_create_part_with_multiple_suppliers(self, admin_client, db, factories):
        """A multi-select must keep every selected value, not just the first."""
        a = factories.supplier(name="Supplier A")
        b = factories.supplier(name="Supplier B")

        admin_client.post(
            "/inventory/create",
            data=MultiDict(
                [
                    ("name", "Multi"),
                    ("price", "10.00"),
                    ("sku", "MULTI-1"),
                    ("supplier_ids", str(a.id)),
                    ("supplier_ids", str(b.id)),
                ]
            ),
        )

        part = Part.query.filter_by(sku="MULTI-1").one()
        assert {s.id for s in part.suppliers} == {a.id, b.id}

    def test_invalid_form_re_renders_with_400(self, admin_client, db):
        response = admin_client.post(
            "/inventory/create",
            data={
                "name": "",
                "price": "not-a-number",
            },
        )
        assert response.status_code == 400
        assert Part.query.count() == 0

    def test_supplier_edit_saves_validated_values(self, admin_client, db, factories):
        supplier = factories.supplier(name="Old Name")

        admin_client.post(
            f"/inventory/suppliers/{supplier.id}/edit",
            data={
                "name": "  New Name  ",
                "email": "new@example.com",
                "contact_no": "",
            },
        )

        db.session.refresh(supplier)
        assert supplier.name == "New Name", "value should be trimmed by the schema"
        assert supplier.email == "new@example.com"

    def test_staff_create_via_form(self, admin_client, db):
        response = admin_client.post(
            "/staff/create",
            data={
                "name": "New Hire",
                "email": "hire@example.com",
                "username": "hire",
                "password": "password123",
                "role": "staff",
            },
        )

        assert response.status_code == 302
        assert User.query.filter_by(username="hire").one().role == "staff"

    def test_staff_form_rejects_a_bad_role(self, admin_client, db):
        admin_client.post(
            "/staff/create",
            data={
                "name": "Sneaky",
                "email": "sneaky@example.com",
                "username": "sneaky",
                "password": "password123",
                "role": "superuser",
            },
        )
        assert User.query.filter_by(username="sneaky").first() is None

    def test_cannot_demote_the_last_admin_via_form(self, admin_client, db, admin):
        admin_client.post(f"/staff/{admin.id}/edit", data={"role": "staff"})

        db.session.refresh(admin)
        assert admin.role == "admin"

    def test_customer_create_via_form(self, admin_client, db):
        from app.models import Customer

        response = admin_client.post(
            "/customers/create",
            data={
                "name": "Form Customer",
                "email": "form@example.com",
                "phone": "",
                "credit_limit": "",
            },
        )

        assert response.status_code == 302
        assert Customer.query.filter_by(email="form@example.com").count() == 1

    def test_delete_supplier_via_form(self, admin_client, db, factories):
        supplier = factories.supplier()
        response = admin_client.post(f"/suppliers/{supplier.id}/delete")

        assert response.status_code == 302
        assert db.session.get(Supplier, supplier.id) is None


class TestWebPermissions:
    def test_staff_cannot_open_the_staff_page(self, staff_client):
        response = staff_client.get("/staff/")
        assert response.status_code == 302

    def test_staff_cannot_open_reports(self, staff_client):
        response = staff_client.get("/reports/")
        assert response.status_code == 302

    def test_staff_cannot_open_settings(self, staff_client):
        response = staff_client.get("/settings/")
        assert response.status_code == 302

    def test_manager_can_open_reports_and_settings(self, manager_client, seeded_settings):
        assert manager_client.get("/reports/").status_code == 200
        assert manager_client.get("/settings/").status_code == 200

    def test_staff_can_still_use_inventory_and_sales(self, staff_client, seeded_settings):
        assert staff_client.get("/inventory/").status_code == 200
        assert staff_client.get("/sales/").status_code == 200


class TestErrorPages:
    def test_404_page_renders(self, admin_client):
        response = admin_client.get("/no-such-page", headers={"Accept": "text/html"})
        assert response.status_code == 404
        assert b"<" in response.data
