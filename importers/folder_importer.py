"""
Multi-file / folder import for GrowthChart v2.

Processes multiple files in batch:
- Classifies files by extension: .pdf -> pdf_extractor, .xlsx/.xls/.csv/.tsv -> excel_importer
- Extracts ZIP archives to a temp directory
- Two modes:
    "same_patient": all files assigned to a specified patient_id
    "auto_detect": extract patient info from each file, group by patient using patient_matcher
- Returns grouped results for frontend review
"""

import os
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from importers.pdf_extractor import ValidatedPDFExtractor
from importers.excel_importer import ExcelImporter
from importers.patient_matcher import PatientMatcher


# File extensions -> handler type
PDF_EXTENSIONS = {'.pdf'}
EXCEL_EXTENSIONS = {'.xlsx', '.xls', '.csv', '.tsv', '.txt'}
ZIP_EXTENSIONS = {'.zip'}

# All supported extensions
ALL_EXTENSIONS = PDF_EXTENSIONS | EXCEL_EXTENSIONS | ZIP_EXTENSIONS


def _classify_file(path: str) -> Optional[str]:
    """Classify a file by extension. Returns 'pdf', 'excel', 'zip', or None."""
    ext = Path(path).suffix.lower()
    if ext in PDF_EXTENSIONS:
        return "pdf"
    elif ext in EXCEL_EXTENSIONS:
        return "excel"
    elif ext in ZIP_EXTENSIONS:
        return "zip"
    return None


def _extract_zip(zip_path: str, target_dir: str) -> List[str]:
    """
    Extract a ZIP file to target_dir. Returns list of extracted file paths.
    Only extracts supported file types, skips hidden files and __MACOSX.
    """
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for member in zf.namelist():
                # Skip directories, hidden files, macOS resource forks
                basename = os.path.basename(member)
                if not basename or basename.startswith('.') or '__MACOSX' in member:
                    continue
                ext = Path(basename).suffix.lower()
                if ext not in (PDF_EXTENSIONS | EXCEL_EXTENSIONS):
                    continue
                # Extract to flat directory to avoid path traversal
                target_path = os.path.join(target_dir, basename)
                # Handle name collisions
                counter = 1
                original_stem = Path(basename).stem
                original_ext = Path(basename).suffix
                while os.path.exists(target_path):
                    target_path = os.path.join(
                        target_dir, f"{original_stem}_{counter}{original_ext}"
                    )
                    counter += 1
                with zf.open(member) as source, open(target_path, 'wb') as target:
                    shutil.copyfileobj(source, target)
                extracted.append(target_path)
    except zipfile.BadZipFile:
        pass  # Will be reported as a warning
    return extracted


# ══════════════════════════════════════════════════════════════
#  FolderImporter — main class
# ══════════════════════════════════════════════════════════════

