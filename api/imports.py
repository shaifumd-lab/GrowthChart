"""
Import API — PDF/Excel/folder upload + parse + confirm.

Endpoints:
  POST /api/import/pdf      — Upload and parse a single PDF
  POST /api/import/excel    — Upload and parse an Excel/CSV file
  POST /api/import/folder   — Upload multiple files / ZIP for batch import
  POST /api/import/confirm  — Save confirmed import data to database
"""

import uuid
from datetime import date
from pathlib import Path

from flask import Blueprint, request, jsonify, current_app
from config import UPLOAD_FOLDER

from importers.pdf_extractor import ValidatedPDFExtractor
from importers.excel_importer import ExcelImporter
from importers.folder_importer import FolderImporter
from importers.patient_matcher import PatientMatcher
from importers.image_extractor import ImageExtractor, is_image_file, SUPPORTED_IMAGE_EXTENSIONS
from importers.chart_detector import ChartPointDetector
from models import Patient, Measurement


imports_bp = Blueprint("imports", __name__)


def _save_upload(file_storage, subfolder: str = "") -> str:
    """
    Save an uploaded file to UPLOAD_FOLDER with a unique name.
    Returns the absolute path to the saved file.
    """
    upload_dir = UPLOAD_FOLDER / subfolder if subfolder else UPLOAD_FOLDER
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename to prevent collisions
    original_name = file_storage.filename or "upload"
    stem = Path(original_name).stem
    ext = Path(original_name).suffix
    unique_name = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
    save_path = upload_dir / unique_name
    file_storage.save(str(save_path))
    return str(save_path)


# ── POST /api/import/pdf ──────────────────────────────────────

@imports_bp.route("/import/pdf", methods=["POST"])
def import_pdf():
    """
    Upload and parse a PDF file.

    Form data:
        file: PDF file (multipart)
        patient_birth_date (optional): YYYY-MM-DD for age validation

    Returns JSON:
        {success, patient, measurements, parental_heights, bone_age_years,
         source_file, warnings, raw_measurement_count, validated_measurement_count}
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext != ".pdf":
        return jsonify({"success": False, "error": f"Expected PDF file, got {ext}"}), 400

    # Parse optional birth date
    birth_date = None
    bd_str = request.form.get("patient_birth_date")
    if bd_str:
        try:
            birth_date = date.fromisoformat(bd_str)
        except ValueError:
            return jsonify({"success": False, "error": f"Invalid birth date: {bd_str}"}), 400

    try:
        saved_path = _save_upload(file, subfolder="pdf")
        extractor = ValidatedPDFExtractor()
        result = extractor.extract(saved_path, patient_birth_date=birth_date)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": f"PDF import failed: {str(e)}"}), 500


# ── POST /api/import/image ───────────────────────────────────

@imports_bp.route("/import/image", methods=["POST"])
def import_image():
    """
    Upload and parse an image file using OCR.

    Accepts: .jpg, .jpeg, .png, .bmp, .tiff, .tif
    Uses Tesseract OCR (Hebrew + English) → same extraction pipeline as PDF.

    Form data:
        file: Image file (multipart)
        patient_birth_date (optional): YYYY-MM-DD for age validation

    Returns JSON: same structure as /import/pdf
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": f"Unsupported image type: {ext}. Expected: {', '.join(SUPPORTED_IMAGE_EXTENSIONS)}"
        }), 400

    birth_date = None
    bd_str = request.form.get("patient_birth_date")
    if bd_str:
        try:
            birth_date = date.fromisoformat(bd_str)
        except ValueError:
            return jsonify({"success": False, "error": f"Invalid birth date: {bd_str}"}), 400

    try:
        saved_path = _save_upload(file, subfolder="images")
        extractor = ImageExtractor()
        result = extractor.extract(saved_path, patient_birth_date=birth_date)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": f"Image import failed: {str(e)}"}), 500


# ── POST /api/import/chart-detect ─────────────────────────────

