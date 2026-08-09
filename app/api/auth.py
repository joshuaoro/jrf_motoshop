"""
Auth API blueprint
"""

import logging
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user

from app.api.utils import (
    admin_required,
    error,
    load_json,
    pagination_args,
    pagination_meta,
)
from app.core.extensions import db, limiter
from app.models import User
from app.schemas import ChangePasswordSchema, LoginSchema, UserSchema
from app.services.system import SettingsService
from app.services.users import UserService

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

user_schema = UserSchema()
users_schema = UserSchema(many=True)


def _config_limit(key: str):
    """Rate-limit a view using a limit string read from config per request.

    The callable form is required because the app config is not available at
    import time. When flask_limiter is missing, ``limiter`` is None and this
    degrades to a no-op decorator instead of breaking the import.
    """
    if limiter is None:
        return lambda view: view
    return limiter.limit(lambda: current_app.config[key])


@auth_bp.route("/login", methods=["POST"])
@_config_limit("RATELIMIT_LOGIN")
def login():
    """User login"""
    data = load_json(LoginSchema())
    email = data["email"].strip().lower()

    user = User.query.filter(User.email == email).first()

    # Same response and timing path for "no such user" and "wrong password" so
    # the endpoint cannot be used to enumerate registered addresses.
    if not user or not user.check_password(data["password"]):
        logger.warning("Failed login attempt for email: %s from %s", email, request.remote_addr)
        return error("Invalid email or password", 401)

    if not user.is_active:
        logger.warning("Login attempt on disabled account: %s", email)
        return error("Account is disabled", 403)

    login_user(user, remember=data.get("remember", False))
    user.last_login = datetime.utcnow()
    db.session.commit()

    logger.info("User logged in: %s (%s)", user.email, user.role)

    return jsonify(
        {
            "message": "Login successful",
            "user": user_schema.dump(user),
            "redirect": "/dashboard",
        }
    )


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """User logout"""
    logger.info("User logged out: %s", current_user.email)
    logout_user()
    return jsonify({"message": "Logged out successfully"})


@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    """Get current user info"""
    return jsonify(user_schema.dump(current_user))


@auth_bp.route("/check", methods=["GET"])
def check_auth():
    """Check authentication status (for frontend)"""
    if current_user.is_authenticated:
        return jsonify(
            {
                "authenticated": True,
                "user": user_schema.dump(current_user),
            }
        )
    return jsonify({"authenticated": False})


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """Change the signed-in user's password"""
    data = load_json(ChangePasswordSchema())

    if not current_user.check_password(data["current_password"]):
        logger.warning("Failed password change for %s (wrong current password)", current_user.email)
        return error("Current password is incorrect", 400)

    new_password = data["new_password"]
    if new_password == data["current_password"]:
        return error("New password must be different from the current one", 400)

    min_length = SettingsService.get_setting("security", "password_min_length", 8)
    try:
        min_length = int(min_length)
    except (TypeError, ValueError):
        min_length = 8

    if len(new_password) < min_length:
        return error(f"Password must be at least {min_length} characters", 400)

    current_user.set_password(new_password)
    db.session.commit()

    logger.info("Password changed for user: %s", current_user.email)
    return jsonify({"message": "Password changed successfully"})


@auth_bp.route("/users", methods=["GET"])
@login_required
@admin_required
def list_users():
    """List all users (admin only)"""
    page, per_page = pagination_args()
    users, total = UserService.get_users(
        page=page,
        per_page=per_page,
        search=request.args.get("search"),
        role=request.args.get("role"),
    )

    return jsonify(
        {
            "users": users_schema.dump(users),
            "pagination": pagination_meta(page, per_page, total),
        }
    )


@auth_bp.route("/users", methods=["POST"])
@login_required
@admin_required
def create_user():
    """Create new user (admin only)"""
    data = load_json(user_schema)

    try:
        user = UserService.create_user(data)
    except ValueError as exc:
        return error(str(exc), 400)

    logger.info("User created: %s by %s", user.email, current_user.email)
    return jsonify(user_schema.dump(user)), 201


@auth_bp.route("/users/<int:user_id>", methods=["GET"])
@login_required
def get_user(user_id):
    """Get user by ID"""
    if not current_user.can_manage_staff() and current_user.id != user_id:
        return error("Insufficient permissions", 403)

    user = UserService.get_user(user_id)
    if not user:
        return error("User not found", 404)
    return jsonify(user_schema.dump(user))


@auth_bp.route("/users/<int:user_id>", methods=["PUT"])
@login_required
def update_user(user_id):
    """Update a user.

    Administrators may edit anyone; everyone else only their own name and
    contact number. The allow-list lives in ``UserService`` so this endpoint
    and ``/api/staff`` cannot enforce different rules.
    """
    data = load_json(user_schema, partial=True)

    try:
        user = UserService.update_user(user_id, data, editor=current_user)
    except PermissionError as exc:
        return error(str(exc), 403)
    except ValueError as exc:
        return error(str(exc), 400)

    if not user:
        return error("User not found", 404)

    logger.info("User updated: %s by %s", user.email, current_user.email)
    return jsonify(user_schema.dump(user))


@auth_bp.route("/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_user(user_id):
    """Delete user (admin only)"""
    try:
        found, message = UserService.delete_user(user_id, editor=current_user)
    except ValueError as exc:
        return error(str(exc), 400)

    if not found:
        return error("User not found", 404)

    logger.info("User %s: %s by %s", user_id, message, current_user.email)
    return jsonify({"message": message})
