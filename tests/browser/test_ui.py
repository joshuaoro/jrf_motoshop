"""
Browser tests: drive the real UI in Chromium.

Every test also asserts the page produced no JavaScript errors, which is the
main thing the server-side suite cannot see. A template can render a perfect
200 while its script throws on the first click.
"""

import re

import pytest

pytestmark = pytest.mark.browser


def assert_clean(page):
    """No JS exceptions, console errors, or failed requests on this page."""
    assert not page.js_errors, "page reported errors:\n  " + "\n  ".join(page.js_errors)


class TestAuth:
    def test_login_and_reach_the_dashboard(self, page, seeded):
        page.goto(f"{seeded['url']}/login")
        page.fill("#email", seeded["email"])
        page.fill("#password", seeded["password"])
        page.click("button[type=submit]")

        page.wait_for_url(lambda url: "/login" not in url, timeout=10_000)
        assert page.locator("text=Browser Admin").first.is_visible()
        assert_clean(page)

    def test_bad_password_keeps_you_on_the_login_page(self, page, seeded):
        page.goto(f"{seeded['url']}/login")
        page.fill("#email", seeded["email"])
        page.fill("#password", "wrong-password")
        page.click("button[type=submit]")

        page.wait_for_selector("text=Invalid email or password", timeout=5_000)
        assert "/login" in page.url

    def test_logout_button_works(self, logged_in, seeded):
        logged_in.click("button[title='Log out']")
        logged_in.wait_for_url("**/login**", timeout=10_000)
        assert "/login" in logged_in.url


@pytest.mark.parametrize(
    "path,heading",
    [
        ("/dashboard", "Dashboard"),
        ("/inventory/", "Inventory"),
        ("/sales/", "Point of Sale"),
        ("/customers/", "Customer"),
        ("/suppliers/", "Supplier"),
        ("/purchase-orders/", "Purchase Orders"),
        ("/expenses/", "Expense Register"),
        ("/maintenance/", "Equipment Maintenance"),
        ("/reports/", "Report"),
        ("/settings/", "Settings"),
        ("/staff/", "Staff"),
    ],
)
def test_every_page_loads_without_js_errors(logged_in, seeded, path, heading):
    logged_in.goto(f"{seeded['url']}{path}")
    logged_in.wait_for_load_state("networkidle")

    assert logged_in.locator(f"text={heading}").first.is_visible()
    assert_clean(logged_in)


class TestPointOfSale:
    """The most important flow in the app, and the one that was broken."""

    def test_add_to_cart_updates_the_totals(self, logged_in, seeded):
        logged_in.goto(f"{seeded['url']}/sales/")
        logged_in.wait_for_load_state("networkidle")

        logged_in.locator(".add-to-cart-btn").first.click()

        # Subtotal must move off zero once something is in the cart.
        subtotal = logged_in.locator("#subtotal")
        assert subtotal.inner_text().strip() not in ("₱0.00", "")
        assert "1 items" in logged_in.locator("#cartCount").inner_text()
        assert_clean(logged_in)

    def test_tax_is_twelve_percent_not_a_hundredth_of_it(self, logged_in, seeded):
        """Regression: the client divided the stored 0.12 by 100 again."""
        logged_in.goto(f"{seeded['url']}/sales/")
        logged_in.wait_for_load_state("networkidle")

        logged_in.locator(".add-to-cart-btn").first.click()

        subtotal = float(
            logged_in.locator("#subtotal").inner_text().replace("₱", "").replace(",", "")
        )
        tax = float(logged_in.locator("#tax").inner_text().replace("₱", "").replace(",", ""))

        assert subtotal > 0
        assert tax == pytest.approx(
            subtotal * 0.12, rel=0.01
        ), f"expected 12% of {subtotal}, got {tax}"
        assert "Tax (12" in logged_in.locator("#taxLabel").inner_text()

    def test_checkout_records_a_sale_and_reduces_stock(self, logged_in, seeded, live_server):
        """Regression: checkout POSTed a payload shape the API rejected."""
        from app.models import Part, Sale

        logged_in.goto(f"{seeded['url']}/sales/")
        logged_in.wait_for_load_state("networkidle")

        logged_in.locator(".add-to-cart-btn").first.click()
        logged_in.click("#checkoutBtn")

        # Choose cash, cover the total, and pay.
        logged_in.locator(".payment-method").first.click()
        total = logged_in.locator("#total").inner_text().replace("₱", "").replace(",", "")
        received = logged_in.locator("#amountReceived")
        if received.is_visible():
            received.fill(str(float(total) + 100))

        logged_in.click("#processPaymentBtn")
        logged_in.wait_for_selector("text=recorded", timeout=10_000)

        with live_server.app.app_context():
            assert Sale.query.count() == 1
            sale = Sale.query.one()
            assert float(sale.total_amount) > 0
            # Stock came down for whatever was sold.
            sold = sale.details[0]
            part = Sale.query.session.get(Part, sold.part_id)
            assert (
                part.stock_quantity == 25 - sold.quantity
                or part.stock_quantity == 100 - sold.quantity
            )

        assert_clean(logged_in)

    def test_customer_dropdown_is_populated(self, logged_in, seeded):
        """Regression: the whole {customers, pagination} envelope was assigned."""
        logged_in.goto(f"{seeded['url']}/sales/")
        logged_in.wait_for_load_state("networkidle")

        options = logged_in.locator("#customerSelect option")
        assert options.count() >= 2, "seeded customer should appear in the dropdown"
        assert "Regular Customer" in logged_in.locator("#customerSelect").inner_text()
        assert_clean(logged_in)


