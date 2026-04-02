"""Patient CRUD API endpoints."""
from flask import Blueprint, request, jsonify, current_app
from models import Patient
from datetime import datetime

patients_bp = Blueprint("patients", __name__)


def _patient_to_dict(p: Patient) -> dict:
    """Convert Patient to JSON-serializable dict."""
    result = {
        "id": p.id,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "full_name": f"{p.first_name} {p.last_name}".strip(),
        "birth_date": p.birth_date.isoformat() if p.birth_date else None,
        "sex": p.sex,
        "medical_record_number": p.medical_record_number,
        "israeli_id": getattr(p, "israeli_id", ""),
        "notes": p.notes,
        "created_at": p.created_at,
        "age_str": p.age_str if p.birth_date else "",
        # Phase 12-16 additions
        "mother_height_cm": p.mother_height_cm,
        "father_height_cm": p.father_height_cm,
        "mph_cm": p.mph_cm,
        "mph_user_edited": p.mph_user_edited,
        "mph_calculated": round(p.mph_calculated, 1) if p.mph_calculated is not None else None,
        "effective_mph": round(p.effective_mph, 1) if p.effective_mph is not None else None,
        "syndrome": p.syndrome or "",
        "gh_start_date": p.gh_start_date.isoformat() if p.gh_start_date else None,
    }
    # Target height range
    thr = p.target_height_range
    if thr:
        result["target_height_range"] = {"low": round(thr[0], 1), "high": round(thr[1], 1)}
    else:
        result["target_height_range"] = None
    return result


@patients_bp.route("/patients", methods=["GET"])
def list_patients():
    db = current_app.db
    patients = db.get_all_patients()
    return jsonify([_patient_to_dict(p) for p in patients])


@patients_bp.route("/patients/search", methods=["GET"])
def search_patients():
    q = request.args.get("q", "")
    db = current_app.db
    patients = db.search_patients(q) if q else db.get_all_patients()
    return jsonify([_patient_to_dict(p) for p in patients])


@patients_bp.route("/patients/<int:patient_id>", methods=["GET"])
def get_patient(patient_id):
    db = current_app.db
    p = db.get_patient(patient_id)
    if not p:
        return jsonify({"error": "Patient not found"}), 404
    return jsonify(_patient_to_dict(p))


@patients_bp.route("/patients", methods=["POST"])
def create_patient():
    data = request.json
    db = current_app.db
    p = Patient(
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        birth_date=datetime.strptime(data["birth_date"], "%Y-%m-%d").date()
        if data.get("birth_date")
        else None,
        sex=data.get("sex", "M"),
        medical_record_number=data.get("medical_record_number", ""),
        notes=data.get("notes", ""),
        mother_height_cm=_to_float(data.get("mother_height_cm")),
        father_height_cm=_to_float(data.get("father_height_cm")),
        mph_cm=_to_float(data.get("mph_cm")),
        mph_user_edited=bool(data.get("mph_user_edited", False)),
        syndrome=data.get("syndrome", ""),
        gh_start_date=datetime.strptime(data["gh_start_date"], "%Y-%m-%d").date()
        if data.get("gh_start_date") else None,
    )
    saved = db.save_patient(p)
    return jsonify(_patient_to_dict(saved)), 201


@patients_bp.route("/patients/<int:patient_id>", methods=["PUT"])
def update_patient(patient_id):
    data = request.json
    db = current_app.db
    p = db.get_patient(patient_id)
    if not p:
        return jsonify({"error": "Patient not found"}), 404

    if "first_name" in data:
        p.first_name = data["first_name"]
    if "last_name" in data:
        p.last_name = data["last_name"]
    if "birth_date" in data:
        p.birth_date = (
            datetime.strptime(data["birth_date"], "%Y-%m-%d").date()
            if data["birth_date"]
            else None
        )
    if "sex" in data:
        p.sex = data["sex"]
    if "medical_record_number" in data:
        p.medical_record_number = data["medical_record_number"]
    if "notes" in data:
        p.notes = data["notes"]
    # Phase 12-16 fields
    if "mother_height_cm" in data:
        p.mother_height_cm = _to_float(data["mother_height_cm"])
    if "father_height_cm" in data:
        p.father_height_cm = _to_float(data["father_height_cm"])
    if "mph_cm" in data:
        p.mph_cm = _to_float(data["mph_cm"])
    if "mph_user_edited" in data:
        p.mph_user_edited = bool(data["mph_user_edited"])
    if "syndrome" in data:
        p.syndrome = data["syndrome"] or ""
    if "gh_start_date" in data:
        p.gh_start_date = (
            datetime.strptime(data["gh_start_date"], "%Y-%m-%d").date()
            if data["gh_start_date"]
            else None
        )

    saved = db.save_patient(p)
    return jsonify(_patient_to_dict(saved))


@patients_bp.route("/patients/<int:patient_id>", methods=["DELETE"])
def delete_patient(patient_id):
    db = current_app.db
    db.delete_patient(patient_id)
    return jsonify({"ok": True})


def _to_float(val) -> float:
    """Safely convert a value to float, returning None for empty/invalid."""
    if val is None or val == "" or val == "null":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
