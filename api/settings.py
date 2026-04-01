"""Settings API — user preferences persistence."""
import sqlite3
from flask import Blueprint, request, jsonify, current_app
from config import DB_PATH

settings_bp = Blueprint("settings", __name__)

# Default settings
DEFAULTS = {
    "font_size": "16",
    "default_standard": "CDC",
    "date_format": "DD/MM/YYYY",
}


def _ensure_settings_table(db_path=None):
    """Create the settings table if it doesn't exist and populate defaults."""
    if db_path is None:
        db_path = DB_PATH
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # Insert defaults for any missing keys
    for key, value in DEFAULTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
    conn.commit()
    conn.close()


def _get_all_settings(db_path=None):
    """Return all settings as a dict."""
    if db_path is None:
        db_path = DB_PATH
    _ensure_settings_table(db_path)
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    result = dict(DEFAULTS)  # start with defaults
    for key, value in rows:
        result[key] = value
    # Convert numeric values
    if "font_size" in result:
        try:
            result["font_size"] = int(result["font_size"])
        except (ValueError, TypeError):
            result["font_size"] = 16
    return result


def _set_settings(updates: dict, db_path=None):
    """Update settings from a dict."""
    if db_path is None:
        db_path = DB_PATH
    _ensure_settings_table(db_path)
    conn = sqlite3.connect(str(db_path))
    for key, value in updates.items():
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )
    conn.commit()
    conn.close()


@settings_bp.route("/settings", methods=["GET"])
def get_settings():
    """Return current settings."""
    db_path = current_app.db.db_path
    settings = _get_all_settings(db_path)
    return jsonify(settings)


@settings_bp.route("/settings", methods=["PUT"])
def update_settings():
    """Update settings."""
    db_path = current_app.db.db_path
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Validate font_size
    if "font_size" in data:
        try:
            fs = int(data["font_size"])
            if fs < 12 or fs > 24:
                return jsonify({"error": "font_size must be between 12 and 24"}), 400
            data["font_size"] = str(fs)
        except (ValueError, TypeError):
            return jsonify({"error": "font_size must be a number"}), 400

    # Validate default_standard
    if "default_standard" in data:
        if data["default_standard"] not in ("WHO", "CDC"):
            return jsonify({"error": "default_standard must be WHO or CDC"}), 400

    # Validate date_format
    if "date_format" in data:
        valid_formats = ("DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD")
        if data["date_format"] not in valid_formats:
            return jsonify({"error": f"date_format must be one of {valid_formats}"}), 400

    # Only save recognized keys
    allowed = set(DEFAULTS.keys())
    filtered = {k: v for k, v in data.items() if k in allowed}

    _set_settings(filtered, db_path)
    return jsonify(_get_all_settings(db_path))
