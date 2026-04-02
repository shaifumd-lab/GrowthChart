"""
Database schema migrations for GrowthChart v2.

Runs ALTER TABLE statements safely, checking if columns/tables already exist
before attempting modifications. Call run_migrations() from main.py on startup.
"""
import sqlite3
from pathlib import Path
from config import DB_PATH


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Check if a table exists."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    return cursor.fetchone() is not None


def run_migrations(db_path: Path = DB_PATH):
    """Run all schema migrations safely."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    # ── patients table additions ──────────────────────────────
    patient_columns = [
        ("mother_height_cm", "REAL"),
        ("father_height_cm", "REAL"),
        ("mph_cm", "REAL"),
        ("mph_user_edited", "INTEGER DEFAULT 0"),
        ("syndrome", "TEXT DEFAULT ''"),
        ("gh_start_date", "TEXT"),  # ISO date (YYYY-MM-DD) when GH therapy started
    ]
    for col_name, col_type in patient_columns:
        if not _column_exists(conn, "patients", col_name):
            conn.execute(f"ALTER TABLE patients ADD COLUMN {col_name} {col_type}")
            print(f"  Migration: added patients.{col_name}")

    # ── measurements table additions ──────────────────────────
    if not _column_exists(conn, "measurements", "bone_age_years"):
        conn.execute("ALTER TABLE measurements ADD COLUMN bone_age_years REAL")
        print("  Migration: added measurements.bone_age_years")

    # ── settings table ────────────────────────────────────────
    if not _table_exists(conn, "settings"):
        conn.execute("""
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        print("  Migration: created settings table")

    # Insert default settings (ignore if already present)
    default_settings = [
        ("font_size", "16"),
        ("default_standard", "CDC"),
    ]
    for key, value in default_settings:
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    conn.commit()
    conn.close()
    print("  Migrations complete.")


if __name__ == "__main__":
    run_migrations()
