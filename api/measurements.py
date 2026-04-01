"""Measurement CRUD API endpoints."""
from flask import Blueprint, request, jsonify, current_app
from models import Measurement
from config import Standard, Indicator, zscore_to_percentile
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

    return {
        "id": m.id,
        "patient_id": m.patient_id,
        "date": m.date.isoformat() if m.date else None,
        "height_cm": m.height_cm,
        "weight_kg": m.weight_kg,
        "head_circ_cm": m.head_circ_cm,
        "bmi": round(m.bmi, 2) if m.bmi else None,
        "bone_age_years": getattr(m, "bone_age_years", None),
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
    }


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
        )
        saved.append(db.save_measurement(m))

    return jsonify({"saved": len(saved)}), 201


@measurements_bp.route("/measurements/<int:measurement_id>", methods=["DELETE"])
def delete_measurement(measurement_id):
    db = current_app.db
    db.delete_measurement(measurement_id)
    return jsonify({"ok": True})
