"""
Database models - Settings, Notifications, Audit & System Logs
"""

from app.core.extensions import db
from app.core.time_utils import now_utc, time_ago
import json


class Settings(db.Model):
    """Application settings - key-value store with categories"""

    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(
        db.String(50), nullable=False, index=True
    )  # general, inventory, sales, notifications, backup, security
    setting_key = db.Column(db.String(100), nullable=False, index=True)
    setting_value = db.Column(db.Text)
    setting_type = db.Column(
        db.String(20), default="string"
    )  # string, number, boolean, json, password
    description = db.Column(db.Text)
    is_public = db.Column(db.Boolean, default=False)  # Whether safe to expose to frontend
    is_required = db.Column(db.Boolean, default=False)
    validation_regex = db.Column(db.String(200))  # Optional regex validation
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)
    updated_by = db.Column(db.Integer, db.ForeignKey("staff.id"))

    # Unique constraint on category + key
    __table_args__ = (
        db.UniqueConstraint("category", "setting_key", name="uq_settings_category_key"),
    )

    def get_value(self):
        """Get typed value based on setting_type"""
        if self.setting_value is None:
            return None

        if self.setting_type == "boolean":
            return self.setting_value.lower() in ("true", "1", "yes", "on")
        elif self.setting_type == "number":
            try:
                return float(self.setting_value)
            except ValueError:
                return 0
        elif self.setting_type == "integer":
            # Tolerate "30.0" (a float stringified from a JS Number) so an
            # integer setting never collapses to 0 after a round-trip.
            try:
                return int(float(self.setting_value))
            except (ValueError, TypeError):
                return 0
        elif self.setting_type == "json":
            try:
                return json.loads(self.setting_value)
            except (json.JSONDecodeError, ValueError):
                return {}
        return self.setting_value

    def set_value(self, value):
        """Set value with type conversion.

        Integer and number values arrive as JS Numbers (floats). String-ifying
        them verbatim produces "30.0", which the ``integer`` reader then fails
        to parse and turns into 0. Normalise the storage format here so a
        round-trip through the settings page never corrupts a numeric setting.
        """
        if self.setting_type == "boolean":
            self.setting_value = "true" if value else "false"
        elif self.setting_type == "json":
            self.setting_value = json.dumps(value)
        elif self.setting_type == "integer":
            if value in (None, ""):
                self.setting_value = "0"
            else:
                try:
                    self.setting_value = str(int(float(value)))
                except (ValueError, TypeError):
                    self.setting_value = "0"
        elif self.setting_type == "number":
            if value in (None, ""):
                self.setting_value = ""
            else:
                try:
                    self.setting_value = str(float(value))
                except (ValueError, TypeError):
                    self.setting_value = ""
        else:
            self.setting_value = str(value)

    def to_dict(self, include_sensitive: bool = False) -> dict:
        data = {
            "id": self.id,
            "category": self.category,
            "key": self.setting_key,
            "value": (
                self.get_value()
                if (include_sensitive or self.is_public or self.setting_type != "password")
                else "********"
            ),
            "type": self.setting_type,
            "description": self.description,
            "is_public": self.is_public,
            "is_required": self.is_required,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updated_by": self.updated_by,
        }
        return data


class Notification(db.Model):
    """User notifications"""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default="info", index=True)  # info, warning, error, success
    category = db.Column(
        db.String(50), default="system", index=True
    )  # system, inventory, sales, staff, backup
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    read_at = db.Column(db.DateTime)
    action_url = db.Column(db.String(500))
    action_text = db.Column(db.String(100))
    priority = db.Column(db.Integer, default=0)  # Higher = more important

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = now_utc()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "type": self.type,
            "category": self.category,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "time_ago": time_ago(self.created_at),
            "action_url": self.action_url,
            "action_text": self.action_text,
            "priority": self.priority,
        }

    def __repr__(self):
        return f"<Notification {self.title} for user {self.user_id}>"


