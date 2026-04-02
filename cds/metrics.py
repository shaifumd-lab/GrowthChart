"""
CDS Computed Metrics — Phase I

Percentile crossing detection, z-score delta tracking, growth velocity
percentile classification, PAH-MPH gap, BA-CA discordance, SGA status.
"""

import math
from typing import List, Dict, Optional, Any
from datetime import date


# ── I1: Percentile Crossing Detection ─────────────────────────

def detect_percentile_crossing(
    z_scores: List[Dict],
    window_months: int = 12,
) -> Dict[str, Any]:
    """
    Detect percentile line crossings over a time window.

    Args:
        z_scores: List of {age_months, height_z, weight_z, bmi_z, date}
                  sorted by date ascending.
        window_months: Look-back window (default 12 months).

    Returns:
        Dict with crossing counts and directions per indicator.
    """
    if len(z_scores) < 2:
        return {"sufficient_data": False}

    latest = z_scores[-1]
    latest_age = latest.get("age_months", 0)

    # Find the measurement closest to (latest_age - window_months)
    target_age = latest_age - window_months
    baseline = None
    for zs in z_scores:
        age = zs.get("age_months", 0)
        if age <= target_age + 1:  # allow 1 month tolerance
            baseline = zs

    if baseline is None:
        baseline = z_scores[0]

    result = {"sufficient_data": True, "window_months": window_months}

    for indicator in ["height_z", "weight_z", "bmi_z"]:
        z_now = latest.get(indicator)
        z_then = baseline.get(indicator)
        prefix = indicator.replace("_z", "")

        if z_now is not None and z_then is not None:
            delta = z_now - z_then
            # Each 0.67 SD ~ 1 major percentile line crossing
            lines_crossed = abs(delta) / 0.67
            direction = "down" if delta < 0 else ("up" if delta > 0 else "stable")

            result[f"{prefix}_z_delta"] = round(delta, 3)
            result[f"{prefix}_lines_crossed"] = round(lines_crossed, 1)
            result[f"{prefix}_crossing_direction"] = direction
        else:
            result[f"{prefix}_z_delta"] = None
            result[f"{prefix}_lines_crossed"] = None
            result[f"{prefix}_crossing_direction"] = None

    # Detect divergent trajectories (weight up + height down or vice versa)
    ht_dir = result.get("height_crossing_direction")
    wt_dir = result.get("weight_crossing_direction")
    result["trajectories_divergent"] = (
        (ht_dir == "down" and wt_dir == "up") or
        (ht_dir == "up" and wt_dir == "down")
    )

    return result


# ── I2: Z-Score Delta Tracking ─────────────────────────────────

def compute_z_deltas(
    z_scores: List[Dict],
    period_months: int = 12,
) -> Dict[str, Optional[float]]:
    """
    Compute z-score change over a given period.

    Returns:
        {height_z_delta_Nmo, weight_z_delta_Nmo, bmi_z_delta_Nmo}
    """
    if len(z_scores) < 2:
        return {
            f"height_z_delta_{period_months}mo": None,
            f"weight_z_delta_{period_months}mo": None,
            f"bmi_z_delta_{period_months}mo": None,
        }

    latest = z_scores[-1]
    target_age = latest.get("age_months", 0) - period_months

    baseline = None
    min_diff = float("inf")
    for zs in z_scores[:-1]:
        diff = abs(zs.get("age_months", 0) - target_age)
        if diff < min_diff:
            min_diff = diff
            baseline = zs

    result = {}
    for indicator in ["height_z", "weight_z", "bmi_z"]:
        z_now = latest.get(indicator)
        z_then = baseline.get(indicator) if baseline else None
        key = f"{indicator.replace('_z', '')}_z_delta_{period_months}mo"
        if z_now is not None and z_then is not None:
            result[key] = round(z_now - z_then, 3)
        else:
            result[key] = None

    return result


# ── I3: Growth Velocity Percentile Classification ──────────────

