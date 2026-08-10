"""
Settings API blueprint
"""

import json
import logging
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user, login_required

from app.api.utils import admin_required, error, permission_required
from app.core.time_utils import now_utc
from app.services.system import SettingsService

settings_bp = Blueprint("settings", __name__)
logger = logging.getLogger(__name__)

# Refuse settings imports larger than this; the file is parsed into memory.
MAX_IMPORT_BYTES = 1 * 1024 * 1024


@settings_bp.route("/", methods=["GET"])
@settings_bp.route("", methods=["GET"])
@login_required
def get_settings():
    """Get all settings.

    Secret-typed values are masked unless the caller is an administrator.
    Previously any manager received them in the clear, because the visibility
    switch was derived from a supplier permission.
    """
    settings = SettingsService.get_all_settings(
        category=request.args.get("category"),
        include_sensitive=current_user.can_view_sensitive_settings(),
    )
    return jsonify(settings)


@settings_bp.route("/", methods=["PUT", "POST"])
@settings_bp.route("", methods=["PUT", "POST"])
@login_required
@permission_required("can_manage_settings")
def update_settings():
    """Update settings"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return error("A JSON object of settings is required", 400)

    result = SettingsService.update_settings(data, current_user.id)
    if result["errors"] and not result["updated"]:
        return error("No settings were updated", 400, details=result["errors"])

    logger.info("%s updated %d setting(s)", current_user.email, len(result["updated"]))
    return jsonify(result)


# ============================================================
# SPECIAL SETTINGS ENDPOINTS - MUST be before /<category>/<key>
# ============================================================
@settings_bp.route("/reset", methods=["POST"])
@login_required
@admin_required
def reset_settings():
    """Reset settings to defaults"""
    category = request.args.get("category")
    count = SettingsService.reset_to_defaults(category)
    logger.warning(
        "%s reset %d setting(s) to defaults (category=%s)",
        current_user.email,
        count,
        category or "all",
    )
    return jsonify({"message": f"Reset {count} settings to defaults", "count": count})


@settings_bp.route("/export", methods=["GET"])
@login_required
@admin_required
def export_settings():
    """Export all settings as JSON (admin only - includes secrets)."""
    export_data = {
        "exported_at": now_utc().isoformat() + "Z",
        "exported_by": current_user.name,
        "settings": SettingsService.get_all_settings(include_sensitive=True),
    }

    buffer = BytesIO(json.dumps(export_data, indent=2, default=str).encode("utf-8"))
    buffer.seek(0)

    logger.info("%s exported settings", current_user.email)
    return send_file(
        buffer,
        mimetype="application/json",
        as_attachment=True,
        download_name=f"settings_export_{now_utc():%Y%m%d_%H%M%S}.json",
    )


@settings_bp.route("/import", methods=["POST"])
@login_required
@admin_required
def import_settings():
    """Import settings from a previously exported JSON file."""
    file = request.files.get("file")
    if file is None or not file.filename:
        return error("No file provided", 400)

    if not file.filename.lower().endswith(".json"):
        return error("File must be JSON", 400)

    raw = file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        return error("Settings file is too large (limit 1 MB)", 413)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return error(f"Could not parse JSON: {exc}", 400)

    settings = payload.get("settings") if isinstance(payload, dict) else None
    if not isinstance(settings, dict):
        return error("Invalid settings file: expected a top-level 'settings' object", 400)

    # The export nests {category: {key: {…metadata…}}}; accept both that shape
    # and the flat {category: {key: value}} shape.
    normalised = {}
    for category, entries in settings.items():
        if not isinstance(entries, dict):
            continue
        normalised[category] = {
            key: (entry.get("value") if isinstance(entry, dict) else entry)
            for key, entry in entries.items()
        }

    result = SettingsService.update_settings(normalised, current_user.id)
    logger.info("%s imported %d setting(s)", current_user.email, len(result["updated"]))
    return jsonify({"message": "Settings imported successfully", "result": result})


@settings_bp.route("/<category>/<key>", methods=["GET"])
@login_required
def get_setting(category, key):
    """Get single setting"""
    setting = SettingsService.get_setting_record(category, key)
    if setting is None:
        return error("Setting not found", 404)

    if setting.setting_type == "password" and not current_user.can_view_sensitive_settings():
        return error("Insufficient permissions", 403)

    return jsonify({"category": category, "key": key, "value": setting.get_value()})


@settings_bp.route("/<category>/<key>", methods=["PUT"])
@login_required
@permission_required("can_manage_settings")
def update_setting(category, key):
    """Update single setting"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "value" not in data:
        return error("A JSON body with a 'value' field is required", 400)

    result = SettingsService.update_settings({category: {key: data["value"]}}, current_user.id)
    if result["errors"]:
        return error(result["errors"][0], 400)

    return jsonify(result)
