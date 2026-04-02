"""
GrowthChart v2 — Pediatric Growth Monitoring (Flask Web App)

Local web application for pediatric endocrinology:
- WHO/CDC growth charts with interactive Plotly.js zoom/hover
- PDF/Excel/CSV import with Hebrew clinic letter parsing
- Patient matching across sessions
- Elysia branded PDF export
- RTL Hebrew support via native browser rendering

Usage:
    python main.py
"""
import sys
import os
import webbrowser
import threading

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use Agg backend for matplotlib (server-side only, no TkAgg)
import matplotlib
matplotlib.use("Agg")

from flask import Flask, send_from_directory, jsonify
from config import (
    APP_NAME, APP_VERSION, FLASK_HOST, FLASK_PORT,
    STATIC_FOLDER, UPLOAD_FOLDER, DB_PATH, DATA_DIR
)
from database import Database
from zscore.engine import ZScoreEngine
from config import Standard


def create_app():
    """Flask application factory."""
    app = Flask(
        __name__,
        static_folder=str(STATIC_FOLDER),
        static_url_path="/static"
    )
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB upload limit

    # Ensure upload directory exists
    UPLOAD_FOLDER.mkdir(exist_ok=True)

    # ── Initialize services ──────────────────────────────
    db = Database(DB_PATH)
    db.initialize()

    # Run schema migrations (adds new columns safely)
    from migrations import run_migrations
    run_migrations(DB_PATH)

    engine = ZScoreEngine(DATA_DIR)
    engine.load_standard(Standard.WHO)
    engine.load_standard(Standard.CDC)

    # Store on app for access in blueprints
    app.db = db
    app.engine = engine

    # ── Register API blueprints ──────────────────────────
    from api.patients import patients_bp
    from api.measurements import measurements_bp
    from api.charts import charts_bp
    from api.imports import imports_bp
    from api.exports import exports_bp
    from api.settings import settings_bp
    from api.cds import cds_bp

    app.register_blueprint(patients_bp, url_prefix="/api")
    app.register_blueprint(measurements_bp, url_prefix="/api")
    app.register_blueprint(charts_bp, url_prefix="/api")
    app.register_blueprint(imports_bp, url_prefix="/api")
    app.register_blueprint(exports_bp, url_prefix="/api")
    app.register_blueprint(settings_bp, url_prefix="/api")
    app.register_blueprint(cds_bp, url_prefix="/api")

    # ── Serve SPA ────────────────────────────────────────
    @app.route("/")
    def index():
        return send_from_directory(str(STATIC_FOLDER), "index.html")

    @app.route("/api/info")
    def info():
        return jsonify({
            "name": APP_NAME,
            "version": APP_VERSION,
            "standards": ["WHO", "CDC"],
            "indicators": ["hfa", "wfa", "bfa"],
        })

    return app


def open_browser():
    """Open browser after a short delay to let Flask start."""
    import time
    time.sleep(1.0)
    webbrowser.open(f"http://{FLASK_HOST}:{FLASK_PORT}")


def main():
    app = create_app()

    # Open browser in background thread
    threading.Thread(target=open_browser, daemon=True).start()

    print(f"\n  {APP_NAME} v{APP_VERSION}")
    print(f"  Running at http://{FLASK_HOST}:{FLASK_PORT}")
    print(f"  Press Ctrl+C to stop\n")

    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