def classify_velocity_percentile(
    velocity_cm_yr: float,
    age_years: float,
    sex: str,
) -> Dict[str, Any]:
    """
    Classify height velocity into a percentile using Tanner reference data.

    Returns:
        {velocity_percentile (approx), velocity_tier}
    """
    from clinical.velocity import (
        VELOCITY_REF_BOYS, VELOCITY_REF_GIRLS,
        VELOCITY_PERCENTILES, VELOCITY_PCT_INDICES,
        _interpolate_velocity_ref,
    )

    ref = VELOCITY_REF_BOYS if sex == "M" else VELOCITY_REF_GIRLS

    # Get reference values at this age for each percentile
    pct_values = {}
    for pct in VELOCITY_PERCENTILES:
        idx = VELOCITY_PCT_INDICES[pct]
        val = _interpolate_velocity_ref(ref, age_years, idx)
        if val is not None:
            pct_values[pct] = val

    if not pct_values:
        return {"velocity_percentile": None, "velocity_tier": None}

    # Determine where the patient's velocity falls
    estimated_pct = None
    sorted_pcts = sorted(pct_values.keys())

    if velocity_cm_yr <= pct_values.get(sorted_pcts[0], 0):
        estimated_pct = sorted_pcts[0] - 1  # below lowest
    elif velocity_cm_yr >= pct_values.get(sorted_pcts[-1], 999):
        estimated_pct = sorted_pcts[-1] + 1  # above highest
    else:
        for i in range(len(sorted_pcts) - 1):
            p_low = sorted_pcts[i]
            p_high = sorted_pcts[i + 1]
            v_low = pct_values[p_low]
            v_high = pct_values[p_high]
            if v_low <= velocity_cm_yr <= v_high:
                # Linear interpolation between percentiles
                frac = (velocity_cm_yr - v_low) / (v_high - v_low) if v_high != v_low else 0.5
                estimated_pct = p_low + frac * (p_high - p_low)
                break

    if estimated_pct is None:
        return {"velocity_percentile": None, "velocity_tier": None}

    # Tier classification
    if estimated_pct < 5:
        tier = 4
    elif estimated_pct < 10:
        tier = 3
    elif estimated_pct < 25:
        tier = 2
    else:
        tier = 1

    return {
        "velocity_percentile": round(estimated_pct, 1),
        "velocity_tier": tier,
    }


# ── I4: PAH vs MPH Gap ────────────────────────────────────────

def compute_pah_mph_gap(
    pah_cm: Optional[float],
    mph_cm: Optional[float],
) -> Dict[str, Any]:
    """
    Quantify gap between predicted adult height and mid-parental height.
    1 SD ~ 6.5 cm for adult height.
    """
    if pah_cm is None or mph_cm is None:
        return {"pah_mph_gap_cm": None, "pah_mph_gap_sd": None, "pah_mph_tier": None}

    gap_cm = pah_cm - mph_cm
    gap_sd = gap_cm / 6.5  # 1 SD ~ 6.5 cm

    if abs(gap_sd) < 1.0:
        tier = 1
    elif abs(gap_sd) < 1.5:
        tier = 2
    elif abs(gap_sd) < 2.0:
        tier = 3
    else:
        tier = 4

    return {
        "pah_cm": round(pah_cm, 1),
        "mph_cm": round(mph_cm, 1),
        "pah_mph_gap_cm": round(gap_cm, 1),
        "pah_mph_gap_sd": round(gap_sd, 2),
        "pah_mph_tier": tier,
    }


# ── I5: BA-CA Discordance ─────────────────────────────────────

def compute_ba_ca_discordance(
    bone_age_years: Optional[float],
    chronological_age_years: Optional[float],
) -> Dict[str, Any]:
    """Quantify bone age vs chronological age discordance."""
    if bone_age_years is None or chronological_age_years is None:
        return {"ba_ca_delta_years": None, "ba_ca_direction": None, "ba_ca_tier": None}

    delta = bone_age_years - chronological_age_years
    if delta < -0.5:
        direction = "delayed"
    elif delta > 0.5:
        direction = "advanced"
    else:
        direction = "concordant"

    abs_delta = abs(delta)
    if abs_delta < 1.0:
        tier = 1
    elif abs_delta < 2.0:
        tier = 2
    elif abs_delta < 2.5:
        tier = 3
    else:
        tier = 4

    return {
        "bone_age_years": round(bone_age_years, 2),
        "chronological_age_years": round(chronological_age_years, 2),
        "ba_ca_delta_years": round(delta, 2),
        "ba_ca_direction": direction,
        "ba_ca_tier": tier,
    }


# ── I7: SGA Catch-Up Status ───────────────────────────────────

