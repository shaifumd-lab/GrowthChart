"""
Mid-Parental Height (MPH) calculation.

Phase 12: Parental heights and target height computation.

Boys:  MPH = (father_height + mother_height + 13) / 2
Girls: MPH = (father_height + mother_height - 13) / 2

Target range:
  Boys:  MPH +/- 8.5 cm
  Girls: MPH +/- 7.5 cm
"""
from typing import Optional, Tuple, Dict


def calculate_mph(
    father_height_cm: float,
    mother_height_cm: float,
    sex: str,
) -> float:
    """Calculate mid-parental height.

    Args:
        father_height_cm: Father's height in cm.
        mother_height_cm: Mother's height in cm.
        sex: 'M' for boys, 'F' for girls.

    Returns:
        Mid-parental height in cm.
    """
    if sex == "M":
        return (father_height_cm + mother_height_cm + 13) / 2
    else:
        return (father_height_cm + mother_height_cm - 13) / 2


def target_height_range(
    mph_cm: float,
    sex: str,
) -> Tuple[float, float]:
    """Calculate target height range around MPH.

    Args:
        mph_cm: Mid-parental height in cm.
        sex: 'M' for boys, 'F' for girls.

    Returns:
        Tuple of (low, high) in cm.
    """
    margin = 8.5 if sex == "M" else 7.5
    return (mph_cm - margin, mph_cm + margin)


def mph_summary(
    father_height_cm: Optional[float],
    mother_height_cm: Optional[float],
    sex: str,
    user_edited_mph: Optional[float] = None,
) -> Optional[Dict]:
    """Return a complete MPH summary dict for API responses.

    Args:
        father_height_cm: Father's height in cm (can be None).
        mother_height_cm: Mother's height in cm (can be None).
        sex: 'M' or 'F'.
        user_edited_mph: User-overridden MPH value (optional).

    Returns:
        Dict with mph, range_low, range_high, father_height, mother_height,
        or None if insufficient data.
    """
    if user_edited_mph is not None:
        mph = user_edited_mph
    elif father_height_cm is not None and mother_height_cm is not None:
        mph = calculate_mph(father_height_cm, mother_height_cm, sex)
    else:
        return None

    low, high = target_height_range(mph, sex)
    return {
        "mph": round(mph, 1),
        "range_low": round(low, 1),
        "range_high": round(high, 1),
        "father_height_cm": father_height_cm,
        "mother_height_cm": mother_height_cm,
    }
