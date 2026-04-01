"""
Patient matching for GrowthChart v2.

Finds existing patients in the database that match imported data.
Uses a priority-based approach:
  1. Israeli ID (ת.ז.) exact match -> auto-merge
  2. Name + DOB match (name similarity > 0.85) -> suggest merge
  3. Fuzzy name only (similarity > 0.9) -> suggest merge
  4. No match -> new patient

Hebrew name similarity uses character-level Levenshtein distance
with final-form letter normalization (ם->מ, ן->נ, ף->פ, ך->כ, ץ->צ).
"""

from datetime import date
from typing import Dict, List, Optional, Any

from models import Patient


# ── Hebrew Final-Form Normalization ───────────────────────────

# Map Hebrew final (sofit) forms to their regular forms
HEBREW_FINAL_MAP = {
    '\u05DD': '\u05DE',  # ם -> מ
    '\u05DF': '\u05E0',  # ן -> נ
    '\u05E3': '\u05E4',  # ף -> פ
    '\u05DA': '\u05DB',  # ך -> כ
    '\u05E5': '\u05E6',  # ץ -> צ
}


def _normalize_hebrew(text: str) -> str:
    """
    Normalize Hebrew text for comparison:
    - Convert final-form letters to regular forms
    - Lowercase Latin characters
    - Strip whitespace and punctuation
    """
    result = []
    for ch in text:
        if ch in HEBREW_FINAL_MAP:
            result.append(HEBREW_FINAL_MAP[ch])
        else:
            result.append(ch)
    normalized = "".join(result).lower().strip()
    # Remove common punctuation and extra spaces
    normalized = "".join(
        ch for ch in normalized
        if ch.isalnum() or ch == ' ' or '\u0590' <= ch <= '\u05FF'
    )
    # Collapse multiple spaces
    return " ".join(normalized.split())


# ── Levenshtein Distance ──────────────────────────────────────

def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute character-level Levenshtein edit distance."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 otherwise
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,       # insert
                prev_row[j + 1] + 1,   # delete
                prev_row[j] + cost,    # substitute
            ))
        prev_row = curr_row

    return prev_row[-1]


def _name_similarity(name1: str, name2: str) -> float:
    """
    Compute similarity between two names (0-1).
    Uses normalized Levenshtein distance on Hebrew-normalized text.
    """
    n1 = _normalize_hebrew(name1)
    n2 = _normalize_hebrew(name2)

    if not n1 and not n2:
        return 1.0
    if not n1 or not n2:
        return 0.0

    # Exact match after normalization
    if n1 == n2:
        return 1.0

    distance = _levenshtein_distance(n1, n2)
    max_len = max(len(n1), len(n2))
    return 1.0 - (distance / max_len)


def _full_name(patient: Patient) -> str:
    """Get full name string from a Patient."""
    parts = []
    if patient.first_name:
        parts.append(patient.first_name)
    if patient.last_name:
        parts.append(patient.last_name)
    return " ".join(parts)


# ══════════════════════════════════════════════════════════════
#  PatientMatcher — main class
# ══════════════════════════════════════════════════════════════

