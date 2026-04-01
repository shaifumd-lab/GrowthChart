"""Export API — Elysia PDF + chart PNG generation."""
from flask import Blueprint, request, jsonify, current_app

exports_bp = Blueprint("exports", __name__)


@exports_bp.route("/export/elysia/<int:patient_id>", methods=["GET"])
def export_elysia_pdf(patient_id):
    """Generate Elysia branded PDF for patient."""
    # Placeholder — will be implemented in Phase 10
    return jsonify({"status": "not_implemented"}), 501


@exports_bp.route("/export/chart-png", methods=["GET"])
def export_chart_png():
    """Generate chart PNG with informative filename."""
    # Placeholder — will be implemented in Phase 10
    return jsonify({"status": "not_implemented"}), 501
