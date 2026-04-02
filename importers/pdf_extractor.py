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
#
# Real-world Hebrew clinic letters (via pdfplumber, reversed text) look like:
#   מ״ס 175 הבוג ,יזקווק אצוממ ,1977 הדיל תנש טרבלא – בא
#   מ״ס 159 הבוג ,הדר הרימדר – םא
# = "אב – אלברט... גובה 175 ס"מ" / "אם – רדמירה... גובה 159 ס"מ"
#
# Key insight: "בא" (father) or "םא" (mother) and "הבוג NUMBER" appear on
# the SAME LINE but with arbitrary text between them. We use line-based matching.

# Father/mother label indicators (both normal and reversed Hebrew)
_FATHER_LABELS = [
    '– בא', '- בא', ':בא', 'בא –', 'בא:', 'אב –', 'אב:', '– אב',
    'father', 'אבא', 'אבא:', 'האב', 'האב:', 'באה', 'באה:',
    'גובה אב', 'גובה האב', 'בא הבוג', 'באה הבוג',
]
_MOTHER_LABELS = [
    '– םא', '- םא', ':םא', 'םא –', 'םא:', 'אם –', 'אם:', '– אם',
    'mother', 'אמא', 'אמא:', 'האם', 'האם:', 'םאה', 'םאה:',
    'גובה אם', 'גובה האם', 'םא הבוג', 'םאה הבוג',
]

# Height value near "הבוג" or "גובה" (both reversed and normal)
_HEIGHT_IN_LINE = re.compile(
    r'(?:מ[״"]ס|cm)?\s*(\d{2,3}(?:\.\d{1,2})?)\s*(?:הבוג|גובה)'
    r'|(?:הבוג|גובה)\s*[:\-]?\s*(\d{2,3}(?:\.\d{1,2})?)',
    re.IGNORECASE,
)

# MPH extraction: "174.5 :(MPH) דעי הבוג" or "גובה יעד (MPH): 174.5"
_MPH_PATTERNS = [
    re.compile(r'(\d{2,3}(?:\.\d{1,2})?)\s*:?\s*\(?MPH\)?.*?הבוג', re.IGNORECASE),
    re.compile(r'הבוג.*?\(?MPH\)?\s*:?\s*(\d{2,3}(?:\.\d{1,2})?)', re.IGNORECASE),
    re.compile(r'גובה\s*יעד.*?(\d{2,3}(?:\.\d{1,2})?)', re.IGNORECASE),
    re.compile(r'(\d{2,3}(?:\.\d{1,2})?)\s*.*?דעי\s*הבוג', re.IGNORECASE),
    re.compile(r'(?:MPH|mph|target\s*height)\s*[:\-=]?\s*(\d{2,3}(?:\.\d{1,2})?)', re.IGNORECASE),
]


def _extract_height_from_line(line: str) -> Optional[float]:
    """Extract a height value from a line containing הבוג/גובה."""
    m = _HEIGHT_IN_LINE.search(line)
    if m:
        val_str = m.group(1) or m.group(2)
        if val_str:
            val = float(val_str)
            if 0.5 <= val <= 2.2:
                val *= 100
            if 130 <= val <= 220:
                return round(val, 1)
    return None


def _extract_parental_heights(text: str) -> Dict[str, Optional[float]]:
    """Extract father's and mother's heights from text using line-based matching.

    Handles pdfplumber reversed Hebrew where labels and values appear on the
    same line but with arbitrary text between them.
    """
    result = {"father_height_cm": None, "mother_height_cm": None, "mph_from_letter": None}

    # Split into lines and search each
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')

    for line in lines:
        line_lower = line.lower().strip()
        if not line_lower:
            continue

        # Check if this line mentions father
        if result["father_height_cm"] is None:
            for label in _FATHER_LABELS:
                if label in line_lower or label in line:
                    h = _extract_height_from_line(line)
                    if h and 150 <= h <= 210:  # father plausible range
                        result["father_height_cm"] = h
                        break

        # Check if this line mentions mother
        if result["mother_height_cm"] is None:
            for label in _MOTHER_LABELS:
                if label in line_lower or label in line:
                    h = _extract_height_from_line(line)
                    if h and 140 <= h <= 200:  # mother plausible range
                        result["mother_height_cm"] = h
                        break

    # Extract MPH if stated in the letter
    for pat in _MPH_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                mph = float(m.group(1))
                if 140 <= mph <= 200:
                    result["mph_from_letter"] = round(mph, 1)
                    break
            except (ValueError, IndexError):
                continue

    return result


# ── Bone Age Extraction ───────────────────────────────────────

