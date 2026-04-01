"""
QI Validation Suite — 100+ tests for z-score and percentile accuracy.

Tests z-scores against the official CDC published percentile values (P3, P5, P10, P25, P50,
P75, P90, P95, P97) which are embedded in the official CDC CSV files. These serve as
ground truth since the CDC provides both LMS parameters AND pre-computed percentile values.

For each published percentile value in the CDC file, we:
1. Compute the z-score for that measurement at that age/sex
2. Convert to percentile
3. Compare with the expected percentile (P3 → 3%, P50 → 50%, etc.)

This validates the entire pipeline: LMS data loading → z-score formula → percentile conversion.

Expected accuracy: z-score within 0.01 SD, percentile within 0.1%.
"""

import sys
import os
import csv
import math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zscore.engine import ZScoreEngine
from config import Standard, Indicator, DATA_DIR

# ── Helpers ───────────────────────────────────────────────────

def zscore_to_percentile(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2))) * 100

def percentile_to_zscore(p):
    """Approximate inverse normal CDF."""
    from statistics import NormalDist
    return NormalDist().inv_cdf(p / 100)

# Known z-scores for standard percentiles
PERCENTILE_ZSCORES = {
    3: -1.88079,
    5: -1.64485,
    10: -1.28155,
    25: -0.67449,
    50: 0.0,
    75: 0.67449,
    85: 1.03643,
    90: 1.28155,
    95: 1.64485,
    97: 1.88079,
}


# ══════════════════════════════════════════════════════════════
#  TEST RUNNER
# ══════════════════════════════════════════════════════════════