class PatientMatcher:
    """
    Match imported patient data against existing patients in the database.
    """

    # Thresholds
    NAME_DOB_THRESHOLD = 0.85     # name similarity needed when DOB matches
    NAME_ONLY_THRESHOLD = 0.90    # name similarity needed without DOB

    def __init__(self, db):
        """
        Args:
            db: Database instance (from current_app.db) with
                search_patients() and get_all_patients() methods.
        """
        self.db = db

    def find_match(self, first_name: str = "", last_name: str = "",
                   birth_date: Optional[date] = None,
                   medical_record_number: str = "") -> Dict[str, Any]:
        """
        Find a matching patient in the database.

        Returns:
            {
                "match_type": "id_exact" | "name_dob" | "name_fuzzy" | "none",
                "confidence": float (0-1),
                "patient": {patient dict} or None,
                "action": "auto_merge" | "suggest_merge" | "new_patient",
                "candidates": [...],  # other possible matches
            }
        """
        mrn = medical_record_number.strip()
        fname = first_name.strip()
        lname = last_name.strip()
        full = f"{fname} {lname}".strip()

        # Priority 1: Israeli ID exact match
        if mrn and len(mrn) >= 5:
            match = self._match_by_id(mrn)
            if match:
                return match

        # Priority 2: Name + DOB match
        if full and birth_date:
            match = self._match_by_name_dob(fname, lname, birth_date)
            if match:
                return match

        # Priority 3: Fuzzy name only
        if full:
            match = self._match_by_name_only(fname, lname)
            if match:
                return match

        # Priority 4: No match
        return {
            "match_type": "none",
            "confidence": 0.0,
            "patient": None,
            "action": "new_patient",
            "candidates": [],
        }

    def _match_by_id(self, mrn: str) -> Optional[Dict[str, Any]]:
        """Priority 1: exact ID match."""
        results = self.db.search_patients(mrn)
        for patient in results:
            if patient.medical_record_number == mrn:
                return {
                    "match_type": "id_exact",
                    "confidence": 1.0,
                    "patient": self._patient_to_dict(patient),
                    "action": "auto_merge",
                    "candidates": [],
                }
        return None

    def _match_by_name_dob(self, first_name: str, last_name: str,
                           birth_date: date) -> Optional[Dict[str, Any]]:
        """Priority 2: name + DOB match."""
        full_import = f"{first_name} {last_name}".strip()
        candidates = []

        # Search by first and last name fragments
        search_terms = []
        if first_name:
            search_terms.append(first_name)
        if last_name:
            search_terms.append(last_name)

        patients = set()
        for term in search_terms:
            for p in self.db.search_patients(term):
                patients.add(p.id)

        # Also get all patients if the search terms are short (Hebrew names can be tricky)
        if len(full_import) <= 4 or not search_terms:
            for p in self.db.get_all_patients():
                patients.add(p.id)

        checked = []
        for pid in patients:
            p = self.db.get_patient(pid)
            if p is None:
                continue
            checked.append(p)

        for patient in checked:
            full_db = _full_name(patient)
            sim = _name_similarity(full_import, full_db)

            if sim >= self.NAME_DOB_THRESHOLD and patient.birth_date == birth_date:
                candidates.append({
                    "patient": self._patient_to_dict(patient),
                    "similarity": round(sim, 3),
                    "dob_match": True,
                })

        if candidates:
            # Sort by similarity
            candidates.sort(key=lambda c: c["similarity"], reverse=True)
            best = candidates[0]
            return {
                "match_type": "name_dob",
                "confidence": best["similarity"],
                "patient": best["patient"],
                "action": "suggest_merge",
                "candidates": candidates[:5],
            }

        return None

    def _match_by_name_only(self, first_name: str, last_name: str
                            ) -> Optional[Dict[str, Any]]:
        """Priority 3: fuzzy name match only."""
        full_import = f"{first_name} {last_name}".strip()
        candidates = []

        # Get all patients for fuzzy matching
        all_patients = self.db.get_all_patients()

        for patient in all_patients:
            full_db = _full_name(patient)
            if not full_db:
                continue
            sim = _name_similarity(full_import, full_db)

            if sim >= self.NAME_ONLY_THRESHOLD:
                candidates.append({
                    "patient": self._patient_to_dict(patient),
                    "similarity": round(sim, 3),
                    "dob_match": patient.birth_date is not None,
                })

        if candidates:
            candidates.sort(key=lambda c: c["similarity"], reverse=True)
            best = candidates[0]
            return {
                "match_type": "name_fuzzy",
                "confidence": best["similarity"],
                "patient": best["patient"],
                "action": "suggest_merge",
                "candidates": candidates[:5],
            }

        return None

    @staticmethod
    def _patient_to_dict(patient: Patient) -> Dict[str, Any]:
        """Convert a Patient model to a JSON-friendly dict."""
        return {
            "id": patient.id,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "birth_date": patient.birth_date.isoformat() if patient.birth_date else None,
            "sex": patient.sex,
            "medical_record_number": patient.medical_record_number,
            "notes": patient.notes or "",
        }
