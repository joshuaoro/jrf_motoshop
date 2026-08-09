"""
Report generation tasks.

Each task builds a CSV and hands it to the email queue. Delivery is optional:
if email is not configured, ``send_email_task`` reports itself as skipped and
the report is still logged as generated.
"""

import csv
import io
import logging
from datetime import datetime, timedelta

from celery import shared_task
from sqlalchemy import func

from app.core.extensions import db
from app.models import Part, Sale, User
from app.services.dashboard import DashboardService
from app.services.sales import SalesService

logger = logging.getLogger(__name__)


def _recipients() -> list[str]:
    """Email addresses of active admins and managers."""
    return [
        user.email
        for user in User.query.filter(
            User.role.in_(("admin", "manager")),
            User.is_active.is_(True),
        ).all()
        if user.email
    ]


def _queue_report(subject: str, body: str, csv_content: str) -> int:
    from app.tasks.email_tasks import send_email_task

    addresses = _recipients()
    for email in addresses:
        send_email_task.delay(email, subject, body, csv_content)
    return len(addresses)


@shared_task
def generate_daily_sales_report():
    """Generate and distribute yesterday's sales report."""
    yesterday = datetime.utcnow().date() - timedelta(days=1)
    start_date = datetime.combine(yesterday, datetime.min.time())
    end_date = datetime.combine(yesterday, datetime.max.time())

    summary = SalesService.get_sales_summary(start_date, end_date)
    # Both bounds cover the same single day - the previous version passed a
    # different end bound here than to get_sales_summary, so the "top parts"
    # section could describe a different period than the totals above it.
    top_parts = SalesService.get_top_selling_parts(10, start_date, end_date)

    in_period = (
        Sale.sale_date >= start_date,
        Sale.sale_date <= end_date,
        Sale.payment_status != "refunded",
    )

    staff_sales = (
        db.session.query(
            User.name,
            func.count(Sale.id).label("count"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("total"),
        )
        .join(Sale, Sale.staff_id == User.id)
        .filter(*in_period)
        .group_by(User.id, User.name)
        .all()
    )

    payment_methods = (
        db.session.query(
            Sale.payment_method,
            func.count(Sale.id).label("count"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("total"),
        )
        .filter(*in_period)
        .group_by(Sale.payment_method)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Daily Sales Report", yesterday.isoformat()])
    writer.writerow([])
    writer.writerow(["Summary"])
    writer.writerow(["Total Sales", summary["total_sales"]])
    writer.writerow(["Total Revenue", summary["total_revenue"]])
    writer.writerow(["Total Tax", summary["total_tax"]])
    writer.writerow(["Total Discount", summary["total_discount"]])
    writer.writerow(["Average Sale", summary["avg_sale"]])
    writer.writerow([])
    writer.writerow(["Top Parts"])
    writer.writerow(["Part", "Quantity Sold", "Revenue"])
    for part in top_parts:
        writer.writerow([part["name"], part["total_sold"], part["total_revenue"]])
    writer.writerow([])
    writer.writerow(["Sales by Staff"])
    writer.writerow(["Staff", "Count", "Total"])
    for row in staff_sales:
        writer.writerow([row.name, row.count, float(row.total or 0)])
    writer.writerow([])
    writer.writerow(["Sales by Payment Method"])
    writer.writerow(["Method", "Count", "Total"])
    for row in payment_methods:
        writer.writerow([row.payment_method, row.count, float(row.total or 0)])

    queued = _queue_report(
        f"Daily Sales Report - {yesterday}",
        f"Daily sales report for {yesterday} is attached.",
        output.getvalue(),
    )

    logger.info(
        "Daily sales report generated for %s (queued to %d recipient(s))",
        yesterday,
        queued,
    )
    return {
        "status": "completed",
        "date": yesterday.isoformat(),
        "summary": summary,
        "recipients": queued,
    }


@shared_task
def generate_inventory_report():
    """Generate and distribute an inventory valuation report."""
    threshold = DashboardService.low_stock_threshold()

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
        .all()
    )

    low_stock = (
        Part.query.filter(
            Part.is_active.is_(True),
            Part.stock_quantity <= threshold,
        )
        .order_by(Part.stock_quantity.asc())
        .all()
    )

    today = datetime.utcnow().date()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Inventory Report", today.isoformat()])
    writer.writerow([])
    writer.writerow(["Total Retail Value", float(totals.retail or 0)])
    writer.writerow(["Total Cost Value", float(totals.cost or 0)])
    writer.writerow(["Potential Profit", float((totals.retail or 0) - (totals.cost or 0))])
    writer.writerow([])
    writer.writerow(["By Category"])
    writer.writerow(["Category", "Items", "Total Qty", "Value"])
    for row in by_category:
        writer.writerow([row.part_type, row.count, row.total_qty, float(row.value or 0)])
    writer.writerow([])
    writer.writerow(["Low Stock Items"])
    writer.writerow(["Part", "SKU", "Current Stock", "Threshold"])
    for part in low_stock:
        writer.writerow([part.name, part.sku, part.stock_quantity, threshold])

    queued = _queue_report(
        f"Inventory Report - {today}",
        "The inventory valuation report is attached.",
        output.getvalue(),
    )

    logger.info("Inventory report generated (queued to %d recipient(s))", queued)
    return {
        "status": "completed",
        "date": today.isoformat(),
        "low_stock_count": len(low_stock),
        "recipients": queued,
    }


@shared_task
def send_daily_sales_report():
    """Scheduled entry point for the daily sales report."""
    return generate_daily_sales_report()
