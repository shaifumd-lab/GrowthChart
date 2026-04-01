"""
Validated PDF extraction wrapper for GrowthChart v2.

Wraps the existing pdf/extractor.py PDFExtractor class, adding:
- Height/weight/date validation layers
- Parental height extraction from Hebrew clinic letters
- Bone age extraction
- Age-appropriate plausibility checks
- Confidence threshold filtering
- Structured JSON-friendly output
"""

import re
from datetime import date
from typing import Dict, List, Optional, Any

# Import the existing v1 extractor
from pdf.extractor import PDFExtractor, ExtractedPatientData, ExtractedMeasurement


# ── Validation Constants ──────────────────────────────────────

MIN_HEIGHT_CM = 30.0
MAX_HEIGHT_CM = 220.0
MIN_WEIGHT_KG = 0.5
MAX_WEIGHT_KG = 200.0
MIN_DATE_YEAR = 1990
CONFIDENCE_THRESHOLD = 0.3

# Age-appropriate height ranges (approximate, generous bounds)
# Keys: (min_age_years, max_age_years) -> (min_height_cm, max_height_cm)
AGE_HEIGHT_RANGES = {
    (0, 0.5):   (30, 80),
    (0.5, 1):   (55, 85),
    (1, 2):     (65, 100),
    (2, 5):     (75, 125),
    (5, 10):    (95, 160),
    (10, 15):   (110, 195),
    (15, 20):   (130, 210),
    (20, 100):  (130, 220),
}

# Age-appropriate weight ranges
AGE_WEIGHT_RANGES = {
    (0, 0.5):   (0.5, 12),
    (0.5, 1):   (3, 15),
    (1, 2):     (5, 20),
    (2, 5):     (8, 35),
    (5, 10):    (12, 60),
    (10, 15):   (20, 100),
    (15, 20):   (30, 150),
    (20, 100):  (30, 200),
}


# ── Validation Helpers ────────────────────────────────────────

def _validate_height(value: Optional[float]) -> Optional[float]:
    """Validate and normalize height to cm. Returns None if invalid."""
    if value is None:
        return None
    # Auto-convert meters to cm
    if 0.3 <= value <= 2.2:
        value = round(value * 100, 1)
    if MIN_HEIGHT_CM <= value <= MAX_HEIGHT_CM:
        return round(value, 1)
    return None


def _validate_weight(value: Optional[float]) -> Optional[float]:
    """Validate and normalize weight to kg. Returns None if invalid."""
    if value is None:
        return None
    # Auto-convert grams to kg
    if 500 <= value <= 200000:
        value = round(value / 1000, 2)
    if MIN_WEIGHT_KG <= value <= MAX_WEIGHT_KG:
        return round(value, 2)
    return None


def _validate_date(d: Optional[date]) -> Optional[date]:
    """Validate date: not future, not before 1990."""
    if d is None:
        return None
    if d > date.today():
        return None
    if d.year < MIN_DATE_YEAR:
        return None
    return d


def _age_appropriate_height(height_cm: float, birth_date: date,
                            measurement_date: date) -> bool:
    """Check if height is plausible for the patient's age."""
    age_days = (measurement_date - birth_date).days
    age_years = age_days / 365.25
    for (lo, hi), (min_h, max_h) in AGE_HEIGHT_RANGES.items():
        if lo <= age_years < hi:
            return min_h <= height_cm <= max_h
    return True  # age out of range table, accept


def _age_appropriate_weight(weight_kg: float, birth_date: date,
                            measurement_date: date) -> bool:
    """Check if weight is plausible for the patient's age."""
    age_days = (measurement_date - birth_date).days
    age_years = age_days / 365.25
    for (lo, hi), (min_w, max_w) in AGE_WEIGHT_RANGES.items():
        if lo <= age_years < hi:
            return min_w <= weight_kg <= max_w
    return True


# ── Parental Height Extraction ────────────────────────────────

# Hebrew patterns for father's height, mother's height, parental heights
_PARENT_HEIGHT_PATTERNS = {
    "father": [
        r'(?:גובה\s*(?:ה)?אב|גובה\s*אבא)\s*[:\-=]?\s*(\d{2,3}(?:\.\d{1,2})?)',
        r'(\d{2,3}(?:\.\d{1,2})?)\s*(?:ס"מ|cm)?\s*[:\-]?\s*(?:גובה\s*(?:ה)?אב)',
        # Reversed Hebrew from pdfplumber
        r'(?:בא(?:ה)?\s*הבוג|אבא\s*הבוג)\s*[:\-=]?\s*(\d{2,3}(?:\.\d{1,2})?)',
        r'(\d{2,3}(?:\.\d{1,2})?)\s*[:\-]?\s*(?:בא(?:ה)?\s*הבוג)',
        # English
        r"(?:father'?s?\s*height|paternal\s*height)\s*[:\-=]?\s*(\d{2,3}(?:\.\d{1,2})?)",
    ],
    "mother": [
        r'(?:גובה\s*(?:ה)?אם|גובה\s*אמא)\s*[:\-=]?\s*(\d{2,3}(?:\.\d{1,2})?)',
        r'(\d{2,3}(?:\.\d{1,2})?)\s*(?:ס"מ|cm)?\s*[:\-]?\s*(?:גובה\s*(?:ה)?אם)',
        # Reversed Hebrew
        r'(?:םא(?:ה)?\s*הבוג|אמא\s*הבוג)\s*[:\-=]?\s*(\d{2,3}(?:\.\d{1,2})?)',
        r'(\d{2,3}(?:\.\d{1,2})?)\s*[:\-]?\s*(?:םא(?:ה)?\s*הבוג)',
        # English
        r"(?:mother'?s?\s*height|maternal\s*height)\s*[:\-=]?\s*(\d{2,3}(?:\.\d{1,2})?)",
    ],
}

