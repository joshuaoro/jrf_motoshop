"""
Staff API blueprint.

Staff accounts and login accounts are the same ``User`` rows, so every rule
here is delegated to ``UserService`` - the same one ``/api/auth/users`` uses.
This blueprint is the staff-management view of that resource.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.api.utils import (
    admin_required,
    error,
    load_json,
    pagination_args,
    pagination_meta,
    permission_required,
)
from app.schemas import user_schema, users_schema
from app.services.users import VALID_ROLES, UserService

staff_bp = Blueprint("staff", __name__)
logger = logging.getLogger(__name__)

ROLE_LABELS = {
    "admin": "Administrator",
    "manager": "Manager",
    "staff": "Staff",
}


@staff_bp.route("/", methods=["GET"])
@login_required
@permission_required("can_manage_staff")
def list_staff():
    """List all staff"""
    page, per_page = pagination_args()
    staff, total = UserService.get_users(
        page=page,
        per_page=per_page,
        search=request.args.get("search"),
        role=request.args.get("role"),
    )

    return jsonify(
        {
            "staff": users_schema.dump(staff),
            "pagination": pagination_meta(page, per_page, total),
        }
    )


@staff_bp.route("/", methods=["POST"])
@login_required
@admin_required
def create_staff():
    """Create new staff member (admin only)"""
    data = load_json(user_schema)

    try:
        user = UserService.create_user(data)
    except ValueError as exc:
        return error(str(exc), 400)

    logger.info("Staff created: %s by %s", user.email, current_user.email)
    return jsonify(user_schema.dump(user)), 201


# ============================================================
# SPECIAL STAFF ENDPOINTS - MUST be before /<int:staff_id>
# ============================================================
@staff_bp.route("/roles", methods=["GET"])
@login_required
def get_roles():
    """Get available roles"""
    return jsonify({"roles": [{"value": role, "label": ROLE_LABELS[role]} for role in VALID_ROLES]})


# ============================================================
# DYNAMIC STAFF ENDPOINTS
# ============================================================
@staff_bp.route("/<int:staff_id>", methods=["GET"])
@login_required
def get_staff(staff_id):
    """Get staff by ID"""
    if not current_user.can_manage_staff() and current_user.id != staff_id:
        return error("Insufficient permissions", 403)

    user = UserService.get_user(staff_id)
    if not user:
        return error("Staff member not found", 404)
    return jsonify(user_schema.dump(user))


@staff_bp.route("/<int:staff_id>", methods=["PUT"])
@login_required
def update_staff(staff_id):
    """Update staff"""
    data = load_json(user_schema, partial=True)

    try:
        user = UserService.update_user(staff_id, data, editor=current_user)
    except PermissionError as exc:
        return error(str(exc), 403)
    except ValueError as exc:
        return error(str(exc), 400)

    if not user:
        return error("Staff member not found", 404)

    logger.info("Staff updated: %s by %s", user.email, current_user.email)
    return jsonify(user_schema.dump(user))


@staff_bp.route("/<int:staff_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_staff(staff_id):
    """Delete/deactivate staff (admin only)"""
    try:
        found, message = UserService.delete_user(staff_id, editor=current_user)
    except ValueError as exc:
        return error(str(exc), 400)

    if not found:
        return error("Staff member not found", 404)

    logger.info("Staff %s: %s by %s", staff_id, message, current_user.email)
    return jsonify({"message": message})