def compute_sga_status(
    born_sga: Optional[bool],
    current_age_years: Optional[float],
    current_height_z: Optional[float],
) -> Dict[str, Any]:
    """Determine SGA catch-up status and GH eligibility."""
    if born_sga is None or not born_sga:
        return {"born_sga": False, "sga_gh_eligible": False}

    if current_age_years is None or current_height_z is None:
        return {"born_sga": True, "catch_up_achieved": None, "sga_gh_eligible": None}

    catch_up = current_height_z >= -2.0
    # FDA criteria: age >= 2, height < -2.5 SD, born SGA, no catch-up
    gh_eligible = (
        current_age_years >= 2.0 and
        current_height_z < -2.5 and
        not catch_up
    )

    return {
        "born_sga": True,
        "current_age_years": round(current_age_years, 2),
        "current_height_z": round(current_height_z, 3),
        "catch_up_achieved": catch_up,
        "sga_gh_eligible": gh_eligible,
    }


# ── I8: HOMA-IR Calculation ────────────────────────────────────

def compute_homa_ir(
    fasting_glucose_mg_dl: Optional[float],
    fasting_insulin_uiu_ml: Optional[float],
) -> Dict[str, Any]:
    """Compute HOMA-IR from fasting glucose and insulin."""
    if fasting_glucose_mg_dl is None or fasting_insulin_uiu_ml is None:
        return {"homa_ir": None, "homa_ir_elevated": None}

    homa_ir = (fasting_glucose_mg_dl * fasting_insulin_uiu_ml) / 405.0

    return {
        "homa_ir": round(homa_ir, 2),
        "homa_ir_elevated": homa_ir > 3.16,
    }


# ── Build Full Metrics Snapshot ────────────────────────────────

def build_patient_metrics(
    patient: dict,
    measurements: List[dict],
    z_scores: List[dict],
    velocities: List[dict],
    labs: List[dict],
    pah_cm: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build a complete metrics snapshot for CDS evaluation.

    Args:
        patient: Patient dict with sex, birth_date, mph, sga_flag, etc.
        measurements: List of measurement dicts sorted by date
        z_scores: List of {age_months, height_z, weight_z, bmi_z} sorted by date
        velocities: List of {midpoint_age_years, velocity_cm_year} from velocity computation
        labs: List of lab result dicts
        pah_cm: Bayley-Pinneau predicted adult height if available

    Returns:
        Complete metrics dict for CDS engine input.
    """
    metrics = {}

    # Crossing detection
    metrics["crossing"] = detect_percentile_crossing(z_scores, window_months=12)

    # Z-score deltas
    metrics["z_deltas"] = compute_z_deltas(z_scores, period_months=12)

    # Velocity percentile (use most recent velocity)
    if velocities:
        latest_v = velocities[-1]
        metrics["velocity"] = classify_velocity_percentile(
            latest_v["velocity_cm_year"],
            latest_v["midpoint_age_years"],
            patient.get("sex", "M"),
        )
        metrics["velocity"]["velocity_cm_yr"] = latest_v["velocity_cm_year"]
    else:
        metrics["velocity"] = {"velocity_percentile": None, "velocity_tier": None}

    # PAH vs MPH gap
    metrics["pah_mph"] = compute_pah_mph_gap(pah_cm, patient.get("effective_mph"))

    # BA-CA discordance (use most recent bone age)
    latest_ba = None
    latest_ca = None
    for m in reversed(measurements):
        if m.get("bone_age_years") and latest_ba is None:
            latest_ba = m["bone_age_years"]
            if m.get("age_months"):
                latest_ca = m["age_months"] / 12.0
            break
    metrics["ba_ca"] = compute_ba_ca_discordance(latest_ba, latest_ca)

    # SGA status
    current_ht_z = z_scores[-1].get("height_z") if z_scores else None
    current_age = z_scores[-1].get("age_months", 0) / 12.0 if z_scores else None
    metrics["sga"] = compute_sga_status(
        patient.get("sga_flag"),
        current_age,
        current_ht_z,
    )

    # HOMA-IR (from latest fasting glucose + insulin labs)
    glucose = None
    insulin = None
    for lab in labs:
        name = lab.get("lab_name", "").upper()
        if "GLUCOSE" in name and "FASTING" in name.upper():
            glucose = lab.get("value")
        elif "INSULIN" in name and "FASTING" in name.upper():
            insulin = lab.get("value")
    metrics["homa_ir"] = compute_homa_ir(glucose, insulin)

    # Latest z-scores for direct CDS thresholds
    if z_scores:
        latest = z_scores[-1]
        metrics["current"] = {
            "height_z": latest.get("height_z"),
            "weight_z": latest.get("weight_z"),
            "bmi_z": latest.get("bmi_z"),
            "age_months": latest.get("age_months"),
        }
    else:
        metrics["current"] = {}

    return metrics
