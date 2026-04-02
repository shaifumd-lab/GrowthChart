"""SQLite database layer for patient and measurement storage."""
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional
from models import Patient, Measurement
from config import DB_PATH


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path = DB_PATH):
    """Create database tables if they don't exist."""
    conn = get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            birth_date TEXT,
            sex TEXT NOT NULL DEFAULT 'M',
            medical_record_number TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            height_cm REAL,
            weight_kg REAL,
            head_circ_cm REAL,
            notes TEXT DEFAULT '',
            source_pdf TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_measurements_patient
            ON measurements(patient_id, date);
    """)
    conn.commit()
    conn.close()


# ── Patient CRUD ──────────────────────────────────────────────

def save_patient(patient: Patient, db_path: Path = DB_PATH) -> Patient:
    """Insert or update a patient. Returns the patient with its ID set."""
    conn = get_connection(db_path)
    if patient.id is None:
        cur = conn.execute(
            """INSERT INTO patients (first_name, last_name, birth_date, sex,
               medical_record_number, notes,
               mother_height_cm, father_height_cm, mph_cm, mph_user_edited, syndrome,
               gh_start_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient.first_name, patient.last_name,
             patient.birth_date.isoformat() if patient.birth_date else None,
             patient.sex, patient.medical_record_number, patient.notes,
             patient.mother_height_cm, patient.father_height_cm,
             patient.mph_cm, 1 if patient.mph_user_edited else 0,
             patient.syndrome or "",
             patient.gh_start_date.isoformat() if patient.gh_start_date else None)
        )
        patient.id = cur.lastrowid
    else:
        conn.execute(
            """UPDATE patients SET first_name=?, last_name=?, birth_date=?,
               sex=?, medical_record_number=?, notes=?,
               mother_height_cm=?, father_height_cm=?, mph_cm=?,
               mph_user_edited=?, syndrome=?, gh_start_date=?
               WHERE id=?""",
            (patient.first_name, patient.last_name,
             patient.birth_date.isoformat() if patient.birth_date else None,
             patient.sex, patient.medical_record_number, patient.notes,
             patient.mother_height_cm, patient.father_height_cm,
             patient.mph_cm, 1 if patient.mph_user_edited else 0,
             patient.syndrome or "",
             patient.gh_start_date.isoformat() if patient.gh_start_date else None,
             patient.id)
        )
    conn.commit()
    conn.close()
    return patient


def get_patient(patient_id: int, db_path: Path = DB_PATH) -> Optional[Patient]:
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    conn.close()
    if row:
        return _row_to_patient(row)
    return None


def get_all_patients(db_path: Path = DB_PATH) -> List[Patient]:
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM patients ORDER BY last_name, first_name").fetchall()
    conn.close()
    return [_row_to_patient(r) for r in rows]


def search_patients(query: str, db_path: Path = DB_PATH) -> List[Patient]:
    conn = get_connection(db_path)
    like = f"%{query}%"
    rows = conn.execute(
        """SELECT * FROM patients
           WHERE first_name LIKE ? OR last_name LIKE ?
              OR medical_record_number LIKE ?
           ORDER BY last_name, first_name""",
        (like, like, like)
    ).fetchall()
    conn.close()
    return [_row_to_patient(r) for r in rows]


def delete_patient(patient_id: int, db_path: Path = DB_PATH):
    conn = get_connection(db_path)
    conn.execute("DELETE FROM patients WHERE id=?", (patient_id,))
    conn.commit()
    conn.close()


# ── Measurement CRUD ──────────────────────────────────────────

