"""
Syndromic growth chart reference data.

Phase 16: Turner syndrome and Down syndrome height-for-age reference curves.

Provides approximate percentile curves (P3, P50, P97) from published references:
- Turner syndrome (girls only): Lyon et al.
- Down syndrome (boys and girls): Zemel et al. 2015

Data is stored as age-value pairs and linearly interpolated for smooth curves.
"""
import math
from typing import Dict, List, Optional, Tuple

# ── Supported syndromes ──────────────────────────────────────
SUPPORTED_SYNDROMES = ["Turner", "Down"]

# ── Turner Syndrome (girls only) — height for age ────────────
# Ages in years, heights in cm
TURNER_GIRLS = {
    "P3":  [(2, 78),  (4, 90),  (6, 100), (8, 108), (10, 115), (12, 121), (14, 126), (16, 128), (18, 129)],
    "P50": [(2, 83),  (4, 96),  (6, 107), (8, 116), (10, 124), (12, 131), (14, 137), (16, 140), (18, 141)],
    "P97": [(2, 88),  (4, 102), (6, 114), (8, 124), (10, 133), (12, 141), (14, 148), (16, 152), (18, 153)],
}

# ── Down Syndrome — height for age ────────────────────────────
DOWN_BOYS = {
    "P3":  [(2, 76),  (4, 87),  (6, 96),  (8, 104), (10, 111), (12, 118), (14, 126), (16, 134), (18, 139)],
    "P50": [(2, 83),  (4, 95),  (6, 106), (8, 115), (10, 123), (12, 131), (14, 140), (16, 149), (18, 154)],
    "P97": [(2, 90),  (4, 103), (6, 116), (8, 126), (10, 135), (12, 144), (14, 154), (16, 164), (18, 169)],
}

DOWN_GIRLS = {
    "P3":  [(2, 74),  (4, 85),  (6, 94),  (8, 102), (10, 109), (12, 116), (14, 122), (16, 126), (18, 127)],
    "P50": [(2, 81),  (4, 93),  (6, 103), (8, 112), (10, 120), (12, 128), (14, 135), (16, 139), (18, 141)],
    "P97": [(2, 88),  (4, 101), (6, 112), (8, 122), (10, 131), (12, 140), (14, 148), (16, 152), (18, 155)],
}


def _interpolate_curve(points: List[Tuple[float, float]], step_years: float = 0.25) -> Tuple[List[float], List[float]]:
    """Linearly interpolate a set of (age_years, value) points into a smooth curve.

    Returns (ages_years, values) arrays suitable for Plotly.
    """
    if not points or len(points) < 2:
        return [], []

    points = sorted(points, key=lambda p: p[0])
    age_min = points[0][0]
    age_max = points[-1][0]

    ages = []
    values = []

    age = age_min
    while age <= age_max + 0.001:  # small epsilon for float comparison
        # Find bracketing points
        for i in range(len(points) - 1):
            a1, v1 = points[i]
            a2, v2 = points[i + 1]
            if a1 <= age <= a2:
                if a2 == a1:
                    val = v1
                else:
                    frac = (age - a1) / (a2 - a1)
                    val = v1 + frac * (v2 - v1)
                ages.append(round(age, 2))
                values.append(round(val, 1))
                break
        age += step_years

    return ages, values


def _get_syndrome_data(syndrome: str, sex: str) -> Optional[Dict[str, List[Tuple[float, float]]]]:
    """Get the raw reference data for a syndrome/sex combination.

    Returns dict mapping percentile label to list of (age_years, value) points,
    or None if the combination is not available.
    """
    syndrome_upper = syndrome.strip().capitalize()

    if syndrome_upper == "Turner":
        if sex == "F":
            return TURNER_GIRLS
        return None  # Turner only applies to girls

    if syndrome_upper == "Down":
        if sex == "M":
            return DOWN_BOYS
        elif sex == "F":
            return DOWN_GIRLS

    return None


def get_syndromic_percentile_curves(
    syndrome: str,
    sex: str,
    percentiles: List[int] = None,
) -> Optional[List[dict]]:
    """Generate Plotly-compatible traces for syndromic growth curves.

    Args:
        syndrome: 'Turner' or 'Down'.
        sex: 'M' or 'F'.
        percentiles: List of percentiles to include (default: [3, 50, 97]).

    Returns:
        List of Plotly trace dicts, or None if syndrome/sex combo is not available.
    """
    if percentiles is None:
        percentiles = [3, 50, 97]

    data = _get_syndrome_data(syndrome, sex)
    if data is None:
        return None

    # Style mapping for syndromic curves
    SYND_STYLES = {
        3:  {"dash": "dash", "width": 1.2},
        50: {"dash": "solid", "width": 2.0},
        97: {"dash": "dash", "width": 1.2},
    }

    traces = []
    for pct in percentiles:
        key = f"P{pct}"
        if key not in data:
            continue

        ages, values = _interpolate_curve(data[key])
        if not ages:
            continue

        style = SYND_STYLES.get(pct, {"dash": "dot", "width": 1.0})
        traces.append({
            "name": f"{syndrome} P{pct}",
            "x": ages,
            "y": values,
            "mode": "lines",
            "line": {
                "color": "#9333EA",  # purple
                **style,
            },
            "hovertemplate": f"{syndrome} P{pct}: %{{y:.1f}} cm at %{{x:.1f}} years<extra></extra>",
            "showlegend": True,
        })

    return traces if traces else None
