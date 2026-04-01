"""Export API — Elysia PDF + chart PNG generation."""
import io
from flask import Blueprint, request, jsonify, current_app, send_file

exports_bp = Blueprint("exports", __name__)


@exports_bp.route("/export/elysia/<int:patient_id>", methods=["GET"])
def export_elysia_pdf(patient_id):
    """Generate Elysia branded PDF for patient and return as file download."""
    from exports.elysia_pdf import generate_elysia_pdf

    db = current_app.db
    engine = current_app.engine

    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    measurements = db.get_measurements(patient_id)
    standard = request.args.get("standard", "CDC")
    font_scale = float(request.args.get("font_scale", "1.0"))

    try:
        pdf_bytes = generate_elysia_pdf(
            patient=patient,
            measurements=measurements,
            engine=engine,
            standard=standard,
            font_scale=font_scale,
        )
    except Exception as e:
        return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500

    # Build filename
    name = f"{patient.first_name}_{patient.last_name}".strip("_") or "patient"
    filename = f"{name}_Elysia_{standard}.pdf"

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@exports_bp.route("/export/chart-png", methods=["GET"])
def export_chart_png():
    """Generate chart PNG with informative filename and return as file download."""
    from exports.chart_png import generate_chart_png, get_chart_filename

    db = current_app.db
    engine = current_app.engine

    patient_id = request.args.get("patient_id", type=int)
    if not patient_id:
        return jsonify({"error": "patient_id is required"}), 400

    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    measurements = db.get_measurements(patient_id)
    indicator = request.args.get("indicator", "hfa")
    standard = request.args.get("standard", "CDC")
    font_scale = float(request.args.get("font_scale", "1.0"))

    try:
        png_bytes = generate_chart_png(
            patient=patient,
            measurements=measurements,
            engine=engine,
            indicator=indicator,
            standard=standard,
            font_scale=font_scale,
        )
    except Exception as e:
        return jsonify({"error": f"PNG generation failed: {str(e)}"}), 500

    filename = get_chart_filename(patient, indicator, standard)

    return send_file(
        io.BytesIO(png_bytes),
        mimetype="image/png",
        as_attachment=True,
        download_name=filename,
    )
