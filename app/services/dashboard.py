"""
Dashboard/statistics service.

These figures were previously reimplemented in four places - the dashboard API,
the reports API, the realtime API and the server-rendered dashboard page - and
had drifted apart. Two of those copies counted rows in the ``supplier_part``
join table and reported it as the number of suppliers; one embedded
``is_active = true`` as raw SQL, which is not valid on SQLite. Everything now
routes through here.
"""

from datetime import datetime, timedelta
from typing import List

from sqlalchemy import func

from app.core.extensions import db
from app.models import Customer, Part, Sale, Supplier, User
from app.services.system import SettingsService


class DashboardService:
    """Aggregate figures shown on the dashboard and the realtime poller."""

    @staticmethod
    def low_stock_threshold() -> int:
        value = SettingsService.get_setting("inventory", "low_stock_threshold", 5)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 5

    @staticmethod
    def get_stats() -> dict:
        """Headline counts and today's revenue."""
        threshold = DashboardService.low_stock_threshold()
        now = datetime.utcnow()

        today_revenue = (
            db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))
            .filter(
                func.date(Sale.sale_date) == now.date(),
                Sale.payment_status != "refunded",
            )
            .scalar()
        )

        return {
            "total_parts": Part.query.filter_by(is_active=True).count(),
            "low_stock_parts": Part.query.filter(
                Part.is_active.is_(True), Part.stock_quantity <= threshold
            ).count(),
            "total_sales": db.session.query(func.count(Sale.id)).scalar() or 0,
            "total_suppliers": Supplier.query.filter_by(is_active=True).count(),
            "total_customers": Customer.query.filter_by(is_active=True).count(),
            "total_staff": User.query.filter_by(is_active=True).count(),
            "recent_sales": Sale.query.filter(Sale.sale_date >= now - timedelta(days=7)).count(),
            "today_revenue": float(today_revenue or 0),
            "low_stock_threshold": threshold,
        }

    @staticmethod
    def get_low_stock(limit: int = 10) -> List[Part]:
        threshold = DashboardService.low_stock_threshold()
        return (
            Part.query.filter(Part.is_active.is_(True), Part.stock_quantity <= threshold)
            .order_by(Part.stock_quantity.asc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_recent_sales(limit: int = 5) -> List[Sale]:
        return Sale.query.order_by(Sale.sale_date.desc()).limit(limit).all()

    @staticmethod
    def get_activities(limit: int = 10) -> List[dict]:
        """Merged activity feed of recent sales and low-stock warnings."""
        activities = []

        for sale in DashboardService.get_recent_sales(limit=5):
            activities.append(
                {
                    "type": "sale",
                    "message": (
                        f"New sale: {sale.receipt_number} - "
                        f"₱{float(sale.total_amount or 0):,.2f}"
                    ),
                    "timestamp": sale.sale_date,
                    "icon": "fas fa-shopping-cart",
                    "icon_bg": "bg-green-500",
                    "url": f"/sales/{sale.id}",
                }
            )

        for part in DashboardService.get_low_stock(limit=3):
            activities.append(
                {
                    "type": "low_stock",
                    "message": f"Low stock: {part.name} ({part.stock_quantity} left)",
                    "timestamp": part.updated_at or part.created_at,
                    "icon": "fas fa-exclamation-triangle",
                    "icon_bg": "bg-yellow-500",
                    "url": f"/inventory/{part.id}/edit",
                }
            )

        # datetime.min keeps rows with no timestamp at the bottom instead of
        # raising when None is compared against a datetime.
        activities.sort(key=lambda a: a["timestamp"] or datetime.min, reverse=True)
        return activities[:limit]

    @staticmethod
    def get_sales_chart(days: int = 7) -> List[dict]:
        """Daily sale count and revenue for the last ``days`` days."""
        days = max(1, min(days, 365))
        start_date = datetime.utcnow() - timedelta(days=days)

        results = (
            db.session.query(
                func.date(Sale.sale_date).label("date"),
                func.count(Sale.id).label("count"),
                func.coalesce(func.sum(Sale.total_amount), 0).label("total"),
            )
            .filter(
                Sale.sale_date >= start_date,
                Sale.payment_status != "refunded",
            )
            .group_by(func.date(Sale.sale_date))
            .order_by(func.date(Sale.sale_date))
            .all()
        )

        return [
            {"date": str(r.date), "count": r.count, "total": float(r.total or 0)} for r in results
        ]
