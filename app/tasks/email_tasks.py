"""
Email tasks for async email sending.

Email is an optional feature. It requires both an SMTP host (``MAIL_SERVER``)
and the ``Flask-Mail`` package, neither of which is required to run the app.
When either is absent the tasks return a ``skipped`` result instead of raising
and burning through Celery retries.
"""

import logging

from celery import shared_task
from flask import current_app

from app.core.extensions import db
from app.models import Notification, User
from app.services.system import SettingsService

logger = logging.getLogger(__name__)


def mail_unavailable_reason() -> str | None:
    """Why email cannot be sent right now, or None when it can."""
    if not SettingsService.get_setting("notifications", "email_notifications", False):
        return "email_notifications_disabled"
    if not current_app.config.get("MAIL_SERVER"):
        return "mail_server_not_configured"
    try:
        import flask_mail  # noqa: F401
    except ImportError:
        return "flask_mail_not_installed"
    return None


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, to_email: str, subject: str, body: str, html_body: str = None):
    """Send one email, retrying only on genuine delivery failures."""
    reason = mail_unavailable_reason()
    if reason:
        logger.info("Skipping email to %s: %s", to_email, reason)
        return {"status": "skipped", "reason": reason}

    from flask_mail import Mail, Message

    try:
        Mail(current_app).send(
            Message(
                subject=subject,
                recipients=[to_email],
                body=body,
                html=html_body,
                sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
            )
        )
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        raise self.retry(exc=exc)

    logger.info("Email sent to %s: %s", to_email, subject)
    return {"status": "sent", "to": to_email}


@shared_task
def send_notification_email(user_id: int, notification_id: int):
    """Send email for a notification"""
    user = db.session.get(User, user_id)
    notification = db.session.get(Notification, notification_id)

    if not user or not notification:
        return {"status": "error", "message": "User or notification not found"}

    if not user.email:
        return {"status": "skipped", "reason": "no_email"}

    reason = mail_unavailable_reason()
    if reason:
        return {"status": "skipped", "reason": reason}

    subject = f"JRF System: {notification.title}"
    body = f"""
Dear {user.name},

{notification.message}

---
JRF Motorcycle Parts & Accessories
This is an automated notification. Please do not reply to this email.
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #2563eb; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background: #f9fafb; }}
        .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>JRF Motorcycle Parts</h1>
        </div>
        <div class="content">
            <h2>{notification.title}</h2>
            <p>{notification.message}</p>
        </div>
        <div class="footer">
            <p>JRF Motorcycle Parts & Accessories</p>
            <p>This is an automated notification. Please do not reply to this email.</p>
        </div>
    </div>
</body>
</html>
"""

    # Send via send_email_task
    send_email_task.delay(user.email, subject, body, html_body)

    return {"status": "queued", "user_id": user_id, "notification_id": notification_id}


@shared_task
def send_bulk_notification_email(role: str, title: str, message: str):
    """Send notification email to all active users with a specific role"""
    reason = mail_unavailable_reason()
    if reason:
        return {"status": "skipped", "reason": reason}

    recipients = [
        user.email for user in User.query.filter_by(role=role, is_active=True).all() if user.email
    ]

    for email in recipients:
        send_email_task.delay(email, f"JRF System: {title}", message)

    return {"status": "queued", "count": len(recipients), "role": role}