class TestInventory:
    def test_add_part_modal_saves(self, logged_in, seeded, live_server):
        from app.models import Part

        logged_in.goto(f"{seeded['url']}/inventory/")
        logged_in.wait_for_load_state("networkidle")

        logged_in.click("#addPartBtn")
        logged_in.wait_for_selector("#partModal:not(.hidden)")

        logged_in.fill("#partName", "Browser Test Chain")
        logged_in.fill("#partBrand", "RK")
        logged_in.select_option("#partType", index=1)
        logged_in.fill("#partPrice", "999.50")
        logged_in.fill("#partCost", "610.25")
        logged_in.fill("#partStock", "7")
        logged_in.click("#partModal button[onclick='savePart()']")

        logged_in.wait_for_load_state("networkidle")
        logged_in.wait_for_timeout(500)

        with live_server.app.app_context():
            part = Part.query.filter_by(name="Browser Test Chain").one()
            assert part.stock_quantity == 7
            assert float(part.price) == 999.50
            # Regression: the modal had no cost field, so margins were unusable.
            assert float(part.cost_price) == 610.25

    def test_supplier_dropdown_is_populated(self, logged_in, seeded):
        """Regression: the {suppliers, pagination} envelope was assigned raw."""
        logged_in.goto(f"{seeded['url']}/inventory/")
        logged_in.wait_for_load_state("networkidle")
        logged_in.click("#addPartBtn")
        logged_in.wait_for_selector("#partModal:not(.hidden)")

        options = logged_in.locator("#availableSuppliers option")
        assert options.count() >= 2, "seeded supplier should be selectable"
        assert "Playwright Supplies" in logged_in.locator("#availableSuppliers").inner_text()
        assert_clean(logged_in)

    def test_edit_modal_prefills_the_existing_values(self, logged_in, seeded):
        logged_in.goto(f"{seeded['url']}/inventory/")
        logged_in.wait_for_load_state("networkidle")

        # Edit is wired through delegation on the table body.
        logged_in.locator("#partsTableBody button[data-action='edit']").first.click()
        logged_in.wait_for_selector("#partModal:not(.hidden)")

        assert logged_in.input_value("#partName") != ""
        assert logged_in.input_value("#partPrice") not in ("", "0.00")
        assert_clean(logged_in)


class TestPurchaseOrders:
    def test_raise_and_receive_an_order(self, logged_in, seeded, live_server):
        from app.models import Part, PurchaseOrder

        logged_in.goto(f"{seeded['url']}/purchase-orders/")
        logged_in.wait_for_load_state("networkidle")

        logged_in.click("button:has-text('New Purchase Order')")
        logged_in.wait_for_selector("#orderModal:not(.hidden)")

        logged_in.select_option("#orderSupplier", index=1)
        logged_in.select_option(".line-part", index=1)
        logged_in.fill(".line-qty", "5")
        logged_in.fill(".line-cost", "700.00")
        logged_in.click("#orderSubmit")

        # Creating an order navigates to its detail page.
        logged_in.wait_for_url(re.compile(r"/purchase-orders/\d+$"), timeout=10_000)
        logged_in.wait_for_load_state("networkidle")
        assert "PO-" in logged_in.content()

        with live_server.app.app_context():
            order = PurchaseOrder.query.one()
            assert order.status == "pending"
            assert float(order.total_amount) == 3500.0  # 5 x 700
            part_id = order.items[0].part_id
            before = (
                live_server.app.extensions["sqlalchemy"].session.get(Part, part_id).stock_quantity
            )

        # pending -> ordered -> receive
        logged_in.click("button:has-text('Mark ordered')")
        logged_in.wait_for_load_state("networkidle")

        logged_in.click("button:has-text('Fill all outstanding')")
        logged_in.click("#receiveSubmit")
        logged_in.wait_for_load_state("networkidle")
        logged_in.wait_for_timeout(500)

        with live_server.app.app_context():
            from app.core.extensions import db

            order = PurchaseOrder.query.one()
            assert order.status == "received"
            part = db.session.get(Part, part_id)
            assert part.stock_quantity == before + 5
            # Cost price follows what was actually paid.
            assert float(part.cost_price) == 700.0

        assert_clean(logged_in)

    def test_invalid_status_transition_is_not_offered(self, logged_in, seeded):
        logged_in.goto(f"{seeded['url']}/purchase-orders/")
        logged_in.wait_for_load_state("networkidle")

        logged_in.click("button:has-text('New Purchase Order')")
        logged_in.wait_for_selector("#orderModal:not(.hidden)")
        logged_in.select_option("#orderSupplier", index=1)
        logged_in.select_option(".line-part", index=1)
        logged_in.click("#orderSubmit")
        logged_in.wait_for_url(re.compile(r"/purchase-orders/\d+$"), timeout=10_000)

        # pending may only go to ordered or cancelled.
        assert logged_in.locator("button:has-text('Mark ordered')").is_visible()
        assert logged_in.locator("button:has-text('Mark received')").count() == 0


