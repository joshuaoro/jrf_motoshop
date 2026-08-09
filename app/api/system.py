"""
System API blueprint - health, logs, backups, maintenance
"""

import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required

from app.api.utils import (
    admin_required,
    error,
    pagination_args,
    pagination_meta,
    parse_date_arg,
)
from app.core.extensions import db
from app.models import AuditLog, BackupLog, Notification, SystemLog
from app.services.system import SettingsService

system_bp = Blueprint("system", __name__)
logger = logging.getLogger(__name__)


def _backup_root() -> Path:
    """Resolved directory that all backups must live inside."""
    configured = (
        SettingsService.get_setting("backup", "backup_location")
        or current_app.config.get("BACKUP_DIR")
        or "./backups"
    )
    return Path(configured).resolve()


@system_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint (no auth required)"""
    try:
        db.session.execute(db.text("SELECT 1"))
        healthy = True
    except Exception as exc:
        # Log the detail, return only a boolean. The previous version echoed
        # str(exc) to an unauthenticated caller, which exposed the database
        # host, user and driver version in the failure message.
        logger.error("Health check database probe failed: %s", exc)
        healthy = False

    return jsonify(
        {
            "status": "healthy" if healthy else "unhealthy",
            "database": "connected" if healthy else "disconnected",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    ), (200 if healthy else 503)


@system_bp.route("/info", methods=["GET"])
@login_required
@admin_required
def system_info():
    """System information (admin only)"""
    import platform
    import sys

    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    # Show only the host/database portion - never the credentials.
    db_target = uri.rsplit("@", 1)[-1] if "@" in uri else "not set"

    return jsonify(
        {
            "app_version": current_app.config.get("APP_VERSION"),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "flask_env": current_app.config.get("FLASK_ENV"),
            "debug": current_app.debug,
            "database": db_target,
        }
    )


@system_bp.route("/logs", methods=["GET"])
@login_required
@admin_required
def get_system_logs():
    """Get system logs"""
    page, per_page = pagination_args(default_per_page=50)

    query = SystemLog.query

    if level := request.args.get("level"):
        query = query.filter(SystemLog.log_level == level)
    if category := request.args.get("category"):
        query = query.filter(SystemLog.category == category)
    if start_date := parse_date_arg("start_date"):
        query = query.filter(SystemLog.log_date >= start_date)
    if end_date := parse_date_arg("end_date", end_of_day=True):
        query = query.filter(SystemLog.log_date <= end_date)

    pagination = query.order_by(SystemLog.log_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify(
        {
            "logs": [
                {
                    "id": log.id,
                    "log_date": log.log_date.isoformat() if log.log_date else None,
                    "log_level": log.log_level,
                    "category": log.category,
                    "message": log.message,
                    "details": log.details,
                    "source": log.source,
                    "request_id": log.request_id,
                }
                for log in pagination.items
            ],
            "pagination": pagination_meta(page, per_page, pagination.total),
        }
    )


@system_bp.route("/audit-logs", methods=["GET"])
@login_required
@admin_required
def get_audit_logs():
    """Get audit logs"""
    page, per_page = pagination_args(default_per_page=50)

    query = AuditLog.query

    if action_type := request.args.get("action_type"):
        query = query.filter(AuditLog.action_type == action_type)
    if table_name := request.args.get("table_name"):
        query = query.filter(AuditLog.table_name == table_name)
    if user_id := request.args.get("user_id", type=int):
        query = query.filter(AuditLog.user_id == user_id)
    if start_date := parse_date_arg("start_date"):
        query = query.filter(AuditLog.action_date >= start_date)
    if end_date := parse_date_arg("end_date", end_of_day=True):
        query = query.filter(AuditLog.action_date <= end_date)

    pagination = query.order_by(AuditLog.action_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify(
        {
            "logs": [
                {
                    "id": log.id,
                    "action_date": log.action_date.isoformat() if log.action_date else None,
                    "user_id": log.user_id,
                    "user_name": log.user.name if log.user else None,
                    "action_type": log.action_type,
                    "table_name": log.table_name,
                    "record_id": log.record_id,
                    "old_values": log.old_values,
                    "new_values": log.new_values,
                    "ip_address": log.ip_address,
                }
                for log in pagination.items
            ],
            "pagination": pagination_meta(page, per_page, pagination.total),
        }
    )


@system_bp.route("/backups", methods=["GET"])
@login_required
@admin_required
def list_backups():
    """List backup logs"""
    page, per_page = pagination_args()
    pagination = BackupLog.query.order_by(BackupLog.backup_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify(
        {
            "backups": [b.to_dict() for b in pagination.items],
            "pagination": pagination_meta(page, per_page, pagination.total),
        }
    )


@system_bp.route("/backups", methods=["POST"])
@login_required
@admin_required
def create_backup():
    """Trigger a pg_dump of the configured database."""
    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI")
    if not db_url or not db_url.startswith("postgresql"):
        return error("Backups require a PostgreSQL database", 400)

    backup_dir = _backup_root()
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return error(f"Cannot create backup directory: {exc}", 500)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filepath = backup_dir / f"jrf_backup_{timestamp}.sql"

    backup_log = BackupLog(
        backup_type="manual",
        backup_location=str(filepath),
        status="in_progress",
        created_by=current_user.id,
    )
    db.session.add(backup_log)
    db.session.commit()

    try:
        # Argument list (never a shell string) so nothing in the URL can be
        # interpreted as a shell token. The password is passed via the
        # connection URL in argv, which is visible in the process list; on a
        # shared host prefer a .pgpass file and PGPASSFILE.
        result = subprocess.run(
            [
                "pg_dump",
                db_url,
                "--no-owner",
                "--no-privileges",
                "--file",
                str(filepath),
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip()[:500] or "pg_dump failed")

        backup_log.file_size = filepath.stat().st_size
        backup_log.status = "success"
        backup_log.completed_at = datetime.utcnow()
        backup_log.tables_included = "all"
        db.session.commit()

    except FileNotFoundError:
        backup_log.status = "failed"
        backup_log.error_message = "pg_dump executable not found on PATH"
        backup_log.completed_at = datetime.utcnow()
        db.session.commit()
        return error("Backup failed: pg_dump is not installed on the server", 500)

    except Exception as exc:
        backup_log.status = "failed"
        backup_log.error_message = str(exc)[:500]
        backup_log.completed_at = datetime.utcnow()
        if filepath.exists():
            filepath.unlink(missing_ok=True)
        db.session.commit()
        logger.exception("Backup failed")
        return error("Backup failed", 500, details=str(exc)[:500])

    logger.info("Backup created at %s by %s", filepath, current_user.email)
    return jsonify(
        {
            "success": True,
            "message": "Backup completed successfully",
            "backup": backup_log.to_dict(),
        }
    )


@system_bp.route("/backups/<int:backup_id>/download", methods=["GET"])
@login_required
@admin_required
def download_backup(backup_id):
    """Download backup file"""
    backup = db.session.get(BackupLog, backup_id)
    if not backup:
        return error("Backup not found", 404)

    if backup.status != "success" or not backup.backup_location:
        return error("Backup file not available", 404)

    path = Path(backup.backup_location).resolve()

    # Containment check: serve only files that really sit inside the backup
    # directory. Without it, a tampered backup_location row would turn this
    # endpoint into arbitrary file read.
    try:
        path.relative_to(_backup_root())
    except ValueError:
        logger.error("Refusing to serve backup outside the backup directory: %s", path)
        return error("Backup file not available", 404)

    if not path.is_file():
        return error("Backup file not available", 404)

    return send_file(path, as_attachment=True, download_name=path.name)


@system_bp.route("/maintenance/cleanup", methods=["POST"])
@login_required
@admin_required
def maintenance_cleanup():
    """Prune old logs and read notifications."""
    data = request.get_json(silent=True) or {}

    try:
        days = int(data.get("days", 90))
    except (TypeError, ValueError):
        return error("'days' must be an integer", 400)
    if days < 1:
        return error("'days' must be at least 1", 400)

    dry_run = bool(data.get("dry_run", False))
    now = datetime.utcnow()

    targets = (
        (
            "system_logs",
            SystemLog.query.filter(SystemLog.log_date < now - timedelta(days=days)),
        ),
        # Audit history is kept far longer than operational logs.
        (
            "audit_logs",
            AuditLog.query.filter(AuditLog.action_date < now - timedelta(days=max(days, 365))),
        ),
        (
            "notifications",
            Notification.query.filter(
                Notification.is_read.is_(True),
                Notification.read_at < now - timedelta(days=30),
            ),
        ),
    )

    results = {}
    for name, query in targets:
        if dry_run:
            results[f"{name}_cleaned"] = query.count()
        else:
            # synchronize_session=False: we discard the session right after,
            # so there is no need to pay for in-Python synchronisation.
            results[f"{name}_cleaned"] = query.delete(synchronize_session=False)

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
        logger.info("Maintenance cleanup by %s: %s", current_user.email, results)

    return jsonify(
        {
            "message": "Dry run completed" if dry_run else "Maintenance cleanup completed",
            "dry_run": dry_run,
            "results": results,
        }
    )
