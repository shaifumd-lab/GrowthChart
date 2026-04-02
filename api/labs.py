"""
Lab Results API — CRUD for laboratory results and HOMA-IR trend.

Endpoints:
  GET    /api/patient/<id>/labs      — Get all lab results for a patient
  POST   /api/patient/<id>/labs      — Add a lab result
  DELETE /api/labs/<id>              — Delete a lab result
  GET    /api/patient/<id>/homa-trend — Get HOMA-IR trend data for charting
"""

from flask import Blueprint, request, jsonify, current_app
from datetime import date

labs_bp = Blueprint("labs", __name__)


@labs_bp.route("/patient/<int:patient_id>/labs", methods=["GET"])
def get_labs(patient_id):
    """Get all lab results for a patient."""
    db = current_app.db
    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    labs = db.get_lab_results(patient_id)
    return jsonify({"labs": labs})


@labs_bp.route("/patient/<int:patient_id>/labs", methods=["POST"])
def add_lab(patient_id):
    """Add a lab result."""
    db = current_app.db
    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required = ["lab_name", "value", "lab_date"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    lab = {
        "patient_id": patient_id,
        "lab_name": data["lab_name"],
        "value": float(data["value"]),
        "lab_date": data["lab_date"],
        "unit": data.get("unit", ""),
        "reference_low": data.get("reference_low"),
        "reference_high": data.get("reference_high"),
        "z_score": data.get("z_score"),
        "source": data.get("source", "manual"),
    }

    lab_id = db.save_lab_result(lab)
    return jsonify({"success": True, "id": lab_id})


@labs_bp.route("/labs/<int:lab_id>", methods=["DELETE"])
def delete_lab(lab_id):
    """Delete a lab result."""
    db = current_app.db
    db.delete_lab_result(lab_id)
    return jsonify({"success": True})


@labs_bp.route("/patient/<int:patient_id>/homa-trend", methods=["GET"])
def homa_trend(patient_id):
    """
    Get HOMA-IR trend data for charting.
    Returns dates and HOMA-IR values computed from paired fasting glucose + insulin.
    """
    db = current_app.db
    labs = db.get_lab_results(patient_id)

    # Group by date, find paired glucose + insulin
    by_date = {}
    for lab in labs:
        d = lab.get("lab_date", "")
        name = (lab.get("lab_name") or "").upper()
        val = lab.get("value")
        if not d or val is None:
            continue
        if d not in by_date:
            by_date[d] = {}
        if "GLUCOSE" in name and "FASTING" in name:
            by_date[d]["glucose"] = val
        elif "INSULIN" in name and "FASTING" in name:
            by_date[d]["insulin"] = val

    # Compute HOMA-IR for dates with both values
    trend = []
    for d in sorted(by_date.keys()):
        pair = by_date[d]
        if "glucose" in pair and "insulin" in pair:
            homa = (pair["glucose"] * pair["insulin"]) / 405.0
            trend.append({
                "date": d,
                "homa_ir": round(homa, 2),
                "glucose": pair["glucose"],
                "insulin": pair["insulin"],
            })

    # Build Plotly trace
    trace = None
    if trend:
        trace = {
            "name": "HOMA-IR",
            "x": [t["date"] for t in trend],
            "y": [t["homa_ir"] for t in trend],
            "mode": "lines+markers",
            "line": {"color": "#7C3AED", "width": 2},
            "marker": {"size": 8},
            "hovertemplate": "HOMA-IR: %{y:.2f}<br>Date: %{x}<br><extra></extra>",
        }

    # Threshold line at 3.16
    threshold_line = {
        "type": "line",
        "y0": 3.16, "y1": 3.16,
        "x0": 0, "x1": 1, "xref": "paper",
        "line": {"color": "#DC2626", "width": 1.5, "dash": "dash"},
    }

    return jsonify({
        "trend": trend,
        "trace": trace,
        "threshold_line": threshold_line,
        "threshold_value": 3.16,
    })
