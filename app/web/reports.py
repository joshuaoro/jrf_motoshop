"""
Web reports blueprint
"""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.services.dashboard import DashboardService
from app.services.system import SettingsService

reports_web_bp = Blueprint("reports_web", __name__, template_folder="../../templates")

CURRENCY_SYMBOLS = {"PHP": "₱", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


def _store_context() -> dict:
    """Store name and currency symbol, shared by every report page."""
    currency = SettingsService.get_setting("general", "currency", "PHP")
    return {
        "store_name": SettingsService.get_setting("general", "store_name", "JRF Motorcycle Parts"),
        "currency": currency,
        "currency_symbol": CURRENCY_SYMBOLS.get(currency, "₱"),
    }


def _require_reports():
    """Guard shared by all report pages. Returns a redirect, or None."""
    if not current_user.can_view_reports():
        flash("You do not have permission to access reports", "error")
        return redirect(url_for("dashboard_web.index"))
    return None


@reports_web_bp.route("/")
@login_required
def index():
    """Reports dashboard page"""
    if (denied := _require_reports()) is not None:
        return denied

    return render_template(
        "reports.html",
        recent_activities=DashboardService.get_activities(limit=5),
        **DashboardService.get_stats(),
        **_store_context(),
    )


@reports_web_bp.route("/sales")
@login_required
def sales_report():
    """Detailed sales report page"""
    if (denied := _require_reports()) is not None:
        return denied
    return render_template("reports_sales.html", **_store_context())


@reports_web_bp.route("/inventory")
@login_required
def inventory_report():
    """Inventory report page"""
    if (denied := _require_reports()) is not None:
        return denied
    return render_template("reports_inventory.html", **_store_context())


@reports_web_bp.route("/profitability")
@login_required
def profitability_report():
    """Profitability report page"""
    if (denied := _require_reports()) is not None:
        return denied
    return render_template("reports_profitability.html", **_store_context())
