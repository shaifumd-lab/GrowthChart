"""
PDF data extraction for clinic summaries and growth tables.

Extracts birth date, measurement dates, heights, and weights from:
1. Digital PDFs (text-based) using pdfplumber
2. Scanned PDFs using Tesseract OCR via pytesseract

Handles Hebrew RTL text (pdfplumber often reverses Hebrew chars).
"""

import re
import unicodedata
from datetime import date, datetime
from typing import List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass


@dataclass
class ExtractedMeasurement:
    """A single measurement extracted from a PDF."""
    date: Optional[date] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    head_circ_cm: Optional[float] = None
    raw_text: str = ""
    confidence: float = 0.0  # 0-1


@dataclass
class ExtractedPatientData:
    """All data extracted from a PDF."""
    birth_date: Optional[date] = None
    first_name: str = ""
    last_name: str = ""
    sex: Optional[str] = None
    medical_record_number: str = ""
    measurements: List[ExtractedMeasurement] = None
    raw_text: str = ""
    source_file: str = ""

    def __post_init__(self):
        if self.measurements is None:
            self.measurements = []


# ── Hebrew RTL Helpers ────────────────────────────────────────

def _is_hebrew(ch: str) -> bool:
    """Check if a character is a Hebrew letter."""
    return '\u0590' <= ch <= '\u05FF'

def _reverse_hebrew_runs(text: str) -> str:
    """
    Reverse contiguous Hebrew character runs in a string.
    pdfplumber often extracts RTL text with Hebrew chars in visual (reversed)
    order. This restores logical order so regex can match Hebrew words.

    Example: '141.7 הבוג 31.7 לקשמ' → '141.7 גובה 31.7 משקל'
    """
    result = []
    hebrew_buf = []

    for ch in text:
        if _is_hebrew(ch) or (hebrew_buf and ch == '"'):
            # Accumulate Hebrew chars (including ״ geresh/gershayim)
            hebrew_buf.append(ch)
        else:
            if hebrew_buf:
                result.extend(reversed(hebrew_buf))
                hebrew_buf = []
            result.append(ch)
    if hebrew_buf:
        result.extend(reversed(hebrew_buf))

    return "".join(result)


def _normalize_hebrew_text(text: str) -> str:
    """Normalize extracted text: reverse Hebrew runs, clean whitespace."""
    lines = text.split("\n")
    normalized = []
    for line in lines:
        normalized.append(_reverse_hebrew_runs(line))
    return "\n".join(normalized)


# ── Date Patterns ─────────────────────────────────────────────

DATE_PATTERNS = [
    (r'(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})', 'dmy'),
    (r'(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})', 'ymd'),
    (r'(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2})\b', 'dmy_short'),
]

def _parse_date(groups: tuple, fmt: str) -> Optional[date]:
    try:
        if fmt == 'dmy':
            d, m, y = int(groups[0]), int(groups[1]), int(groups[2])
            if 1 <= m <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100:
                return date(y, m, d)
        elif fmt == 'ymd':
            y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
            if 1 <= m <= 12 and 1 <= d <= 31:
                return date(y, m, d)
        elif fmt == 'dmy_short':
            d, m, y = int(groups[0]), int(groups[1]), int(groups[2])
            y += 2000 if y < 50 else 1900
            if 1 <= m <= 12 and 1 <= d <= 31:
                return date(y, m, d)
    except (ValueError, IndexError):
        pass
    return None

def _find_all_dates(text: str) -> List[Tuple[date, int, int]]:
    """Find all dates in text. Returns (date, start_pos, end_pos)."""
    results = []
    for pattern, fmt in DATE_PATTERNS:
        for match in re.finditer(pattern, text):
            d = _parse_date(match.groups(), fmt)
            if d:
                results.append((d, match.start(), match.end()))
    return results


# ══════════════════════════════════════════════════════════════
#  PDFExtractor
# ══════════════════════════════════════════════════════════════

