"""
Growth velocity computation and reference data.

Phase 15: Compute height velocity (cm/year) between consecutive measurements
and provide reference velocity percentile curves by age and sex.

Reference velocity data derived from Tanner/WHO published velocity charts.
"""
from typing import List, Optional
from datetime import date
import math


# ══════════════════════════════════════════════════════════════
#  HEIGHT VELOCITY REFERENCE DATA (approximate, Tanner-based)
#  Format: (age_years, P3, P10, P25, P50, P75, P90, P97)
# ══════════════════════════════════════════════════════════════

VELOCITY_REF_BOYS = [
    # age,  P3,   P10,  P25,  P50,  P75,  P90,  P97
    (1,    9.0,  10.0, 11.0, 12.0, 13.0, 14.0, 15.0),
    (2,    6.0,   6.8,  7.5,  8.5,  9.5,  10.2, 11.0),
    (3,    5.2,   6.0,  6.6,  7.5,  8.4,  9.0,  9.8),
    (4,    4.8,   5.4,  6.0,  6.8,  7.6,  8.2,  8.9),
    (5,    4.4,   5.0,  5.5,  6.2,  7.0,  7.6,  8.2),
    (6,    4.0,   4.6,  5.1,  5.8,  6.5,  7.1,  7.7),
    (7,    3.8,   4.3,  4.8,  5.5,  6.2,  6.8,  7.4),
    (8,    3.5,   4.0,  4.5,  5.2,  5.9,  6.5,  7.1),
    (9,    3.3,   3.8,  4.3,  5.0,  5.7,  6.3,  6.9),
    (10,   3.2,   3.7,  4.2,  4.8,  5.5,  6.2,  6.8),
    (11,   3.2,   3.8,  4.4,  5.2,  6.0,  7.0,  7.8),
    (12,   3.5,   4.2,  5.0,  6.0,  7.2,  8.2,  9.2),
    (13,   4.0,   5.0,  6.2,  7.5,  8.8, 10.0, 10.8),
    (14,   3.5,   4.8,  6.2,  7.8,  9.2, 10.2, 11.0),
    (15,   2.0,   3.0,  4.2,  5.8,  7.5,  8.8,  9.8),
    (16,   1.0,   1.8,  2.5,  3.5,  5.0,  6.2,  7.2),
    (17,   0.5,   0.8,  1.2,  2.0,  3.0,  4.0,  5.0),
    (18,   0.0,   0.2,  0.5,  1.0,  1.8,  2.5,  3.2),
]

VELOCITY_REF_GIRLS = [
    # age,  P3,   P10,  P25,  P50,  P75,  P90,  P97
    (1,    8.5,   9.5, 10.5, 11.5, 12.5, 13.5, 14.5),
    (2,    5.8,   6.5,  7.2,  8.2,  9.2,  10.0, 10.8),
    (3,    5.0,   5.7,  6.3,  7.2,  8.1,  8.8,  9.5),
    (4,    4.5,   5.2,  5.8,  6.5,  7.3,  8.0,  8.6),
    (5,    4.2,   4.8,  5.3,  6.0,  6.8,  7.4,  8.0),
    (6,    3.8,   4.4,  4.9,  5.6,  6.3,  6.9,  7.5),
    (7,    3.6,   4.1,  4.6,  5.3,  6.0,  6.6,  7.2),
    (8,    3.4,   3.9,  4.4,  5.1,  5.8,  6.4,  7.0),
    (9,    3.5,   4.0,  4.6,  5.3,  6.2,  7.0,  7.6),
    (10,   3.8,   4.5,  5.2,  6.2,  7.2,  8.0,  8.8),
    (11,   4.0,   5.0,  6.0,  7.2,  8.2,  9.0,  9.8),
    (12,   2.8,   3.8,  4.8,  6.0,  7.2,  8.0,  8.8),
    (13,   1.5,   2.2,  3.0,  4.0,  5.2,  6.2,  7.0),
    (14,   0.5,   1.0,  1.5,  2.2,  3.2,  4.0,  4.8),
    (15,   0.0,   0.3,  0.8,  1.2,  2.0,  2.8,  3.5),
    (16,   0.0,   0.0,  0.2,  0.5,  1.0,  1.5,  2.0),
]

VELOCITY_PERCENTILES = [3, 10, 25, 50, 75, 90, 97]
VELOCITY_PCT_INDICES = {3: 1, 10: 2, 25: 3, 50: 4, 75: 5, 90: 6, 97: 7}


