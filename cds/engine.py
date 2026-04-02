"""
CDS Engine — Clinical Decision Support for pediatric growth.

Evaluates a patient's metrics against configurable thresholds (cds/thresholds.json)
and returns tier assessments (1-4) per clinical category.

Tier levels:
  1 = On Track (no action)
  2 = Observe (monitor closely)
  3 = Evaluate (workup recommended)
  4 = Act / Refer (urgent action)
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


_THRESHOLDS_PATH = Path(__file__).parent / "thresholds.json"
_thresholds = None


def _load_thresholds() -> dict:
    global _thresholds
    if _thresholds is None:
        with open(_THRESHOLDS_PATH, "r") as f:
            _thresholds = json.load(f)
    return _thresholds


def _tier_result(tier: int, label: str, criteria: list, action: str = "",
                 order_set: str = "", parent_msg: str = "", recheck: str = "") -> dict:
    labels = {1: "On Track", 2: "Observe", 3: "Evaluate", 4: "Act / Refer"}
    return {
        "tier": tier,
        "tier_label": labels.get(tier, "Unknown"),
        "scenario_name": label,
        "trigger_criteria_met": criteria,
        "physician_action": action,
        "order_set": order_set,
        "parent_message": parent_msg,
        "recheck_interval": recheck,
    }


# ═══════════════════════════════════════════════════════════════
#  Category Evaluators
# ═══════════════════════════════════════════════════════════════

def evaluate_short_stature(metrics: dict, patient: dict) -> dict:
    t = _load_thresholds()["short_stature"]
    ht_z = metrics.get("current", {}).get("height_z")
    gv_pct = metrics.get("velocity", {}).get("velocity_percentile")
    ht_delta = metrics.get("z_deltas", {}).get("height_z_delta_12mo")

    if ht_z is None:
        return _tier_result(1, "Short stature", ["Insufficient height data"])

    criteria = []
    tier = 1

    # Height z-score thresholds
    if ht_z <= t["height_z"]["tier_4_below"]:
        tier = max(tier, 4)
        criteria.append(f"Height z={ht_z:.2f} (<= {t['height_z']['tier_4_below']})")
    elif ht_z <= t["height_z"]["tier_3_max"]:
        tier = max(tier, 3)
        criteria.append(f"Height z={ht_z:.2f} (<= {t['height_z']['tier_3_max']})")
    elif ht_z <= t["height_z"]["tier_2_max"]:
        tier = max(tier, 2)
        criteria.append(f"Height z={ht_z:.2f} (<= {t['height_z']['tier_2_max']})")

    # Growth velocity
    if gv_pct is not None:
        if gv_pct < t["gv_percentile"]["tier_4_below"]:
            tier = max(tier, 4)
            criteria.append(f"GV {gv_pct:.0f}th %ile (< {t['gv_percentile']['tier_4_below']}th)")
        elif gv_pct < t["gv_percentile"]["tier_3_below"]:
            tier = max(tier, 3)
            criteria.append(f"GV {gv_pct:.0f}th %ile (< {t['gv_percentile']['tier_3_below']}th)")
        elif gv_pct < t["gv_percentile"]["tier_2_below"]:
            tier = max(tier, 2)
            criteria.append(f"GV {gv_pct:.0f}th %ile (< {t['gv_percentile']['tier_2_below']}th)")

    # Height z-score decline
    if ht_delta is not None and ht_delta <= t["height_z_delta_12mo"]["tier_3_threshold"]:
        tier = max(tier, 3)
        criteria.append(f"Height z-delta {ht_delta:+.2f} over 12mo (threshold: {t['height_z_delta_12mo']['tier_3_threshold']})")

    action = ""
    if tier >= 3:
        action = "Full short stature workup. Consider endocrine referral. Females: ALWAYS karyotype."
    elif tier == 2:
        action = "Monitor growth velocity closely. Recheck in 4-6 months."

    return _tier_result(tier, "Short stature", criteria, action,
                        order_set="short_stature_initial" if tier >= 3 else "",
                        recheck="6-8 weeks post-labs" if tier >= 3 else "4-6 months")


def evaluate_tall_stature(metrics: dict, patient: dict) -> dict:
    t = _load_thresholds()["tall_stature"]
    ht_z = metrics.get("current", {}).get("height_z")

    if ht_z is None or ht_z < t["height_z"]["tier_2_min"]:
        return _tier_result(1, "Tall stature", [])

    criteria = []
    tier = 1

    if ht_z >= t["height_z"]["tier_4_above"]:
        tier = 4
        criteria.append(f"Height z={ht_z:.2f} (>= {t['height_z']['tier_4_above']})")
    elif ht_z >= t["height_z"]["tier_3_min"]:
        tier = 3
        criteria.append(f"Height z={ht_z:.2f} (>= {t['height_z']['tier_3_min']})")
    elif ht_z >= t["height_z"]["tier_2_min"]:
        tier = 2
        criteria.append(f"Height z={ht_z:.2f} (>= {t['height_z']['tier_2_min']})")

    action = ""
    if tier >= 3:
        action = "Evaluate for endocrine causes of tall stature. Consider IGF-1, thyroid function, karyotype if features present."

    return _tier_result(tier, "Tall stature", criteria, action)


def evaluate_obesity(metrics: dict, patient: dict) -> dict:
    t = _load_thresholds()["obesity"]
    bmi_z = metrics.get("current", {}).get("bmi_z")
    bmi_delta = metrics.get("z_deltas", {}).get("bmi_z_delta_12mo")

    if bmi_z is None or bmi_z < t["bmi_z"]["tier_2_min"]:
        return _tier_result(1, "Obesity", [])

    criteria = []
    tier = 1

    if bmi_z >= t["bmi_z"]["tier_4_min"]:
        tier = 4
        criteria.append(f"BMI z={bmi_z:.2f} (>= {t['bmi_z']['tier_4_min']})")
    elif bmi_z >= t["bmi_z"]["tier_3_min"]:
        tier = 3
        criteria.append(f"BMI z={bmi_z:.2f} (>= {t['bmi_z']['tier_3_min']})")
    elif bmi_z >= t["bmi_z"]["tier_2_min"]:
        tier = 2
        criteria.append(f"BMI z={bmi_z:.2f} (>= {t['bmi_z']['tier_2_min']})")

    # BMI acceleration
    if bmi_delta is not None and bmi_delta >= t["bmi_z_delta_12mo"]["tier_3_threshold"]:
        tier = max(tier, 3)
        criteria.append(f"BMI z-delta {bmi_delta:+.2f} over 12mo")

    # HTN escalation
    homa = metrics.get("homa_ir", {})
    if homa.get("homa_ir_elevated"):
        tier = max(tier, 3)
        criteria.append(f"HOMA-IR elevated ({homa.get('homa_ir', '?')})")

    action = ""
    if tier >= 3:
        action = "Metabolic workup: HbA1c, fasting glucose/insulin, lipid panel, liver enzymes. Consider endocrine referral."
    elif tier == 2:
        action = "Lifestyle counseling. Recheck in 3-6 months."

    return _tier_result(tier, "Obesity", criteria, action,
                        order_set="obesity_metabolic" if tier >= 3 else "")


def evaluate_ftt(metrics: dict, patient: dict) -> dict:
    t = _load_thresholds()["ftt"]
    wt_z = metrics.get("current", {}).get("weight_z")
    wt_delta = metrics.get("z_deltas", {}).get("weight_z_delta_12mo")

    if wt_z is None or wt_z > t["weight_z"]["tier_2_max"]:
        return _tier_result(1, "Failure to thrive", [])

    criteria = []
    tier = 1

    if wt_z <= t["weight_z"]["tier_4_below"]:
        tier = 4
        criteria.append(f"Weight z={wt_z:.2f} (<= {t['weight_z']['tier_4_below']})")
    elif wt_z <= t["weight_z"]["tier_3_max"]:
        tier = 3
        criteria.append(f"Weight z={wt_z:.2f} (<= {t['weight_z']['tier_3_max']})")
    elif wt_z <= t["weight_z"]["tier_2_max"]:
        tier = 2
        criteria.append(f"Weight z={wt_z:.2f} (<= {t['weight_z']['tier_2_max']})")

    if wt_delta is not None and wt_delta <= t["weight_z_delta_12mo"]["tier_3_threshold"]:
        tier = max(tier, 3)
        criteria.append(f"Weight z-delta {wt_delta:+.2f} over 12mo")

    action = ""
    if tier >= 3:
        action = "FTT workup: CBC, CMP, celiac panel, thyroid, urinalysis. Nutrition referral."

    return _tier_result(tier, "Failure to thrive", criteria, action,
                        order_set="ftt_workup" if tier >= 3 else "")


def evaluate_percentile_crossing(metrics: dict, patient: dict) -> dict:
    t = _load_thresholds()["percentile_crossing"]
    crossing = metrics.get("crossing", {})

    if not crossing.get("sufficient_data"):
        return _tier_result(1, "Percentile crossing", ["Insufficient longitudinal data"])

    criteria = []
    tier = 1

    # Check height crossing
    ht_lines = crossing.get("height_lines_crossed")
    if ht_lines is not None:
        if ht_lines >= t["lines_crossed"]["tier_4_min"]:
            tier = max(tier, 4)
            criteria.append(f"Height: {ht_lines:.1f} lines crossed ({crossing.get('height_crossing_direction')})")
        elif ht_lines >= t["lines_crossed"]["tier_3_min"]:
            tier = max(tier, 3)
            criteria.append(f"Height: {ht_lines:.1f} lines crossed ({crossing.get('height_crossing_direction')})")
        elif ht_lines >= t["lines_crossed"]["tier_2_min"]:
            tier = max(tier, 2)
            criteria.append(f"Height: {ht_lines:.1f} lines crossed ({crossing.get('height_crossing_direction')})")

    # Check weight crossing
    wt_lines = crossing.get("weight_lines_crossed")
    if wt_lines is not None and wt_lines >= t["lines_crossed"]["tier_2_min"]:
        tier = max(tier, 2)
        criteria.append(f"Weight: {wt_lines:.1f} lines crossed ({crossing.get('weight_crossing_direction')})")

    # Divergent trajectories
    if crossing.get("trajectories_divergent"):
        tier = max(tier, t["divergent_trajectories"]["auto_tier"])
        criteria.append("Divergent trajectories (height down + weight up or vice versa)")

    action = ""
    if tier >= 3:
        action = "Significant growth trajectory change. Full endocrine workup recommended."

    return _tier_result(tier, "Percentile crossing", criteria, action)


def evaluate_bone_age(metrics: dict, patient: dict) -> dict:
    t = _load_thresholds()["bone_age"]
    ba_ca = metrics.get("ba_ca", {})
    delta = ba_ca.get("ba_ca_delta_years")

    if delta is None:
        return _tier_result(1, "Bone age", ["No bone age data"])

    abs_delta = abs(delta)
    criteria = []
    tier = 1

    if abs_delta >= t["ba_ca_delta_years"]["tier_4_min"]:
        tier = 4
        criteria.append(f"BA-CA delta {delta:+.1f}y ({ba_ca.get('ba_ca_direction')})")
    elif abs_delta >= t["ba_ca_delta_years"]["tier_3_min"]:
        tier = 3
        criteria.append(f"BA-CA delta {delta:+.1f}y ({ba_ca.get('ba_ca_direction')})")
    elif abs_delta >= t["ba_ca_delta_years"]["tier_2_min"]:
        tier = 2
        criteria.append(f"BA-CA delta {delta:+.1f}y ({ba_ca.get('ba_ca_direction')})")

    action = ""
    if tier >= 3:
        action = "Significant bone age discordance. Correlate with clinical picture and consider endocrine evaluation."

    return _tier_result(tier, "Bone age discordance", criteria, action)


def evaluate_puberty(metrics: dict, patient: dict) -> dict:
    t = _load_thresholds()["puberty"]
    sex = patient.get("sex", "M")
    age_months = metrics.get("current", {}).get("age_months")
    if age_months is None:
        return _tier_result(1, "Puberty", ["No age data"])

    age_years = age_months / 12.0

    # Get latest Tanner staging from patient measurements
    tanner = patient.get("latest_tanner", {})
    breast = tanner.get("tanner_breast")
    genital = tanner.get("tanner_genital")
    pubic = tanner.get("tanner_pubic_hair")

    criteria = []
    tier = 1

    # Precocious puberty
    precocious_age = t["precocious_female_age"] if sex == "F" else t["precocious_male_age"]
    if sex == "F" and breast is not None and breast >= t["tanner_precocious_stage"] and age_years < precocious_age:
        tier = 3
        criteria.append(f"Tanner breast B{breast} at age {age_years:.1f}y (precocious: <{precocious_age}y)")
    elif sex == "M" and genital is not None and genital >= t["tanner_precocious_stage"] and age_years < precocious_age:
        tier = 3
        criteria.append(f"Tanner genital G{genital} at age {age_years:.1f}y (precocious: <{precocious_age}y)")

    # Delayed puberty — only flag if Tanner stage was explicitly recorded as 1
    # Missing Tanner data (None) = not assessed, NOT "no development"
    delayed_age = t["delayed_female_age"] if sex == "F" else t["delayed_male_age"]
    if age_years >= delayed_age:
        if sex == "F" and breast is not None and breast <= 1:
            tier = max(tier, 3)
            criteria.append(f"No breast development (B{breast}) at age {age_years:.1f}y (delayed: >={delayed_age}y)")
        elif sex == "M" and genital is not None and genital <= 1:
            tier = max(tier, 3)
            criteria.append(f"No genital development (G{genital}) at age {age_years:.1f}y (delayed: >={delayed_age}y)")

    action = ""
    if tier >= 3:
        action = "Puberty evaluation: LH, FSH, estradiol/testosterone. Consider bone age. Endocrine referral."

    return _tier_result(tier, "Puberty timing", criteria, action,
                        order_set="puberty_evaluation" if tier >= 3 else "")


def evaluate_sga(metrics: dict, patient: dict) -> dict:
    sga = metrics.get("sga", {})
    if not sga.get("born_sga"):
        return _tier_result(1, "SGA", [])

    criteria = [f"Born SGA"]
    tier = 2

    if sga.get("sga_gh_eligible"):
        tier = 4
        criteria.append(f"GH eligible: age >={2}y, height z={sga.get('current_height_z', '?'):.2f}, no catch-up")
    elif sga.get("catch_up_achieved") is False:
        tier = 3
        criteria.append("No catch-up growth (height still < -2 SD)")
    elif sga.get("catch_up_achieved"):
        tier = 1
        criteria.append("Catch-up achieved (height >= -2 SD)")

    action = ""
    if tier >= 3:
        action = "SGA without catch-up. Consider GH evaluation if age >= 2 and height < -2.5 SD."

    return _tier_result(tier, "SGA follow-up", criteria, action)


def evaluate_cushing(metrics: dict, patient: dict) -> dict:
    """Compound trigger: obesity + height crossing down + HTN."""
    t = _load_thresholds()["cushing"]

    bmi_z = metrics.get("current", {}).get("bmi_z")
    crossing = metrics.get("crossing", {})
    ht_dir = crossing.get("height_crossing_direction")

    criteria = []
    flags = 0

    if bmi_z is not None and bmi_z >= 1.64:  # >= 95th percentile
        flags += 1
        criteria.append(f"Obesity: BMI z={bmi_z:.2f}")

    if ht_dir == "down":
        flags += 1
        criteria.append("Height trajectory declining")

    if crossing.get("trajectories_divergent"):
        flags += 1
        criteria.append("Divergent trajectories (weight up, height down)")

    tier = 1
    if flags >= 2:
        tier = t["auto_tier"]

    action = ""
    if tier >= 3:
        action = "Cushing's screening: 24hr urinary free cortisol, late-night salivary cortisol, or low-dose dexamethasone suppression test."

    return _tier_result(tier, "Cushing's screening", criteria, action,
                        order_set="cushing_screen" if tier >= 3 else "")


def evaluate_turner(metrics: dict, patient: dict) -> dict:
    t = _load_thresholds()["turner"]
    sex = patient.get("sex", "M")

    if sex != t["applies_to"]:
        return _tier_result(1, "Turner screening", [])

    ht_z = metrics.get("current", {}).get("height_z")
    if ht_z is None:
        return _tier_result(1, "Turner screening", ["No height data"])

    criteria = []
    tier = 1

    if ht_z <= t["height_z_trigger"]:
        tier = t["auto_karyotype_tier"]
        criteria.append(f"Female with height z={ht_z:.2f} (<= {t['height_z_trigger']}). Karyotype recommended.")

    action = ""
    if tier >= 3:
        action = "All females with significant short stature should have karyotype to rule out Turner syndrome."

    return _tier_result(tier, "Turner screening", criteria, action,
                        order_set="karyotype" if tier >= 3 else "")


def evaluate_thyroid_celiac(metrics: dict, patient: dict) -> dict:
    t = _load_thresholds()["thyroid_celiac"]
    ht_z = metrics.get("current", {}).get("height_z")
    gv_pct = metrics.get("velocity", {}).get("velocity_percentile")

    trigger = False
    criteria = []

    if ht_z is not None and ht_z <= t["height_z_trigger"]:
        trigger = True
        criteria.append(f"Height z={ht_z:.2f}")
    if gv_pct is not None and gv_pct < t["gv_percentile_trigger"]:
        trigger = True
        criteria.append(f"GV {gv_pct:.0f}th %ile")

    if not trigger:
        return _tier_result(1, "Thyroid/Celiac screen", [])

    return _tier_result(
        t["tier_when_labs_missing"], "Thyroid/Celiac screen", criteria,
        action="Screen TSH, Free T4, tTG-IgA with total IgA.",
        order_set="thyroid_celiac_screen",
        recheck="6-8 weeks post-labs",
    )


def evaluate_disproportion(metrics: dict, patient: dict) -> dict:
    """Check for disproportionate growth (sitting height, arm span)."""
    # Requires sitting_height or arm_span data
    latest_meas = patient.get("latest_measurement", {})
    sitting_ht = latest_meas.get("sitting_height_cm")
    arm_span = latest_meas.get("arm_span_cm")
    height = latest_meas.get("height_cm")

    if not height or (not sitting_ht and not arm_span):
        return _tier_result(1, "Disproportionate growth", [])

    criteria = []
    tier = 1

    if sitting_ht and height:
        ratio = sitting_ht / height
        # Normal sitting height / height ratio decreases with age
        # Elevated ratio suggests short limbs (skeletal dysplasia, SHOX)
        if ratio > 0.55:  # Approximate threshold for older children
            tier = 2
            criteria.append(f"Sitting height ratio {ratio:.3f} (elevated)")
        if ratio > 0.58:
            tier = 3
            criteria.append(f"Sitting height ratio {ratio:.3f} (significantly elevated)")

    if arm_span and height:
        span_diff = arm_span - height
        if abs(span_diff) > 5:  # >5cm difference
            tier = max(tier, 2)
            criteria.append(f"Arm span - height = {span_diff:+.1f} cm")

    action = ""
    if tier >= 3:
        action = "Evaluate for skeletal dysplasia or SHOX deficiency. Consider skeletal survey, SHOX gene analysis."

    return _tier_result(tier, "Disproportionate growth", criteria, action)


# ═══════════════════════════════════════════════════════════════
#  Main Evaluator
# ═══════════════════════════════════════════════════════════════

def evaluate_patient(metrics: dict, patient: dict) -> dict:
    """
    Run all CDS category evaluators and return comprehensive tier assessment.

    Args:
        metrics: Output from cds.metrics.build_patient_metrics()
        patient: Patient dict with sex, birth_date, sga_flag, latest_tanner, etc.

    Returns:
        Dict with per-category results + overall max_tier.
    """
    results = {
        "short_stature": evaluate_short_stature(metrics, patient),
        "tall_stature": evaluate_tall_stature(metrics, patient),
        "obesity": evaluate_obesity(metrics, patient),
        "ftt": evaluate_ftt(metrics, patient),
        "percentile_crossing": evaluate_percentile_crossing(metrics, patient),
        "bone_age": evaluate_bone_age(metrics, patient),
        "puberty": evaluate_puberty(metrics, patient),
        "sga": evaluate_sga(metrics, patient),
        "cushing": evaluate_cushing(metrics, patient),
        "turner": evaluate_turner(metrics, patient),
        "thyroid_celiac": evaluate_thyroid_celiac(metrics, patient),
        "disproportion": evaluate_disproportion(metrics, patient),
    }

    # Overall highest tier
    max_tier = max(
        r["tier"] for r in results.values() if isinstance(r, dict) and "tier" in r
    )
    results["max_tier"] = max_tier
    results["max_tier_label"] = {1: "On Track", 2: "Observe", 3: "Evaluate", 4: "Act / Refer"}.get(max_tier, "Unknown")

    # Flagged categories (tier >= 2)
    flagged = [k for k, v in results.items()
               if isinstance(v, dict) and v.get("tier", 0) >= 2]
    results["categories_flagged"] = flagged

    return results