class PDFExtractor:
    """Extract growth data from PDF documents."""

    def extract_from_pdf(self, pdf_path: str) -> ExtractedPatientData:
        result = ExtractedPatientData(source_file=pdf_path)

        text = self._extract_text_digital(pdf_path)
        if not text or len(text.strip()) < 20:
            text = self._extract_text_ocr(pdf_path)

        if text:
            result.raw_text = text
            # Normalize Hebrew RTL
            norm = _normalize_hebrew_text(text)
            self._parse_text(norm, text, result)

        return result

    def extract_from_text(self, text: str) -> ExtractedPatientData:
        result = ExtractedPatientData(raw_text=text)
        norm = _normalize_hebrew_text(text)
        self._parse_text(norm, text, result)
        return result

    # ── Text Extraction ───────────────────────────────────

    def _extract_text_digital(self, pdf_path: str) -> str:
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            if row:
                                text_parts.append("\t".join(
                                    str(cell) if cell else "" for cell in row
                                ))
            return "\n".join(text_parts)
        except Exception as e:
            print(f"Digital PDF extraction failed: {e}")
            return ""

    def _extract_text_ocr(self, pdf_path: str) -> str:
        try:
            from PIL import Image
            import pytesseract
            from config import TESSERACT_CMD
            if Path(TESSERACT_CMD).exists():
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(pdf_path, dpi=300)
            except ImportError:
                import pypdfium2 as pdfium
                pdf_doc = pdfium.PdfDocument(pdf_path)
                images = []
                for page in pdf_doc:
                    bitmap = page.render(scale=4)
                    images.append(bitmap.to_pil())
                pdf_doc.close()
            text_parts = []
            for img in images:
                text = pytesseract.image_to_string(img, lang="heb+eng", config="--psm 6")
                text_parts.append(text)
            return "\n".join(text_parts)
        except Exception as e:
            print(f"OCR extraction failed: {e}")
            return ""

    # ── Main Parse ────────────────────────────────────────

    def _parse_text(self, norm_text: str, raw_text: str, result: ExtractedPatientData):
        """
        Parse text for patient data.
        norm_text = Hebrew-normalized text (Hebrew runs reversed to logical order)
        raw_text  = original extracted text (for fallback matching)
        """
        # Search both for most fields
        both = norm_text + "\n" + raw_text

        result.birth_date = self._find_birth_date(both)
        # Name uses raw_text specifically (needs char reversal for pdfplumber)
        self._find_patient_name(raw_text, result)
        result.sex = self._find_sex(both)
        result.medical_record_number = self._find_mrn(both)
        result.measurements = self._find_measurements(both, result.birth_date)

    # ── Birth Date ────────────────────────────────────────

    def _find_birth_date(self, text: str) -> Optional[date]:
        """
        Find birth date using multiple strategies:
        1. Labeled: "תאריך לידה:" / "DOB:" followed by date
        2. Context: date near "גיל:" (age) — in Hebrew clinic letters the
           DOB appears right after the age field
        3. Earliest date that looks like a DOB (before 18 years ago)
        """
        # Strategy 1: labeled birth date (Hebrew + English, both normal and reversed)
        bd_labels = [
            r'תאריך\s*לידה', r'ת\.?\s*לידה', r'תל"ד', r'תל״ד',
            r'הדיל\s*ךיראת', r'הדיל\s*\.?ת',   # reversed Hebrew
            r'נולד\s*(?:ביום|בתאריך)', r'נולדה\s*(?:ביום|בתאריך)',  # "born on"
            r'(?:ביום|בתאריך)\s*(?:דלונ|הדלונ)',  # reversed "born on"
            r'(?:date\s*of\s*)?birth\s*(?:date)?', r'd\.?o\.?b\.?',
            r'born\s*(?:on)?',
        ]
        for label in bd_labels:
            for dp, fmt in DATE_PATTERNS:
                pat = label + r'\s*[:\-]?\s*' + dp
                match = re.search(pat, text, re.IGNORECASE)
                if match:
                    # groups after the label capture
                    all_groups = match.groups()
                    d = _parse_date(all_groups[-3:], fmt)
                    if d and d.year < date.today().year - 1:
                        return d

        # Strategy 2: date near "גיל:" (age) field — common in Hebrew letters
        # Pattern: "DD/MM/YYYY  13.7  :ליג" or "גיל: 13.7  DD/MM/YYYY"
        age_labels = [r'ליג', r'גיל', r'age']
        for label in age_labels:
            # Look for label with a date nearby (within ~40 chars)
            pat = label + r'.{0,40}?(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4})'
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                d = self._try_parse_date(match.group(1))
                if d and d.year < date.today().year - 1:
                    return d

            # Reversed: date ... age_label
            pat2 = r'(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}).{0,40}?' + label
            match = re.search(pat2, text, re.IGNORECASE)
            if match:
                d = self._try_parse_date(match.group(1))
                if d and d.year < date.today().year - 1:
                    return d

        # Strategy 3: look for the earliest plausible DOB
        all_dates = _find_all_dates(text)
        today = date.today()
        dob_candidates = [d for d, s, e in all_dates
                         if d.year < today.year - 1 and d.year > today.year - 25]
        if dob_candidates:
            return min(dob_candidates)  # earliest = most likely DOB

        return None

    # ── Patient Name ──────────────────────────────────────

    def _find_patient_name(self, text: str, result: ExtractedPatientData):
        """
        Find patient name from Hebrew clinic letter patterns.

        In RTL PDFs extracted by pdfplumber, text comes in VISUAL order:
          "221232846 :ההזמ רפסמ/ז.ת . :החפשמ םש לאנתנ בייניב :יטרפ םש"
        Where values appear BEFORE their labels (reading left-to-right).

        We search BOTH the raw text (visual order with reversed chars)
        and the normalized text (chars fixed, still visual word order).
        """
        # ── Strategy 1: Colon-delimited parsing ─────────────
        # In RTL visual text, fields are separated by colons:
        # "221232846 :ההזמ רפסמ/ז.ת . :החפשמ םש לאנתנ בייניב :יטרפ םש"
        # Split on ":" and find segments containing name labels
        #
        # Segment before ":יטרפ םש" is "...החפשמ םש לאנתנ בייניב"
        # We grab the Hebrew words, strip out known label text

        # FIRST NAME: text between ":label_last_name" and ":label_first_name"
        # Visual: "...החפשמ םש **לאנתנ בייניב** :יטרפ םש"
        # In pdfplumber visual LTR output for RTL text, the line looks like:
        #   ". :החפשמ םש **ןטול** **ןרע** :יטרפ םש"
        # Reading RTL: "שם פרטי: ערן לוטן שם משפחה: ."
        # Between "שם משפחה" and "שם פרטי", words appear as:
        #   last_name_reversed first_name_reversed
        # The word closest to ":שם פרטי" is the FIRST name.
        # Capture all Hebrew words between "שם משפחה" and "שם פרטי" labels.
        # pdfplumber's visual LTR word order is inconsistent, so we reverse
        # each word's characters (visual→logical) then reverse the word order
        # (since Hebrew reads R-to-L, the rightmost word in the visual
        # layout — which pdfplumber puts LAST — is actually the first word
        # in logical Hebrew reading order).
        name_between_pat = r'(?:החפשמ\s*םש|משפחה\s*שם)\s+([\u0590-\u05FF]+(?:\s+[\u0590-\u05FF]+){0,3})\s*:\s*(?:יטרפ\s*םש|פרטי\s*שם)'
        m = re.search(name_between_pat, text)
        if m:
            raw = m.group(1).strip()
            heb_words = re.findall(r'[\u0590-\u05FF]+', raw)
            if heb_words:
                # Reverse each word's characters (pdfplumber visual → logical)
                logical_words = [w[::-1] for w in heb_words]
                # NOTE: pdfplumber word order varies between PDFs —
                # we keep the extracted order. User can adjust in import UI.
                result.first_name = " ".join(logical_words)

        # Fallback: last name from token before ":שם משפחה"
        if not result.last_name:
            for pat in [
                r'(\S+)\s*:\s*(?:החפשמ\s*םש|משפחה\s*שם)',
            ]:
                m = re.search(pat, text)
                if m:
                    raw = m.group(1).strip().strip('.')
                    heb_words = re.findall(r'[\u0590-\u05FF]+', raw)
                    if heb_words:
                        result.last_name = " ".join(w[::-1] for w in heb_words)
                    break

        # ── Strategy 2: Logical order "label: name" ───────
        if not result.first_name:
            m = re.search(
                r'(?:שם\s*פרטי)\s*[:\-]\s*([\u0590-\u05FF]+(?:\s+[\u0590-\u05FF]+){0,3})',
                text
            )
            if m:
                result.first_name = m.group(1).strip()

        if not result.last_name:
            m = re.search(
                r'(?:שם\s*משפחה)\s*[:\-]\s*([\u0590-\u05FF]+(?:\s+[\u0590-\u05FF]+){0,3})',
                text
            )
            if m:
                name = m.group(1).strip()
                if name and name != '.':
                    result.last_name = name

    # ── Sex ───────────────────────────────────────────────

    def _find_sex(self, text: str) -> Optional[str]:
        # Hebrew male indicators (both normal and reversed)
        male = [r'\bזכר\b', r'\bבן\b', r'\bרכז\b', r'\bנב\b', r'\bmale\b', r'\bboy\b', r'\bילד\b', r'\bדלי\b']
        female = [r'\bנקבה\b', r'\bבת\b', r'\bהבקנ\b', r'\bתב\b', r'\bfemale\b', r'\bgirl\b', r'\bילדה\b', r'\bהדלי\b']

        # Also detect from Tanner staging (TV = testes, male-only)
        if re.search(r'TV\s*=\s*\d', text):
            return "M"
        # Menarche = female
        if re.search(r'(?:menarche|מנארכה|הכרנמ)', text, re.IGNORECASE):
            return "F"

        for p in male:
            if re.search(p, text, re.IGNORECASE):
                return "M"
        for p in female:
            if re.search(p, text, re.IGNORECASE):
                return "F"
        return None

    # ── MRN ───────────────────────────────────────────────

    def _find_mrn(self, text: str) -> str:
        patterns = [
            r'(?:ת\.?ז\.?|ז\.?ת)\s*[:/\-]?\s*(\d{6,9})',
            r'(\d{9})\s*[:\-]?\s*(?:ת\.?ז|ז\.?ת)',
            # Reversed: "ז.ת" → "ת.ז" patterns for raw text
            r'(\d{9})\s*[:\-]?\s*(?:ההזמ\s*רפסמ|הנמזה\s*רפסמ)',
            r'(?:MRN|ID)\s*[:\-]?\s*(\d{5,10})',
            r'(?:הזמנה|ההזמ)\s*(?:מספר|רפסמ)?\s*[:/\-]?\s*(\d{6,10})',
            # Standalone 9-digit number at start of line (likely Israeli ID)
            r'^(\d{9})\s',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    # ══════════════════════════════════════════════════════
    #  MEASUREMENT EXTRACTION
    # ══════════════════════════════════════════════════════

    def _find_measurements(self, text: str, birth_date: Optional[date] = None
                          ) -> List[ExtractedMeasurement]:
        """
        Find measurements using explicit labeled patterns.
        STRICT: only accept lines with labeled height/weight keywords,
        not bare numbers. This prevents false positives from random numbers.
        """
        measurements = []

        # ── Strategy 1: Explicit labeled lines ────────────
        # Look for lines with Hebrew/English height + weight labels
        # Example (normalized): "11/11/2025  משקל 31.7  גובה 141.7"
        # Example (raw):        "141.7 הבוג 31.7 לקשמ 11/11/2025"
        lines = text.split("\n")
        for line in lines:
            m = self._parse_labeled_measurement(line)
            if m:
                measurements.append(m)

        # ── Strategy 1.5: Date-line + measurement-lines pattern ──
        # Common in Hebrew clinic letters:
        #   3.7.2024                          ← date on its own line
        #   51.1 לקשמ 150.4 הבוג             ← measurements (labeled or bare)
        #   27.11.2024
        #   151.5 הבוג
        #   12.8.2025
        #   54.8 154.9                        ← bare numbers: weight height
        if not measurements:
            measurements = self._parse_date_then_measurements(text)

        # ── Strategy 1.6: Multi-line "value :label" blocks ──
        if not measurements:
            measurements = self._parse_labeled_value_block(text)

        # ── Strategy 2: Physical exam block ───────────────
        if not measurements:
            measurements = self._parse_exam_block(text)

        # ── Validate & filter ─────────────────────────────
        if birth_date:
            measurements = self._validate_measurements(measurements, birth_date)

        # Deduplicate
        seen = set()
        unique = []
        for m in measurements:
            key = (m.date, m.height_cm, m.weight_kg)
            if key not in seen:
                seen.add(key)
                unique.append(m)

        return unique

    def _parse_labeled_measurement(self, line: str) -> Optional[ExtractedMeasurement]:
        """
        Parse a line ONLY if it has explicitly labeled height/weight.
        Must find a keyword like "גובה"/"משקל"/"height"/"weight" adjacent to a number.
        """
        m = ExtractedMeasurement(raw_text=line.strip())

        # Height keywords (Hebrew normal + reversed + English)
        # (?![/.\-]\d) prevents matching date fragments like "11/11"
        # Also handle RTL "value :label" format and height in meters
        ht_patterns = [
            r'(\d{2,3}(?:\.\d{1,2})?)\s*(?:גובה|הבוג|height|cm|ס"מ|מ"ס)',
            r'(?:גובה|הבוג|אורך|ךרוא|height|length|ht)\s*[:\-=]?\s*(\d{2,3}(?:\.\d{1,2})?)(?![/.\-]\d)',
            # RTL visual: "value :label" — number before colon+label
            r'(\d{2,3}(?:\.\d{1,2})?)\s*:\s*(?:גובה|הבוג)',
            # Height in meters (1.XX format) near height keyword
            r'(1\.\d{1,2})\s*(?:גובה|הבוג|height|m\b)',
            r'(?:גובה|הבוג|height)\s*[:\-=]?\s*(1\.\d{1,2})\b',
            r'(1\.\d{1,2})\s*:\s*(?:גובה|הבוג)',
        ]
        # Weight keywords
        wt_patterns = [
            r'(\d{1,3}(?:\.\d{1,2})?)\s*(?:משקל|לקשמ|weight|kg|ק"ג|ג"ק)',
            r'(?:משקל|לקשמ|weight|wt)\s*[:\-=]?\s*(\d{1,3}(?:\.\d{1,2})?)(?![/.\-]\d)',
            # RTL visual: "value :label"
            r'(\d{1,3}(?:\.\d{1,2})?)\s*:\s*(?:משקל|לקשמ)',
        ]

        # Find height (strict: must have label)
        for pat in ht_patterns:
            match = re.search(pat, line, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1))
                    # Height in meters? Convert to cm
                    if 0.4 <= val <= 2.2:
                        val = val * 100
                    if 40 <= val <= 220:
                        m.height_cm = round(val, 1)
                        break
                except ValueError:
                    pass

        # Find weight (strict: must have label)
        for pat in wt_patterns:
            match = re.search(pat, line, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1))
                    if 2 <= val <= 200:
                        m.weight_kg = val
                        break
                except ValueError:
                    pass

        # Need at least one labeled measurement
        if not m.height_cm and not m.weight_kg:
            return None

        # Find date in the same line
        for dp, fmt in DATE_PATTERNS:
            match = re.search(dp, line)
            if match:
                d = _parse_date(match.groups(), fmt)
                if d:
                    m.date = d
                    break

        # REQUIRE a date — measurements without dates are likely from
        # family history (parent heights) or other non-patient data
        if not m.date:
            return None

        # Calculate confidence
        m.confidence = 0.5
        if m.height_cm:
            m.confidence += 0.2
        if m.weight_kg:
            m.confidence += 0.2
        if m.height_cm and m.weight_kg:
            m.confidence += 0.1

        return m

    def _parse_date_then_measurements(self, text: str) -> List[ExtractedMeasurement]:
        """
        Parse pattern: date on its own line, measurements on following lines.
        Common in Hebrew clinic letters where visits are listed chronologically:
            3.7.2024
            51.1 לקשמ 150.4 הבוג
            27.11.2024
            151.5 הבוג
            12.8.2025
            54.8 154.9
        """
        measurements = []
        lines = text.split("\n")
        current_date = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if this line IS a date (standalone or near-standalone)
            date_match = None
            for dp, fmt in DATE_PATTERNS:
                m = re.fullmatch(r'\s*' + dp + r'\s*', line)
                if m:
                    d = _parse_date(m.groups(), fmt)
                    if d:
                        date_match = d
                        break

            if date_match:
                current_date = date_match
                continue

            if current_date is None:
                continue

            # Try labeled extraction on this line
            meas = self._parse_labeled_measurement_no_date(line)

            # If no labeled match, try bare number pairs (height weight)
            if meas is None:
                meas = self._parse_bare_numbers(line)

            if meas and (meas.height_cm or meas.weight_kg):
                meas.date = current_date
                meas.raw_text = f"{current_date} | {line.strip()}"
                measurements.append(meas)
                current_date = None  # consume the date

        return measurements

    def _parse_labeled_measurement_no_date(self, line: str) -> 'ExtractedMeasurement | None':
        """Parse height/weight from a line using labels, without requiring a date."""
        m = ExtractedMeasurement(raw_text=line.strip())

        ht_patterns = [
            r'(\d{2,3}(?:\.\d{1,2})?)\s*(?:גובה|הבוג|height|cm|ס"מ|מ"ס)',
            r'(?:גובה|הבוג|אורך|ךרוא|height|length|ht)\s*[:\-=]?\s*(\d{2,3}(?:\.\d{1,2})?)(?![/.\-]\d)',
            r'(\d{2,3}(?:\.\d{1,2})?)\s*:\s*(?:גובה|הבוג)',
            r'(1\.\d{1,2})\s*(?:גובה|הבוג|height|m\b)',
            r'(?:גובה|הבוג|height)\s*[:\-=]?\s*(1\.\d{1,2})\b',
        ]
        wt_patterns = [
            r'(\d{1,3}(?:\.\d{1,2})?)\s*(?:משקל|לקשמ|weight|kg|ק"ג|ג"ק)',
            r'(?:משקל|לקשמ|weight|wt)\s*[:\-=]?\s*(\d{1,3}(?:\.\d{1,2})?)(?![/.\-]\d)',
            r'(\d{1,3}(?:\.\d{1,2})?)\s*:\s*(?:משקל|לקשמ)',
        ]

        for pat in ht_patterns:
            match = re.search(pat, line, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1))
                    if 0.4 <= val <= 2.2:
                        val = val * 100
                    if 40 <= val <= 220:
                        m.height_cm = round(val, 1)
                        break
                except ValueError:
                    pass

        for pat in wt_patterns:
            match = re.search(pat, line, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1))
                    if 2 <= val <= 200:
                        m.weight_kg = val
                        break
                except ValueError:
                    pass

        if not m.height_cm and not m.weight_kg:
            return None

        m.confidence = 0.7 if (m.height_cm and m.weight_kg) else 0.5
        return m

    def _parse_bare_numbers(self, line: str) -> 'ExtractedMeasurement | None':
        """
        Parse bare number pairs like "54.8 154.9" as weight height.
        The larger number in height range is height, smaller is weight.
        Only if no Hebrew/English keywords are present (those go through labeled).
        """
        # Skip lines with text labels — those should use labeled extraction
        if re.search(r'[a-zA-Z\u0590-\u05FF]{2,}', line):
            return None

        nums = re.findall(r'(\d{1,3}(?:\.\d{1,2})?)', line)
        if len(nums) < 1:
            return None

        values = [float(n) for n in nums]

        # Single number: could be height if in range
        if len(values) == 1:
            v = values[0]
            if 50 <= v <= 220:
                return ExtractedMeasurement(height_cm=round(v, 1), confidence=0.4)
            return None

        # Two numbers: larger in height range = height, smaller = weight
        if len(values) == 2:
            a, b = values
            height, weight = None, None
            # Assign based on typical ranges
            for v in sorted(values, reverse=True):
                if 50 <= v <= 220 and height is None:
                    height = round(v, 1)
                elif 2 <= v <= 150 and weight is None and v != height:
                    weight = round(v, 1)

            if height or weight:
                return ExtractedMeasurement(
                    height_cm=height, weight_kg=weight,
                    confidence=0.4, raw_text=line.strip()
                )

        return None

    def _parse_labeled_value_block(self, text: str) -> List[ExtractedMeasurement]:
        """
        Parse multi-line "value :label" patterns common in Hebrew clinic letters.
        Lines like:
            28.9 :לקשמ    → weight: 28.9
            1.38 :הבוג    → height: 1.38 (meters → 138 cm)
        These appear near dates in the clinical summary.
        """
        height = None
        weight = None

        # Scan for "value :label" patterns across ALL lines
        for line in text.split("\n"):
            line = line.strip()
            # Height in cm: "137.8 :הבוג" or "141.7 הבוג"
            ht_match = re.search(
                r'(\d{2,3}(?:\.\d{1,2})?)\s*:?\s*(?:גובה|הבוג|height)\b', line, re.IGNORECASE)
            if ht_match:
                val = float(ht_match.group(1))
                if 40 <= val <= 220:
                    height = val
                    continue

            # Height in meters: "1.38 :הבוג"
            ht_m_match = re.search(
                r'(1\.\d{1,2})\s*:?\s*(?:גובה|הבוג|height)\b', line, re.IGNORECASE)
            if ht_m_match:
                val = float(ht_m_match.group(1)) * 100
                if 40 <= val <= 220:
                    height = round(val, 1)
                    continue

            # Weight: "28.9 :לקשמ" or "31.7 לקשמ"
            wt_match = re.search(
                r'(\d{1,3}(?:\.\d{1,2})?)\s*:?\s*(?:משקל|לקשמ|weight)\b', line, re.IGNORECASE)
            if wt_match:
                val = float(wt_match.group(1))
                if 2 <= val <= 200:
                    weight = val
                    continue

        if not height and not weight:
            return []

        # Find the most likely visit date (not DOB)
        all_dates = _find_all_dates(text)
        today = date.today()
        visit_dates = [d for d, s, e in all_dates
                      if d.year >= today.year - 2 and d <= today]
        visit_date = max(visit_dates) if visit_dates else None

        if not visit_date:
            return []

        m = ExtractedMeasurement(
            date=visit_date,
            height_cm=height,
            weight_kg=weight,
            confidence=0.8 if (height and weight) else 0.6,
            raw_text=f"ht={height}, wt={weight} on {visit_date}"
        )
        return [m]

    def _parse_exam_block(self, text: str) -> List[ExtractedMeasurement]:
        """
        Parse physical exam blocks in Hebrew clinic letters.
        Pattern: a date line, then height/weight on nearby lines.
        """
        measurements = []

        # Find "physical exam" sections
        # Hebrew: "בדיקה גופנית" (normal) / "תינפוג הקידב" (reversed)
        exam_markers = [
            r'בדיקה\s*גופנית', r'תינפוג\s*הקידב',
            r'physical\s*exam',
        ]

        exam_start = None
        for marker in exam_markers:
            match = re.search(marker, text, re.IGNORECASE)
            if match:
                exam_start = match.start()
                break

        if exam_start is None:
            # Fallback: search entire text for labeled measurement patterns
            return []

        # Search in the 500 chars after the physical exam header
        exam_text = text[exam_start:exam_start + 500]

        # Find all dates in the exam block
        dates_found = _find_all_dates(exam_text)

        for d, d_start, d_end in dates_found:
            # Look for height/weight within ~150 chars of this date
            search_window = exam_text[max(0, d_start - 80):d_end + 150]

            m = ExtractedMeasurement(date=d, raw_text=search_window.strip())

            # Height — labeled patterns + meters support
            for pat in [
                r'(\d{2,3}(?:\.\d{1,2})?)\s*(?:גובה|הבוג|height|cm)',
                r'(?:גובה|הבוג|height)\s*[:\-=]?\s*(\d{2,3}(?:\.\d{1,2})?)(?![/.\-]\d)',
                r'(\d{2,3}(?:\.\d{1,2})?)\s*:\s*(?:גובה|הבוג)',
                r'(1\.\d{1,2})\s*(?:גובה|הבוג|height|:)',
                r'(?:גובה|הבוג)\s*[:\-=]?\s*(1\.\d{1,2})\b',
            ]:
                match = re.search(pat, search_window, re.IGNORECASE)
                if match:
                    val = float(match.group(1))
                    if 0.4 <= val <= 2.2:
                        val = val * 100
                    if 40 <= val <= 220:
                        m.height_cm = round(val, 1)
                        break

            # Weight — labeled patterns
            for pat in [
                r'(\d{1,3}(?:\.\d{1,2})?)\s*(?:משקל|לקשמ|weight|kg)',
                r'(?:משקל|לקשמ|weight)\s*[:\-=]?\s*(\d{1,3}(?:\.\d{1,2})?)(?![/.\-]\d)',
                r'(\d{1,3}(?:\.\d{1,2})?)\s*:\s*(?:משקל|לקשמ)',
            ]:
                match = re.search(pat, search_window, re.IGNORECASE)
                if match:
                    val = float(match.group(1))
                    if 2 <= val <= 200:
                        m.weight_kg = val
                        break

            # Fallback: if weight found but no height, look for a bare number
            # in height range on the same line (common in Hebrew exam: "28.9 לקשמ 137.8")
            if m.weight_kg and not m.height_cm:
                for num_match in re.finditer(r'(\d{2,3}(?:\.\d{1,2})?)', search_window):
                    val = float(num_match.group(1))
                    if 50 <= val <= 220 and val != m.weight_kg:
                        m.height_cm = val
                        break

            if m.height_cm or m.weight_kg:
                m.confidence = 0.7
                if m.height_cm and m.weight_kg:
                    m.confidence = 0.95
                measurements.append(m)

        return measurements

    # ── Validation ────────────────────────────────────────

    def _validate_measurements(self, measurements: List[ExtractedMeasurement],
                              birth_date: date) -> List[ExtractedMeasurement]:
        """
        Filter out unlikely measurements:
        - Date must be after birth date
        - Date must not be in the future
        - Height/weight must be plausible for age
        """
        today = date.today()
        valid = []
        for m in measurements:
            if m.date:
                if m.date < birth_date:
                    continue  # measurement before birth
                if m.date > today:
                    continue  # future date

                age_days = (m.date - birth_date).days
                age_years = age_days / 365.25

                # Height sanity check by age
                if m.height_cm:
                    if age_years < 2 and m.height_cm > 110:
                        m.height_cm = None  # too tall for infant
                    elif age_years > 2 and m.height_cm < 50:
                        m.height_cm = None  # too short for child

                # Weight sanity check by age
                if m.weight_kg:
                    if age_years < 1 and m.weight_kg > 20:
                        m.weight_kg = None
                    elif age_years > 2 and m.weight_kg < 5:
                        m.weight_kg = None

            if m.height_cm or m.weight_kg:
                valid.append(m)

        return valid

    # ── Helpers ───────────────────────────────────────────

    def _try_parse_date(self, text: str) -> Optional[date]:
        """Try to parse a date string in common formats."""
        for pattern, fmt in DATE_PATTERNS:
            match = re.fullmatch(pattern, text.strip())
            if match:
                return _parse_date(match.groups(), fmt)
        return None