def _interpolate_velocity_ref(ref_data: list, age: float, pct_idx: int) -> Optional[float]:
    """Interpolate velocity reference at a given age."""
    if age < ref_data[0][0] or age > ref_data[-1][0]:
        return None
    for i in range(len(ref_data) - 1):
        a1, a2 = ref_data[i][0], ref_data[i + 1][0]
        if a1 <= age <= a2:
            frac = (age - a1) / (a2 - a1)
            v1 = ref_data[i][pct_idx]
            v2 = ref_data[i + 1][pct_idx]
            return v1 + frac * (v2 - v1)
    return None


def get_velocity_reference_curves(sex: str) -> List[dict]:
    """Return Plotly-compatible traces for velocity reference percentile curves.

    Returns list of trace dicts for P3, P10, P25, P50, P75, P90, P97.
    """
    ref = VELOCITY_REF_BOYS if sex == "M" else VELOCITY_REF_GIRLS

    # Generate smooth curves at 0.5-year intervals
    age_min = ref[0][0]
    age_max = ref[-1][0]
    ages = []
    a = age_min
    while a <= age_max:
        ages.append(a)
        a += 0.5

    line_styles = {
        3:  {"color": "#DC2626", "dash": "dash",  "width": 0.8},
        10: {"color": "#D97706", "dash": "dash",  "width": 0.8},
        25: {"color": "#65A30D", "dash": "dot",   "width": 0.8},
        50: {"color": "#15803D", "dash": "solid", "width": 1.8},
        75: {"color": "#65A30D", "dash": "dot",   "width": 0.8},
        90: {"color": "#D97706", "dash": "dash",  "width": 0.8},
        97: {"color": "#DC2626", "dash": "dash",  "width": 0.8},
    }

    band_defs = [
        (3, 10,  "rgba(254,202,202,0.35)"),
        (10, 25, "rgba(254,249,195,0.35)"),
        (25, 50, "rgba(209,250,229,0.40)"),
        (50, 75, "rgba(209,250,229,0.40)"),
        (75, 90, "rgba(254,249,195,0.35)"),
        (90, 97, "rgba(254,202,202,0.35)"),
    ]

    traces = []
    curves = {}  # pct -> (ages, values)

    for pct in VELOCITY_PERCENTILES:
        idx = VELOCITY_PCT_INDICES[pct]
        vals = []
        valid_ages = []
        for a in ages:
            v = _interpolate_velocity_ref(ref, a, idx)
            if v is not None:
                valid_ages.append(a)
                vals.append(round(v, 1))

        if not valid_ages:
            continue

        curves[pct] = (valid_ages, vals)
        style = line_styles.get(pct, {"color": "#999", "dash": "dot", "width": 0.5})
        traces.append({
            "name": f"P{pct}" if pct != 50 else "P50 (median)",
            "x": valid_ages,
            "y": vals,
            "mode": "lines",
            "line": style,
            "hovertemplate": f"P{pct}: %{{y:.1f}} cm/yr at age %{{x:.1f}}<extra></extra>",
            "showlegend": pct in (3, 25, 50, 75, 97),
        })

    # Color bands
    bands = []
    for p_low, p_high, color in band_defs:
        if p_low in curves and p_high in curves:
            x_l, y_l = curves[p_low]
            x_h, y_h = curves[p_high]
            bands.append({
                "x": x_l + x_h[::-1],
                "y": y_l + y_h[::-1],
                "fill": "toself",
                "fillcolor": color,
                "line": {"width": 0},
                "showlegend": False,
                "hoverinfo": "skip",
            })

    return bands + traces


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
            midpoint_age_months: float
            midpoint_age_years: float
            velocity_cm_year: float — annualized height velocity
            date_start, date_end: ISO date strings
            interval_months: float
    """
    valid = []
    for m in measurements:
        h = m.get("height_cm")
        d = m.get("date")
        if h is None or d is None:
            continue
        if isinstance(d, str):
            d = date.fromisoformat(d)
        age_months = (d - birth_date).days / 30.4375
        valid.append({"date": d, "height_cm": h, "age_months": age_months})

    if len(valid) < 2:
        return []

    valid.sort(key=lambda x: x["date"])

    velocities = []
    for i in range(len(valid) - 1):
        m1, m2 = valid[i], valid[i + 1]
        delta_months = m2["age_months"] - m1["age_months"]
        if delta_months <= 0:
            continue

        velocity = (m2["height_cm"] - m1["height_cm"]) / (delta_months / 12.0)
        midpoint = (m1["age_months"] + m2["age_months"]) / 2.0

        velocities.append({
            "midpoint_age_months": round(midpoint, 1),
            "midpoint_age_years": round(midpoint / 12.0, 2),
            "velocity_cm_year": round(velocity, 1),
            "date_start": m1["date"].isoformat(),
            "date_end": m2["date"].isoformat(),
            "interval_months": round(delta_months, 1),
        })

    return velocities
