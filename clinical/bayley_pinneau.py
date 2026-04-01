"""
Bayley-Pinneau Predicted Adult Height (PAH) calculation.

Phase 14: Predicts adult height from current height and bone age
using the Bayley-Pinneau method.

PAH = current_height / (fraction_of_adult_height_at_bone_age / 100)

The lookup tables contain the percentage of adult height achieved at each
bone age in 0.5-year increments (average maturation rates).
"""
from typing import Optional, Dict

# ── Bayley-Pinneau lookup tables (average maturation) ─────────
# Bone age (years) → percentage of adult height achieved

BP_BOYS = {
    6.0: 65.0,  6.5: 67.0,  7.0: 69.0,  7.5: 71.0,
    8.0: 72.5,  8.5: 74.0,  9.0: 75.5,  9.5: 77.0,
    10.0: 78.3, 10.5: 79.7, 11.0: 81.1, 11.5: 83.0,
    12.0: 84.8, 12.5: 86.9, 13.0: 88.9, 13.5: 91.2,
    14.0: 93.0, 14.5: 94.8, 15.0: 96.1, 15.5: 97.2,
    16.0: 98.0, 16.5: 98.6, 17.0: 99.0, 17.5: 99.4,
    18.0: 99.8,
}

BP_GIRLS = {
    6.0: 70.0,  6.5: 72.0,  7.0: 74.2,  7.5: 76.3,
    8.0: 78.5,  8.5: 80.4,  9.0: 82.3,  9.5: 84.3,
    10.0: 86.0, 10.5: 88.0, 11.0: 89.8, 11.5: 91.5,
    12.0: 93.5, 12.5: 95.5, 13.0: 97.0, 13.5: 98.0,
    14.0: 98.8, 14.5: 99.3, 15.0: 99.6, 15.5: 99.8,
    16.0: 100.0,
}


def _interpolate_percentage(bone_age: float, table: Dict[float, float]) -> Optional[float]:
    """Linearly interpolate the percentage of adult height at a given bone age.

    Returns None if bone_age is outside the table range.
    """
    ages = sorted(table.keys())
    if bone_age < ages[0] or bone_age > ages[-1]:
        return None

    # Exact match
    if bone_age in table:
        return table[bone_age]

    # Find bracketing ages
    for i in range(len(ages) - 1):
        if ages[i] <= bone_age <= ages[i + 1]:
            a1, a2 = ages[i], ages[i + 1]
            p1, p2 = table[a1], table[a2]
            frac = (bone_age - a1) / (a2 - a1)
            return p1 + frac * (p2 - p1)

    return None


def predict_adult_height(
    current_height_cm: float,
    bone_age_years: float,
    sex: str,
) -> Optional[Dict]:
    """Predict adult height using the Bayley-Pinneau method.

    Args:
        current_height_cm: Current measured height in cm.
        bone_age_years: Bone age in years (from hand X-ray).
        sex: 'M' for boys, 'F' for girls.

    Returns:
        Dict with:
            pah: predicted adult height in cm
            pct_achieved: percentage of adult height achieved
            confidence_range: (low, high) — approximate 68% confidence interval
        or None if bone age is outside the table range.
    """
    table = BP_BOYS if sex == "M" else BP_GIRLS
    pct = _interpolate_percentage(bone_age_years, table)

    if pct is None or pct <= 0:
        return None

    pah = current_height_cm / (pct / 100.0)

    # Approximate confidence interval:
    # The Bayley-Pinneau method has an SE of about 2-3 cm for the
    # average maturer tables. We use +/- 2.5 cm as a reasonable estimate.
    se = 2.5
    return {
        "pah": round(pah, 1),
        "pct_achieved": round(pct, 1),
        "confidence_range": (round(pah - se, 1), round(pah + se, 1)),
    }
