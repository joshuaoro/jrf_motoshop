"""
Notifications API blueprint
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app.api.utils import (
    admin_required,
    error,
    load_json,
    pagination_args,
    pagination_meta,
)
from app.schemas import NotificationSchema
from app.services.system import NotificationService

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/", methods=["GET"])
@notifications_bp.route("", methods=["GET"])
@login_required
def list_notifications():
    """Get user notifications with pagination"""
    page, per_page = pagination_args()

    pagination = NotificationService.get_user_notifications(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        unread_only=request.args.get("unread_only", "false").lower() == "true",
        category=request.args.get("category"),
    )

    return jsonify(
        {
            "notifications": [n.to_dict() for n in pagination.items],
            "pagination": pagination_meta(page, per_page, pagination.total),
            "unread_count": NotificationService.get_unread_count(current_user.id),
        }
    )


# ============================================================
# SPECIAL NOTIFICATION ENDPOINTS - MUST be before /<int:notification_id>
# ============================================================
@notifications_bp.route("/unread-count", methods=["GET"])
@login_required
def unread_count():
    """Get unread notification count"""
    count = NotificationService.get_unread_count(current_user.id)
    return jsonify({"unread_count": count})


@notifications_bp.route("/mark-all-read", methods=["POST"])
@login_required
def mark_all_read():
    """Mark all notifications as read"""
    count = NotificationService.mark_all_read(current_user.id)
    return jsonify({"success": True, "marked_count": count, "unread_count": 0})


@notifications_bp.route("/clear-all", methods=["DELETE"])
@login_required
def clear_all():
    """Clear all notifications for user"""
    count = NotificationService.clear_all(current_user.id)
    return jsonify({"success": True, "cleared_count": count})


@notifications_bp.route("/test", methods=["POST"])
@login_required
@admin_required
def create_test_notification():
    """Create a test notification addressed to the caller (admin only)"""
    # partial=True so an empty body is valid; the defaults below then apply.
    data = load_json(NotificationSchema(), partial=True)

    notification = NotificationService.create_notification(
        user_id=current_user.id,
        title=data.get("title") or "Test Notification",
        message=data.get("message") or "This is a test notification",
        type=data.get("type", "info"),
        category="system",
    )

    return jsonify({"success": True, "notification": notification.to_dict()})


# ============================================================
# DYNAMIC NOTIFICATION ENDPOINTS
# ============================================================
@notifications_bp.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    """Mark notification as read"""
    success = NotificationService.mark_read(notification_id, current_user.id)
    if not success:
        return error("Notification not found", 404)

    return jsonify(
        {
            "success": True,
            "unread_count": NotificationService.get_unread_count(current_user.id),
        }
    )


@notifications_bp.route("/<int:notification_id>", methods=["DELETE"])
@login_required
def delete_notification(notification_id):
    """Delete a notification"""
    success = NotificationService.delete_notification(notification_id, current_user.id)
    if not success:
        return error("Notification not found", 404)

    return jsonify(
        {
            "success": True,
            "unread_count": NotificationService.get_unread_count(current_user.id),
        }
    )
