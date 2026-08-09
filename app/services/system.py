"""
Settings and Notification services
"""

from typing import List, Optional, Dict, Any
from app.core.extensions import db
from app.models import Settings, Notification, User
from datetime import datetime


class SettingsService:
    """Service layer for application settings"""

    # Default settings definition
    DEFAULT_SETTINGS = {
        "general": {
            "store_name": {
                "value": "JRF Motorcycle Parts & Accessories",
                "type": "string",
                "description": "Store name",
                "public": True,
            },
            "store_address": {
                "value": "123 Main Street, Manila, Philippines",
                "type": "string",
                "description": "Store address",
                "public": True,
            },
            "contact_number": {
                "value": "+63 2 1234 5678",
                "type": "string",
                "description": "Contact number",
                "public": True,
            },
            "email_address": {
                "value": "info@jrfmotorparts.com",
                "type": "string",
                "description": "Email address",
                "public": True,
            },
            "currency": {
                "value": "PHP",
                "type": "string",
                "description": "Currency code",
                "public": True,
            },
            "timezone": {
                "value": "Asia/Manila",
                "type": "string",
                "description": "Timezone",
                "public": True,
            },
        },
        "inventory": {
            "low_stock_alert": {
                "value": "true",
                "type": "boolean",
                "description": "Enable low stock alerts",
                "public": False,
            },
            "low_stock_threshold": {
                "value": "5",
                "type": "integer",
                "description": "Low stock threshold",
                "public": False,
            },
            "auto_generate_sku": {
                "value": "true",
                "type": "boolean",
                "description": "Auto-generate SKU",
                "public": False,
            },
            "track_serial_numbers": {
                "value": "false",
                "type": "boolean",
                "description": "Track serial numbers",
                "public": False,
            },
            "allow_negative_stock": {
                "value": "false",
                "type": "boolean",
                "description": "Allow negative stock",
                "public": False,
            },
        },
        "sales": {
            "tax_rate": {
                "value": "0.12",
                "type": "number",
                "description": "Tax rate (0.12 = 12%)",
                "public": True,
            },
            "default_payment_method": {
                "value": "cash",
                "type": "string",
                "description": "Default payment method",
                "public": False,
            },
            "enable_receipts": {
                "value": "true",
                "type": "boolean",
                "description": "Enable receipt printing",
                "public": False,
            },
            "email_receipts": {
                "value": "false",
                "type": "boolean",
                "description": "Email receipts to customers",
                "public": False,
            },
            "receipt_header": {
                "value": "JRF MOTORCYCLE PARTS",
                "type": "string",
                "description": "Receipt header text",
                "public": False,
            },
            "receipt_footer": {
                "value": "Thank you for your business!",
                "type": "string",
                "description": "Receipt footer text",
                "public": False,
            },
            "high_value_sale_threshold": {
                "value": "5000",
                "type": "number",
                "description": "High value sale alert threshold",
                "public": False,
            },
        },
        "notifications": {
            "email_notifications": {
                "value": "true",
                "type": "boolean",
                "description": "Enable email notifications",
                "public": False,
            },
            "low_stock_email": {
                "value": "true",
                "type": "boolean",
                "description": "Send low stock emails",
                "public": False,
            },
            "sales_email": {
                "value": "false",
                "type": "boolean",
                "description": "Send sales emails",
                "public": False,
            },
            "backup_reminder": {
                "value": "true",
                "type": "boolean",
                "description": "Backup reminders",
                "public": False,
            },
            "notification_email": {
                "value": "admin@jrfmotorparts.com",
                "type": "string",
                "description": "Notification email",
                "public": False,
            },
        },
        "backup": {
            "auto_backup": {
                "value": "true",
                "type": "boolean",
                "description": "Enable auto backup",
                "public": False,
            },
            "backup_frequency": {
                "value": "daily",
                "type": "string",
                "description": "Backup frequency",
                "public": False,
            },
            "backup_retention": {
                "value": "30",
                "type": "integer",
                "description": "Backup retention days",
                "public": False,
            },
            "backup_location": {
                "value": "./backups",
                "type": "string",
                "description": "Backup storage location",
                "public": False,
            },
        },
        "security": {
            "session_timeout": {
                "value": "30",
                "type": "integer",
                "description": "Session timeout minutes",
                "public": False,
            },
            "password_min_length": {
                "value": "8",
                "type": "integer",
                "description": "Minimum password length",
                "public": False,
            },
            "require_password_change": {
                "value": "false",
                "type": "boolean",
                "description": "Require periodic password change",
                "public": False,
            },
            "login_attempts": {
                "value": "5",
                "type": "integer",
                "description": "Max login attempts before lockout",
                "public": False,
            },
            "password_expiry_days": {
                "value": "90",
                "type": "integer",
                "description": "Password expiry days",
                "public": False,
            },
        },
    }

    @staticmethod
    def get_all_settings(
        category: str = None,
        public_only: bool = False,
        include_sensitive: bool = False,
    ) -> Dict[str, Dict]:
        """Get all settings grouped by category.

        ``include_sensitive`` controls whether password-typed values are
        returned in the clear or masked. It is an explicit argument rather
        than being inferred from ``public_only``, which previously meant that
        asking for "all settings" also meant "reveal every secret".
        """
        query = Settings.query

        if category:
            query = query.filter(Settings.category == category)

        if public_only:
            query = query.filter(Settings.is_public.is_(True))

        settings = query.order_by(Settings.category, Settings.setting_key).all()

        result: Dict[str, Dict] = {}
        for setting in settings:
            result.setdefault(setting.category, {})[setting.setting_key] = setting.to_dict(
                include_sensitive=include_sensitive
            )

        return result

    @staticmethod
    def get_setting_record(category: str, key: str) -> Optional[Settings]:
        """Get the Settings row itself (callers needing the type or metadata)."""
        return Settings.query.filter_by(category=category, setting_key=key).first()

    @staticmethod
    def get_setting(category: str, key: str, default: Any = None) -> Optional[Any]:
        """Get a single setting value, converted to its declared type.

        Returns ``default`` when the setting row is absent or holds NULL, so
        callers work on a fresh database where ``init_defaults`` has not run.
        """
        setting = Settings.query.filter_by(category=category, setting_key=key).first()
        if setting is None:
            return default
        value = setting.get_value()
        return default if value is None else value

    @staticmethod
    def get_settings_dict(category: str = None, public_only: bool = False) -> Dict:
        """Get settings as flat dict with typed values"""
        settings = SettingsService.get_all_settings(category, public_only)
        result = {}
        for cat, cat_settings in settings.items():
            for key, setting in cat_settings.items():
                result[f"{cat}.{key}"] = setting["value"]
        return result

    @staticmethod
    def init_defaults():
        """Initialize default settings if not exist"""
        for category, settings in SettingsService.DEFAULT_SETTINGS.items():
            for key, config in settings.items():
                existing = Settings.query.filter_by(category=category, setting_key=key).first()
                if not existing:
                    setting = Settings(
                        category=category,
                        setting_key=key,
                        setting_value=str(config["value"]),
                        setting_type=config["type"],
                        description=config["description"],
                        is_public=config.get("public", False),
                    )
                    db.session.add(setting)
        db.session.commit()

    @staticmethod
    def update_settings(data: Dict[str, Dict], user_id: int) -> Dict[str, Any]:
        """Update multiple settings"""
        updated = []
        errors = []

        for category, settings in data.items():
            for key, value in settings.items():
                setting = Settings.query.filter_by(category=category, setting_key=key).first()

                if not setting:
                    errors.append(f"Setting {category}.{key} does not exist")
                    continue

                try:
                    # Validate
                    if setting.validation_regex:
                        import re

                        if not re.match(setting.validation_regex, str(value)):
                            errors.append(f"Invalid value for {category}.{key}")
                            continue

                    old_value = setting.get_value()
                    setting.set_value(value)
                    setting.updated_by = user_id
                    setting.updated_at = datetime.utcnow()

                    updated.append(
                        {
                            "category": category,
                            "key": key,
                            "old_value": old_value,
                            "new_value": setting.get_value(),
                        }
                    )
                except Exception as e:
                    errors.append(f"Error updating {category}.{key}: {str(e)}")

        if updated:
            db.session.commit()
        else:
            # Nothing applied - drop any partial state instead of committing it.
            db.session.rollback()

        return {"updated": updated, "errors": errors}

    @staticmethod
    def reset_to_defaults(category: str = None) -> int:
        """Reset settings to defaults"""
        count = 0
        for cat, settings in SettingsService.DEFAULT_SETTINGS.items():
            if category and cat != category:
                continue
            for key, config in settings.items():
                setting = Settings.query.filter_by(category=cat, setting_key=key).first()
                if setting:
                    setting.set_value(config["value"])
                    setting.updated_at = datetime.utcnow()
                    count += 1
        db.session.commit()
        return count


