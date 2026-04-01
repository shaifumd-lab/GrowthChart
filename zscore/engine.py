"""
Z-Score computation engine using the LMS method.

The LMS method (Cole, 1990) uses three parameters:
    L (Lambda) - Box-Cox power for skewness
    M (Mu)     - Median
    S (Sigma)  - Generalized coefficient of variation

Z-score formula:
    Z = ((measurement / M)^L - 1) / (L * S)   when L ≠ 0
    Z = ln(measurement / M) / S                when L = 0

Measurement at a given z-score:
    value = M * (1 + L * S * Z)^(1/L)          when L ≠ 0
    value = M * exp(S * Z)                      when L = 0

Supports WHO (0-5 standards, 5-19 references) and CDC (0-20) growth charts.
"""

import math
import csv
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from bisect import bisect_left
from config import DATA_DIR, Standard, Indicator


class LMSTable:
    """Holds LMS parameters for a single indicator/sex combination."""

    def __init__(self):
        self.ages: List[float] = []   # age in months
        self.L: List[float] = []
        self.M: List[float] = []
        self.S: List[float] = []

    def add_point(self, age_months: float, l: float, m: float, s: float):
        self.ages.append(age_months)
        self.L.append(l)
        self.M.append(m)
        self.S.append(s)

    def sort_and_deduplicate(self):
        """Sort by age and remove duplicates (keep first occurrence)."""
        if not self.ages:
            return
        combined = sorted(zip(self.ages, self.L, self.M, self.S), key=lambda x: x[0])
        # Deduplicate: keep first occurrence of each age
        seen = set()
        unique = []
        for item in combined:
            if item[0] not in seen:
                seen.add(item[0])
                unique.append(item)
        self.ages = [x[0] for x in unique]
        self.L = [x[1] for x in unique]
        self.M = [x[2] for x in unique]
        self.S = [x[3] for x in unique]

    def interpolate_lms(self, age_months: float) -> Optional[Tuple[float, float, float]]:
        """Get L, M, S at a given age by linear interpolation."""
        if not self.ages:
            return None
        if age_months < self.ages[0] or age_months > self.ages[-1]:
            return None

        idx = bisect_left(self.ages, age_months)

        # Exact match
        if idx < len(self.ages) and abs(self.ages[idx] - age_months) < 0.001:
            return (self.L[idx], self.M[idx], self.S[idx])

        # Interpolate
        if idx == 0:
            return (self.L[0], self.M[0], self.S[0])
        if idx >= len(self.ages):
            return (self.L[-1], self.M[-1], self.S[-1])

        i0 = idx - 1
        i1 = idx
        frac = (age_months - self.ages[i0]) / (self.ages[i1] - self.ages[i0])

        l = self.L[i0] + frac * (self.L[i1] - self.L[i0])
        m = self.M[i0] + frac * (self.M[i1] - self.M[i0])
        s = self.S[i0] + frac * (self.S[i1] - self.S[i0])
        return (l, m, s)

    def value_at_zscore(self, age_months: float, z: float) -> Optional[float]:
        """Get measurement value at a given z-score and age."""
        lms = self.interpolate_lms(age_months)
        if lms is None:
            return None
        l, m, s = lms
        if abs(l) < 1e-10:
            return m * math.exp(s * z)
        else:
            val = m * (1 + l * s * z) ** (1 / l)
            return val if val > 0 else None

    @property
    def age_range(self) -> Tuple[float, float]:
        if not self.ages:
            return (0, 0)
        return (self.ages[0], self.ages[-1])


