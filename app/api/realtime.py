"""
Real-time API blueprint (polling-based).

The front-end polls these endpoints on a timer. They share their aggregation
with the dashboard API through ``DashboardService`` rather than keeping a
second, slightly different copy of the same queries.
"""

from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.core.extensions import db
from app.models import Customer, Notification, Part, Sale
from app.services.dashboard import DashboardService

realtime_bp = Blueprint("realtime", __name__)


def _limit(default: int, maximum: int = 100) -> int:
    value = request.args.get("limit", default, type=int) or default
    return max(1, min(value, maximum))


@realtime_bp.route("/stats", methods=["GET"])
@login_required
def realtime_stats():
    """Real-time dashboard stats"""
    stats = DashboardService.get_stats()
    stats["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return jsonify(stats)


@realtime_bp.route("/activities", methods=["GET"])
@login_required
def realtime_activities():
    """Real-time activities feed"""
    activities = DashboardService.get_activities(limit=_limit(10, 50))
    return jsonify(
        [
            {
                **activity,
                "timestamp": activity["timestamp"].isoformat() if activity["timestamp"] else None,
            }
            for activity in activities
        ]
    )


@realtime_bp.route("/inventory", methods=["GET"])
@login_required
def realtime_inventory():
    """Real-time inventory updates"""
    parts = (
        Part.query.filter_by(is_active=True)
        .order_by(Part.updated_at.desc().nullslast())
        .limit(_limit(20, 100))
        .all()
    )

    return jsonify(
        [
            {
                "id": p.id,
                "name": p.name,
                "part_type": p.part_type,
                "brand": p.brand,
                "price": float(p.price or 0),
                "stock_quantity": p.stock_quantity,
                "stock_status": p.stock_status,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in parts
        ]
    )


@realtime_bp.route("/sales", methods=["GET"])
@login_required
def realtime_sales():
    """Real-time sales feed"""
    rows = (
        db.session.query(Sale, Customer)
        .outerjoin(Customer, Sale.customer_id == Customer.id)
        .order_by(Sale.sale_date.desc())
        .limit(_limit(10, 50))
        .all()
    )

    return jsonify(
        [
            {
                "id": sale.id,
                "receipt_number": sale.receipt_number,
                "total_amount": float(sale.total_amount or 0),
                "payment_method": sale.payment_method,
                "payment_status": sale.payment_status,
                "sale_date": sale.sale_date.isoformat() if sale.sale_date else None,
                "staff_name": sale.staff.name if sale.staff else "Unknown",
                "customer_name": customer.name if customer else "Walk-in Customer",
            }
            for sale, customer in rows
        ]
    )


@realtime_bp.route("/notifications", methods=["GET"])
@login_required
def realtime_notifications():
    """Real-time unread notifications"""
    notifications = (
        Notification.query.filter_by(user_id=current_user.id, is_read=False)
        .order_by(Notification.created_at.desc())
        .limit(_limit(10, 50))
        .all()
    )

    return jsonify(
        [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "action_url": n.action_url,
            }
            for n in notifications
        ]
    )


@realtime_bp.route("/customers", methods=["GET"])
@login_required
def realtime_customers():
    """Real-time customers"""
    customers = (
        Customer.query.filter_by(is_active=True)
        .order_by(Customer.created_at.desc())
        .limit(_limit(10, 50))
        .all()
    )

    return jsonify(
        [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "total_sales": c.total_orders,
                "total_spent": c.total_spent,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in customers
        ]
    )
