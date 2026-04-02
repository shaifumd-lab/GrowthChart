"""Measurement CRUD API endpoints."""
from flask import Blueprint, request, jsonify, current_app
from models import Measurement
from config import Standard, Indicator, zscore_to_percentile
from clinical.bayley_pinneau import predict_adult_height
from database import get_connection
from datetime import datetime, date

measurements_bp = Blueprint("measurements", __name__)


def _enrich_measurement(m: Measurement, patient_birth_date, sex, engine, standard) -> dict:
    """Compute age, BMI, z-scores and return dict."""
    if patient_birth_date and m.date:
        m.compute_age(patient_birth_date)
    m.compute_bmi()

    for indicator, val_attr, z_attr, p_attr in [
        (Indicator.HEIGHT_FOR_AGE, "height_cm", "height_zscore", "height_percentile"),
        (Indicator.WEIGHT_FOR_AGE, "weight_kg", "weight_zscore", "weight_percentile"),
        (Indicator.BMI_FOR_AGE, "bmi", "bmi_zscore", "bmi_percentile"),
    ]:
        val = getattr(m, val_attr, None)
        if val and m.age_months and m.age_months > 0:
            z = engine.compute_zscore(val, m.age_months, sex, indicator, standard)
            setattr(m, z_attr, z)
            if z is not None:
                setattr(m, p_attr, round(zscore_to_percentile(z), 1))

    result = {
        "id": m.id,
        "patient_id": m.patient_id,
        "date": m.date.isoformat() if m.date else None,
        "height_cm": m.height_cm,
        "weight_kg": m.weight_kg,
        "head_circ_cm": m.head_circ_cm,
        "bmi": round(m.bmi, 2) if m.bmi else None,
        "bone_age_years": m.bone_age_years,
        "age_months": round(m.age_months, 1) if m.age_months else None,
        "age_str": m.age_str if m.age_months else "",
        "height_zscore": round(m.height_zscore, 2) if m.height_zscore is not None else None,
        "weight_zscore": round(m.weight_zscore, 2) if m.weight_zscore is not None else None,
        "bmi_zscore": round(m.bmi_zscore, 2) if m.bmi_zscore is not None else None,
        "height_percentile": m.height_percentile,
        "weight_percentile": m.weight_percentile,
        "bmi_percentile": m.bmi_percentile,
        "notes": m.notes,
        "source_pdf": m.source_pdf,
        "pah": None,
    }
    # Compute PAH if bone age and height are available
    if m.bone_age_years and m.height_cm and sex:
        pah_result = predict_adult_height(m.height_cm, m.bone_age_years, sex)
        if pah_result:
            result["pah"] = pah_result["pah"]
            result["pah_range"] = pah_result["confidence_range"]
    return result


@measurements_bp.route("/patients/<int:patient_id>/measurements", methods=["GET"])
def get_measurements(patient_id):
    db = current_app.db
    engine = current_app.engine
    standard = request.args.get("standard", "CDC")

    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    measurements = db.get_measurements(patient_id)
    result = []
    for m in measurements:
        result.append(_enrich_measurement(m, patient.birth_date, patient.sex, engine, standard))

    # Compute height velocity (cm/year) between consecutive measurements >= 6 months apart
    for i, r in enumerate(result):
        r["velocity"] = None
        if i == 0 or r["height_cm"] is None or r["age_months"] is None:
            continue
        # Find the most recent prior measurement with height, at least 6 months earlier
        for j in range(i - 1, -1, -1):
            prev = result[j]
            if prev["height_cm"] is None or prev["age_months"] is None:
                continue
            delta_months = r["age_months"] - prev["age_months"]
            if delta_months >= 6:
                delta_years = delta_months / 12.0
                r["velocity"] = round((r["height_cm"] - prev["height_cm"]) / delta_years, 1)
                break

    return jsonify(result)


@measurements_bp.route("/patients/<int:patient_id>/measurements", methods=["POST"])
def add_measurements(patient_id):
    db = current_app.db
    data = request.json

    # Support single measurement or array
    items = data if isinstance(data, list) else [data]

    saved = []
    for item in items:
        m = Measurement(
            patient_id=patient_id,
            date=datetime.strptime(item["date"], "%Y-%m-%d").date() if item.get("date") else None,
            height_cm=item.get("height_cm"),
            weight_kg=item.get("weight_kg"),
            head_circ_cm=item.get("head_circ_cm"),
            notes=item.get("notes", ""),
            source_pdf=item.get("source_pdf", ""),
            bone_age_years=_to_float(item.get("bone_age_years")),
        )
        saved.append(db.save_measurement(m))

    return jsonify({"saved": len(saved)}), 201


@measurements_bp.route("/measurements/<int:measurement_id>", methods=["PUT"])
def update_measurement(measurement_id):
    """Update a single measurement (partial update — only supplied fields change)."""
    import traceback
    try:
        db = current_app.db
        engine = current_app.engine
        data = request.json

        # Fetch all measurements for the patient that owns this measurement
        conn = get_connection(db.db_path)
        row = conn.execute("SELECT * FROM measurements WHERE id=?", (measurement_id,)).fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "Measurement not found"}), 404

        # Build Measurement from existing row
        m = Measurement(id=row["id"], patient_id=row["patient_id"])
        m.date = datetime.strptime(row["date"], "%Y-%m-%d").date() if row["date"] else None
        m.height_cm = row["height_cm"]
        m.weight_kg = row["weight_kg"]
        m.head_circ_cm = row["head_circ_cm"] if "head_circ_cm" in row.keys() else None
        m.bone_age_years = row["bone_age_years"] if "bone_age_years" in row.keys() else None
        m.notes = row["notes"] if "notes" in row.keys() else ""
        m.source_pdf = row["source_pdf"] if "source_pdf" in row.keys() else ""
        for fld in ["tanner_breast", "tanner_pubic_hair", "tanner_genital", "testicular_volume",
                     "bp_systolic", "bp_diastolic", "sitting_height_cm", "arm_span_cm", "waist_circumference_cm"]:
            if fld in row.keys():
                setattr(m, fld, row[fld])

        # Apply partial update
        if "date" in data and data["date"]:
            m.date = datetime.strptime(data["date"], "%Y-%m-%d").date()
        if "height_cm" in data:
            m.height_cm = _to_float(data["height_cm"])
        if "weight_kg" in data:
            m.weight_kg = _to_float(data["weight_kg"])
        if "bone_age_years" in data:
            m.bone_age_years = _to_float(data["bone_age_years"])
        if "head_circ_cm" in data:
            m.head_circ_cm = _to_float(data["head_circ_cm"])
        if "notes" in data:
            m.notes = data["notes"]

        db.save_measurement(m)

        # Return enriched measurement
        patient = db.get_patient(m.patient_id)
        standard = request.args.get("standard", "CDC")
        result = _enrich_measurement(m, patient.birth_date if patient else None, patient.sex if patient else "M", engine, standard)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@measurements_bp.route("/measurements/<int:measurement_id>", methods=["DELETE"])
def delete_measurement(measurement_id):
    db = current_app.db
    db.delete_measurement(measurement_id)
    return jsonify({"ok": True})


def _to_float(val) -> float:
    """Safely convert a value to float, returning None for empty/invalid."""
    if val is None or val == "" or val == "null":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