class ZScoreEngine:
    """Main z-score calculation engine supporting WHO and CDC standards."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self._tables: Dict[str, LMSTable] = {}
        self._loaded_standards = set()
        # CDC pre-computed percentile curves: {(indicator, sex, pct): [(age, value), ...]}
        self._cdc_percentiles: Dict[tuple, List[Tuple[float, float]]] = {}

    def _table_key(self, standard: str, indicator: str, sex: str) -> str:
        return f"{standard}_{indicator}_{sex}"

    def load_standard(self, standard: str):
        """Load all data files for a given standard (WHO or CDC)."""
        if standard in self._loaded_standards:
            return
        if standard == Standard.WHO:
            self._load_who_data()
        elif standard == Standard.CDC:
            self._load_cdc_data()
        self._loaded_standards.add(standard)

    def ensure_loaded(self, standard: str):
        if standard not in self._loaded_standards:
            self.load_standard(standard)

    def compute_zscore(self, measurement: float, age_months: float,
                       sex: str, indicator: str,
                       standard: str = Standard.WHO) -> Optional[float]:
        """
        Compute z-score for a measurement.

        Args:
            measurement: The measurement value (cm, kg, or kg/m²)
            age_months: Age in months
            sex: 'M' or 'F'
            indicator: One of Indicator constants (hfa, wfa, bfa)
            standard: Standard.WHO or Standard.CDC

        Returns:
            Z-score or None if out of range
        """
        self.ensure_loaded(standard)
        key = self._table_key(standard, indicator, sex)
        table = self._tables.get(key)
        if table is None:
            return None

        lms = table.interpolate_lms(age_months)
        if lms is None:
            return None

        l, m, s = lms
        if m <= 0 or s <= 0:
            return None

        try:
            if abs(l) < 1e-10:
                z = math.log(measurement / m) / s
            else:
                z = ((measurement / m) ** l - 1) / (l * s)

            # Restrict to bounded SD (WHO restricts to ±5 for most indicators)
            z = max(-5.0, min(5.0, z))
            return round(z, 4)
        except (ValueError, ZeroDivisionError):
            return None

    def compute_percentile(self, zscore: float) -> float:
        """Convert z-score to percentile."""
        return round(0.5 * (1 + math.erf(zscore / math.sqrt(2))) * 100, 2)

    def get_percentile_curve(self, standard: str, indicator: str, sex: str,
                             zscore: float,
                             age_min: float = None, age_max: float = None,
                             step: float = 1.0) -> List[Tuple[float, float]]:
        """
        Get a list of (age_months, value) points for a percentile curve.
        Interpolates at regular intervals for smooth chart display.

        Args:
            step: interval in months between points (default 1.0 = monthly)
            age_min/age_max: optional range to limit output
        """
        self.ensure_loaded(standard)
        key = self._table_key(standard, indicator, sex)
        table = self._tables.get(key)
        if table is None:
            return []

        t_min, t_max = table.age_range
        if age_min is not None:
            t_min = max(t_min, age_min)
        if age_max is not None:
            t_max = min(t_max, age_max)

        if t_max <= t_min:
            return []

        # Generate evenly-spaced ages for smooth curves
        points = []
        age = t_min
        while age <= t_max:
            val = table.value_at_zscore(age, zscore)
            if val is not None and val > 0:
                points.append((age, val))
            age += step

        return points

    def get_percentile_curve_for_chart(self, standard: str, indicator: str,
                                         sex: str, percentile: int,
                                         age_min: float = None,
                                         age_max: float = None) -> List[Tuple[float, float]]:
        """
        Get a percentile curve for chart display.

        For CDC: uses pre-computed P-columns from official CSV files (ground truth).
        For WHO: computes from LMS using the z-score for the given percentile.

        Returns: list of (age_months, measurement_value) pairs.
        """
        from config import PERCENTILE_ZSCORES
        self.ensure_loaded(standard)

        if standard == Standard.CDC:
            # Use pre-computed CDC percentile values (ground truth)
            pct_key = (indicator, sex, percentile)
            raw = self._cdc_percentiles.get(pct_key, [])
            if raw:
                # Sort by age and filter to range
                sorted_pts = sorted(set(raw))
                if age_min is not None:
                    sorted_pts = [(a, v) for a, v in sorted_pts if a >= age_min]
                if age_max is not None:
                    sorted_pts = [(a, v) for a, v in sorted_pts if a <= age_max]
                return sorted_pts

        # WHO or CDC fallback: compute from LMS using z-score
        zscore = PERCENTILE_ZSCORES.get(percentile)
        if zscore is None:
            return []
        return self.get_percentile_curve(
            standard, indicator, sex, zscore,
            age_min=age_min, age_max=age_max, step=1.0)

    def get_age_range(self, standard: str, indicator: str, sex: str) -> Tuple[float, float]:
        """Get the valid age range for an indicator."""
        self.ensure_loaded(standard)
        key = self._table_key(standard, indicator, sex)
        table = self._tables.get(key)
        if table:
            return table.age_range
        return (0, 0)

    # ── WHO Data Loading ──────────────────────────────────────

    def _load_who_data(self):
        """Load WHO growth standard/reference data."""
        # IMPORTANT: Load 5-19 FIRST, then 0-5. Stable sort+dedup keeps
        # the first occurrence, so the 0-5 standard values at month 61
        # (the overlap point) take priority over the 5-19 reference.
        who_files = [
            # 5-19 years (references) — load first
            ("hfa", "M", "who_hfa_boys_5_19.csv"),
            ("hfa", "F", "who_hfa_girls_5_19.csv"),
            ("bfa", "M", "who_bfa_boys_5_19.csv"),
            ("bfa", "F", "who_bfa_girls_5_19.csv"),
            ("wfa", "M", "who_wfa_boys_5_10.csv"),
            ("wfa", "F", "who_wfa_girls_5_10.csv"),
            # 0-5 years (standards) — load second, wins at overlap
            ("hfa", "M", "who_lhfa_boys_0_5.csv"),
            ("hfa", "F", "who_lhfa_girls_0_5.csv"),
            ("wfa", "M", "who_wfa_boys_0_5.csv"),
            ("wfa", "F", "who_wfa_girls_0_5.csv"),
            ("bfa", "M", "who_bfa_boys_0_5.csv"),
            ("bfa", "F", "who_bfa_girls_0_5.csv"),
        ]
        for indicator, sex, filename in who_files:
            filepath = self.data_dir / filename
            if filepath.exists():
                key = self._table_key(Standard.WHO, indicator, sex)
                if key not in self._tables:
                    self._tables[key] = LMSTable()
                self._load_csv_into_table(self._tables[key], filepath)
        # Sort and deduplicate all WHO tables
        for key, table in self._tables.items():
            if key.startswith("WHO"):
                table.sort_and_deduplicate()

    # ── CDC Data Loading ──────────────────────────────────────

    def _load_cdc_data(self):
        """Load CDC growth chart data."""
        # IMPORTANT: Load the primary (older-child) files FIRST, then infant files.
        # Python's stable sort + dedup keeps the FIRST value for duplicate ages.
        # At ages 24-36mo where both infant and child files overlap, we want
        # the standing-height/child-weight values (not recumbent-length/infant).
        cdc_mappings = [
            ("cdc_statage.csv", "hfa"),      # stature 24-240mo (load first!)
            ("cdc_lenageinf.csv", "hfa"),    # infant length 0-36mo
            ("cdc_wtage.csv", "wfa"),        # weight 24-240mo (load first!)
            ("cdc_wtageinf.csv", "wfa"),     # infant weight 0-36mo
            ("cdc_bmiage.csv", "bfa"),       # BMI 24-240mo
        ]
        for filename, indicator in cdc_mappings:
            filepath = self.data_dir / filename
            if filepath.exists():
                self._load_cdc_csv(filepath, indicator)
        # Sort and deduplicate all CDC tables
        for key, table in self._tables.items():
            if key.startswith("CDC"):
                table.sort_and_deduplicate()

    def _load_cdc_csv(self, filepath: Path, indicator: str):
        """Load a CDC CSV file. CDC format has Sex, Agemos, L, M, S columns."""
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()

            # Find the header line
            header_idx = 0
            for i, line in enumerate(lines):
                stripped = line.strip().lower()
                if "sex" in stripped and ("agemos" in stripped or "age" in stripped):
                    header_idx = i
                    break

            reader = csv.DictReader(lines[header_idx:])
            # Normalize fieldnames: strip BOM and whitespace
            if reader.fieldnames:
                reader.fieldnames = [f.strip().strip('\ufeff') for f in reader.fieldnames]

            # Detect which percentile columns exist in this file
            pct_cols = []
            if reader.fieldnames:
                for fn in reader.fieldnames:
                    if fn.startswith("P") and fn[1:].isdigit():
                        pct_cols.append((fn, int(fn[1:])))

            for row in reader:
                try:
                    sex_code = row.get("Sex", "").strip()
                    if sex_code not in ("1", "2"):
                        continue
                    sex = "M" if sex_code == "1" else "F"
                    age = float(row.get("Agemos", "0").strip())
                    l = float(row.get("L", "0").strip())
                    m = float(row.get("M", "0").strip())
                    s = float(row.get("S", "0").strip())

                    # LMS table (for z-score computation)
                    key = self._table_key(Standard.CDC, indicator, sex)
                    if key not in self._tables:
                        self._tables[key] = LMSTable()
                    self._tables[key].add_point(age, l, m, s)

                    # Pre-computed percentile values (for chart curves)
                    for col_name, pct_num in pct_cols:
                        val_str = row.get(col_name, "").strip()
                        if val_str:
                            pct_key = (indicator, sex, pct_num)
                            if pct_key not in self._cdc_percentiles:
                                self._cdc_percentiles[pct_key] = []
                            self._cdc_percentiles[pct_key].append(
                                (age, float(val_str)))
                except (ValueError, KeyError):
                    continue
        except Exception as e:
            print(f"Warning: Could not load CDC data from {filepath}: {e}")

    # ── Generic CSV Loading ───────────────────────────────────

    def _load_csv_into_table(self, table: LMSTable, filepath: Path):
        """Load a CSV with columns: Month (or Age), L, M, S."""
        try:
            with open(filepath, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # Try common column names
                        age = None
                        for col in ["Month", "Age", "Agemos", "age_months", "Age_months"]:
                            if col in row:
                                age = float(row[col])
                                break
                        if age is None:
                            continue

                        l = float(row.get("L", row.get("l", "0")))
                        m = float(row.get("M", row.get("m", "0")))
                        s = float(row.get("S", row.get("s", "0")))
                        table.add_point(age, l, m, s)
                    except (ValueError, KeyError):
                        continue
        except Exception as e:
            print(f"Warning: Could not load data from {filepath}: {e}")