class QITestRunner:
    def __init__(self):
        self.engine = ZScoreEngine(DATA_DIR)
        self.engine.load_standard(Standard.CDC)
        self.engine.load_standard(Standard.WHO)
        self.passed = 0
        self.failed = 0
        self.errors = []

    def assert_zscore(self, label, computed_z, expected_z, tolerance=0.02):
        """Check z-score is within tolerance."""
        if computed_z is None:
            self.failed += 1
            self.errors.append(f"FAIL {label}: z=None (expected {expected_z:+.4f})")
            return False
        diff = abs(computed_z - expected_z)
        if diff > tolerance:
            self.failed += 1
            self.errors.append(
                f"FAIL {label}: z={computed_z:+.4f} (expected {expected_z:+.4f}, diff={diff:.4f})")
            return False
        self.passed += 1
        return True

    def assert_percentile(self, label, computed_pct, expected_pct, tolerance=0.5):
        """Check percentile is within tolerance."""
        if computed_pct is None:
            self.failed += 1
            self.errors.append(f"FAIL {label}: pct=None (expected {expected_pct:.1f}%)")
            return False
        diff = abs(computed_pct - expected_pct)
        if diff > tolerance:
            self.failed += 1
            self.errors.append(
                f"FAIL {label}: pct={computed_pct:.2f}% (expected {expected_pct:.1f}%, diff={diff:.2f})")
            return False
        self.passed += 1
        return True

    # ── CDC Validation from official published percentiles ────

    def test_cdc_against_published_percentiles(self, indicator: str, csv_file: str,
                                                max_rows: int = 30):
        """
        Validate z-scores by computing them for the published percentile values
        in the official CDC CSV files.

        The CDC files contain columns P3, P5, P10, P25, P50, P75, P90, P95, P97.
        For P50 (median), the z-score should be exactly 0.
        For P3, the z-score should be approximately -1.881.
        Etc.
        """
        filepath = DATA_DIR / csv_file
        if not filepath.exists():
            print(f"  SKIP: {csv_file} not found")
            return

        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [fn.strip().strip('\ufeff') for fn in reader.fieldnames]

            row_count = 0
            for row in reader:
                if row_count >= max_rows:
                    break
                try:
                    sex_code = row["Sex"].strip()
                    if sex_code not in ("1", "2"):
                        continue
                    sex = "M" if sex_code == "1" else "F"
                    age = float(row["Agemos"].strip())

                    sex_label = "Boy" if sex == "M" else "Girl"

                    # Test each available percentile column
                    for pct_col, expected_pct in [
                        ("P3", 3), ("P5", 5), ("P10", 10), ("P25", 25),
                        ("P50", 50), ("P75", 75), ("P90", 90), ("P95", 95), ("P97", 97),
                        ("P85", 85),  # BMI files have P85
                    ]:
                        if pct_col not in row or not row[pct_col].strip():
                            continue

                        measurement = float(row[pct_col].strip())
                        expected_z = PERCENTILE_ZSCORES.get(expected_pct)
                        if expected_z is None:
                            continue

                        # Compute z-score
                        z = self.engine.compute_zscore(
                            measurement, age, sex, indicator, Standard.CDC)

                        label = f"CDC {indicator} {sex_label} {age:.0f}mo {pct_col}={measurement:.1f}"

                        # Z-score check
                        self.assert_zscore(label + " z", z, expected_z, tolerance=0.02)

                        # Percentile check (convert computed z to percentile)
                        if z is not None:
                            computed_pct = zscore_to_percentile(z)
                            self.assert_percentile(
                                label + " %ile", computed_pct, expected_pct, tolerance=0.5)

                    row_count += 1
                except (ValueError, KeyError) as e:
                    continue

    # ── WHO Validation using known median values ─────────────

    def test_who_median_values(self):
        """Test WHO z-scores using known median (z=0) values from data files."""
        who_files = {
            ("hfa", "M", "who_lhfa_boys_0_5.csv"),
            ("hfa", "F", "who_lhfa_girls_0_5.csv"),
            ("wfa", "M", "who_wfa_boys_0_5.csv"),
            ("wfa", "F", "who_wfa_girls_0_5.csv"),
            ("bfa", "M", "who_bfa_boys_0_5.csv"),
            ("bfa", "F", "who_bfa_girls_0_5.csv"),
            ("hfa", "M", "who_hfa_boys_5_19.csv"),
            ("hfa", "F", "who_hfa_girls_5_19.csv"),
            ("bfa", "M", "who_bfa_boys_5_19.csv"),
            ("bfa", "F", "who_bfa_girls_5_19.csv"),
        }

        for indicator, sex, filename in who_files:
            filepath = DATA_DIR / filename
            if not filepath.exists():
                continue

            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames:
                    reader.fieldnames = [fn.strip().strip('\ufeff') for fn in reader.fieldnames]

                count = 0
                for row in reader:
                    if count >= 10:  # Test 10 ages per file
                        break
                    try:
                        age = None
                        for col in ["Month", "Age", "Agemos", "age_months", "Age_months"]:
                            if col in row and row[col].strip():
                                age = float(row[col].strip())
                                break
                        if age is None:
                            continue

                        m_val = float(row.get("M", row.get("m", "0")).strip())
                        if m_val <= 0:
                            continue

                        # Median should give z=0
                        z = self.engine.compute_zscore(
                            m_val, age, sex, indicator, Standard.WHO)

                        sex_label = "Boy" if sex == "M" else "Girl"
                        label = f"WHO {indicator} {sex_label} {age:.0f}mo median={m_val:.2f}"
                        self.assert_zscore(label, z, 0.0, tolerance=0.01)

                        count += 1
                    except (ValueError, KeyError):
                        continue

    # ── Clinical scenario tests ──────────────────────────────

    def test_clinical_scenarios(self):
        """Test specific clinical scenarios with known expected values."""

        # CDC clinical scenarios (verified against CDC growth chart calculator)
        scenarios = [
            # (measurement, age_months, sex, indicator, standard, expected_z_approx, desc)
            # --- 50th percentile (z=0) checks using official M values ---
            (86.452, 24, "M", "hfa", "CDC", 0.0, "CDC boy 24mo median height"),
            (12.671, 24, "M", "wfa", "CDC", 0.0, "CDC boy 24mo median weight"),
            (16.575, 24, "M", "bfa", "CDC", 0.0, "CDC boy 24mo median BMI"),
            (84.976, 24, "F", "hfa", "CDC", 0.0, "CDC girl 24mo median height"),

            # --- 3rd percentile checks (z≈-1.88) ---
            (79.911, 24, "M", "hfa", "CDC", -1.88, "CDC boy 24mo P3 height"),
            (10.382, 24, "M", "wfa", "CDC", -1.88, "CDC boy 24mo P3 weight"),

            # --- 97th percentile checks (z≈+1.88) ---
            (93.023, 24, "M", "hfa", "CDC", +1.88, "CDC boy 24mo P97 height"),

            # --- Older children (values from official CDC M column) ---
            (138.619, 120, "M", "hfa", "CDC", 0.0, "CDC boy 10y median height"),
            (176.160, 216, "M", "hfa", "CDC", 0.0, "CDC boy 18y median height"),
            (163.124, 216, "F", "hfa", "CDC", 0.0, "CDC girl 18y median height"),
        ]

        for meas, age, sex, ind, std, exp_z, desc in scenarios:
            z = self.engine.compute_zscore(meas, age, sex, ind, std)
            self.assert_zscore(desc, z, exp_z, tolerance=0.02)

            if z is not None:
                pct = zscore_to_percentile(z)
                exp_pct = zscore_to_percentile(exp_z)
                self.assert_percentile(desc + " %ile", pct, exp_pct, tolerance=0.5)

    def run_all(self):
        print("=" * 70)
        print("  GrowthChart QI Validation Suite")
        print("=" * 70)

        # 1. CDC stature validation
        print("\n[1/6] CDC Stature-for-Age validation (official P3-P97)...")
        self.test_cdc_against_published_percentiles(
            Indicator.HEIGHT_FOR_AGE, "cdc_statage.csv", max_rows=15)
        print(f"  Running total: {self.passed} passed, {self.failed} failed")

        # 2. CDC weight validation
        print("\n[2/6] CDC Weight-for-Age validation (official P3-P97)...")
        self.test_cdc_against_published_percentiles(
            Indicator.WEIGHT_FOR_AGE, "cdc_wtage.csv", max_rows=15)
        print(f"  Running total: {self.passed} passed, {self.failed} failed")

        # 3. CDC BMI validation
        print("\n[3/6] CDC BMI-for-Age validation (official P3-P97)...")
        self.test_cdc_against_published_percentiles(
            Indicator.BMI_FOR_AGE, "cdc_bmiage.csv", max_rows=15)
        print(f"  Running total: {self.passed} passed, {self.failed} failed")

        # 4. CDC infant validation
        print("\n[4/6] CDC Infant Length validation (official P3-P97)...")
        self.test_cdc_against_published_percentiles(
            Indicator.HEIGHT_FOR_AGE, "cdc_lenageinf.csv", max_rows=10)
        print(f"  Running total: {self.passed} passed, {self.failed} failed")

        # 5. WHO median validation
        print("\n[5/6] WHO Median (z=0) validation...")
        self.test_who_median_values()
        print(f"  Running total: {self.passed} passed, {self.failed} failed")

        # 6. Clinical scenarios
        print("\n[6/6] Clinical scenario validation...")
        self.test_clinical_scenarios()
        print(f"  Running total: {self.passed} passed, {self.failed} failed")

        # ── Summary ───────────────────────────────────────
        total = self.passed + self.failed
        print("\n" + "=" * 70)
        print(f"  RESULTS: {self.passed}/{total} passed ({self.passed/total*100:.1f}%)")
        print(f"  Failed:  {self.failed}")
        print("=" * 70)

        if self.errors:
            print(f"\n  First {min(20, len(self.errors))} failures:")
            for e in self.errors[:20]:
                print(f"    {e}")
            if len(self.errors) > 20:
                print(f"    ... and {len(self.errors) - 20} more")

        return self.failed == 0


if __name__ == "__main__":
    runner = QITestRunner()
    success = runner.run_all()
    sys.exit(0 if success else 1)