@imports_bp.route("/import/chart-detect", methods=["POST"])
def import_chart_detect():
    """
    Auto-detect data points on a growth chart image using OpenCV.

    Form data:
        file: Chart image (multipart)
        cal_x1_px, cal_x1_val: First X calibration point (pixel, age)
        cal_x2_px, cal_x2_val: Second X calibration point
        cal_y1_py, cal_y1_val: First Y calibration point (pixel, value)
        cal_y2_py, cal_y2_val: Second Y calibration point

    Returns JSON:
        {success, points: [{px, py, color}], message}
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    # Parse calibration data
    try:
        cal = {
            "cal_x1_px": float(request.form["cal_x1_px"]),
            "cal_x1_val": float(request.form["cal_x1_val"]),
            "cal_x2_px": float(request.form["cal_x2_px"]),
            "cal_x2_val": float(request.form["cal_x2_val"]),
            "cal_y1_py": float(request.form["cal_y1_py"]),
            "cal_y1_val": float(request.form["cal_y1_val"]),
            "cal_y2_py": float(request.form["cal_y2_py"]),
            "cal_y2_val": float(request.form["cal_y2_val"]),
        }
    except (KeyError, ValueError) as e:
        return jsonify({"success": False, "error": f"Missing or invalid calibration data: {e}"}), 400

    try:
        saved_path = _save_upload(file, subfolder="chart_images")
        detector = ChartPointDetector()
        result = detector.detect(saved_path, **cal)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": f"Chart detection failed: {str(e)}"}), 500


# ── POST /api/import/excel ────────────────────────────────────

@imports_bp.route("/import/excel", methods=["POST"])
def import_excel():
    """
    Upload and analyze an Excel/CSV file.

    Form data:
        file: Excel or CSV file (multipart)
        sheet_name (optional): specific sheet to analyze

    Returns JSON:
        {success, file_path, file_type, sheets, active_sheet,
         column_mapping, column_headers, preview_rows,
         total_data_rows, detected_units, warnings}
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    # Validate extension
    ext = Path(file.filename).suffix.lower()
    allowed = {'.xlsx', '.xls', '.csv', '.tsv', '.txt'}
    if ext not in allowed:
        return jsonify({
            "success": False,
            "error": f"Unsupported file type: {ext}. Expected: {', '.join(allowed)}"
        }), 400

    sheet_name = request.form.get("sheet_name")

    try:
        saved_path = _save_upload(file, subfolder="excel")
        importer = ExcelImporter()
        result = importer.analyze(saved_path, sheet_name=sheet_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": f"Excel import failed: {str(e)}"}), 500


# ── POST /api/import/folder ───────────────────────────────────

@imports_bp.route("/import/folder", methods=["POST"])
def import_folder():
    """
    Upload multiple files or a ZIP for batch import.

    Form data:
        files: one or more files (multipart, field name "files")
        mode: "same_patient" or "auto_detect" (default: "auto_detect")
        patient_id (optional): required if mode=same_patient
        patient_birth_date (optional): YYYY-MM-DD for validation

    Returns JSON:
        {success, mode, groups: [...], skipped_files, warnings,
         total_files, total_measurements}
    """
    if "files" not in request.files:
        return jsonify({"success": False, "error": "No files uploaded"}), 400

    files = request.files.getlist("files")
    if not files or not any(f.filename for f in files):
        return jsonify({"success": False, "error": "No valid files uploaded"}), 400

    mode = request.form.get("mode", "auto_detect")
    if mode not in ("same_patient", "auto_detect"):
        return jsonify({"success": False, "error": f"Invalid mode: {mode}"}), 400

    patient_id = None
    if mode == "same_patient":
        pid_str = request.form.get("patient_id")
        if not pid_str:
            return jsonify({
                "success": False,
                "error": "patient_id is required for same_patient mode"
            }), 400
        try:
            patient_id = int(pid_str)
        except ValueError:
            return jsonify({"success": False, "error": "Invalid patient_id"}), 400

    birth_date = None
    bd_str = request.form.get("patient_birth_date")
    if bd_str:
        try:
            birth_date = date.fromisoformat(bd_str)
        except ValueError:
            pass

    try:
        # Save all uploaded files
        saved_paths = []
        for f in files:
            if f.filename:
                saved_path = _save_upload(f, subfolder="batch")
                saved_paths.append(saved_path)

        db = current_app.db
        importer = FolderImporter(db=db)
        result = importer.process(
            file_paths=saved_paths,
            mode=mode,
            patient_id=patient_id,
            patient_birth_date=birth_date,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": f"Folder import failed: {str(e)}"}), 500


# ── POST /api/import/confirm ──────────────────────────────────

@imports_bp.route("/import/confirm", methods=["POST"])
def confirm_import():
    """
    Save confirmed import data to the database.

    JSON body:
        {
            "patient": {
                "id": int or null (null = new patient),
                "first_name": str,
                "last_name": str,
                "birth_date": "YYYY-MM-DD" or null,
                "sex": "M" or "F",
                "medical_record_number": str,
                "notes": str,
            },
            "measurements": [
                {
                    "date": "YYYY-MM-DD",
                    "height_cm": float or null,
                    "weight_kg": float or null,
                    "head_circ_cm": float or null,
                    "notes": str,
                    "source_pdf": str,
                },
                ...
            ],
            "match_action": "auto_merge" | "merge" | "new_patient" (optional),
        }

    Returns JSON:
        {success, patient_id, measurements_saved, warnings}
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No JSON body provided"}), 400

    patient_data = data.get("patient")
    measurements_data = data.get("measurements", [])
    match_action = data.get("match_action", "new_patient")

    if not patient_data:
        return jsonify({"success": False, "error": "No patient data provided"}), 400

    db = current_app.db
    warnings = []

    try:
        # ── Resolve or create patient ─────────────────────
        patient_id = patient_data.get("id")

        if patient_id and match_action in ("auto_merge", "merge"):
            # Merge into existing patient
            existing = db.get_patient(patient_id)
            if not existing:
                return jsonify({
                    "success": False,
                    "error": f"Patient ID {patient_id} not found"
                }), 404

            # Update empty fields from import data
            changed = False
            if not existing.first_name and patient_data.get("first_name"):
                existing.first_name = patient_data["first_name"]
                changed = True
            if not existing.last_name and patient_data.get("last_name"):
                existing.last_name = patient_data["last_name"]
                changed = True
            if not existing.birth_date and patient_data.get("birth_date"):
                try:
                    existing.birth_date = date.fromisoformat(patient_data["birth_date"])
                    changed = True
                except (ValueError, TypeError):
                    pass
            if not existing.medical_record_number and patient_data.get("medical_record_number"):
                existing.medical_record_number = patient_data["medical_record_number"]
                changed = True

            if changed:
                db.save_patient(existing)
                warnings.append("Updated existing patient with new imported data")

            patient = existing

        else:
            # Check for existing match first
            matcher = PatientMatcher(db)
            birth_date = None
            bd_str = patient_data.get("birth_date")
            if bd_str:
                try:
                    birth_date = date.fromisoformat(bd_str)
                except (ValueError, TypeError):
                    pass

            match = matcher.find_match(
                first_name=patient_data.get("first_name", ""),
                last_name=patient_data.get("last_name", ""),
                birth_date=birth_date,
                medical_record_number=patient_data.get("medical_record_number", ""),
            )

            if match["match_type"] == "id_exact" and match["action"] == "auto_merge":
                # Auto-merge on exact ID match
                patient = db.get_patient(match["patient"]["id"])
                if patient:
                    warnings.append(
                        f"Auto-merged with existing patient (ID match: "
                        f"{patient.medical_record_number})"
                    )
                else:
                    # Patient ID existed in match but not found in DB — create new
                    patient = Patient(
                        first_name=patient_data.get("first_name", ""),
                        last_name=patient_data.get("last_name", ""),
                        birth_date=birth_date,
                        sex=patient_data.get("sex", "M"),
                        medical_record_number=patient_data.get("medical_record_number", ""),
                        notes=patient_data.get("notes", ""),
                    )
                    patient = db.save_patient(patient)
            else:
                # Create new patient
                patient = Patient(
                    first_name=patient_data.get("first_name", ""),
                    last_name=patient_data.get("last_name", ""),
                    birth_date=birth_date,
                    sex=patient_data.get("sex", "M"),
                    medical_record_number=patient_data.get("medical_record_number", ""),
                    notes=patient_data.get("notes", ""),
                )
                patient = db.save_patient(patient)

        # ── Save measurements ─────────────────────────────
        saved_count = 0
        for m_data in measurements_data:
            try:
                meas_date = None
                if m_data.get("date"):
                    try:
                        meas_date = date.fromisoformat(m_data["date"])
                    except (ValueError, TypeError):
                        warnings.append(f"Skipped measurement with invalid date: {m_data.get('date')}")
                        continue

                # Must have at least one value
                height = m_data.get("height_cm")
                weight = m_data.get("weight_kg")
                head = m_data.get("head_circ_cm")
                if height is None and weight is None and head is None:
                    continue

                measurement = Measurement(
                    patient_id=patient.id,
                    date=meas_date,
                    height_cm=float(height) if height is not None else None,
                    weight_kg=float(weight) if weight is not None else None,
                    head_circ_cm=float(head) if head is not None else None,
                    bone_age_years=float(m_data["bone_age_years"]) if m_data.get("bone_age_years") else None,
                    notes=m_data.get("notes", ""),
                    source_pdf=m_data.get("source_pdf", ""),
                )
                # Tanner staging from import
                for fld in ["tanner_breast", "tanner_pubic_hair", "tanner_genital"]:
                    if m_data.get(fld) is not None:
                        setattr(measurement, fld, int(m_data[fld]))
                if m_data.get("testicular_volume") is not None:
                    measurement.testicular_volume = float(m_data["testicular_volume"])
                db.save_measurement(measurement)
                saved_count += 1
            except Exception as e:
                warnings.append(f"Failed to save measurement: {str(e)}")

        return jsonify({
            "success": True,
            "patient_id": patient.id,
            "patient_name": f"{patient.first_name} {patient.last_name}".strip(),
            "measurements_saved": saved_count,
            "warnings": warnings,
        })

    except Exception as e:
        return jsonify({"success": False, "error": f"Confirm import failed: {str(e)}"}), 500