_BONE_AGE_PATTERNS = [
    # Hebrew: "גיל עצמות תואם 12 שנים ו-6 חודשים" (with intervening words like תואם/מתאים/הינו/של)
    r'(?:גיל\s*עצמות|תומצע\s*ליג)(?:\s*[:\-=]?\s*(?:תואם|מתאים|הינו|של|כ[- ]?|approximately|corresponds?\s*to)?\s*)(\d{1,2})\s*(?:שנ(?:ים|ה|\')?)\s*(?:ו[- ]?)?\s*(\d{1,2})\s*(?:חוד(?:שים|ש|\')?)',
    # Hebrew: "גיל עצמות תואם 12" / "גיל עצמות: 12.5" (number after optional intervening word)
    r'(?:גיל\s*עצמות|תומצע\s*ליג)(?:\s*[:\-=]?\s*(?:תואם|מתאים|הינו|של|כ[- ]?|approximately|corresponds?\s*to)?\s*)(\d{1,2}(?:[./]\d{1,2})?)\s*(?:שנ(?:ים|ה|\')?)?',
    # Hebrew: "גיל עצמות: 12 שנים ו-6 חודשים" / "12 שנ' ו-6 חו'"
    r'(?:גיל\s*עצמות|תומצע\s*ליג)\s*[:\-=]?\s*(\d{1,2})\s*(?:שנ(?:ים|ה|\')?)\s*(?:ו[- ]?)?\s*(\d{1,2})\s*(?:חוד(?:שים|ש|\')?)',
    # Hebrew reversed (RTL issues): "תומצע ליג" = "גיל עצמות" reversed
    r'(?:תומצע\s*ליג|ליג\s*תומצע)\s*[:\-=]?\s*(\d{1,2}(?:[./]\d{1,2})?)',
    # English variants
    r'(?:bone\s*age|BA|skeletal\s*age)\s*[:\-=]?\s*(\d{1,2}(?:[./]\d{1,2})?)\s*(?:y(?:ears?)?|שנים)?',
    # "BA: 12y6m" or "BA: 12;6" or "BA: 12 y 6 m"
    r'(?:bone\s*age|BA)\s*[:\-=]?\s*(\d{1,2})\s*[y;]\s*(\d{1,2})\s*m?',
    r'(?:bone\s*age|BA)\s*[:\-=]?\s*(\d{1,2})\s*(?:years?|y)\s*(?:and\s*)?(\d{1,2})\s*(?:months?|m)',
    # "BA = XX" at start of line
    r'^BA\s*[=:]\s*(\d{1,2}(?:\.\d{1,2})?)',
    # "G.P. bone age" / "bone age according to G-P"
    r'(?:G\.?P\.?\s*)?bone\s*age\s*[:\-=]?\s*(\d{1,2}(?:[./]\d{1,2})?)',
    # Inline in text: "bone age of 12.5 years"
    r'bone\s*age\s+(?:of\s+)?(\d{1,2}(?:\.\d)?)\s*(?:years?|y)',
]


# ── Tanner staging extraction ────────────────────────────────
def _extract_tanner_staging(text: str) -> Dict[str, Optional[any]]:
    """Extract Tanner staging data from clinic letter text.
    Returns dict with tanner_breast, tanner_pubic_hair, tanner_genital,
    testicular_volume, menarche."""
    result = {
        "tanner_breast": None,
        "tanner_pubic_hair": None,
        "tanner_genital": None,
        "testicular_volume": None,
        "menarche": None,
    }

    if not text:
        return result

    # Normalize text for matching
    t = text

    # ── Breast (B1-B5) ──
    for pat in [
        r'(?:breast|שד|B)\s*(?:stage)?\s*[:\-=]?\s*([1-5])',
        r'\bB([1-5])\b(?!\d)',          # B3 standalone
        r'(?:טאנר|tanner)\s*[:\-]?\s*B([1-5])',
    ]:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            result["tanner_breast"] = int(m.group(1))
            break

    # ── Pubic hair (P1-P5 / PH1-PH5) ──
    for pat in [
        r'(?:pubic|שער\s*ערו|ערווה|P\.?H\.?|PH)\s*(?:hair|stage)?\s*[:\-=]?\s*([1-5])',
        r'(?:טאנר|tanner)\s*[:\-]?\s*(?:B[1-5]\s*)?P([1-5])',
        r'\bP([1-5])\b(?!\d|th|%|\.)',  # P3 standalone (not P50, P3rd, etc.)
    ]:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            result["tanner_pubic_hair"] = int(m.group(1))
            break

    # ── Genital (G1-G5) ──
    for pat in [
        r'(?:genital|גניטלי|איבר\s*מין|G)\s*(?:stage)?\s*[:\-=]?\s*([1-5])',
        r'(?:טאנר|tanner)\s*[:\-]?\s*(?:.*?)?G([1-5])',
        r'\bG([1-5])\b(?!\d|Hz)',       # G3 standalone (not GHz)
    ]:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            result["tanner_genital"] = int(m.group(1))
            break

    # ── Testicular volume (TV / אשכים) ──
    for pat in [
        r'(?:TV|test(?:icular)?\s*vol(?:ume)?|אשכ(?:ים|י)?|נפח\s*אשכ)\s*[:\-=]?\s*(\d{1,2}(?:\.\d)?)\s*(?:ml|מ"ל|cc)?',
        r'(?:אשכ(?:ים|י)?)\s*[:\-]?\s*(\d{1,2}(?:\.\d)?)',
    ]:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            vol = float(m.group(1))
            if 1 <= vol <= 30:  # valid testicular volume range
                result["testicular_volume"] = vol
                break

    # ── Menarche ──
    for pat in [
        r'(?:menarche|מנארכה|וסת\s*ראשונה|menarch)\s*[:\-]?\s*([+✓✔]|yes|כן|חיובי)',
        r'(?:menarche|מנארכה)\s*[:\-]?\s*(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})',
    ]:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            result["menarche"] = True
            break

    return result


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
        tanner = _extract_tanner_staging(raw.raw_text) if raw.raw_text else {}

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
            "tanner_staging": tanner,
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
