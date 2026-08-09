"""
Web blueprints for expenses, purchase orders and maintenance.

Pages render server-side from the service layer; mutations go through the JSON
API in ``app/api/operations.py``. Same split as the rest of the web layer, so
the business rules live in exactly one place.
"""

import logging
from datetime import datetime, time

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app.core.extensions import db
from app.models import Expense, Part, PurchaseOrder, Supplier
from app.schemas import (
    EXPENSE_CATEGORIES,
    MAINTENANCE_TYPES,
    PAYMENT_METHODS,
    PO_STATUSES,
)
from app.services.operations import (
    ExpenseService,
    MaintenanceService,
    PurchaseOrderService,
)

expenses_web_bp = Blueprint("expenses_web", __name__, template_folder="../../templates")
purchase_orders_web_bp = Blueprint(
    "purchase_orders_web", __name__, template_folder="../../templates"
)
maintenance_web_bp = Blueprint("maintenance_web", __name__, template_folder="../../templates")

logger = logging.getLogger(__name__)
PER_PAGE = 20
# Cap what gets embedded in a page's <select> options.
PICKER_LIMIT = 500


def _parse_date(raw: str, *, end_of_day: bool = False):
    """Parse an ISO date from the query string, ignoring malformed input."""
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


def _pagination(page: int, total: int) -> dict:
    return {
        "page": page,
        "per_page": PER_PAGE,
        "total": total,
        "pages": (total + PER_PAGE - 1) // PER_PAGE,
    }


def _deny(permission: str, message: str):
    """Shared permission guard. Returns a redirect, or None when allowed."""
    if not getattr(current_user, permission)():
        flash(message, "error")
        return redirect(url_for("dashboard_web.index"))
    return None


def _active_parts():
    """Minimal part records for a <select>: id, name and last known cost."""
    rows = (
        db.session.query(Part.id, Part.name, Part.sku, Part.cost_price)
        .filter(Part.is_active.is_(True))
        .order_by(Part.name)
        .limit(PICKER_LIMIT)
        .all()
    )
    return [
        {
            "id": row.id,
            "name": row.name,
            "sku": row.sku,
            "cost_price": float(row.cost_price or 0),
        }
        for row in rows
    ]


# ============================================================
# EXPENSES
# ============================================================
# endpoint="index" keeps url_for("expenses_web.index") working while the
# function keeps a distinct name - three `def index` in one module is a
# needless shadowing trap.
@expenses_web_bp.route("/", endpoint="index")
@login_required
def expenses_index():
    """Expense register with totals for the selected period."""
    denied = _deny("can_manage_finances", "You do not have permission to view expenses")
    if denied:
        return denied

    page = max(1, request.args.get("page", 1, type=int) or 1)
    category = request.args.get("category") or None
    start_date = _parse_date(request.args.get("start_date"))
    end_date = _parse_date(request.args.get("end_date"), end_of_day=True)
    search = request.args.get("search") or None

    expenses, total = ExpenseService.get_expenses(
        page=page,
        per_page=PER_PAGE,
        category=category,
        start_date=start_date,
        end_date=end_date,
        search=search,
    )

    # Totals describe the whole filtered set, not just the visible page.
    conditions = []
    if category:
        conditions.append(Expense.category == category)
    if start_date:
        conditions.append(Expense.expense_date >= start_date)
    if end_date:
        conditions.append(Expense.expense_date <= end_date)

    totals = (
        db.session.query(
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter(*conditions)
        .one()
    )

    by_category = (
        db.session.query(
            Expense.category,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(*conditions)
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_total = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.expense_date >= month_start)
        .scalar()
    )

    return render_template(
        "expenses.html",
        expenses=[e.to_dict() for e in expenses],
        pagination=_pagination(page, total),
        categories=EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS,
        filters={
            "category": category or "",
            "start_date": request.args.get("start_date", ""),
            "end_date": request.args.get("end_date", ""),
            "search": search or "",
        },
        summary={
            "filtered_total": float(totals.total or 0),
            "filtered_count": totals.count or 0,
            "month_total": float(month_total or 0),
            "by_category": [
                {"category": row.category, "total": float(row.total or 0)} for row in by_category
            ],
        },
    )


# ============================================================
# PURCHASE ORDERS
# ============================================================
@purchase_orders_web_bp.route("/", endpoint="index")
@login_required
def purchase_orders_index():
    """Purchase order list, filterable by supplier and status."""
    denied = _deny("can_manage_inventory", "You do not have permission to view purchase orders")
    if denied:
        return denied

    page = max(1, request.args.get("page", 1, type=int) or 1)
    supplier_id = request.args.get("supplier_id", type=int)
    status = request.args.get("status") or None

    orders, total = PurchaseOrderService.get_orders(
        page=page, per_page=PER_PAGE, supplier_id=supplier_id, status=status
    )

    status_counts = dict(
        db.session.query(PurchaseOrder.status, func.count(PurchaseOrder.id))
        .group_by(PurchaseOrder.status)
        .all()
    )

    return render_template(
        "purchase_orders.html",
        orders=[o.to_dict() for o in orders],
        pagination=_pagination(page, total),
        suppliers=Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all(),
        parts=_active_parts(),
        statuses=PO_STATUSES,
        status_counts=status_counts,
        outstanding_value=float(
            db.session.query(func.coalesce(func.sum(PurchaseOrder.total_amount), 0))
            .filter(PurchaseOrder.status.in_(("pending", "ordered", "partial")))
            .scalar()
            or 0
        ),
        filters={"supplier_id": supplier_id, "status": status or ""},
    )


@purchase_orders_web_bp.route("/<int:order_id>", endpoint="detail")
@login_required
def purchase_order_detail(order_id):
    """Purchase order detail, including the goods-receipt form."""
    denied = _deny("can_manage_inventory", "You do not have permission to view purchase orders")
    if denied:
        return denied

    order = PurchaseOrderService.get_order(order_id)
    if not order:
        flash("Purchase order not found", "error")
        return redirect(url_for("purchase_orders_web.index"))

    return render_template(
        "purchase_order_detail.html",
        order=order,
        items=[item.to_dict() for item in order.items],
        can_receive=order.status in ("ordered", "partial"),
        next_statuses=sorted(PurchaseOrderService.next_statuses(order.status)),
    )


# ============================================================
# MAINTENANCE
# ============================================================
@maintenance_web_bp.route("/", endpoint="index")
@login_required
def maintenance_index():
    """Maintenance log, with overdue items called out."""
    denied = _deny("can_manage_inventory", "You do not have permission to view maintenance")
    if denied:
        return denied

    page = max(1, request.args.get("page", 1, type=int) or 1)
    maintenance_type = request.args.get("type") or None
    overdue_only = request.args.get("overdue", "false").lower() == "true"

    logs, total = MaintenanceService.get_logs(
        page=page,
        per_page=PER_PAGE,
        maintenance_type=maintenance_type,
        overdue_only=overdue_only,
    )

    return render_template(
        "maintenance.html",
        logs=[log.to_dict() for log in logs],
        pagination=_pagination(page, total),
        types=MAINTENANCE_TYPES,
        parts=_active_parts(),
        filters={"type": maintenance_type or "", "overdue": overdue_only},
        summary=MaintenanceService.get_summary(),
    )
