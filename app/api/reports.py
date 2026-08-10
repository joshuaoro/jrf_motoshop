"""
Reports API blueprint
"""

from datetime import datetime, time, timedelta

from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy import func

from app.api.utils import error, parse_date_arg, permission_required
from app.core.extensions import db
from app.core.time_utils import now_utc
from app.models import Customer, Expense, Part, Sale, SaleDetail, User
from app.services.dashboard import DashboardService
from app.services.system import SettingsService

reports_bp = Blueprint("reports", __name__)

DEFAULT_WINDOW_DAYS = 30


def _period():
    """Resolve the reporting window, defaulting to the last 30 days."""
    end_date = parse_date_arg("end_date", end_of_day=True) or now_utc()
    start_date = parse_date_arg("start_date")
    if start_date is None:
        start_date = datetime.combine(
            (end_date - timedelta(days=DEFAULT_WINDOW_DAYS)).date(), time.min
        )
    return start_date, end_date


def _period_block(start_date, end_date):
    return {
        "start": start_date.date().isoformat(),
        "end": end_date.date().isoformat(),
    }


def _low_stock_threshold() -> int:
    threshold = SettingsService.get_setting("inventory", "low_stock_threshold", 5)
    try:
        return int(threshold)
    except (TypeError, ValueError):
        return 5


@reports_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard_stats():
    """Get dashboard statistics"""
    return jsonify(DashboardService.get_stats())


@reports_bp.route("/sales", methods=["GET"])
@login_required
@permission_required("can_view_reports")
def sales_report():
    """Sales report grouped by day, week, month, staff or customer."""
    start_date, end_date = _period()
    group_by = request.args.get("group_by", "day")

    query = Sale.query.filter(
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.payment_status != "refunded",
    )

    if staff_id := request.args.get("staff_id", type=int):
        query = query.filter(Sale.staff_id == staff_id)
    if customer_id := request.args.get("customer_id", type=int):
        query = query.filter(Sale.customer_id == customer_id)

    if group_by in ("day", "week", "month"):
        # strftime works identically on SQLite and PostgreSQL via SQLAlchemy's
        # generic func, and avoids date_trunc which SQLite lacks.
        fmt = {"day": "%Y-%m-%d", "week": "%Y-W%W", "month": "%Y-%m"}[group_by]
        period = (
            func.strftime(fmt, Sale.sale_date)
            if db.engine.name == "sqlite"
            else func.to_char(
                Sale.sale_date,
                {"day": "YYYY-MM-DD", "week": 'IYYY-"W"IW', "month": "YYYY-MM"}[group_by],
            )
        )

        results = (
            query.with_entities(
                period.label("period"),
                func.count(Sale.id).label("count"),
                func.coalesce(func.sum(Sale.total_amount), 0).label("total"),
            )
            .group_by(period)
            .order_by(period)
            .all()
        )

        data = [
            {"period": str(r.period), "count": r.count, "total": float(r.total or 0)}
            for r in results
        ]

    elif group_by == "staff":
        results = (
            query.with_entities(
                User.name,
                func.count(Sale.id).label("count"),
                func.coalesce(func.sum(Sale.total_amount), 0).label("total"),
                func.coalesce(func.avg(Sale.total_amount), 0).label("avg"),
            )
            .join(User, User.id == Sale.staff_id)
            .group_by(User.id, User.name)
            .order_by(func.count(Sale.id).desc())
            .all()
        )

        data = [
            {
                "staff_name": r.name,
                "count": r.count,
                "total": float(r.total or 0),
                "avg_sale": float(r.avg or 0),
            }
            for r in results
        ]

    elif group_by == "customer":
        results = (
            query.with_entities(
                Customer.name,
                func.count(Sale.id).label("count"),
                func.coalesce(func.sum(Sale.total_amount), 0).label("total"),
            )
            .join(Customer, Customer.id == Sale.customer_id)
            .group_by(Customer.id, Customer.name)
            .order_by(func.count(Sale.id).desc())
            .all()
        )

        data = [
            {
                "customer_name": r.name,
                "count": r.count,
                "total": float(r.total or 0),
            }
            for r in results
        ]

    else:
        return error(
            "Invalid 'group_by': expected one of day, week, month, staff, customer",
            400,
        )

    return jsonify(
        {
            "period": _period_block(start_date, end_date),
            "group_by": group_by,
            "data": data,
        }
    )