class TestExpensesAndMaintenance:
    def test_record_an_expense(self, logged_in, seeded, live_server):
        from app.models import Expense

        logged_in.goto(f"{seeded['url']}/expenses/")
        logged_in.wait_for_load_state("networkidle")

        logged_in.click("button:has-text('Record Expense')")
        logged_in.wait_for_selector("#expenseModal:not(.hidden)")

        logged_in.select_option("#expenseCategory", "utilities")
        logged_in.fill("#expenseAmount", "1450.75")
        logged_in.fill("#expenseDescription", "Browser test electricity")
        logged_in.select_option("#expensePaymentMethod", "cash")
        logged_in.click("#expenseSubmit")

        logged_in.wait_for_load_state("networkidle")
        logged_in.wait_for_timeout(500)

        with live_server.app.app_context():
            expense = Expense.query.one()
            assert float(expense.amount) == 1450.75
            assert expense.category == "utilities"

        assert_clean(logged_in)

    def test_expense_validation_error_is_shown_in_the_modal(self, logged_in, seeded):
        logged_in.goto(f"{seeded['url']}/expenses/")
        logged_in.wait_for_load_state("networkidle")

        logged_in.click("button:has-text('Record Expense')")
        logged_in.wait_for_selector("#expenseModal:not(.hidden)")

        # Zero is rejected server-side (minimum is 0.01).
        logged_in.fill("#expenseAmount", "0.00")
        logged_in.fill("#expenseDescription", "Should fail")
        logged_in.evaluate("document.getElementById('expenseAmount').setCustomValidity('')")
        logged_in.evaluate("document.getElementById('expenseForm').noValidate = true")
        logged_in.click("#expenseSubmit")

        error_box = logged_in.locator("#expenseError")
        error_box.wait_for(state="visible", timeout=5_000)
        assert "amount" in error_box.inner_text().lower()

    def test_log_maintenance(self, logged_in, seeded, live_server):
        from app.models import MaintenanceLog

        logged_in.goto(f"{seeded['url']}/maintenance/")
        logged_in.wait_for_load_state("networkidle")

        logged_in.click("button:has-text('Log Maintenance')")
        logged_in.wait_for_selector("#logModal:not(.hidden)")

        logged_in.fill("#logEquipment", "Browser Test Lift")
        logged_in.select_option("#logType", "preventive")
        logged_in.fill("#logDescription", "Routine check")
        logged_in.fill("#logCost", "500")
        logged_in.click("#logSubmit")

        logged_in.wait_for_load_state("networkidle")
        logged_in.wait_for_timeout(500)

        with live_server.app.app_context():
            log = MaintenanceLog.query.one()
            assert log.equipment_name == "Browser Test Lift"

        assert_clean(logged_in)


class TestXssInTheBrowser:
    def test_a_scripted_part_name_does_not_execute(self, logged_in, seeded, live_server):
        """The real proof: render a hostile name and check nothing fired."""
        from app.core.extensions import db
        from app.models import Part

        with live_server.app.app_context():
            db.session.add(
                Part(
                    name='<img src=x onerror="window.__xss=true">',
                    sku="XSS-BROWSER",
                    price=10,
                    cost_price=5,
                    stock_quantity=1,
                )
            )
            db.session.commit()

        for path in ("/inventory/", "/sales/"):
            logged_in.goto(f"{seeded['url']}{path}")
            logged_in.wait_for_load_state("networkidle")
            assert (
                logged_in.evaluate("window.__xss === true") is False
            ), f"XSS payload executed on {path}"