class NotificationService:
    """Service layer for notifications"""

    @staticmethod
    def create_notification(
        user_id: int,
        title: str,
        message: str,
        type: str = "info",
        category: str = "system",
        action_url: str = None,
        action_text: str = None,
        priority: int = 0,
    ) -> Notification:
        """Create a single notification"""
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=type,
            category=category,
            action_url=action_url,
            action_text=action_text,
            priority=priority,
        )
        db.session.add(notification)
        db.session.commit()
        return notification

    @staticmethod
    def create_for_role(
        role: str,
        title: str,
        message: str,
        type: str = "info",
        category: str = "system",
        action_url: str = None,
        action_text: str = None,
        priority: int = 0,
    ) -> List[Notification]:
        """Create notifications for all users with a role"""
        users = User.query.filter_by(role=role, is_active=True).all()
        notifications = []

        for user in users:
            notification = NotificationService.create_notification(
                user_id=user.id,
                title=title,
                message=message,
                type=type,
                category=category,
                action_url=action_url,
                action_text=action_text,
                priority=priority,
            )
            notifications.append(notification)

        return notifications

    @staticmethod
    def create_for_all(
        title: str,
        message: str,
        type: str = "info",
        category: str = "system",
        action_url: str = None,
        action_text: str = None,
    ) -> List[Notification]:
        """Create notifications for all active users"""
        users = User.query.filter_by(is_active=True).all()
        notifications = []

        for user in users:
            notification = NotificationService.create_notification(
                user_id=user.id,
                title=title,
                message=message,
                type=type,
                category=category,
                action_url=action_url,
                action_text=action_text,
            )
            notifications.append(notification)

        return notifications

    @staticmethod
    def get_user_notifications(
        user_id: int,
        page: int = 1,
        per_page: int = 20,
        unread_only: bool = False,
        category: str = None,
    ):
        """Get paginated notifications for user"""
        query = Notification.query.filter_by(user_id=user_id)

        if unread_only:
            query = query.filter_by(is_read=False)

        if category:
            query = query.filter_by(category=category)

        query = query.order_by(Notification.priority.desc(), Notification.created_at.desc())
        return query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_unread_count(user_id: int) -> int:
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()

    @staticmethod
    def mark_read(notification_id: int, user_id: int) -> bool:
        """Mark one notification read. Idempotent.

        Returns False only when the notification does not exist (or belongs to
        someone else). Marking an already-read notification succeeds, so a
        double-click cannot surface a spurious 404.
        """
        notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
        if not notification:
            return False

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            db.session.commit()

        return True

    @staticmethod
    def mark_all_read(user_id: int) -> int:
        notifications = Notification.query.filter_by(user_id=user_id, is_read=False).all()
        count = len(notifications)
        for notification in notifications:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
        db.session.commit()
        return count

    @staticmethod
    def delete_notification(notification_id: int, user_id: int) -> bool:
        notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
        if notification:
            db.session.delete(notification)
            db.session.commit()
            return True
        return False

    @staticmethod
    def clear_all(user_id: int) -> int:
        count = Notification.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        return count