@reports_bp.route("/inventory", methods=["GET"])
@login_required
@permission_required("can_view_reports")
def inventory_report():
    """Inventory valuation and status"""
    threshold = _low_stock_threshold()

    totals = (
        db.session.query(
            func.coalesce(func.sum(Part.price * Part.stock_quantity), 0).label("retail"),
            func.coalesce(func.sum(Part.cost_price * Part.stock_quantity), 0).label("cost"),
        )
        .filter(Part.is_active.is_(True))
        .one()
    )

    by_category = (
        db.session.query(
            Part.part_type,
            func.count(Part.id).label("count"),
            func.coalesce(func.sum(Part.price * Part.stock_quantity), 0).label("value"),
            func.coalesce(func.sum(Part.stock_quantity), 0).label("total_qty"),
        )
        .filter(Part.is_active.is_(True), Part.part_type.isnot(None))
        .group_by(Part.part_type)
        .order_by(Part.part_type)
        .all()
    )

    low_stock = (
        Part.query.filter(Part.is_active.is_(True), Part.stock_quantity <= threshold)
        .order_by(Part.stock_quantity)
        .all()
    )

    out_of_stock = Part.query.filter(Part.is_active.is_(True), Part.stock_quantity <= 0).count()

    return jsonify(
        {
            "total_value": float(totals.retail or 0),
            "total_cost": float(totals.cost or 0),
            "potential_profit": float((totals.retail or 0) - (totals.cost or 0)),
            "by_category": [
                {
                    "category": r.part_type,
                    "count": r.count,
                    "value": float(r.value or 0),
                    "total_qty": int(r.total_qty or 0),
                }
                for r in by_category
            ],
            "low_stock_count": len(low_stock),
            "low_stock_items": [
                {
                    "id": p.id,
                    "name": p.name,
                    "sku": p.sku,
                    "stock": p.stock_quantity,
                    "threshold": threshold,
                }
                for p in low_stock[:20]
            ],
            "out_of_stock_count": out_of_stock,
        }
    )


@reports_bp.route("/profitability", methods=["GET"])
@login_required
@permission_required("can_view_reports")
def profitability_report():
    """Profit margin analysis.

    COGS comes from ``SaleDetail.unit_cost`` - the purchase cost captured when
    the sale was made. The previous implementation used ``unit_price``, the
    *selling* price, which made cost equal revenue and reported a ~0% margin
    on every period regardless of the underlying data.
    """
    start_date, end_date = _period()

    in_period = (
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.payment_status != "refunded",
    )

    totals = (
        db.session.query(
            func.coalesce(func.sum(SaleDetail.line_total), 0).label("revenue"),
            func.coalesce(func.sum(SaleDetail.unit_cost * SaleDetail.quantity), 0).label("cogs"),
        )
        .join(Sale, Sale.id == SaleDetail.sale_id)
        .filter(*in_period)
        .one()
    )

    revenue = float(totals.revenue or 0)
    cogs = float(totals.cogs or 0)
    gross_profit = revenue - cogs
    margin = (gross_profit / revenue * 100) if revenue > 0 else 0.0

    by_type = (
        db.session.query(
            Part.part_type,
            func.coalesce(func.sum(SaleDetail.line_total), 0).label("revenue"),
            func.coalesce(func.sum(SaleDetail.unit_cost * SaleDetail.quantity), 0).label("cogs"),
        )
        .join(SaleDetail, SaleDetail.part_id == Part.id)
        .join(Sale, Sale.id == SaleDetail.sale_id)
        .filter(*in_period, Part.part_type.isnot(None))
        .group_by(Part.part_type)
        .order_by(func.sum(SaleDetail.line_total).desc())
        .all()
    )

    categories = []
    for row in by_type:
        row_revenue = float(row.revenue or 0)
        row_cogs = float(row.cogs or 0)
        row_profit = row_revenue - row_cogs
        categories.append(
            {
                "category": row.part_type,
                "revenue": row_revenue,
                "cogs": row_cogs,
                "profit": row_profit,
                "margin": round(row_profit / row_revenue * 100, 2) if row_revenue > 0 else 0.0,
            }
        )

    return jsonify(
        {
            "period": _period_block(start_date, end_date),
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "margin_percent": round(margin, 2),
            "by_category": categories,
        }
    )


@reports_bp.route("/expenses", methods=["GET"])
@login_required
@permission_required("can_manage_finances")
def expenses_report():
    """Expenses report"""
    start_date, end_date = _period()

    query = Expense.query.filter(
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
    )

    if category := request.args.get("category"):
        query = query.filter(Expense.category == category)

    total = query.with_entities(func.coalesce(func.sum(Expense.amount), 0)).scalar()

    by_category = (
        query.with_entities(
            Expense.category,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
            func.count(Expense.id).label("count"),
        )
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    return jsonify(
        {
            "period": _period_block(start_date, end_date),
            "total_expenses": float(total or 0),
            "by_category": [
                {
                    "category": r.category,
                    "total": float(r.total or 0),
                    "count": r.count,
                }
                for r in by_category
            ],
        }
    )
