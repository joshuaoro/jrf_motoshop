"""
Database models - User/Staff
"""

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.core.extensions import db
from datetime import datetime

#: The roles a staff account may hold, most privileged first. Imported by the
#: schemas and the user service so validation, the API and the UI stay in step.
VALID_ROLES = ("admin", "manager", "staff")


class User(UserMixin, db.Model):
    """Staff/User model with role-based access control"""

    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default="staff", index=True)
    contact_no = db.Column(db.String(20))
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Relationships
    sales = db.relationship("Sale", backref="staff", lazy="dynamic")
    created_purchase_orders = db.relationship("PurchaseOrder", backref="creator", lazy="dynamic")
    expenses = db.relationship("Expense", backref="creator", lazy="dynamic")
    maintenance_logs = db.relationship("MaintenanceLog", backref="creator", lazy="dynamic")
    notifications = db.relationship(
        "Notification", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    audit_logs = db.relationship("AuditLog", backref="user", lazy="dynamic")
    backups = db.relationship("BackupLog", backref="creator", lazy="dynamic")

    def set_password(self, password: str) -> None:
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify password"""
        return check_password_hash(self.password_hash, password)

    # Role checks
    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_manager(self) -> bool:
        return self.role == "manager"

    def is_staff(self) -> bool:
        return self.role == "staff"

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    # Permission checks
    def can_manage_staff(self) -> bool:
        return self.is_admin()

    def can_manage_inventory(self) -> bool:
        return self.is_admin() or self.is_manager()

    def can_view_reports(self) -> bool:
        return self.is_admin() or self.is_manager()

    def can_manage_suppliers(self) -> bool:
        return self.is_admin() or self.is_manager()

    def can_manage_finances(self) -> bool:
        return self.is_admin() or self.is_manager()

    def can_manage_settings(self) -> bool:
        """Change application settings.

        Distinct from can_manage_suppliers(), which the settings endpoints
        previously borrowed as a stand-in - they happened to resolve to the
        same roles, so changing one silently changed the other.
        """
        return self.is_admin() or self.is_manager()

    def can_view_sensitive_settings(self) -> bool:
        """See secret-typed settings in the clear. Administrators only."""
        return self.is_admin()

    def to_dict(self, include_sensitive: bool = False) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "contact_no": self.contact_no,
            "email": self.email,
            "username": self.username,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
        return data

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
