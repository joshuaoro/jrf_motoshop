"""
User/staff service.

Both ``/api/auth/users`` and ``/api/staff`` manage the same ``User`` rows. The
rules below (uniqueness, the last-administrator guard, which fields a
non-admin may change) live here so the two blueprints - and the server-rendered
staff page - cannot drift apart or enforce different things.
"""

from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.core.extensions import db
from app.models import VALID_ROLES, User

# Fields a user may change on their own profile.
SELF_EDITABLE_FIELDS = ("name", "contact_no")
# Fields an administrator may change on anyone.
ADMIN_EDITABLE_FIELDS = ("name", "email", "username", "role", "contact_no", "is_active")


class UserService:
    """Service layer for staff accounts."""

    @staticmethod
    def get_users(
        page: int = 1,
        per_page: int = 20,
        search: Optional[str] = None,
        role: Optional[str] = None,
        active_only: bool = False,
    ) -> Tuple[List[User], int]:
        query = User.query

        if active_only:
            query = query.filter(User.is_active.is_(True))

        if search:
            term = f"%{search}%"
            query = query.filter(
                or_(
                    User.name.ilike(term),
                    User.email.ilike(term),
                    User.username.ilike(term),
                )
            )

        if role:
            query = query.filter(User.role == role)

        pagination = query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return pagination.items, pagination.total

    @staticmethod
    def get_user(user_id: int) -> Optional[User]:
        return db.session.get(User, user_id)

    @staticmethod
    def _assert_unique(data: dict, exclude_id: Optional[int] = None) -> None:
        if data.get("email"):
            query = User.query.filter(User.email == data["email"])
            if exclude_id is not None:
                query = query.filter(User.id != exclude_id)
            if query.first():
                raise ValueError("Email already registered")

        if data.get("username"):
            query = User.query.filter(User.username == data["username"])
            if exclude_id is not None:
                query = query.filter(User.id != exclude_id)
            if query.first():
                raise ValueError("Username already taken")

    @staticmethod
    def count_other_active_admins(exclude_id: int) -> int:
        return User.query.filter(
            User.role == "admin",
            User.is_active.is_(True),
            User.id != exclude_id,
        ).count()

    @staticmethod
    def create_user(data: dict) -> User:
        """Create a staff account. ``data`` must carry a plaintext password."""
        password = data.get("password")
        if not password:
            raise ValueError("A password is required")

        role = data.get("role", "staff")
        if role not in VALID_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(VALID_ROLES)}")

        UserService._assert_unique(data)

        try:
            user = User(
                name=data["name"],
                email=data["email"],
                username=data["username"],
                role=role,
                contact_no=data.get("contact_no"),
                is_active=data.get("is_active", True),
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return user

    @staticmethod
    def update_user(user_id: int, data: dict, *, editor: User) -> Optional[User]:
        """Apply an update on behalf of ``editor``.

        Raises ``PermissionError`` when the editor may not perform the change
        and ``ValueError`` for rule violations, so callers can map them to 403
        and 400 respectively.
        """
        user = db.session.get(User, user_id)
        if not user:
            return None

        is_self = editor.id == user_id
        if not editor.is_admin() and not is_self:
            raise PermissionError("Insufficient permissions")

        allowed = ADMIN_EDITABLE_FIELDS if editor.is_admin() else SELF_EDITABLE_FIELDS

        if "role" in data and data["role"] not in VALID_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(VALID_ROLES)}")

        # Block the change that would leave nobody able to administer the app.
        if user.is_admin():
            losing_admin = data.get("role", user.role) != "admin"
            being_disabled = data.get("is_active", user.is_active) is False
            if (losing_admin or being_disabled) and UserService.count_other_active_admins(
                user_id
            ) == 0:
                raise ValueError("Cannot demote or disable the last active administrator")

        UserService._assert_unique(
            {k: v for k, v in data.items() if k in ("email", "username")},
            exclude_id=user_id,
        )

        try:
            for key in allowed:
                if key in data:
                    setattr(user, key, data[key])

            if data.get("password"):
                # Only an admin may set a password without proving the old
                # one; self-service goes through /api/auth/change-password.
                if not editor.is_admin():
                    raise PermissionError(
                        "Use the change-password endpoint to change your own password"
                    )
                user.set_password(data["password"])

            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        except PermissionError:
            db.session.rollback()
            raise

        return user

    @staticmethod
    def delete_user(user_id: int, *, editor: User) -> Tuple[bool, str]:
        """Delete or deactivate a user.

        Returns ``(found, message)``. A user with sales history is deactivated
        rather than deleted, because ``Sale.staff_id`` is NOT NULL and the
        sales record must stay attributable.
        """
        if editor.id == user_id:
            raise ValueError("Cannot delete your own account")

        user = db.session.get(User, user_id)
        if not user:
            return False, "User not found"

        if user.is_admin() and UserService.count_other_active_admins(user_id) == 0:
            raise ValueError("Cannot delete the last active administrator")

        try:
            if user.sales.count() > 0:
                user.is_active = False
                message = "User deactivated (has sales history)"
            else:
                db.session.delete(user)
                message = "User deleted successfully"

            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return True, message