# Generic "parental heights" pattern (both together)
_PARENTS_HEIGHT_PATTERNS = [
    # "גובה הורים: אב 175 אם 162" or similar
    r'גובה\s*הורים\s*[:\-]?\s*(?:אב\s*)?(\d{2,3}(?:\.\d)?)\s*(?:אם\s*)?(\d{2,3}(?:\.\d)?)',
    r'םירוה\s*הבוג\s*[:\-]?\s*(?:בא\s*)?(\d{2,3}(?:\.\d)?)\s*(?:םא\s*)?(\d{2,3}(?:\.\d)?)',
    r'parental\s*heights?\s*[:\-]?\s*(?:father\s*)?(\d{2,3}(?:\.\d)?)\s*(?:mother\s*)?(\d{2,3}(?:\.\d)?)',
]


def _extract_parental_heights(text: str) -> Dict[str, Optional[float]]:
    """Extract father's and mother's heights from text."""
    result = {"father_height_cm": None, "mother_height_cm": None}

    # Try combined pattern first
    for pat in _PARENTS_HEIGHT_PATTERNS:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            try:
                father_h = float(match.group(1))
                mother_h = float(match.group(2))
                if 0.5 <= father_h <= 2.2:
                    father_h *= 100
                if 0.5 <= mother_h <= 2.2:
                    mother_h *= 100
                if 140 <= father_h <= 220:
                    result["father_height_cm"] = round(father_h, 1)
                if 130 <= mother_h <= 210:
                    result["mother_height_cm"] = round(mother_h, 1)
                return result
            except (ValueError, IndexError):
                pass

    # Try individual patterns
    for parent, patterns in _PARENT_HEIGHT_PATTERNS.items():
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1))
                    # Convert meters to cm
                    if 0.5 <= val <= 2.2:
                        val *= 100
                    key = f"{parent}_height_cm"
                    if parent == "father" and 140 <= val <= 220:
                        result[key] = round(val, 1)
                        break
                    elif parent == "mother" and 130 <= val <= 210:
                        result[key] = round(val, 1)
                        break
                except (ValueError, IndexError):
                    continue

    return result


# ── Bone Age Extraction ───────────────────────────────────────

_BONE_AGE_PATTERNS = [
    # Hebrew: "גיל עצמות: 12.5" / "גיל עצמות 12 שנים ו-6 חודשים"
    r'(?:גיל\s*עצמות|תומצע\s*ליג)\s*[:\-=]?\s*(\d{1,2}(?:[./]\d{1,2})?)',
    # English variants
    r'(?:bone\s*age|BA|skeletal\s*age)\s*[:\-=]?\s*(\d{1,2}(?:[./]\d{1,2})?)\s*(?:y(?:ears?)?|שנים)?',
    # "BA: 12y6m" or "BA: 12;6"
    r'(?:bone\s*age|BA)\s*[:\-=]?\s*(\d{1,2})\s*[y;]\s*(\d{1,2})\s*m?',
    # "BA = XX" at start of line
    r'^BA\s*[=:]\s*(\d{1,2}(?:\.\d{1,2})?)',
]


def _extract_bone_age(text: str) -> Optional[float]:
    """
    Extract bone age in years from text.
    Returns a float (e.g. 12.5 for 12 years 6 months).
    """
    for pat in _BONE_AGE_PATTERNS:
        match = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if match:
            groups = match.groups()
            try:
                if len(groups) == 2 and groups[1] is not None:
                    # "12y6m" format
                    years = int(groups[0])
                    months = int(groups[1])
                    return round(years + months / 12, 2)
                else:
                    val_str = groups[0]
                    # Handle "12/6" as 12 years 6 months
                    if '/' in val_str:
                        parts = val_str.split('/')
                        return round(int(parts[0]) + int(parts[1]) / 12, 2)
                    val = float(val_str)
                    if 0 <= val <= 22:
                        return round(val, 2)
            except (ValueError, IndexError):
                continue
    return None


# ══════════════════════════════════════════════════════════════
#  ValidatedPDFExtractor — main class
# ══════════════════════════════════════════════════════════════

