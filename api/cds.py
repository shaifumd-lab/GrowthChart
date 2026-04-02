"""
CDS API — Clinical Decision Support endpoint.

GET /api/patient/<id>/cds — Returns tier assessment for a patient.
"""

import json
from flask import Blueprint, request, jsonify, current_app
from cds.engine import evaluate_patient
from cds.metrics import build_patient_metrics
from clinical.velocity import compute_velocity
from clinical.bayley_pinneau import predict_adult_height
from config import Standard

cds_bp = Blueprint("cds", __name__)


def _build_z_scores(patient, measurements, engine, standard):
    """Build z-score list from measurements for CDS metrics."""
    z_scores = []
    for m in measurements:
        if not m.date or not patient.birth_date:
            continue
        age_days = (m.date - patient.birth_date).days
        age_months = age_days / 30.4375

        entry = {"age_months": age_months, "date": m.date.isoformat()}

        if m.height_cm:
            z = engine.compute_zscore(m.height_cm, age_months, patient.sex, "hfa", standard)
            entry["height_z"] = z
        if m.weight_kg:
            z = engine.compute_zscore(m.weight_kg, age_months, patient.sex, "wfa", standard)
            entry["weight_z"] = z
        if m.height_cm and m.weight_kg and m.height_cm > 0:
            bmi = m.weight_kg / ((m.height_cm / 100) ** 2)
            z = engine.compute_zscore(bmi, age_months, patient.sex, "bfa", standard)
            entry["bmi_z"] = z

        z_scores.append(entry)

    return z_scores


@cds_bp.route("/patient/<int:patient_id>/cds", methods=["GET"])
def get_cds(patient_id):
    """Return CDS tier assessment for a patient."""
    db = current_app.db
    engine = current_app.engine
    standard = request.args.get("standard", "CDC")

    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    measurements = db.get_measurements(patient_id)
    labs = db.get_lab_results(patient_id)

    # Build z-scores
    z_scores = _build_z_scores(patient, measurements, engine, standard)

    # Build velocities
    meas_dicts = [{"date": m.date.isoformat() if m.date else None, "height_cm": m.height_cm}
                  for m in measurements]
    velocities = compute_velocity(meas_dicts, patient.birth_date) if patient.birth_date else []

    # Get PAH if bone age available
    pah_cm = None
    for m in reversed(measurements):
        ba = getattr(m, "bone_age_years", None)
        if ba and m.height_cm:
            bp_result = predict_adult_height(m.height_cm, ba, patient.sex)
            if bp_result:
                pah_cm = bp_result.get("pah")
            break

    # Build patient dict for CDS
    patient_dict = {
        "sex": patient.sex,
        "sga_flag": patient.sga_flag,
        "effective_mph": patient.effective_mph,
        "latest_tanner": {},
        "latest_measurement": {},
    }

    # Get latest Tanner staging
    for m in reversed(measurements):
        t = {}
        if getattr(m, "tanner_breast", None):
            t["tanner_breast"] = m.tanner_breast
        if getattr(m, "tanner_genital", None):
            t["tanner_genital"] = m.tanner_genital
        if getattr(m, "tanner_pubic_hair", None):
            t["tanner_pubic_hair"] = m.tanner_pubic_hair
        if t:
            patient_dict["latest_tanner"] = t
            break

    # Latest measurement for disproportion check
    if measurements:
        lm = measurements[-1]
        patient_dict["latest_measurement"] = {
            "height_cm": lm.height_cm,
            "sitting_height_cm": getattr(lm, "sitting_height_cm", None),
            "arm_span_cm": getattr(lm, "arm_span_cm", None),
        }

    # Build metrics
    meas_dicts_full = []
    for m in measurements:
        md = {
            "date": m.date.isoformat() if m.date else None,
            "height_cm": m.height_cm,
            "weight_kg": m.weight_kg,
            "bone_age_years": getattr(m, "bone_age_years", None),
            "age_months": (m.date - patient.birth_date).days / 30.4375 if m.date and patient.birth_date else None,
        }
        meas_dicts_full.append(md)

    metrics = build_patient_metrics(
        patient=patient_dict,
        measurements=meas_dicts_full,
        z_scores=z_scores,
        velocities=velocities,
        labs=labs,
        pah_cm=pah_cm,
    )

    # Run CDS engine
    cds_result = evaluate_patient(metrics, patient_dict)

    # Save to audit trail
    try:
        eval_json = json.dumps(cds_result, default=str)
        db.save_cds_evaluation(
            patient_id=patient_id,
            eval_json=eval_json,
            max_tier=cds_result.get("max_tier", 0),
            categories=",".join(cds_result.get("categories_flagged", [])),
        )
    except Exception:
        pass  # Audit trail failure should not block CDS response

    return jsonify(cds_result)
