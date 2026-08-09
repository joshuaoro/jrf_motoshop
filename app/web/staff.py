"""
Web staff blueprint.

All account rules are delegated to ``UserService`` - the same code path the
JSON API uses. The previous version assigned form values straight onto the
model, which skipped role validation and allowed the last administrator to be
demoted or deleted through the UI.
"""

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from marshmallow import ValidationError

from app.api.utils import load_form
from app.models import VALID_ROLES, User
from app.schemas import UserSchema
from app.services.users import UserService

staff_web_bp = Blueprint("staff_web", __name__, template_folder="../../templates")
logger = logging.getLogger(__name__)


def _flash_validation(exc: ValidationError, action: str) -> None:
    """Turn marshmallow's nested error dict into readable flash messages."""
    for field, messages in exc.messages.items():
        if isinstance(messages, (list, tuple)):
            messages = "; ".join(str(m) for m in messages)
        flash(f"{action}: {field} - {messages}", "error")


@staff_web_bp.route("/")
@login_required
def index():
    """Staff list page"""
    if not current_user.can_manage_staff():
        flash("You do not have permission to access staff", "error")
        return redirect(url_for("dashboard_web.index"))

    staff = User.query.order_by(User.name).all()

    staff_data = []
    for user in staff:
        data = user.to_dict()
        data["sales_count"] = user.sales.count()
        staff_data.append(data)

    return render_template(
        "staff.html",
        staff=staff,
        staff_json=staff_data,
        roles=VALID_ROLES,
    )


@staff_web_bp.route("/create", methods=["POST"])
@login_required
def create():
    """Create new staff member"""
    if not current_user.can_manage_staff():
        flash("Insufficient permissions", "error")
        return redirect(url_for("staff_web.index"))

    try:
        data = load_form(UserSchema(), request.form)
        user = UserService.create_user(data)
    except ValidationError as exc:
        _flash_validation(exc, "Could not create staff member")
        return redirect(url_for("staff_web.index"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("staff_web.index"))

    logger.info("Staff created: %s by %s", user.email, current_user.email)
    flash(f"Staff member {user.name} created successfully", "success")
    return redirect(url_for("staff_web.index"))


@staff_web_bp.route("/<int:staff_id>/edit", methods=["POST"])
@login_required
def edit(staff_id):
    """Update staff member"""
    if not current_user.can_manage_staff():
        flash("Insufficient permissions", "error")
        return redirect(url_for("staff_web.index"))

    try:
        data = load_form(UserSchema(), request.form, partial=True)
        user = UserService.update_user(staff_id, data, editor=current_user)
    except ValidationError as exc:
        _flash_validation(exc, "Could not update staff member")
        return redirect(url_for("staff_web.index"))
    except PermissionError as exc:
        flash(str(exc), "error")
        return redirect(url_for("staff_web.index"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("staff_web.index"))

    if not user:
        flash("Staff member not found", "error")
    else:
        logger.info("Staff updated: %s by %s", user.email, current_user.email)
        flash("Staff member updated successfully", "success")

    return redirect(url_for("staff_web.index"))


@staff_web_bp.route("/<int:staff_id>/delete", methods=["POST"])
@login_required
def delete(staff_id):
    """Delete staff member"""
    if not current_user.can_manage_staff():
        flash("Insufficient permissions", "error")
        return redirect(url_for("staff_web.index"))

    try:
        found, message = UserService.delete_user(staff_id, editor=current_user)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("staff_web.index"))

    flash(message if found else "Staff member not found", "success" if found else "error")
    return redirect(url_for("staff_web.index"))