class ValidatedPDFExtractor:
    """
    Wrapper around pdf.extractor.PDFExtractor that adds validation,
    parental height extraction, bone age extraction, and structured output.
    """

    def __init__(self, confidence_threshold: float = CONFIDENCE_THRESHOLD):
        self._extractor = PDFExtractor()
        self.confidence_threshold = confidence_threshold

    def extract(self, pdf_path: str,
                patient_birth_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Extract and validate data from a PDF file.

        Args:
            pdf_path: Path to the PDF file.
            patient_birth_date: If known, used for age-appropriate validation.

        Returns:
            Structured dict with patient info, measurements, parental heights,
            bone age, warnings, and metadata.
        """
        try:
            raw: ExtractedPatientData = self._extractor.extract_from_pdf(pdf_path)
        except Exception as e:
            return {
                "success": False,
                "error": f"PDF extraction failed: {str(e)}",
                "source_file": pdf_path,
            }

        return self._process_extracted_data(raw, patient_birth_date)

    def extract_from_text(self, text: str,
                          patient_birth_date: Optional[date] = None) -> Dict[str, Any]:
        """Extract and validate from raw text (for testing)."""
        try:
            raw: ExtractedPatientData = self._extractor.extract_from_text(text)
        except Exception as e:
            return {
                "success": False,
                "error": f"Text extraction failed: {str(e)}",
            }
        return self._process_extracted_data(raw, patient_birth_date)

    def _process_extracted_data(self, raw: ExtractedPatientData,
                                patient_birth_date: Optional[date] = None
                                ) -> Dict[str, Any]:
        """Validate and structure the extracted data."""
        warnings: List[str] = []

        # Use extracted birth date if none provided
        dob = patient_birth_date or raw.birth_date
        validated_dob = _validate_date(dob)
        if dob and not validated_dob:
            warnings.append(f"Birth date {dob} failed validation (future or before 1990)")

        # Validate and filter measurements
        validated_measurements = []
        rejected_count = 0

        for m in (raw.measurements or []):
            entry = self._validate_measurement(m, validated_dob, warnings)
            if entry is not None:
                validated_measurements.append(entry)
            else:
                rejected_count += 1

        if rejected_count > 0:
            warnings.append(
                f"{rejected_count} measurement(s) rejected "
                f"(below confidence {self.confidence_threshold} or invalid values)"
            )

        # Extract parental heights and bone age from raw text
        parental = _extract_parental_heights(raw.raw_text) if raw.raw_text else {
            "father_height_cm": None, "mother_height_cm": None
        }
        bone_age = _extract_bone_age(raw.raw_text) if raw.raw_text else None

        return {
            "success": True,
            "patient": {
                "first_name": raw.first_name or "",
                "last_name": raw.last_name or "",
                "birth_date": validated_dob.isoformat() if validated_dob else None,
                "sex": raw.sex,
                "medical_record_number": raw.medical_record_number or "",
            },
            "measurements": validated_measurements,
            "parental_heights": parental,
            "bone_age_years": bone_age,
            "source_file": raw.source_file or "",
            "warnings": warnings,
            "raw_measurement_count": len(raw.measurements or []),
            "validated_measurement_count": len(validated_measurements),
        }

    def _validate_measurement(self, m: ExtractedMeasurement,
                              birth_date: Optional[date],
                              warnings: List[str]) -> Optional[Dict[str, Any]]:
        """
        Validate a single measurement. Returns a dict or None if rejected.
        """
        # Confidence threshold
        if m.confidence < self.confidence_threshold:
            return None

        # Validate date
        meas_date = _validate_date(m.date)
        if m.date and not meas_date:
            warnings.append(
                f"Measurement date {m.date} invalid (future or before 1990)"
            )
            return None

        # Validate height
        height = _validate_height(m.height_cm)
        if m.height_cm is not None and height is None:
            warnings.append(
                f"Height {m.height_cm} out of range ({MIN_HEIGHT_CM}-{MAX_HEIGHT_CM} cm)"
            )

        # Validate weight
        weight = _validate_weight(m.weight_kg)
        if m.weight_kg is not None and weight is None:
            warnings.append(
                f"Weight {m.weight_kg} out of range ({MIN_WEIGHT_KG}-{MAX_WEIGHT_KG} kg)"
            )

        # Age-appropriate checks
        if birth_date and meas_date:
            if height is not None and not _age_appropriate_height(height, birth_date, meas_date):
                warnings.append(
                    f"Height {height} cm seems implausible for age on {meas_date}"
                )
                height = None
            if weight is not None and not _age_appropriate_weight(weight, birth_date, meas_date):
                warnings.append(
                    f"Weight {weight} kg seems implausible for age on {meas_date}"
                )
                weight = None

        # Must have at least one valid value
        if height is None and weight is None:
            return None

        # Validate head circumference (basic range)
        head_circ = None
        if m.head_circ_cm is not None and 20 <= m.head_circ_cm <= 65:
            head_circ = round(m.head_circ_cm, 1)

        return {
            "date": meas_date.isoformat() if meas_date else None,
            "height_cm": height,
            "weight_kg": weight,
            "head_circ_cm": head_circ,
            "confidence": round(m.confidence, 2),
            "raw_text": m.raw_text or "",
        }
