"""
Smart Excel/CSV column detection and import for GrowthChart v2.

Reads .xlsx, .xls, and .csv/.tsv files. Uses fuzzy header matching
and data-type analysis to map columns to growth data fields:
  date, height, weight, head circumference, age, BMI, name, ID.

Handles:
- Hebrew and English headers (including reversed Hebrew from copy-paste)
- Merged cells, multi-sheet workbooks, empty rows
- Header rows that appear mid-table
- Unit detection: meters -> cm, grams -> kg
"""

import csv
import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Column Name Patterns ──────────────────────────────────────

# Each field maps to a list of (pattern, score) tuples.
# Higher score = better match. Patterns are checked case-insensitively.
FIELD_PATTERNS: Dict[str, List[Tuple[str, float]]] = {
    "date": [
        (r'^תאריך$', 1.0),
        (r'תאריך', 0.8),
        (r'^date$', 1.0),
        (r'date', 0.7),
        (r'^ךיראת$', 0.9),   # reversed Hebrew
        (r'visit', 0.5),
        (r'ביקור', 0.5),
        (r'רוקיב', 0.5),
    ],
    "height_cm": [
        (r'^גובה$', 1.0),
        (r'גובה', 0.8),
        (r'^height$', 1.0),
        (r'height', 0.7),
        (r'^הבוג$', 0.9),    # reversed
        (r'ht\b', 0.6),
        (r'אורך', 0.7),      # length (for infants)
        (r'ךרוא', 0.7),
        (r'length', 0.6),
        (r'cm', 0.4),
        (r'ס"מ', 0.4),
    ],
    "weight_kg": [
        (r'^משקל$', 1.0),
        (r'משקל', 0.8),
        (r'^weight$', 1.0),
        (r'weight', 0.7),
        (r'^לקשמ$', 0.9),    # reversed
        (r'wt\b', 0.6),
        (r'kg', 0.4),
        (r'ק"ג', 0.4),
    ],
    "head_circ_cm": [
        (r'היקף\s*ראש', 1.0),
        (r'שאר\s*ףקיה', 0.9),
        (r'head\s*circ', 1.0),
        (r'hc\b', 0.6),
        (r'ofc', 0.6),
    ],
    "age": [
        (r'^גיל$', 1.0),
        (r'גיל', 0.7),
        (r'^age$', 1.0),
        (r'age', 0.6),
        (r'^ליג$', 0.9),
    ],
    "bmi": [
        (r'^bmi$', 1.0),
        (r'bmi', 0.7),
        (r'BMI', 0.9),
    ],
    "name": [
        (r'^שם$', 1.0),
        (r'שם\s*מלא', 1.0),
        (r'שם\s*פרטי', 0.9),
        (r'שם\s*משפחה', 0.9),
        (r'^name$', 1.0),
        (r'first\s*name', 0.9),
        (r'last\s*name', 0.9),
        (r'patient', 0.6),
        (r'^םש$', 0.9),
    ],
    "id": [
        (r'^ת\.?ז\.?$', 1.0),
        (r'ת\.?ז', 0.8),
        (r'ז\.?ת', 0.8),
        (r'^id$', 0.8),
        (r'מספר\s*זהות', 1.0),
        (r'תעודת\s*זהות', 1.0),
        (r'medical.*record', 0.7),
        (r'mrn', 0.7),
    ],
}


# ── Data Type Heuristics ──────────────────────────────────────

def _looks_like_date(values: List[Any]) -> float:
    """Score how likely a column of values contains dates (0-1)."""
    if not values:
        return 0.0
    date_count = 0
    total = 0
    for v in values:
        if v is None or str(v).strip() == "":
            continue
        total += 1
        s = str(v).strip()
        # Check common date patterns
        if re.match(r'^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}$', s):
            date_count += 1
        elif re.match(r'^\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}$', s):
            date_count += 1
        elif isinstance(v, (date, datetime)):
            date_count += 1
    return date_count / total if total > 0 else 0.0


