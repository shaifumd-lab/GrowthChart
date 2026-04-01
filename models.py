"""Data models for GrowthChart application."""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Tuple
import math


@dataclass
class Patient:
    id: Optional[int] = None
    first_name: str = ""
    last_name: str = ""
    birth_date: Optional[date] = None
    sex: str = "M"  # 'M' or 'F'
    medical_record_number: str = ""
    notes: str = ""
    created_at: Optional[datetime] = None
    # Phase 12-16 additions
    mother_height_cm: Optional[float] = None
    father_height_cm: Optional[float] = None
    mph_cm: Optional[float] = None
    mph_user_edited: bool = False
    syndrome: str = ""

    @property
    def full_name(self) -> str:
        raw = f"{self.first_name} {self.last_name}".strip()
        return self._fix_hebrew_display(raw)

    @staticmethod
    def _fix_hebrew_display(text: str) -> str:
        """Fix Hebrew text that may have reversed characters from pdfplumber."""
        if not text:
            return text
        if not any('\u0590' <= c <= '\u05FF' for c in text):
            return text
        # Hebrew final-form letters: if a word STARTS with one, it's reversed
        FINALS = set('םןץףך')
        words = text.split()
        fixed = []
        for w in words:
            heb_chars = [c for c in w if '\u0590' <= c <= '\u05FF']
            if heb_chars and heb_chars[0] in FINALS:
                fixed.append(w[::-1])
            else:
                fixed.append(w)
        return ' '.join(fixed)

    @property
    def age_str(self) -> str:
        if not self.birth_date:
            return ""
        today = date.today()
        years = today.year - self.birth_date.year
        months = today.month - self.birth_date.month
        if months < 0:
            years -= 1
            months += 12
        if today.day < self.birth_date.day:
            months -= 1
            if months < 0:
                years -= 1
                months += 12
        if years > 0:
            return f"{years}y {months}m"
        return f"{months}m"

    @property
    def sex_label(self) -> str:
        return "Male" if self.sex == "M" else "Female"

    @property
    def mph_calculated(self) -> Optional[float]:
        """Calculate mid-parental height from parental heights.
        Boys: (father + mother + 13) / 2
        Girls: (father + mother - 13) / 2
        """
        if self.father_height_cm is None or self.mother_height_cm is None:
            return None
        if self.sex == "M":
            return (self.father_height_cm + self.mother_height_cm + 13) / 2
        else:
            return (self.father_height_cm + self.mother_height_cm - 13) / 2

    @property
    def target_height_range(self) -> Optional[Tuple[float, float]]:
        """Return (low, high) target height range based on MPH.
        Boys: MPH +/- 8.5 cm
        Girls: MPH +/- 7.5 cm
        Uses user-edited MPH if available, otherwise calculated.
        """
        mph = self.mph_cm if self.mph_user_edited and self.mph_cm is not None else self.mph_calculated
        if mph is None:
            return None
        margin = 8.5 if self.sex == "M" else 7.5
        return (mph - margin, mph + margin)

    @property
    def effective_mph(self) -> Optional[float]:
        """Return the effective MPH value (user-edited or calculated)."""
        if self.mph_user_edited and self.mph_cm is not None:
            return self.mph_cm
        return self.mph_calculated


@dataclass
class Measurement:
    id: Optional[int] = None
    patient_id: Optional[int] = None
    date: Optional[date] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    head_circ_cm: Optional[float] = None
    notes: str = ""
    source_pdf: str = ""
    created_at: Optional[datetime] = None
    # Phase 12-16 addition
    bone_age_years: Optional[float] = None

    # Computed fields (populated by z-score engine)
    age_days: Optional[int] = None
    age_months: Optional[float] = None
    bmi: Optional[float] = None
    height_zscore: Optional[float] = None
    weight_zscore: Optional[float] = None
    bmi_zscore: Optional[float] = None
    height_percentile: Optional[float] = None
    weight_percentile: Optional[float] = None
    bmi_percentile: Optional[float] = None

    def compute_age(self, birth_date: date):
        """Compute age in days and months from birth date."""
        if self.date and birth_date:
            delta = self.date - birth_date
            self.age_days = delta.days
            self.age_months = delta.days / 30.4375  # Average days per month

    def compute_bmi(self):
        """Compute BMI from height and weight."""
        if self.height_cm and self.weight_kg and self.height_cm > 0:
            height_m = self.height_cm / 100
            self.bmi = round(self.weight_kg / (height_m ** 2), 2)

    @property
    def age_str(self) -> str:
        if self.age_months is None:
            return ""
        years = int(self.age_months // 12)
        months = int(self.age_months % 12)
        if years > 0:
            return f"{years}y {months}m"
        return f"{months}m"

    @property
    def height_sds_str(self) -> str:
        if self.height_zscore is not None:
            return f"{self.height_zscore:+.2f}"
        return "—"

    @property
    def weight_sds_str(self) -> str:
        if self.weight_zscore is not None:
            return f"{self.weight_zscore:+.2f}"
        return "—"

    @property
    def bmi_sds_str(self) -> str:
        if self.bmi_zscore is not None:
            return f"{self.bmi_zscore:+.2f}"
        return "—"