class AuditLog(db.Model):
    """Audit trail for important changes"""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action_date = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("staff.id", ondelete="SET NULL"), index=True)
    action_type = db.Column(
        db.String(20), nullable=False, index=True
    )  # create, update, delete, login, logout, export
    table_name = db.Column(db.String(50), nullable=False, index=True)
    record_id = db.Column(db.Integer, index=True)
    old_values = db.Column(db.Text)  # JSON
    new_values = db.Column(db.Text)  # JSON
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    request_id = db.Column(db.String(36))  # Correlation ID for request tracing

    @staticmethod
    def log(
        action_type: str,
        table_name: str,
        record_id: int = None,
        old_values: dict = None,
        new_values: dict = None,
        user_id: int = None,
        request_id: str = None,
    ):
        """Create audit log entry"""
        from flask import request, has_request_context
        import json

        if has_request_context():
            ip = request.remote_addr
            ua = request.headers.get("User-Agent")
            req_id = request_id or request.headers.get("X-Request-ID")
        else:
            ip = ua = req_id = None

        audit = AuditLog(
            user_id=user_id,
            action_type=action_type,
            table_name=table_name,
            record_id=record_id,
            old_values=json.dumps(old_values, default=str) if old_values else None,
            new_values=json.dumps(new_values, default=str) if new_values else None,
            ip_address=ip,
            user_agent=ua,
            request_id=req_id,
        )
        db.session.add(audit)
        # Don't commit here - let the caller commit


class SystemLog(db.Model):
    """System/application logs"""

    __tablename__ = "system_logs"

    id = db.Column(db.Integer, primary_key=True)
    log_date = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    log_level = db.Column(
        db.String(20), default="info", index=True
    )  # debug, info, warning, error, critical
    category = db.Column(db.String(50), index=True)  # system, database, security, performance, api
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text)  # JSON
    source = db.Column(db.String(100))  # Module/component
    request_id = db.Column(db.String(36), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("staff.id", ondelete="SET NULL"), index=True)

    @staticmethod
    def log(
        level: str,
        message: str,
        category: str = "system",
        details: dict = None,
        source: str = "application",
        user_id: int = None,
        request_id: str = None,
    ):
        """Create system log entry"""
        from flask import request, has_request_context
        import json

        if has_request_context():
            req_id = request_id or request.headers.get("X-Request-ID")
            uid = user_id or (request.current_user.id if hasattr(request, "current_user") else None)
        else:
            req_id = uid = None

        log = SystemLog(
            log_level=level,
            message=message,
            category=category,
            details=json.dumps(details, default=str) if details else None,
            source=source,
            request_id=req_id,
            user_id=uid,
        )
        db.session.add(log)


class BackupLog(db.Model):
    """Database backup logs"""

    __tablename__ = "backup_logs"

    id = db.Column(db.Integer, primary_key=True)
    backup_date = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    backup_type = db.Column(db.String(20), default="manual", index=True)  # manual, scheduled
    backup_location = db.Column(db.String(500))
    file_size = db.Column(db.BigInteger)
    status = db.Column(db.String(20), default="success", index=True)  # success, failed, in_progress
    error_message = db.Column(db.Text)
    tables_included = db.Column(db.Text)  # JSON list of tables
    created_by = db.Column(db.Integer, db.ForeignKey("staff.id"))
    completed_at = db.Column(db.DateTime)

    @property
    def duration_seconds(self) -> float:
        if self.completed_at and self.backup_date:
            return (self.completed_at - self.backup_date).total_seconds()
        return 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "backup_date": self.backup_date.isoformat() if self.backup_date else None,
            "backup_type": self.backup_type,
            "backup_location": self.backup_location,
            "file_size": self.file_size,
            "status": self.status,
            "error_message": self.error_message,
            "duration_seconds": self.duration_seconds,
            "created_by": self.created_by,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