def _looks_like_height(values: List[Any]) -> float:
    """Score how likely values are heights (30-220 cm or 0.3-2.2 m)."""
    if not values:
        return 0.0
    match_count = 0
    total = 0
    for v in values:
        if v is None or str(v).strip() == "":
            continue
        try:
            num = float(str(v).strip().replace(',', '.'))
            total += 1
            if 30 <= num <= 220 or 0.3 <= num <= 2.2:
                match_count += 1
        except ValueError:
            total += 1
    return match_count / total if total > 0 else 0.0


def _looks_like_weight(values: List[Any]) -> float:
    """Score how likely values are weights (0.5-200 kg or 500-200000 g)."""
    if not values:
        return 0.0
    match_count = 0
    total = 0
    for v in values:
        if v is None or str(v).strip() == "":
            continue
        try:
            num = float(str(v).strip().replace(',', '.'))
            total += 1
            if 2 <= num <= 200 or 500 <= num <= 200000:
                match_count += 1
        except ValueError:
            total += 1
    return match_count / total if total > 0 else 0.0


# ── Cell Value Normalization ──────────────────────────────────

def _parse_cell_date(v: Any) -> Optional[date]:
    """Try to parse a cell value as a date."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None

    # DD/MM/YYYY or DD.MM.YYYY or DD-MM-YYYY
    m = re.match(r'^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$', s)
    if m:
        try:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return date(y, mo, d)
        except ValueError:
            pass

    # YYYY-MM-DD
    m = re.match(r'^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})$', s)
    if m:
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return date(y, mo, d)
        except ValueError:
            pass

    # DD/MM/YY
    m = re.match(r'^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2})$', s)
    if m:
        try:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            y += 2000 if y < 50 else 1900
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return date(y, mo, d)
        except ValueError:
            pass

    return None


def _parse_cell_float(v: Any) -> Optional[float]:
    """Try to parse a cell value as a float."""
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return None
    s = str(v).strip().replace(',', '.')
    # Remove units
    s = re.sub(r'\s*(kg|g|cm|m|ק"ג|ס"מ)\s*$', '', s, flags=re.IGNORECASE)
    try:
        return float(s)
    except ValueError:
        return None


# ══════════════════════════════════════════════════════════════
#  ExcelImporter — main class
# ══════════════════════════════════════════════════════════════

class ExcelImporter:
    """
    Import growth data from Excel (.xlsx/.xls) and CSV/TSV files.
    Detects column mappings and returns preview data.
    """

    def analyze(self, file_path: str,
                sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze a file to detect column mappings.

        Returns:
            {
                "success": bool,
                "file_path": str,
                "file_type": str,
                "sheets": [...],        # for multi-sheet workbooks
                "active_sheet": str,
                "column_mapping": {field: col_index, ...},
                "column_headers": [str, ...],
                "preview_rows": [...],
                "total_data_rows": int,
                "detected_units": {...},
                "warnings": [...],
            }
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        try:
            if ext in ('.xlsx', '.xls'):
                return self._analyze_excel(file_path, sheet_name)
            elif ext in ('.csv', '.tsv', '.txt'):
                return self._analyze_csv(file_path, delimiter='\t' if ext == '.tsv' else None)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported file type: {ext}",
                    "file_path": file_path,
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to analyze file: {str(e)}",
                "file_path": file_path,
            }

    def parse_data(self, file_path: str, column_mapping: Dict[str, int],
                   sheet_name: Optional[str] = None,
                   header_row: int = 0) -> Dict[str, Any]:
        """
        Parse file data using the provided column mapping.

        Args:
            file_path: Path to the file.
            column_mapping: {field_name: column_index} mapping.
            sheet_name: Sheet name for Excel files.
            header_row: Row index of the header (0-based). Data starts after this.

        Returns:
            {
                "success": bool,
                "measurements": [...],
                "patient_info": {...},  # if name/id columns detected
                "row_count": int,
                "warnings": [...],
            }
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        try:
            if ext in ('.xlsx', '.xls'):
                rows = self._read_excel_rows(file_path, sheet_name)
            else:
                rows = self._read_csv_rows(file_path,
                                           delimiter='\t' if ext == '.tsv' else None)
        except Exception as e:
            return {"success": False, "error": str(e)}

        if not rows:
            return {"success": False, "error": "No data rows found"}

        # Skip header and empty rows before data
        data_rows = rows[header_row + 1:]
        warnings = []
        measurements = []
        patient_name = None
        patient_id = None

        for row_idx, row in enumerate(data_rows):
            # Skip fully empty rows
            if not any(cell is not None and str(cell).strip() != "" for cell in row):
                continue

            entry: Dict[str, Any] = {"_row": row_idx + header_row + 2}  # 1-based display

            for field, col_idx in column_mapping.items():
                if col_idx >= len(row):
                    continue
                cell = row[col_idx]

                if field == "date":
                    entry["date"] = _parse_cell_date(cell)
                    if cell and entry["date"] is None:
                        warnings.append(f"Row {entry['_row']}: could not parse date '{cell}'")
                elif field == "height_cm":
                    val = _parse_cell_float(cell)
                    if val is not None:
                        # Auto-convert meters to cm
                        if 0.3 <= val <= 2.2:
                            val = round(val * 100, 1)
                        entry["height_cm"] = round(val, 1) if 30 <= val <= 220 else None
                    else:
                        entry["height_cm"] = None
                elif field == "weight_kg":
                    val = _parse_cell_float(cell)
                    if val is not None:
                        # Auto-convert grams to kg
                        if 500 <= val <= 200000:
                            val = round(val / 1000, 2)
                        entry["weight_kg"] = round(val, 2) if 0.5 <= val <= 200 else None
                    else:
                        entry["weight_kg"] = None
                elif field == "head_circ_cm":
                    val = _parse_cell_float(cell)
                    if val is not None and 20 <= val <= 65:
                        entry["head_circ_cm"] = round(val, 1)
                elif field == "name":
                    if cell and str(cell).strip():
                        patient_name = str(cell).strip()
                elif field == "id":
                    if cell and str(cell).strip():
                        patient_id = str(cell).strip()

            # Only include rows that have at least a date and one measurement
            has_data = (
                entry.get("date") is not None
                and (entry.get("height_cm") is not None
                     or entry.get("weight_kg") is not None)
            )
            if has_data:
                meas = {
                    "date": entry["date"].isoformat() if entry.get("date") else None,
                    "height_cm": entry.get("height_cm"),
                    "weight_kg": entry.get("weight_kg"),
                    "head_circ_cm": entry.get("head_circ_cm"),
                    "source_row": entry["_row"],
                }
                measurements.append(meas)

        result: Dict[str, Any] = {
            "success": True,
            "measurements": measurements,
            "row_count": len(measurements),
            "warnings": warnings,
        }

        # Include patient info if detected
        if patient_name or patient_id:
            result["patient_info"] = {
                "name": patient_name,
                "medical_record_number": patient_id,
            }

        return result

    # ── Excel Analysis ────────────────────────────────────

    def _analyze_excel(self, file_path: str,
                       sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """Analyze an Excel file."""
        import openpyxl

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames

        active = sheet_name if sheet_name and sheet_name in sheet_names else sheet_names[0]
        ws = wb[active]

        # Read first 30 rows
        raw_rows: List[List[Any]] = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= 30:
                break
            raw_rows.append(list(row))

        wb.close()

        return self._analyze_rows(raw_rows, file_path, "xlsx",
                                  sheets=sheet_names, active_sheet=active)

    def _analyze_csv(self, file_path: str,
                     delimiter: Optional[str] = None) -> Dict[str, Any]:
        """Analyze a CSV/TSV file."""
        raw_rows: List[List[Any]] = []

        # Try to detect encoding
        encodings = ['utf-8-sig', 'utf-8', 'cp1255', 'iso-8859-8', 'latin-1']
        content = None
        used_encoding = 'utf-8'

        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                    used_encoding = enc
                    break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            return {"success": False, "error": "Could not decode file with known encodings"}

        # Auto-detect delimiter if not specified
        if delimiter is None:
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(content[:4096])
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ','

        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        for i, row in enumerate(reader):
            if i >= 30:
                break
            raw_rows.append(row)

        ext = Path(file_path).suffix.lower()
        file_type = "tsv" if ext == '.tsv' or delimiter == '\t' else "csv"

        return self._analyze_rows(raw_rows, file_path, file_type)

    # ── Shared Analysis Logic ─────────────────────────────

    def _analyze_rows(self, raw_rows: List[List[Any]], file_path: str,
                      file_type: str, sheets: Optional[List[str]] = None,
                      active_sheet: Optional[str] = None) -> Dict[str, Any]:
        """Analyze raw row data to detect column mapping."""
        if not raw_rows:
            return {"success": False, "error": "File is empty", "file_path": file_path}

        warnings: List[str] = []

        # Find the header row (first row with text-like content)
        header_row_idx = self._find_header_row(raw_rows)
        if header_row_idx is None:
            warnings.append("No clear header row found, treating row 0 as header")
            header_row_idx = 0

        headers = [str(cell).strip() if cell is not None else "" for cell in raw_rows[header_row_idx]]

        # Collect data rows (after header, non-empty)
        data_rows = []
        for row in raw_rows[header_row_idx + 1:]:
            if any(cell is not None and str(cell).strip() != "" for cell in row):
                data_rows.append(row)

        # Score each column by header name matching
        col_scores: Dict[int, Dict[str, float]] = {}
        for col_idx, header in enumerate(headers):
            if not header:
                continue
            col_scores[col_idx] = {}
            for field, patterns in FIELD_PATTERNS.items():
                best_score = 0.0
                for pat, score in patterns:
                    if re.search(pat, header, re.IGNORECASE):
                        best_score = max(best_score, score)
                if best_score > 0:
                    col_scores[col_idx][field] = best_score

        # If header matching is weak, use data-type heuristics
        col_data = {}
        for col_idx in range(len(headers)):
            values = [row[col_idx] if col_idx < len(row) else None for row in data_rows]
            col_data[col_idx] = values

        for col_idx, values in col_data.items():
            if col_idx not in col_scores:
                col_scores[col_idx] = {}

            # Only apply heuristics if header score is low
            date_score = _looks_like_date(values)
            height_score = _looks_like_height(values)
            weight_score = _looks_like_weight(values)

            existing = col_scores[col_idx]
            if existing.get("date", 0) < 0.5 and date_score > 0.6:
                existing["date"] = max(existing.get("date", 0), date_score * 0.7)
            if existing.get("height_cm", 0) < 0.5 and height_score > 0.6:
                existing["height_cm"] = max(existing.get("height_cm", 0), height_score * 0.6)
            if existing.get("weight_kg", 0) < 0.5 and weight_score > 0.6:
                existing["weight_kg"] = max(existing.get("weight_kg", 0), weight_score * 0.6)

        # Assign columns to fields greedily by score
        column_mapping = self._assign_columns(col_scores)

        # Detect units from data
        detected_units: Dict[str, str] = {}
        if "height_cm" in column_mapping:
            height_vals = col_data.get(column_mapping["height_cm"], [])
            nums = [_parse_cell_float(v) for v in height_vals if v is not None]
            nums = [n for n in nums if n is not None]
            if nums:
                avg = sum(nums) / len(nums)
                if avg < 3.0:
                    detected_units["height"] = "meters (will convert to cm)"
                else:
                    detected_units["height"] = "cm"

        if "weight_kg" in column_mapping:
            weight_vals = col_data.get(column_mapping["weight_kg"], [])
            nums = [_parse_cell_float(v) for v in weight_vals if v is not None]
            nums = [n for n in nums if n is not None]
            if nums:
                avg = sum(nums) / len(nums)
                if avg > 500:
                    detected_units["weight"] = "grams (will convert to kg)"
                else:
                    detected_units["weight"] = "kg"

        # Build preview rows (up to 10 data rows)
        preview_rows = []
        for row in data_rows[:10]:
            preview = {}
            for field, col_idx in column_mapping.items():
                if col_idx < len(row):
                    val = row[col_idx]
                    preview[field] = str(val) if val is not None else ""
                else:
                    preview[field] = ""
            preview_rows.append(preview)

        # Count total data rows (including beyond our 30-row sample)
        total_data_rows = len(data_rows)

        result: Dict[str, Any] = {
            "success": True,
            "file_path": file_path,
            "file_type": file_type,
            "column_mapping": column_mapping,
            "column_headers": headers,
            "header_row": header_row_idx,
            "preview_rows": preview_rows,
            "total_data_rows": total_data_rows,
            "detected_units": detected_units,
            "warnings": warnings,
        }

        if sheets:
            result["sheets"] = sheets
            result["active_sheet"] = active_sheet

        return result

    def _find_header_row(self, rows: List[List[Any]]) -> Optional[int]:
        """
        Find the most likely header row. Heuristic: first row where
        most cells are strings (not numbers/dates/empty).
        """
        best_idx = None
        best_text_ratio = 0.0

        for idx, row in enumerate(rows[:10]):  # only check first 10 rows
            if not row:
                continue
            non_empty = [cell for cell in row if cell is not None and str(cell).strip() != ""]
            if not non_empty:
                continue

            text_count = 0
            for cell in non_empty:
                s = str(cell).strip()
                # Text that is not purely numeric
                if s and not re.match(r'^[\d.,/\-]+$', s):
                    text_count += 1

            ratio = text_count / len(non_empty) if non_empty else 0
            if ratio > best_text_ratio and ratio >= 0.4:
                best_text_ratio = ratio
                best_idx = idx

        return best_idx

    def _assign_columns(self, col_scores: Dict[int, Dict[str, float]]
                        ) -> Dict[str, int]:
        """
        Greedily assign columns to fields by score.
        Each column can only be assigned to one field, each field to one column.
        """
        # Build list of (score, field, col_idx) and sort descending
        candidates = []
        for col_idx, field_scores in col_scores.items():
            for field, score in field_scores.items():
                candidates.append((score, field, col_idx))
        candidates.sort(reverse=True)

        mapping: Dict[str, int] = {}
        used_cols: set = set()

        for score, field, col_idx in candidates:
            if field in mapping or col_idx in used_cols:
                continue
            if score >= 0.3:  # minimum threshold
                mapping[field] = col_idx
                used_cols.add(col_idx)

        return mapping

    # ── Row Reading Helpers ───────────────────────────────

    def _read_excel_rows(self, file_path: str,
                         sheet_name: Optional[str] = None) -> List[List[Any]]:
        """Read all rows from an Excel file."""
        import openpyxl

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(list(row))
        wb.close()
        return rows

    def _read_csv_rows(self, file_path: str,
                       delimiter: Optional[str] = None) -> List[List[Any]]:
        """Read all rows from a CSV file."""
        encodings = ['utf-8-sig', 'utf-8', 'cp1255', 'iso-8859-8', 'latin-1']
        content = None

        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            raise ValueError("Could not decode CSV file")

        if delimiter is None:
            try:
                dialect = csv.Sniffer().sniff(content[:4096])
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ','

        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        return [row for row in reader]
