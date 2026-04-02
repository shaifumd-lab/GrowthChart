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
    _patient_fields = """first_name, last_name, birth_date, sex,
               medical_record_number, notes,
               mother_height_cm, father_height_cm, mph_cm, mph_user_edited, syndrome,
               gh_start_date,
               gestational_age_weeks, birth_weight_g, birth_length_cm,
               birth_head_circ_cm, sga_flag"""

    def _patient_values(p):
        return (
            p.first_name, p.last_name,
            p.birth_date.isoformat() if p.birth_date else None,
            p.sex, p.medical_record_number, p.notes,
            p.mother_height_cm, p.father_height_cm,
            p.mph_cm, 1 if p.mph_user_edited else 0,
            p.syndrome or "",
            p.gh_start_date.isoformat() if p.gh_start_date else None,
            p.gestational_age_weeks, p.birth_weight_g, p.birth_length_cm,
            p.birth_head_circ_cm, 1 if p.sga_flag else (0 if p.sga_flag is not None else None),
        )

    if patient.id is None:
        placeholders = ", ".join(["?"] * 17)
        cur = conn.execute(
            f"INSERT INTO patients ({_patient_fields}) VALUES ({placeholders})",
            _patient_values(patient)
        )
        patient.id = cur.lastrowid
    else:
        set_clause = ", ".join(f"{f.strip()}=?" for f in _patient_fields.split(","))
        conn.execute(
            f"UPDATE patients SET {set_clause} WHERE id=?",
            _patient_values(patient) + (patient.id,)
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
    _meas_fields = """patient_id, date, height_cm, weight_kg,
               head_circ_cm, notes, source_pdf, bone_age_years,
               tanner_breast, tanner_pubic_hair, tanner_genital, testicular_volume,
               bp_systolic, bp_diastolic,
               sitting_height_cm, arm_span_cm, waist_circumference_cm"""

    def _meas_values(m):
        return (
            m.patient_id, m.date.isoformat() if m.date else None,
            m.height_cm, m.weight_kg, m.head_circ_cm, m.notes, m.source_pdf,
            m.bone_age_years,
            m.tanner_breast, m.tanner_pubic_hair, m.tanner_genital, m.testicular_volume,
            m.bp_systolic, m.bp_diastolic,
            m.sitting_height_cm, m.arm_span_cm, m.waist_circumference_cm,
        )

    if m.id is None:
        placeholders = ", ".join(["?"] * 17)
        cur = conn.execute(
            f"INSERT INTO measurements ({_meas_fields}) VALUES ({placeholders})",
            _meas_values(m)
        )
        m.id = cur.lastrowid
    else:
        set_clause = ", ".join(f"{f.strip()}=?" for f in _meas_fields.split(","))
        conn.execute(
            f"UPDATE measurements SET {set_clause} WHERE id=?",
            _meas_values(m) + (m.id,)
        )
    conn.commit()
    conn.close()
    return m


def save_measurements_batch(measurements: List[Measurement], db_path: Path = DB_PATH):
    """Save multiple measurements in a single transaction."""
    conn = get_connection(db_path)
    _meas_fields = """patient_id, date, height_cm, weight_kg,
               head_circ_cm, notes, source_pdf, bone_age_years,
               tanner_breast, tanner_pubic_hair, tanner_genital, testicular_volume,
               bp_systolic, bp_diastolic,
               sitting_height_cm, arm_span_cm, waist_circumference_cm"""
    placeholders = ", ".join(["?"] * 17)
    for m in measurements:
        if m.id is None:
            vals = (
                m.patient_id, m.date.isoformat() if m.date else None,
                m.height_cm, m.weight_kg, m.head_circ_cm, m.notes, m.source_pdf,
                m.bone_age_years,
                m.tanner_breast, m.tanner_pubic_hair, m.tanner_genital, m.testicular_volume,
                m.bp_systolic, m.bp_diastolic,
                m.sitting_height_cm, m.arm_span_cm, m.waist_circumference_cm,
            )
            cur = conn.execute(
                f"INSERT INTO measurements ({_meas_fields}) VALUES ({placeholders})", vals
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
        gestational_age_weeks=_safe_get(row, "gestational_age_weeks"),
        birth_weight_g=_safe_get(row, "birth_weight_g"),
        birth_length_cm=_safe_get(row, "birth_length_cm"),
        birth_head_circ_cm=_safe_get(row, "birth_head_circ_cm"),
        sga_flag=bool(_safe_get(row, "sga_flag")) if _safe_get(row, "sga_flag") is not None else None,
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
        tanner_breast=_safe_get(row, "tanner_breast"),
        tanner_pubic_hair=_safe_get(row, "tanner_pubic_hair"),
        tanner_genital=_safe_get(row, "tanner_genital"),
        testicular_volume=_safe_get(row, "testicular_volume"),
        bp_systolic=_safe_get(row, "bp_systolic"),
        bp_diastolic=_safe_get(row, "bp_diastolic"),
        sitting_height_cm=_safe_get(row, "sitting_height_cm"),
        arm_span_cm=_safe_get(row, "arm_span_cm"),
        waist_circumference_cm=_safe_get(row, "waist_circumference_cm"),
    )


# ── Lab Results CRUD ─────────────────────────────────────────

def save_lab_result(lab: dict, db_path: Path = DB_PATH) -> int:
    conn = get_connection(db_path)
    cur = conn.execute(
        """INSERT INTO lab_results (patient_id, lab_date, lab_name, value, unit,
           reference_low, reference_high, z_score, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (lab["patient_id"], lab["lab_date"], lab["lab_name"], lab["value"],
         lab.get("unit", ""), lab.get("reference_low"), lab.get("reference_high"),
         lab.get("z_score"), lab.get("source", "manual"))
    )
    lab_id = cur.lastrowid
    conn.commit()
    conn.close()
    return lab_id


def get_lab_results(patient_id: int, db_path: Path = DB_PATH) -> List[dict]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM lab_results WHERE patient_id=? ORDER BY lab_date DESC, lab_name",
        (patient_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_lab_result(lab_id: int, db_path: Path = DB_PATH):
    conn = get_connection(db_path)
    conn.execute("DELETE FROM lab_results WHERE id=?", (lab_id,))
    conn.commit()
    conn.close()


# ── CDS Evaluations CRUD ────────────────────────────────────

def save_cds_evaluation(patient_id: int, eval_json: str, max_tier: int,
                        categories: str, db_path: Path = DB_PATH) -> int:
    conn = get_connection(db_path)
    cur = conn.execute(
        """INSERT INTO cds_evaluations (patient_id, eval_json, max_tier, categories_flagged)
           VALUES (?, ?, ?, ?)""",
        (patient_id, eval_json, max_tier, categories)
    )
    eval_id = cur.lastrowid
    conn.commit()
    conn.close()
    return eval_id


def get_cds_evaluations(patient_id: int, limit: int = 10, db_path: Path = DB_PATH) -> List[dict]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM cds_evaluations WHERE patient_id=? ORDER BY eval_date DESC LIMIT ?",
        (patient_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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

    # Lab results
    def save_lab_result(self, lab: dict) -> int:
        return save_lab_result(lab, self.db_path)

    def get_lab_results(self, patient_id: int) -> List[dict]:
        return get_lab_results(patient_id, self.db_path)

    def delete_lab_result(self, lab_id: int):
        delete_lab_result(lab_id, self.db_path)

    # CDS evaluations
    def save_cds_evaluation(self, patient_id: int, eval_json: str, max_tier: int, categories: str) -> int:
        return save_cds_evaluation(patient_id, eval_json, max_tier, categories, self.db_path)

    def get_cds_evaluations(self, patient_id: int, limit: int = 10) -> List[dict]:
        return get_cds_evaluations(patient_id, limit, self.db_path)