class FolderImporter:
    """
    Process multiple files, optionally from a ZIP, and return grouped results.
    """

    def __init__(self, db=None):
        """
        Args:
            db: Database instance (for patient matching in auto_detect mode).
                Can be None for same_patient mode.
        """
        self.db = db
        self.pdf_extractor = ValidatedPDFExtractor()
        self.excel_importer = ExcelImporter()

    def process(self, file_paths: List[str], mode: str = "auto_detect",
                patient_id: Optional[int] = None,
                patient_birth_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Process multiple files.

        Args:
            file_paths: List of file paths to process.
            mode: "same_patient" or "auto_detect".
            patient_id: Required for "same_patient" mode.
            patient_birth_date: Optional DOB for validation.

        Returns:
            {
                "success": bool,
                "mode": str,
                "groups": [
                    {
                        "patient_info": {...},
                        "match_result": {...},  # from patient_matcher
                        "files": [{filename, file_type, ...}, ...],
                        "measurements": [...],
                    },
                    ...
                ],
                "skipped_files": [...],
                "warnings": [...],
                "total_files": int,
                "total_measurements": int,
            }
        """
        warnings: List[str] = []
        skipped: List[Dict[str, str]] = []
        temp_dirs: List[str] = []

        try:
            # Expand ZIP files
            expanded_files = []
            for fpath in file_paths:
                file_type = _classify_file(fpath)
                if file_type == "zip":
                    temp_dir = tempfile.mkdtemp(prefix="growthchart_zip_")
                    temp_dirs.append(temp_dir)
                    extracted = _extract_zip(fpath, temp_dir)
                    if not extracted:
                        warnings.append(f"ZIP file {Path(fpath).name} contained no supported files")
                    expanded_files.extend(extracted)
                elif file_type in ("pdf", "excel"):
                    expanded_files.append(fpath)
                else:
                    skipped.append({
                        "file": Path(fpath).name,
                        "reason": f"Unsupported file type: {Path(fpath).suffix}",
                    })

            if not expanded_files:
                return {
                    "success": False,
                    "error": "No supported files to process",
                    "skipped_files": skipped,
                    "warnings": warnings,
                }

            # Process each file
            file_results = []
            for fpath in expanded_files:
                result = self._process_single_file(fpath, patient_birth_date, warnings)
                if result:
                    file_results.append(result)
                else:
                    skipped.append({
                        "file": Path(fpath).name,
                        "reason": "Extraction returned no data",
                    })

            # Group results
            if mode == "same_patient":
                groups = self._group_same_patient(file_results, patient_id)
            else:
                groups = self._group_auto_detect(file_results, warnings)

            # Count totals
            total_measurements = sum(
                len(g.get("measurements", [])) for g in groups
            )

            return {
                "success": True,
                "mode": mode,
                "groups": groups,
                "skipped_files": skipped,
                "warnings": warnings,
                "total_files": len(expanded_files),
                "total_measurements": total_measurements,
            }

        finally:
            # Clean up temp directories from ZIP extraction
            for td in temp_dirs:
                try:
                    shutil.rmtree(td, ignore_errors=True)
                except Exception:
                    pass

    def _process_single_file(self, file_path: str,
                             patient_birth_date: Optional[date],
                             warnings: List[str]) -> Optional[Dict[str, Any]]:
        """Process a single file and return extracted data."""
        file_type = _classify_file(file_path)
        filename = Path(file_path).name

        if file_type == "pdf":
            try:
                result = self.pdf_extractor.extract(file_path, patient_birth_date)
                if not result.get("success"):
                    warnings.append(f"{filename}: {result.get('error', 'extraction failed')}")
                    return None
                return {
                    "file_path": file_path,
                    "filename": filename,
                    "file_type": "pdf",
                    "patient_info": result.get("patient", {}),
                    "measurements": result.get("measurements", []),
                    "parental_heights": result.get("parental_heights", {}),
                    "bone_age_years": result.get("bone_age_years"),
                    "warnings": result.get("warnings", []),
                }
            except Exception as e:
                warnings.append(f"{filename}: PDF extraction error: {str(e)}")
                return None

        elif file_type == "excel":
            try:
                analysis = self.excel_importer.analyze(file_path)
                if not analysis.get("success"):
                    warnings.append(f"{filename}: {analysis.get('error', 'analysis failed')}")
                    return None

                col_mapping = analysis.get("column_mapping", {})
                if not col_mapping:
                    warnings.append(f"{filename}: could not detect column mapping")
                    return None

                parsed = self.excel_importer.parse_data(
                    file_path, col_mapping,
                    header_row=analysis.get("header_row", 0),
                )
                if not parsed.get("success"):
                    warnings.append(f"{filename}: {parsed.get('error', 'parse failed')}")
                    return None

                return {
                    "file_path": file_path,
                    "filename": filename,
                    "file_type": "excel",
                    "patient_info": parsed.get("patient_info", {}),
                    "measurements": parsed.get("measurements", []),
                    "column_mapping": col_mapping,
                    "detected_units": analysis.get("detected_units", {}),
                    "warnings": parsed.get("warnings", []),
                }
            except Exception as e:
                warnings.append(f"{filename}: Excel import error: {str(e)}")
                return None

        return None

    def _group_same_patient(self, file_results: List[Dict],
                            patient_id: Optional[int]) -> List[Dict[str, Any]]:
        """Group all results under a single patient."""
        all_measurements = []
        all_files = []

        for fr in file_results:
            all_measurements.extend(fr.get("measurements", []))
            all_files.append({
                "filename": fr["filename"],
                "file_type": fr["file_type"],
                "measurement_count": len(fr.get("measurements", [])),
                "warnings": fr.get("warnings", []),
            })

        group = {
            "patient_info": {"patient_id": patient_id},
            "match_result": {
                "match_type": "assigned",
                "action": "auto_merge",
                "confidence": 1.0,
            },
            "files": all_files,
            "measurements": all_measurements,
        }

        # Include parental heights from first PDF that has them
        for fr in file_results:
            ph = fr.get("parental_heights", {})
            if ph.get("father_height_cm") or ph.get("mother_height_cm"):
                group["parental_heights"] = ph
                break

        # Include bone age from first PDF that has it
        for fr in file_results:
            ba = fr.get("bone_age_years")
            if ba is not None:
                group["bone_age_years"] = ba
                break

        return [group]

    def _group_auto_detect(self, file_results: List[Dict],
                           warnings: List[str]) -> List[Dict[str, Any]]:
        """
        Group results by detected patient, using patient_matcher
        to find existing patients and group files that belong together.
        """
        if not self.db:
            # Without database access, each file is its own group
            return self._group_individual(file_results)

        matcher = PatientMatcher(self.db)
        groups: List[Dict[str, Any]] = []
        # Track which group each patient_id maps to (for merging)
        id_to_group: Dict[int, int] = {}

        for fr in file_results:
            pi = fr.get("patient_info") or {}
            first_name = pi.get("first_name", "") or pi.get("name", "") or ""
            last_name = pi.get("last_name", "")
            birth_date_str = pi.get("birth_date")
            mrn = pi.get("medical_record_number", "") or pi.get("id", "") or ""

            # Parse birth date if string
            birth_date = None
            if birth_date_str:
                try:
                    from datetime import date as _date
                    birth_date = _date.fromisoformat(birth_date_str)
                except (ValueError, TypeError):
                    pass

            # Try to find a match
            match = matcher.find_match(
                first_name=first_name,
                last_name=last_name,
                birth_date=birth_date,
                medical_record_number=mrn,
            )

            matched_patient = match.get("patient")
            matched_id = matched_patient.get("id") if matched_patient else None

            file_info = {
                "filename": fr["filename"],
                "file_type": fr["file_type"],
                "measurement_count": len(fr.get("measurements", [])),
                "warnings": fr.get("warnings", []),
            }

            # Merge into existing group if same patient
            if matched_id and matched_id in id_to_group:
                group_idx = id_to_group[matched_id]
                groups[group_idx]["files"].append(file_info)
                groups[group_idx]["measurements"].extend(fr.get("measurements", []))
            else:
                new_group = {
                    "patient_info": pi if pi else {
                        "first_name": first_name,
                        "last_name": last_name,
                        "birth_date": birth_date_str,
                        "medical_record_number": mrn,
                    },
                    "match_result": match,
                    "files": [file_info],
                    "measurements": fr.get("measurements", []),
                }

                # Include extras from PDF
                if fr.get("parental_heights"):
                    new_group["parental_heights"] = fr["parental_heights"]
                if fr.get("bone_age_years") is not None:
                    new_group["bone_age_years"] = fr["bone_age_years"]

                group_idx = len(groups)
                groups.append(new_group)
                if matched_id:
                    id_to_group[matched_id] = group_idx

        return groups

    def _group_individual(self, file_results: List[Dict]) -> List[Dict[str, Any]]:
        """Fallback: each file is its own group (no DB for matching)."""
        groups = []
        for fr in file_results:
            group = {
                "patient_info": fr.get("patient_info", {}),
                "match_result": {
                    "match_type": "none",
                    "action": "new_patient",
                    "confidence": 0.0,
                },
                "files": [{
                    "filename": fr["filename"],
                    "file_type": fr["file_type"],
                    "measurement_count": len(fr.get("measurements", [])),
                    "warnings": fr.get("warnings", []),
                }],
                "measurements": fr.get("measurements", []),
            }
            if fr.get("parental_heights"):
                group["parental_heights"] = fr["parental_heights"]
            if fr.get("bone_age_years") is not None:
                group["bone_age_years"] = fr["bone_age_years"]
            groups.append(group)
        return groups
