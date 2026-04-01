"""Import API — PDF/Excel/folder upload + parse."""
from flask import Blueprint, request, jsonify, current_app

imports_bp = Blueprint("imports", __name__)


@imports_bp.route("/import/pdf", methods=["POST"])
def import_pdf():
    """Upload and parse a PDF file."""
    # Placeholder — will be implemented in Phase 6
    return jsonify({"status": "not_implemented"}), 501


@imports_bp.route("/import/excel", methods=["POST"])
def import_excel():
    """Upload and parse an Excel file."""
    # Placeholder — will be implemented in Phase 7
    return jsonify({"status": "not_implemented"}), 501


@imports_bp.route("/import/folder", methods=["POST"])
def import_folder():
    """Upload multiple files or ZIP for batch import."""
    # Placeholder — will be implemented in Phase 9
    return jsonify({"status": "not_implemented"}), 501


@imports_bp.route("/import/confirm", methods=["POST"])
def confirm_import():
    """Save confirmed import data to database."""
    # Placeholder — will be implemented in Phase 6
    return jsonify({"status": "not_implemented"}), 501
