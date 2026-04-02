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
        ("gh_start_date", "TEXT"),
        # CDS Phase H: Birth data
        ("gestational_age_weeks", "INTEGER"),
        ("birth_weight_g", "REAL"),
        ("birth_length_cm", "REAL"),
        ("birth_head_circ_cm", "REAL"),
        ("sga_flag", "INTEGER"),
    ]
    for col_name, col_type in patient_columns:
        if not _column_exists(conn, "patients", col_name):
            conn.execute(f"ALTER TABLE patients ADD COLUMN {col_name} {col_type}")
            print(f"  Migration: added patients.{col_name}")

    # ── measurements table additions ──────────────────────────
    measurement_columns = [
        ("bone_age_years", "REAL"),
        # CDS Phase H: Tanner staging
        ("tanner_breast", "INTEGER"),
        ("tanner_pubic_hair", "INTEGER"),
        ("tanner_genital", "INTEGER"),
        ("testicular_volume", "REAL"),
        # CDS Phase H: Blood pressure
        ("bp_systolic", "INTEGER"),
        ("bp_diastolic", "INTEGER"),
        # CDS Phase H: Additional anthropometrics
        ("sitting_height_cm", "REAL"),
        ("arm_span_cm", "REAL"),
        ("waist_circumference_cm", "REAL"),
    ]
    for col_name, col_type in measurement_columns:
        if not _column_exists(conn, "measurements", col_name):
            conn.execute(f"ALTER TABLE measurements ADD COLUMN {col_name} {col_type}")
            print(f"  Migration: added measurements.{col_name}")

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

    # ── lab_results table (CDS Phase H) ─────────────────────────
    if not _table_exists(conn, "lab_results"):
        conn.execute("""
            CREATE TABLE lab_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                lab_date TEXT NOT NULL,
                lab_name TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT DEFAULT '',
                reference_low REAL,
                reference_high REAL,
                z_score REAL,
                source TEXT DEFAULT 'manual',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lab_results_patient ON lab_results(patient_id, lab_date)")
        print("  Migration: created lab_results table")

    # ── cds_evaluations table (CDS Phase J) ───────────────────
    if not _table_exists(conn, "cds_evaluations"):
        conn.execute("""
            CREATE TABLE cds_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                eval_date TEXT DEFAULT (datetime('now')),
                eval_json TEXT NOT NULL,
                max_tier INTEGER DEFAULT 0,
                categories_flagged TEXT DEFAULT '',
                FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cds_eval_patient ON cds_evaluations(patient_id, eval_date)")
        print("  Migration: created cds_evaluations table")

    conn.commit()
    conn.close()
    print("  Migrations complete.")


if __name__ == "__main__":
    run_migrations()
