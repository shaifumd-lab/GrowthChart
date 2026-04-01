"""
Growth velocity computation.

Phase 15: Compute height velocity (cm/year) between consecutive measurements.

Given a list of measurements sorted by date, compute the annualized growth
velocity between each consecutive pair that has valid height data.
"""
from typing import List, Tuple, Optional
from datetime import date


def compute_velocity(
    measurements: List[dict],
    birth_date: date,
) -> List[dict]:
    """Compute growth velocity between consecutive height measurements.

    Args:
        measurements: List of dicts with 'date' (ISO string or date object),
                      'height_cm' (float or None), sorted by date ascending.
        birth_date: Patient's birth date for age computation.

    Returns:
        List of dicts with:
            midpoint_age_months: float — age at midpoint between the two measurements
            midpoint_age_years: float — same in years
            velocity_cm_year: float — annualized height velocity
            date_start: str — ISO date of first measurement
            date_end: str — ISO date of second measurement
            interval_months: float — time between measurements in months
    """
    # Filter to measurements with valid height
    valid = []
    for m in measurements:
        h = m.get("height_cm")
        d = m.get("date")
        if h is None or d is None:
            continue
        if isinstance(d, str):
            d = date.fromisoformat(d)
        age_months = (d - birth_date).days / 30.4375
        valid.append({
            "date": d,
            "height_cm": h,
            "age_months": age_months,
        })

    if len(valid) < 2:
        return []

    # Sort by date (should already be sorted, but ensure)
    valid.sort(key=lambda x: x["date"])

    velocities = []
    for i in range(len(valid) - 1):
        m1 = valid[i]
        m2 = valid[i + 1]

        age1 = m1["age_months"]
        age2 = m2["age_months"]
        h1 = m1["height_cm"]
        h2 = m2["height_cm"]

        delta_months = age2 - age1
        if delta_months <= 0:
            continue

        # Annualized velocity: (h2 - h1) / (delta in years)
        velocity = (h2 - h1) / (delta_months / 12.0)
        midpoint_months = (age1 + age2) / 2.0

        velocities.append({
            "midpoint_age_months": round(midpoint_months, 1),
            "midpoint_age_years": round(midpoint_months / 12.0, 2),
            "velocity_cm_year": round(velocity, 1),
            "date_start": m1["date"].isoformat(),
            "date_end": m2["date"].isoformat(),
            "interval_months": round(delta_months, 1),
        })

    return velocities
