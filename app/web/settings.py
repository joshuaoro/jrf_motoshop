"""
Web settings blueprint
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import Settings, BackupLog
from app.services.system import SettingsService

settings_web_bp = Blueprint("settings_web", __name__, template_folder="../../templates")


@settings_web_bp.route("/")
@login_required
def index():
    """Settings page"""
    if not current_user.can_manage_settings():
        flash("You do not have permission to access settings", "error")
        return redirect(url_for("dashboard_web.index"))

    # Initialize default settings if needed
    if Settings.query.count() == 0:
        SettingsService.init_defaults()

    # Secret-typed values are masked for non-administrators.
    settings_dict = SettingsService.get_all_settings(
        include_sensitive=current_user.can_view_sensitive_settings()
    )

    # Get last backup
    last_backup = BackupLog.query.order_by(BackupLog.backup_date.desc()).first()
    if last_backup:
        last_backup_display = last_backup.backup_date.strftime("%B %d, %Y at %I:%M %p")
    else:
        last_backup_display = "No backups yet"

    return render_template("settings.html", settings=settings_dict, last_backup=last_backup_display)


@settings_web_bp.route("/update", methods=["POST"])
@login_required
def update():
    """Update settings from form"""
    if not current_user.can_manage_settings():
        flash("Insufficient permissions", "error")
        return redirect(url_for("settings_web.index"))

    # Build settings data from form
    data = {}
    for key, value in request.form.items():
        if key.startswith("setting_"):
            parts = key.replace("setting_", "", 1).split("__", 1)
            if len(parts) == 2:
                category, setting_key = parts
                if category not in data:
                    data[category] = {}
                data[category][setting_key] = value

    if not data:
        flash("No settings to update", "warning")
        return redirect(url_for("settings_web.index"))

    result = SettingsService.update_settings(data, current_user.id)

    if result.get("errors"):
        flash(f"Some settings failed: {'; '.join(result['errors'][:3])}", "error")
    if result.get("updated"):
        flash(f"{len(result['updated'])} settings updated successfully", "success")

    return redirect(url_for("settings_web.index"))


@settings_web_bp.route("/reset", methods=["POST"])
@login_required
def reset():
    """Reset settings to defaults"""
    if not current_user.is_admin():
        flash("Admin access required", "error")
        return redirect(url_for("settings_web.index"))

    category = request.form.get("category")
    count = SettingsService.reset_to_defaults(category)
    flash(f"Reset {count} settings to defaults", "success")
    return redirect(url_for("settings_web.index"))
