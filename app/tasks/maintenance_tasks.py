"""
Maintenance tasks for scheduled background jobs.

Every task reuses the service layer rather than reimplementing the same
queries, so a rule changed in one place cannot go stale here.
"""

import logging
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from celery import shared_task
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.core.extensions import db
from app.core.time_utils import now_utc
from app.models import AuditLog, BackupLog, Notification, SystemLog
from app.services.inventory import InventoryService
from app.services.system import SettingsService

logger = logging.getLogger(__name__)


@shared_task
def check_low_stock():
    """Notify admins and managers about every part below the threshold."""
    try:
        count = InventoryService.notify_low_stock()
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Low stock check failed")
        raise

    logger.info("Low stock check complete: %d item(s) below threshold", count)
    return {"status": "completed", "low_stock_count": count}


@shared_task
def cleanup_old_logs():
    """Prune old system logs, audit logs and read notifications."""
    now = now_utc()

    try:
        deleted_logs = SystemLog.query.filter(SystemLog.log_date < now - timedelta(days=90)).delete(
            synchronize_session=False
        )

        deleted_audits = AuditLog.query.filter(
            AuditLog.action_date < now - timedelta(days=365)
        ).delete(synchronize_session=False)

        deleted_notifs = Notification.query.filter(
            Notification.is_read.is_(True),
            Notification.read_at < now - timedelta(days=30),
        ).delete(synchronize_session=False)

        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception("Log cleanup failed")
        raise

    logger.info(
        "Cleanup complete: %d logs, %d audits, %d notifications",
        deleted_logs,
        deleted_audits,
        deleted_notifs,
    )
    return {
        "status": "completed",
        "deleted_logs": deleted_logs,
        "deleted_audits": deleted_audits,
        "deleted_notifications": deleted_notifs,
    }


@shared_task
def auto_backup():
    """Scheduled pg_dump, with retention pruning."""
    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_url.startswith("postgresql"):
        logger.warning("Skipping auto backup: not a PostgreSQL database")
        return {"status": "skipped", "reason": "not_postgresql"}

    backup_dir = Path(
        SettingsService.get_setting("backup", "backup_location")
        or current_app.config.get("BACKUP_DIR", "./backups")
    ).resolve()

    try:
        retention_days = int(SettingsService.get_setting("backup", "backup_retention", 30))
    except (TypeError, ValueError):
        retention_days = 30

    backup_dir.mkdir(parents=True, exist_ok=True)
    filepath = backup_dir / f"jrf_backup_{now_utc():%Y%m%d_%H%M%S}.sql"

    backup_log = BackupLog(
        backup_type="scheduled",
        backup_location=str(filepath),
        status="in_progress",
    )
    db.session.add(backup_log)
    db.session.commit()

    try:
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

        file_size = filepath.stat().st_size
        backup_log.file_size = file_size
        backup_log.status = "success"
        backup_log.completed_at = now_utc()
        backup_log.tables_included = "all"
        db.session.commit()

    except Exception as exc:
        db.session.rollback()
        backup_log.status = "failed"
        backup_log.error_message = str(exc)[:500]
        backup_log.completed_at = now_utc()
        db.session.commit()

        filepath.unlink(missing_ok=True)
        logger.exception("Auto backup failed")
        return {"status": "failed", "error": str(exc)[:500]}

    removed = _prune_old_backups(backup_dir, retention_days)
    logger.info(
        "Auto backup completed: %s (%d bytes), pruned %d old backup(s)",
        filepath,
        file_size,
        removed,
    )
    return {
        "status": "completed",
        "filename": filepath.name,
        "file_size": file_size,
        "pruned": removed,
    }


def _prune_old_backups(backup_dir: Path, retention_days: int) -> int:
    """Delete .sql dumps older than the retention window."""
    if retention_days <= 0:
        return 0

    cutoff = now_utc() - timedelta(days=retention_days)
    removed = 0

    for path in backup_dir.glob("jrf_backup_*.sql"):
        try:
            # Naive UTC, to match `cutoff` (see app/core/time_utils). Not
            # datetime.utcfromtimestamp: that is deprecated on 3.12+, which
            # this project's pytest config turns into an error.
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC).replace(tzinfo=None)
            if modified < cutoff:
                path.unlink()
                removed += 1
                logger.info("Removed old backup: %s", path.name)
        except OSError as exc:
            logger.error("Failed to remove old backup %s: %s", path.name, exc)

    return removed
