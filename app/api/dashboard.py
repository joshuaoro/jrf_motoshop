"""
Dashboard API blueprint.

All aggregation lives in ``DashboardService`` so this module, the realtime
poller and the server-rendered dashboard cannot report different numbers.
"""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func

from app.core.extensions import db
from app.models import Part, Sale, SaleDetail
from app.services.dashboard import DashboardService
from app.services.inventory import InventoryService
from app.services.sales import SalesService
from app.services.system import NotificationService

dashboard_bp = Blueprint("dashboard", __name__)


def _limit(default: int, maximum: int = 100) -> int:
    value = request.args.get("limit", default, type=int) or default
    return max(1, min(value, maximum))


@dashboard_bp.route("/stats", methods=["GET"])
@login_required
def dashboard_stats():
    """Dashboard statistics"""
    stats = DashboardService.get_stats()
    stats["unread_notifications"] = NotificationService.get_unread_count(current_user.id)
    stats["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return jsonify(stats)


@dashboard_bp.route("/recent-sales", methods=["GET"])
@login_required
def recent_sales():
    """Recent sales for dashboard"""
    sales = DashboardService.get_recent_sales(limit=_limit(5, 50))

    return jsonify(
        [
            {
                "id": s.id,
                "receipt_number": s.receipt_number,
                "total_amount": float(s.total_amount or 0),
                "sale_date": s.sale_date.isoformat() if s.sale_date else None,
                "staff_name": s.staff.name if s.staff else "Unknown",
                "customer_name": s.customer.name if s.customer else "Walk-in",
            }
            for s in sales
        ]
    )


@dashboard_bp.route("/low-stock", methods=["GET"])
@login_required
def low_stock_dashboard():
    """Low stock items for dashboard"""
    threshold = DashboardService.low_stock_threshold()
    parts = DashboardService.get_low_stock(limit=_limit(10, 100))

    return jsonify(
        [
            {
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "stock_quantity": p.stock_quantity,
                "threshold": threshold,
                "stock_status": p.stock_status,
            }
            for p in parts
        ]
    )


@dashboard_bp.route("/sales-chart", methods=["GET"])
@login_required
def sales_chart():
    """Sales data for chart"""
    days = request.args.get("days", 7, type=int) or 7
    return jsonify(DashboardService.get_sales_chart(days))


@dashboard_bp.route("/top-parts", methods=["GET"])
@login_required
def top_parts():
    """Top selling parts for dashboard"""
    days = max(1, min(request.args.get("days", 30, type=int) or 30, 365))
    start_date = datetime.utcnow() - timedelta(days=days)
    return jsonify(SalesService.get_top_selling_parts(_limit(5, 50), start_date))


@dashboard_bp.route("/today", methods=["GET"])
@login_required
def todays_sales():
    """Today's revenue and transaction count.

    Backs the "Today's Sales" card on the reports page, which called a
    /api/todays-sales route that was never implemented.
    """
    stats = DashboardService.get_stats()
    today = datetime.utcnow().date()

    # The reports page fills its "Today's Sales Details" table from this
    # ``sales`` array, so it must carry the per-sale display fields the
    # template reads (sale_date, customer_name, total_amount,
    # payment_method, staff_name). Omitting any leaves the table stuck on
    # its "No sales recorded today" empty state even when sales exist.
    todays_sales = (
        Sale.query.filter(
            func.date(Sale.sale_date) == today,
            Sale.payment_status != "refunded",
        )
        .order_by(Sale.sale_date.desc())
        .all()
    )
    count = len(todays_sales)

    return jsonify(
        {
            "date": today.isoformat(),
            "total_revenue": stats["today_revenue"],
            "total_sales": count,
            "sales": [
                {
                    "id": s.id,
                    "receipt_number": s.receipt_number,
                    "sale_date": s.sale_date.isoformat() if s.sale_date else None,
                    "customer_name": s.customer.name if s.customer else "Walk-in",
                    "total_amount": float(s.total_amount or 0),
                    "payment_method": s.payment_method,
                    "staff_name": s.staff.name if s.staff else "Unknown",
                }
                for s in todays_sales
            ],
        }
    )


@dashboard_bp.route("/overview", methods=["GET"])
@login_required
def overview():
    """Everything the reports landing page renders, in one call.

    The key names here are the contract that templates/reports.html reads:
    statistics, top_parts, low_stock_items, sales_by_day and
    revenue_by_category. Omitting any of them throws a TypeError in the
    browser and leaves the whole page blank.
    """
    days = max(1, min(request.args.get("days", 30, type=int) or 30, 365))
    start_date = datetime.utcnow() - timedelta(days=days)

    stats = DashboardService.get_stats()
    summary = SalesService.get_sales_summary()

    low_stock = InventoryService.get_low_stock_parts()

    revenue_by_category = (
        db.session.query(
            Part.part_type,
            func.coalesce(func.sum(SaleDetail.line_total), 0).label("revenue"),
        )
        .join(SaleDetail, SaleDetail.part_id == Part.id)
        .join(Sale, Sale.id == SaleDetail.sale_id)
        .filter(
            Sale.sale_date >= start_date,
            Sale.payment_status != "refunded",
            Part.part_type.isnot(None),
        )
        .group_by(Part.part_type)
        .order_by(func.sum(SaleDetail.line_total).desc())
        .all()
    )

    return jsonify(
        {
            "statistics": {
                **stats,
                "total_revenue": summary["total_revenue"],
                "avg_sale": summary["avg_sale"],
            },
            "top_parts": SalesService.get_top_selling_parts(10, start_date),
            "low_stock_items": [
                {
                    "id": part.id,
                    "name": part.name,
                    "sku": part.sku,
                    "stock_quantity": part.stock_quantity,
                    "price": float(part.price or 0),
                }
                for part in low_stock[:20]
            ],
            "sales_by_day": DashboardService.get_sales_chart(days=min(days, 30)),
            "revenue_by_category": [
                {"category": row.part_type, "revenue": float(row.revenue or 0)}
                for row in revenue_by_category
            ],
        }
    )


@dashboard_bp.route("/activities", methods=["GET"])
@login_required
def recent_activities():
    """Recent activities for dashboard"""
    activities = DashboardService.get_activities(limit=_limit(10, 50))

    # Serialise the datetimes the service returns as native objects (the web
    # dashboard renders them directly, so the service keeps them typed).
    return jsonify(
        [
            {
                **activity,
                "timestamp": activity["timestamp"].isoformat() if activity["timestamp"] else None,
            }
            for activity in activities
        ]
    )
