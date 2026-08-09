"""
Web sales blueprint (point of sale + history)
"""

import logging
from datetime import datetime, time

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.models import Customer, Part
from app.services.sales import SalesService
from app.services.system import SettingsService

sales_web_bp = Blueprint("sales_web", __name__, template_folder="../../templates")
logger = logging.getLogger(__name__)

PER_PAGE = 20
# The POS screen renders its catalogue client-side. Cap what is embedded so a
# large inventory cannot produce a multi-megabyte page.
POS_CATALOGUE_LIMIT = 500


def _parse_date(raw: str, *, end_of_day: bool = False):
    """Parse an ISO date from a query string, ignoring malformed input.

    A bad ?start_date= previously raised ValueError and returned a 500 page;
    on a browsable page the right behaviour is to fall back to "no filter".
    """
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        flash(f'Ignoring invalid date "{raw}" - expected YYYY-MM-DD', "warning")
        return None

    if end_of_day and len(raw) == 10:
        parsed = datetime.combine(parsed.date(), time.max)
    return parsed


def _tax_rate_percent() -> float:
    """Sales tax as a percentage, accepting either 0.12 or 12 in settings."""
    raw = SettingsService.get_setting("sales", "tax_rate", 0.12)
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        rate = 0.12
    return rate * 100 if rate < 1 else rate


@sales_web_bp.route("/")
@login_required
def index():
    """Sales / Point of Sale page"""
    parts = (
        Part.query.filter_by(is_active=True).order_by(Part.name).limit(POS_CATALOGUE_LIMIT).all()
    )
    customers = (
        Customer.query.filter_by(is_active=True)
        .order_by(Customer.name)
        .limit(POS_CATALOGUE_LIMIT)
        .all()
    )

    page = max(1, request.args.get("page", 1, type=int) or 1)
    recent_sales, total = SalesService.get_sales(page=page, per_page=PER_PAGE)

    return render_template(
        "sales.html",
        parts=[p.to_dict() for p in parts],
        customers=[c.to_dict() for c in customers],
        recent_sales=recent_sales,
        pagination={
            "page": page,
            "per_page": PER_PAGE,
            "total": total,
            "pages": (total + PER_PAGE - 1) // PER_PAGE,
        },
        tax_rate=_tax_rate_percent(),
    )


@sales_web_bp.route("/history")
@login_required
def history():
    """Sales history page"""
    page = max(1, request.args.get("page", 1, type=int) or 1)
    start_date = _parse_date(request.args.get("start_date"))
    end_date = _parse_date(request.args.get("end_date"), end_of_day=True)

    sales, total = SalesService.get_sales(
        page=page,
        per_page=PER_PAGE,
        start_date=start_date,
        end_date=end_date,
        payment_status=request.args.get("payment_status") or None,
    )

    return render_template(
        "sales_history.html",
        sales=sales,
        pagination={
            "page": page,
            "per_page": PER_PAGE,
            "total": total,
            "pages": (total + PER_PAGE - 1) // PER_PAGE,
        },
        start_date=start_date,
        end_date=end_date,
    )


@sales_web_bp.route("/<int:sale_id>")
@login_required
def detail(sale_id):
    """Sale detail page"""
    sale = SalesService.get_sale(sale_id)
    if not sale:
        flash("Sale not found", "error")
        return redirect(url_for("sales_web.index"))

    return render_template(
        "sale_detail.html",
        sale=sale,
        amount_paid=float(SalesService.get_amount_paid(sale)),
    )