def save_measurement(m: Measurement, db_path: Path = DB_PATH) -> Measurement:
    conn = get_connection(db_path)
    if m.id is None:
        cur = conn.execute(
            """INSERT INTO measurements (patient_id, date, height_cm, weight_kg,
               head_circ_cm, notes, source_pdf, bone_age_years)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (m.patient_id, m.date.isoformat() if m.date else None,
             m.height_cm, m.weight_kg, m.head_circ_cm, m.notes, m.source_pdf,
             m.bone_age_years)
        )
        m.id = cur.lastrowid
    else:
        conn.execute(
            """UPDATE measurements SET patient_id=?, date=?, height_cm=?,
               weight_kg=?, head_circ_cm=?, notes=?, source_pdf=?, bone_age_years=?
               WHERE id=?""",
            (m.patient_id, m.date.isoformat() if m.date else None,
             m.height_cm, m.weight_kg, m.head_circ_cm, m.notes, m.source_pdf,
             m.bone_age_years,
             m.id)
        )
    conn.commit()
    conn.close()
    return m


def save_measurements_batch(measurements: List[Measurement], db_path: Path = DB_PATH):
    """Save multiple measurements in a single transaction."""
    conn = get_connection(db_path)
    for m in measurements:
        if m.id is None:
            cur = conn.execute(
                """INSERT INTO measurements (patient_id, date, height_cm, weight_kg,
                   head_circ_cm, notes, source_pdf, bone_age_years)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (m.patient_id, m.date.isoformat() if m.date else None,
                 m.height_cm, m.weight_kg, m.head_circ_cm, m.notes, m.source_pdf,
                 m.bone_age_years)
            )
            m.id = cur.lastrowid
    conn.commit()
    conn.close()


def get_measurements(patient_id: int, db_path: Path = DB_PATH) -> List[Measurement]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM measurements WHERE patient_id=? ORDER BY date",
        (patient_id,)
    ).fetchall()
    conn.close()
    return [_row_to_measurement(r) for r in rows]


def delete_measurement(measurement_id: int, db_path: Path = DB_PATH):
    conn = get_connection(db_path)
    conn.execute("DELETE FROM measurements WHERE id=?", (measurement_id,))
    conn.commit()
    conn.close()


# ── Helpers ───────────────────────────────────────────────────

def _safe_get(row, key, default=None):
    """Safely get a value from a sqlite3.Row, returning default if column doesn't exist."""
    try:
        val = row[key]
        return val if val is not None else default
    except (IndexError, KeyError):
        return default


def _row_to_patient(row) -> Patient:
    return Patient(
        id=row["id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        birth_date=date.fromisoformat(row["birth_date"]) if row["birth_date"] else None,
        sex=row["sex"],
        medical_record_number=row["medical_record_number"] or "",
        notes=row["notes"] or "",
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        mother_height_cm=_safe_get(row, "mother_height_cm"),
        father_height_cm=_safe_get(row, "father_height_cm"),
        mph_cm=_safe_get(row, "mph_cm"),
        mph_user_edited=bool(_safe_get(row, "mph_user_edited", 0)),
        syndrome=_safe_get(row, "syndrome", "") or "",
        gh_start_date=date.fromisoformat(_safe_get(row, "gh_start_date")) if _safe_get(row, "gh_start_date") else None,
    )


def _row_to_measurement(row) -> Measurement:
    return Measurement(
        id=row["id"],
        patient_id=row["patient_id"],
        date=date.fromisoformat(row["date"]) if row["date"] else None,
        height_cm=row["height_cm"],
        weight_kg=row["weight_kg"],
        head_circ_cm=row["head_circ_cm"],
        notes=row["notes"] or "",
        source_pdf=row["source_pdf"] or "",
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        bone_age_years=_safe_get(row, "bone_age_years"),
    )


# ── Class wrapper for Flask integration ──────────────────────

class Database:
    """Thin OOP wrapper around module-level functions for Flask app context."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def initialize(self):
        init_db(self.db_path)

    def save_patient(self, patient: Patient) -> Patient:
        return save_patient(patient, self.db_path)

    def get_patient(self, patient_id: int) -> Optional[Patient]:
        return get_patient(patient_id, self.db_path)

    def get_all_patients(self) -> List[Patient]:
        return get_all_patients(self.db_path)

    def search_patients(self, query: str) -> List[Patient]:
        return search_patients(query, self.db_path)

    def delete_patient(self, patient_id: int):
        delete_patient(patient_id, self.db_path)

    def save_measurement(self, m: Measurement) -> Measurement:
        return save_measurement(m, self.db_path)

    def save_measurements_batch(self, measurements: List[Measurement]):
        save_measurements_batch(measurements, self.db_path)

    def get_measurements(self, patient_id: int) -> List[Measurement]:
        return get_measurements(patient_id, self.db_path)

    def delete_measurement(self, measurement_id: int):
        delete_measurement(measurement_id, self.db_path)
