"""
Celery configuration for background tasks
"""

from celery import Celery
from app.core.factory import create_app


def make_celery(app=None):
    """Create Celery instance"""
    app = app or create_app()

    celery = Celery(
        app.import_name,
        broker=app.config.get("REDIS_URL", "redis://localhost:6379/0"),
        backend=app.config.get("REDIS_URL", "redis://localhost:6379/0"),
        include=[
            "app.tasks.email_tasks",
            "app.tasks.report_tasks",
            "app.tasks.maintenance_tasks",
        ],
    )

    # Update config from Flask app
    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Manila",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=30 * 60,  # 30 minutes
        task_soft_time_limit=25 * 60,  # 25 minutes
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=1000,
        beat_schedule={
            "check-low-stock-daily": {
                "task": "app.tasks.maintenance_tasks.check_low_stock",
                "schedule": 86400.0,  # Daily
            },
            "send-daily-report": {
                "task": "app.tasks.report_tasks.send_daily_sales_report",
                "schedule": 86400.0,  # Daily at midnight
            },
            "cleanup-old-logs-weekly": {
                "task": "app.tasks.maintenance_tasks.cleanup_old_logs",
                "schedule": 604800.0,  # Weekly
            },
            "auto-backup-daily": {
                "task": "app.tasks.maintenance_tasks.auto_backup",
                "schedule": 86400.0,  # Daily
            },
        },
    )

    # Ensure Flask app context for tasks
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery


# Create global celery instance
celery = make_celery()
