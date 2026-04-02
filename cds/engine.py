"""
CDS Engine — Clinical Decision Support for pediatric growth.

Evaluates a patient's metrics against configurable thresholds (cds/thresholds.json)
and returns tier assessments (1-4) per clinical category.

Tier levels (v2.0 — aligned with cds_matrix_v2.html):
  1 = On Track
  2 = Monitor Pattern
  3 = Pattern Warrants Evaluation
  4 = Urgent Pattern / Refer

Categories (13):
  SHORT STATURE, TALL STATURE, EXCESS WEIGHT GAIN,
  WEIGHT FALTERING / POOR WEIGHT GAIN, GROWTH TRAJECTORY CHANGE,
  BONE AGE DISCORDANCE, ATYPICAL PUBERTAL TIMING,
  SGA — POST-NATAL GROWTH TRAJECTORY, DIVERGENT WEIGHT–HEIGHT TRAJECTORY,
  UNEXPLAINED SHORT STATURE — FEMALES, GROWTH DECELERATION — METABOLIC SCREEN,
  DISPROPORTIONATE GROWTH

Phrasing rules (Fuchs review v2.0):
  R1  Flag patterns, never diagnose
  R2  Don't assume data exists — guard on data availability
  R3  Trajectories matter more than thresholds
  R4  Use standard clinical thresholds (-2.0 SD, BMI 95th, etc.)
  R5  Tier language = action-oriented, not diagnostic
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


_TIER_LABELS = {
    1: "On Track",
    2: "Monitor Pattern",
    3: "Pattern Warrants Evaluation",
    4: "Urgent Pattern / Refer",
}


def _tier_result(tier: int, label: str, criteria: list, action: str = "",
                 order_set: str = "", parent_msg: str = "", recheck: str = "") -> dict:
    return {
        "tier": tier,
        "tier_label": _TIER_LABELS.get(tier, "Unknown"),
        "scenario_name": label,
        "trigger_criteria_met": criteria,
        "physician_action": action,
        "order_set": order_set,
        "parent_message": parent_msg,
        "recheck_interval": recheck,
    }


def _tanner_recorded(val) -> bool:
    """Tanner stage is 'recorded' only if not None and not 0.
    Valid Tanner stages are 1-5; 0 means 'not assessed' / placeholder."""
    return val is not None and val != 0


# ═══════════════════════════════════════════════════════════════
#  Category Evaluators
# ═══════════════════════════════════════════════════════════════

def _near_adult_height(patient: dict) -> bool:
    """Return True if patient is near expected end of linear growth.
    Girls ~14y, boys ~16y — slowing/stable height is physiologic, not pathologic."""
    age_years = patient.get("age_years") or (patient.get("age_months", 0) / 12.0)
    sex = patient.get("sex", "M")
    if sex == "F" and age_years >= 14.0:
        return True
    if sex == "M" and age_years >= 16.0:
        return True
    return False


def evaluate_short_stature(metrics: dict, patient: dict) -> dict:
    """SHORT STATURE — Tier 3 ≤ -2.0 SD (standard), Tier 4 ≤ -2.25 SD (ISS/FDA GH)."""
    t = _load_thresholds()["short_stature"]
    ht_z = metrics.get("current", {}).get("height_z")
    gv_pct = metrics.get("velocity", {}).get("velocity_percentile")
    ht_delta = metrics.get("z_deltas", {}).get("height_z_delta_12mo")
    near_adult = _near_adult_height(patient)

    if ht_z is None:
        return _tier_result(1, "SHORT STATURE", ["Insufficient height data"])

    criteria = []
    tier = 1

    # Height z-score thresholds (R4: -2.0 standard, -2.25 FDA GH)
    if ht_z <= t["height_z"]["tier_4_below"]:
        tier = max(tier, 4)
        criteria.append(f"Height z={ht_z:.2f} (≤ {t['height_z']['tier_4_below']} — ISS/FDA GH threshold)")
    elif ht_z <= t["height_z"]["tier_3_max"]:
        tier = max(tier, 3)
        criteria.append(f"Height z={ht_z:.2f} (≤ {t['height_z']['tier_3_max']})")
    elif ht_z <= t["height_z"]["tier_2_max"]:
        tier = max(tier, 2)
        criteria.append(f"Height z={ht_z:.2f} (≤ {t['height_z']['tier_2_max']})")

    # Growth velocity — SUPPRESS if near adult height (physiologic deceleration)
    if gv_pct is not None and not near_adult:
        if gv_pct < t["gv_percentile"]["tier_4_below"]:
            tier = max(tier, 4)
            criteria.append(f"GV {gv_pct:.0f}th %ile (< {t['gv_percentile']['tier_4_below']}th)")
        elif gv_pct < t["gv_percentile"]["tier_3_below"]:
            tier = max(tier, 3)
            criteria.append(f"GV {gv_pct:.0f}th %ile (< {t['gv_percentile']['tier_3_below']}th)")
        elif gv_pct < t["gv_percentile"]["tier_2_below"]:
            tier = max(tier, 2)
            criteria.append(f"GV {gv_pct:.0f}th %ile (< {t['gv_percentile']['tier_2_below']}th)")

    # Height z-delta /12mo — SUPPRESS if near adult height
    if ht_delta is not None and not near_adult:
        abs_delta = abs(ht_delta)
        if abs_delta > abs(t["height_z_delta_12mo"]["tier_4_threshold"]):
            tier = max(tier, 4)
            criteria.append(f"Height z-delta {ht_delta:+.2f} over 12 mo (> {abs(t['height_z_delta_12mo']['tier_4_threshold'])} SD)")
        elif abs_delta > abs(t["height_z_delta_12mo"]["tier_3_threshold"]):
            tier = max(tier, 3)
            criteria.append(f"Height z-delta {ht_delta:+.2f} over 12 mo (> {abs(t['height_z_delta_12mo']['tier_3_threshold'])} SD)")
        elif abs_delta > abs(t["height_z_delta_12mo"]["tier_2_threshold"]):
            tier = max(tier, 2)
            criteria.append(f"Height z-delta {ht_delta:+.2f} over 12 mo (> {abs(t['height_z_delta_12mo']['tier_2_threshold'])} SD)")

    # Action text per spec
    action = ""
    order_set = ""
    recheck = "Routine well-child"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — immediate specialty evaluation recommended."
        order_set = "Severe Short Stature Referral Bundle"
        parent_msg = "We recommend your child see a growth specialist. Their growth pattern meets criteria for further specialized testing."
        recheck = "Specialty appt within 4-6 wk"
    elif tier == 3:
        action = "Pattern warrants evaluation — full growth workup. Consider specialty referral."
        order_set = "Short Stature Initial Workup"
        parent_msg = "Your child's growth pattern needs further evaluation. Your doctor will order some blood tests and possibly an X-ray of the hand to better understand what's happening."
        recheck = "6-8 weeks post-labs"
    elif tier == 2:
        action = "Repeat measurement in 3-6 months. Consider screening labs if trajectory persists."
        parent_msg = "We noticed a small change in your child's growth speed. We'd like to recheck in a few months to see if this is a temporary variation."
        recheck = "3-6 months"

    return _tier_result(tier, "SHORT STATURE", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


def evaluate_tall_stature(metrics: dict, patient: dict) -> dict:
    """TALL STATURE — height >97th %ile, acceleration, advanced BA."""
    t = _load_thresholds()["tall_stature"]
    ht_z = metrics.get("current", {}).get("height_z")
    ht_delta = metrics.get("z_deltas", {}).get("height_z_delta_12mo")

    if ht_z is None or ht_z < t["height_z"]["tier_2_min"]:
        return _tier_result(1, "TALL STATURE", [])

    criteria = []
    tier = 1

    if ht_z >= t["height_z"]["tier_3_min"]:
        tier = max(tier, 3)
        criteria.append(f"Height z={ht_z:.2f} (≥ {t['height_z']['tier_3_min']} — >3 SD above mean)")
    elif ht_z >= t["height_z"]["tier_2_min"]:
        tier = max(tier, 2)
        criteria.append(f"Height z={ht_z:.2f} (≥ {t['height_z']['tier_2_min']})")

    # Height z-delta /12mo upward
    if ht_delta is not None and ht_delta > 0:
        if ht_delta > t["height_z_delta_12mo"]["tier_4_threshold"]:
            tier = max(tier, 4)
            criteria.append(f"Upward height z-delta {ht_delta:+.2f} over 12 mo")
        elif ht_delta > t["height_z_delta_12mo"]["tier_3_threshold"]:
            tier = max(tier, 3)
            criteria.append(f"Upward height z-delta {ht_delta:+.2f} over 12 mo")
        elif ht_delta > t["height_z_delta_12mo"]["tier_2_threshold"]:
            tier = max(tier, 2)
            criteria.append(f"Upward height z-delta {ht_delta:+.2f} over 12 mo")

    # Check for connective tissue / syndromic features (patient flags)
    if patient.get("connective_tissue_features") or patient.get("syndromic_features"):
        tier = max(tier, 4)
        criteria.append("Connective tissue or syndromic features noted")

    action = ""
    order_set = ""
    recheck = "Routine well-child"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — immediate specialty evaluation recommended (endocrine + genetics)."
        order_set = "Echocardiogram, brain MRI, ophthalmology, genetic testing"
        parent_msg = "We recommend your child see a specialist promptly. Some features need evaluation for long-term health."
        recheck = "Referral within 2-4 wk"
    elif tier == 3:
        action = "Pattern warrants evaluation — full tall stature workup."
        order_set = "IGF-1, IGFBP-3, TSH/fT4, estradiol or testosterone, DHEA-S, LH/FSH, BA, karyotype (47,XYY if male)"
        parent_msg = "Your child's growth is faster and taller than expected. We want to check lab work to make sure everything is healthy."
        recheck = "6-8 weeks post-labs"
    elif tier == 2:
        action = "Monitor trajectory closely. Consider screening labs."
        parent_msg = "Your child is growing faster than expected. We'd like to keep a close eye on this."
        recheck = "6 months"

    return _tier_result(tier, "TALL STATURE", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


def evaluate_excess_weight_gain(metrics: dict, patient: dict) -> dict:
    """EXCESS WEIGHT GAIN — BMI-based with weight z-delta trajectory alerts."""
    t = _load_thresholds()["excess_weight_gain"]
    bmi_z = metrics.get("current", {}).get("bmi_z")
    wt_delta = metrics.get("z_deltas", {}).get("weight_z_delta_6mo")
    if wt_delta is None:
        wt_delta = metrics.get("z_deltas", {}).get("weight_z_delta_12mo")

    if bmi_z is None:
        return _tier_result(1, "EXCESS WEIGHT GAIN", ["No BMI data"])

    if bmi_z < t["bmi_z"]["tier_2_min"] and (wt_delta is None or wt_delta < 0.5):
        return _tier_result(1, "EXCESS WEIGHT GAIN", [],
                            parent_msg="Your child's weight is in a healthy range. Continue balanced nutrition and regular activity.")

    criteria = []
    tier = 1

    # BMI z-score thresholds
    if bmi_z >= t["bmi_z"]["tier_4_min"]:
        tier = 4
        criteria.append(f"BMI z={bmi_z:.2f} (≥ {t['bmi_z']['tier_4_min']} — ≥120% of 95th)")
    elif bmi_z >= t["bmi_z"]["tier_3_min"]:
        tier = 3
        criteria.append(f"BMI z={bmi_z:.2f} (≥ {t['bmi_z']['tier_3_min']} — ≥95th %ile)")
    elif bmi_z >= t["bmi_z"]["tier_2_min"]:
        tier = 2
        criteria.append(f"BMI z={bmi_z:.2f} (≥ {t['bmi_z']['tier_2_min']} — ≥85th %ile)")

    # Weight z-delta trajectory alert (R3: trajectory-first)
    if wt_delta is not None and wt_delta > 0:
        if wt_delta > t["weight_z_delta_12mo"]["tier_4_threshold"]:
            tier = max(tier, 4)
            criteria.append(f"Weight z-delta {wt_delta:+.2f} increase (> {t['weight_z_delta_12mo']['tier_4_threshold']} SD)")
        elif wt_delta > t["weight_z_delta_12mo"]["tier_3_threshold"]:
            tier = max(tier, 3)
            criteria.append(f"Weight z-delta {wt_delta:+.2f} increase (> {t['weight_z_delta_12mo']['tier_3_threshold']} SD)")
        elif wt_delta > t["weight_z_delta_12mo"]["tier_2_threshold"]:
            tier = max(tier, 2)
            criteria.append(f"Weight z-delta {wt_delta:+.2f} increase (> {t['weight_z_delta_12mo']['tier_2_threshold']} SD)")

    # Comorbidity escalation (HTN, HOMA-IR)
    homa = metrics.get("homa_ir", {})
    if homa.get("homa_ir_elevated") and tier < 3:
        tier = max(tier, 3)
        criteria.append(f"HOMA-IR elevated ({homa.get('homa_ir', '?')})")

    # Divergent trajectory flag — weight up + height down
    gv_pct = metrics.get("velocity", {}).get("velocity_percentile")
    if gv_pct is not None and gv_pct < 10 and bmi_z >= t["bmi_z"]["tier_2_min"]:
        tier = max(tier, 3)
        criteria.append("DIVERGENT FLAG: Weight gain + height deceleration — see Divergent Trajectory pathway")

    action = ""
    order_set = ""
    recheck = "Routine well-child"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — immediate evaluation recommended. Refer to multidisciplinary weight management and/or endocrinology."
        order_set = "Excess Weight — Advanced / Severe"
        parent_msg = "Your child's weight requires specialized care. We're connecting you with a team of experts."
        recheck = "Referral within 2-4 wk"
    elif tier == 3:
        action = "Pattern warrants evaluation — comprehensive workup. Structured lifestyle intervention. If height decelerating concurrently: add cortisol evaluation (see Divergent Trajectory pathway)."
        order_set = "Excess Weight — Initial Workup"
        parent_msg = "Your child's weight is at a level where we need to check for health effects. This isn't about blame—it's about health."
        recheck = "3 months"
    elif tier == 2:
        action = "Lifestyle counseling. Monitor trajectory — recheck in 3-6 months."
        parent_msg = "Your child's weight is trending higher than ideal. Small changes in diet and activity can make a big difference."
        recheck = "3-6 months"

    return _tier_result(tier, "EXCESS WEIGHT GAIN", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


def evaluate_weight_faltering(metrics: dict, patient: dict) -> dict:
    """WEIGHT FALTERING / POOR WEIGHT GAIN — weight z-delta /6mo per spec.
    SUPPRESS if weight is declining from overweight baseline (therapeutic loss)."""
    t = _load_thresholds()["weight_faltering"]
    wt_z = metrics.get("current", {}).get("weight_z")
    bmi_z = metrics.get("current", {}).get("bmi_z")
    wt_delta_6 = metrics.get("z_deltas", {}).get("weight_z_delta_6mo")
    wt_delta_12 = metrics.get("z_deltas", {}).get("weight_z_delta_12mo")
    wfl_z = metrics.get("current", {}).get("wfl_z")

    # Use 6mo delta preferentially, fall back to 12mo
    wt_delta = wt_delta_6 if wt_delta_6 is not None else wt_delta_12

    if wt_z is None:
        return _tier_result(1, "WEIGHT FALTERING / POOR WEIGHT GAIN", ["No weight data"])

    # SUPPRESS: Weight loss in overweight/obese patient is therapeutic, not pathologic.
    # Only flag weight loss if prior/current BMI was in normal range.
    prior_bmi_z = metrics.get("prior", {}).get("bmi_z")
    was_overweight = (prior_bmi_z is not None and prior_bmi_z >= 1.04) or \
                     (bmi_z is not None and bmi_z >= 1.04)  # ≈85th %ile
    if was_overweight and wt_delta is not None and wt_delta < 0:
        return _tier_result(1, "WEIGHT FALTERING / POOR WEIGHT GAIN",
                            ["Weight declining from overweight — therapeutic, not pathologic"],
                            parent_msg="Your child's weight is moving in a healthier direction.")

    # Early exit if no concern
    if wt_z > -1.0 and (wt_delta is None or wt_delta > -0.5):
        return _tier_result(1, "WEIGHT FALTERING / POOR WEIGHT GAIN", [],
                            parent_msg="Your child's weight gain is on track.")

    criteria = []
    tier = 1

    # Weight z-score absolute thresholds
    if wt_z <= t["weight_z"]["tier_4_below"]:
        tier = 4
        criteria.append(f"Weight z={wt_z:.2f} (< 1st %ile)")
    elif wt_z <= t["weight_z"]["tier_3_max"]:
        tier = 3
        criteria.append(f"Weight z={wt_z:.2f} (< 3rd %ile)")
    elif wt_z <= t["weight_z"]["tier_2_max"]:
        tier = 2
        criteria.append(f"Weight z={wt_z:.2f} (3rd-5th %ile)")

    # Weight z-delta /6mo (R3: trajectory-first)
    if wt_delta is not None and wt_delta < 0:
        if wt_delta <= t["weight_z_delta_6mo"]["tier_4_threshold"]:
            tier = max(tier, 4)
            criteria.append(f"Weight z-delta {wt_delta:+.2f} over 6 mo (≤ {t['weight_z_delta_6mo']['tier_4_threshold']} SD)")
        elif wt_delta <= t["weight_z_delta_6mo"]["tier_3_threshold"]:
            tier = max(tier, 3)
            criteria.append(f"Weight z-delta {wt_delta:+.2f} over 6 mo (≤ {t['weight_z_delta_6mo']['tier_3_threshold']} SD)")
        elif wt_delta <= t["weight_z_delta_6mo"]["tier_2_threshold"]:
            tier = max(tier, 2)
            criteria.append(f"Weight z-delta {wt_delta:+.2f} over 6 mo (≤ {t['weight_z_delta_6mo']['tier_2_threshold']} SD)")

    # Weight-for-length (children <2yr)
    if wfl_z is not None:
        if wfl_z < t["wfl_z"]["tier_4_below"]:
            tier = max(tier, 4)
            criteria.append(f"Weight-for-length z={wfl_z:.2f} (< {t['wfl_z']['tier_4_below']} — severe wasting)")
        elif wfl_z < t["wfl_z"]["tier_3_max"]:
            tier = max(tier, 3)
            criteria.append(f"Weight-for-length z={wfl_z:.2f} (< {t['wfl_z']['tier_3_max']})")

    action = ""
    order_set = ""
    recheck = "Routine well-child"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — immediate evaluation recommended. Consider hospitalization."
        order_set = "Severe Weight Loss / Wasting"
        parent_msg = "Your child needs specialized care right away to ensure they get the nutrition they need."
        recheck = "Immediate / within 1 wk"
    elif tier == 3:
        action = "Pattern warrants evaluation — full workup for underlying causes."
        order_set = "Weight Faltering Workup"
        parent_msg = "Your child needs evaluation for their weight pattern. We want to make sure we're not missing anything."
        recheck = "2-4 weeks"
    elif tier == 2:
        action = "Dietary assessment. Increase monitoring frequency."
        parent_msg = "We noticed your child's weight gain has slowed. Let's review their diet and recheck soon."
        recheck = "1-3 months"

    return _tier_result(tier, "WEIGHT FALTERING / POOR WEIGHT GAIN", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


def evaluate_growth_trajectory_change(metrics: dict, patient: dict) -> dict:
    """GROWTH TRAJECTORY CHANGE — percentile line crossing + z-delta alerts.
    SUPPRESS height deceleration alerts near adult height."""
    t = _load_thresholds()["growth_trajectory_change"]
    crossing = metrics.get("crossing", {})
    z_deltas = metrics.get("z_deltas", {})
    near_adult = _near_adult_height(patient)

    # Data guard: requires ≥2 accurate measurements to confirm
    if not crossing.get("sufficient_data"):
        return _tier_result(1, "GROWTH TRAJECTORY CHANGE", ["Insufficient longitudinal data"])

    criteria = []
    tier = 1

    # Height lines crossed — suppress downward crossing near adult height
    ht_lines = crossing.get("height_lines_crossed")
    ht_dir = crossing.get("height_crossing_direction", "")
    if ht_lines is not None and not (near_adult and "down" in ht_dir.lower()):
        if ht_lines >= t["lines_crossed"]["tier_4_min"]:
            tier = max(tier, 4)
            criteria.append(f"Height: {ht_lines:.1f} lines crossed in <12 mo ({crossing.get('height_crossing_direction', '?')})")
        elif ht_lines >= t["lines_crossed"]["tier_3_min"]:
            tier = max(tier, 3)
            criteria.append(f"Height: {ht_lines:.1f} lines crossed ({crossing.get('height_crossing_direction', '?')})")
        elif ht_lines >= t["lines_crossed"]["tier_2_min"]:
            tier = max(tier, 2)
            criteria.append(f"Height: {ht_lines:.1f} lines crossed ({crossing.get('height_crossing_direction', '?')})")

    # Weight lines crossed
    wt_lines = crossing.get("weight_lines_crossed")
    if wt_lines is not None:
        if wt_lines >= t["lines_crossed"]["tier_4_min"]:
            tier = max(tier, 4)
            criteria.append(f"Weight: {wt_lines:.1f} lines crossed ({crossing.get('weight_crossing_direction', '?')})")
        elif wt_lines >= t["lines_crossed"]["tier_3_min"]:
            tier = max(tier, 3)
            criteria.append(f"Weight: {wt_lines:.1f} lines crossed ({crossing.get('weight_crossing_direction', '?')})")
        elif wt_lines >= t["lines_crossed"]["tier_2_min"]:
            tier = max(tier, 2)
            criteria.append(f"Weight: {wt_lines:.1f} lines crossed ({crossing.get('weight_crossing_direction', '?')})")

    # Z-score change magnitude (either height or weight)
    for key, label in [("height_z_delta_12mo", "Height"), ("weight_z_delta_12mo", "Weight")]:
        delta = z_deltas.get(key)
        if delta is not None:
            abs_d = abs(delta)
            if abs_d > t["z_delta_12mo"]["tier_4_threshold"]:
                tier = max(tier, 4)
                criteria.append(f"{label} z-score change {delta:+.2f} (> {t['z_delta_12mo']['tier_4_threshold']} SD)")
            elif abs_d > t["z_delta_12mo"]["tier_3_threshold"]:
                tier = max(tier, 3)
                criteria.append(f"{label} z-score change {delta:+.2f} (> {t['z_delta_12mo']['tier_3_threshold']} SD)")
            elif abs_d > t["z_delta_12mo"]["tier_2_threshold"]:
                tier = max(tier, 2)
                criteria.append(f"{label} z-score change {delta:+.2f} (> {t['z_delta_12mo']['tier_2_threshold']} SD)")

    # Divergent trajectories flag
    if crossing.get("trajectories_divergent"):
        tier = max(tier, t["divergent_trajectories"]["auto_tier"])
        criteria.append("Divergent trajectories (height and weight moving in opposite directions)")

    action = ""
    order_set = ""
    recheck = "Routine well-child"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — immediate specialty evaluation recommended."
        order_set = "Immediate BA. Full lab panel. Brain MRI if CNS concerns."
        parent_msg = "Your child's growth has changed very quickly. We're referring to a specialist promptly."
        recheck = "Referral within 1-2 wk"
    elif tier == 3:
        action = ("Pattern warrants evaluation — workup based on direction:\n"
                  "  - Both declining: systemic/nutritional\n"
                  "  - Weight declining, height stable: nutritional/GI\n"
                  "  - Weight rising, height declining: DIVERGENT — cortisol evaluation\n"
                  "  - Height accelerating: pubertal timing evaluation")
        order_set = "Direction-specific workup. Divergent trajectory: 24-hr UFC or LNSC x2."
        parent_msg = "Your child's growth pattern has changed significantly. We need testing to understand why."
        recheck = "4-8 weeks"
    elif tier == 2:
        action = "Confirm with repeat measurement. Rule out measurement error first."
        parent_msg = "We noticed a shift in your child's growth curve. Likely normal, but we'd like to recheck."
        recheck = "3-6 months"

    return _tier_result(tier, "GROWTH TRAJECTORY CHANGE", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


def evaluate_bone_age(metrics: dict, patient: dict) -> dict:
    """BONE AGE DISCORDANCE — BA-CA delta tiered per spec (tier_3 >1.5yr, tier_4 >2.5yr)."""
    t = _load_thresholds()["bone_age"]
    ba_ca = metrics.get("ba_ca", {})
    delta = ba_ca.get("ba_ca_delta_years")

    # Data guard: requires bone age X-ray
    if delta is None:
        return _tier_result(1, "BONE AGE DISCORDANCE", ["No bone age data"],
                            recheck="No repeat unless growth changes")

    abs_delta = abs(delta)
    direction = ba_ca.get("ba_ca_direction", "delayed" if delta < 0 else "advanced")
    criteria = []
    tier = 1

    if abs_delta >= t["ba_ca_delta_years"]["tier_4_min"]:
        tier = 4
        criteria.append(f"BA-CA delta {delta:+.1f}y ({direction}) — severely discordant")
    elif abs_delta >= t["ba_ca_delta_years"]["tier_3_min"]:
        tier = 3
        criteria.append(f"BA-CA delta {delta:+.1f}y ({direction})")
    elif abs_delta >= t["ba_ca_delta_years"]["tier_2_min"]:
        tier = 2
        criteria.append(f"BA-CA delta {delta:+.1f}y ({direction})")

    action = ""
    order_set = ""
    recheck = "No repeat unless growth changes"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — immediate specialty evaluation recommended."
        order_set = "Full pubertal/GH axis workup. GnRH stim. Brain MRI. Genetic testing if dysplasia."
        parent_msg = "The bone age is significantly different from your child's age. We're referring to a specialist."
        recheck = "Referral within 2-4 wk"
    elif tier == 3:
        if direction == "delayed":
            action = "Pattern warrants evaluation — targeted workup: thyroid, GH axis, celiac evaluation."
            order_set = "Delayed: TSH, IGF-1, celiac, GH eval. Reassess PAH."
        else:
            action = "Pattern warrants evaluation — targeted workup: pubertal timing evaluation."
            order_set = "Advanced: LH, FSH, sex steroids, DHEA-S, 17-OHP. Reassess PAH."
        parent_msg = "The bone age combined with growth pattern suggests we need additional tests."
        recheck = "6-8 weeks post-labs"
    elif tier == 2:
        action = "Monitor. Likely constitutional pattern."
        order_set = "Repeat BA in 12 months."
        parent_msg = "The bone age shows slightly different bone development pace—usually not a concern."
        recheck = "12 months (repeat BA)"

    return _tier_result(tier, "BONE AGE DISCORDANCE", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


def evaluate_puberty(metrics: dict, patient: dict) -> dict:
    """ATYPICAL PUBERTAL TIMING — R2: only fire if Tanner data explicitly recorded.
    If absent at age threshold → Tier 2 'staging not documented'."""
    t = _load_thresholds()["puberty"]
    sex = patient.get("sex", "M")
    age_months = metrics.get("current", {}).get("age_months")
    if age_months is None:
        return _tier_result(1, "ATYPICAL PUBERTAL TIMING", ["No age data"])

    age_years = age_months / 12.0

    # Get latest Tanner staging from patient measurements
    tanner = patient.get("latest_tanner", {})
    breast = tanner.get("tanner_breast")
    genital = tanner.get("tanner_genital")
    pubic = tanner.get("tanner_pubic_hair")

    criteria = []
    tier = 1

    # ── Precocious puberty (R2: only trigger when Tanner data explicitly recorded) ──
    precocious_age = t["precocious_female_age"] if sex == "F" else t["precocious_male_age"]

    if sex == "F" and _tanner_recorded(breast) and breast >= t["tanner_precocious_stage"]:
        if age_years < 7.0:
            # Very early — Tier 3 for <7 (<6 AA/Hispanic)
            tier = max(tier, 3)
            criteria.append(f"Tanner breast B{breast} at age {age_years:.1f}y (< 7 yr)")
        elif age_years < precocious_age:
            tier = max(tier, 3)
            criteria.append(f"Tanner breast B{breast} at age {age_years:.1f}y (precocious: <{precocious_age}y)")
    elif sex == "M" and _tanner_recorded(genital) and genital >= t["tanner_precocious_stage"]:
        if age_years < 8.0:
            tier = max(tier, 3)
            criteria.append(f"Tanner genital G{genital} at age {age_years:.1f}y (< 8 yr)")
        elif age_years < precocious_age:
            tier = max(tier, 3)
            criteria.append(f"Tanner genital G{genital} at age {age_years:.1f}y (precocious: <{precocious_age}y)")

    # ── Delayed puberty ──
    delayed_age = t["delayed_female_age"] if sex == "F" else t["delayed_male_age"]
    severe_delayed = t.get("severe_delayed_age", 15.0)

    if age_years >= delayed_age:
        if sex == "F":
            if _tanner_recorded(breast):
                if breast <= 1:
                    # Tanner explicitly recorded as stage 1 — no development
                    if age_years >= severe_delayed:
                        tier = max(tier, 4)
                        criteria.append(f"No breast development (B{breast}) at age {age_years:.1f}y (≥{severe_delayed:.0f}y)")
                    else:
                        tier = max(tier, 3)
                        criteria.append(f"No breast development (B{breast}) at age {age_years:.1f}y (delayed: ≥{delayed_age}y)")
            else:
                # Tanner data absent — ONLY yellow (Tier 2): request documentation
                if age_years >= delayed_age:
                    tier = max(tier, 2)
                    criteria.append(f"Puberty staging not documented at age {age_years:.1f}y — please document Tanner stage")
        elif sex == "M":
            if _tanner_recorded(genital):
                if genital <= 1:
                    if age_years >= severe_delayed:
                        tier = max(tier, 4)
                        criteria.append(f"No genital development (G{genital}) at age {age_years:.1f}y (≥{severe_delayed:.0f}y)")
                    else:
                        tier = max(tier, 3)
                        criteria.append(f"No genital development (G{genital}) at age {age_years:.1f}y (delayed: ≥{delayed_age}y)")
            else:
                # Tanner data absent — ONLY yellow (Tier 2): request documentation
                if age_years >= delayed_age:
                    tier = max(tier, 2)
                    criteria.append(f"Puberty staging not documented at age {age_years:.1f}y — please document Tanner stage")

    # ── Tier 2: borderline early ──
    if sex == "F" and _tanner_recorded(breast) and breast >= 2:
        if 7.0 <= age_years < 8.0:
            tier = max(tier, 2)
            criteria.append(f"Borderline early breast development (B{breast}) at age {age_years:.1f}y")
    elif sex == "M" and _tanner_recorded(genital) and genital >= 2:
        if 8.0 <= age_years < 9.0:
            tier = max(tier, 2)
            criteria.append(f"Borderline early genital development (G{genital}) at age {age_years:.1f}y")

    # ── Tier 4 escalation: confirmed central precocity or lab confirmed ──
    if patient.get("confirmed_central_precocity") or patient.get("peripheral_pubertal_pattern"):
        tier = max(tier, 4)
        criteria.append("Central or peripheral pubertal activation confirmed on testing")

    action = ""
    order_set = ""
    recheck = "Routine well-child"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — immediate specialty evaluation recommended."
        order_set = "Brain MRI (all boys with confirmed central early puberty, girls <6). GnRH agonist discussion. Karyotype if delayed pattern."
        parent_msg = "Your child needs a specialist. Treatment is available to support healthy development."
        recheck = "Referral within 2-4 wk"
    elif tier == 3:
        action = "Pattern warrants evaluation — formal pubertal assessment."
        order_set = "Atypical Pubertal Timing — Early Workup" if any("precocious" in c or "early" in c.lower() or "before" in c.lower() for c in criteria) else "Atypical Pubertal Timing — Late Workup"
        parent_msg = "Your child's development pattern is outside the typical range. We need blood tests and imaging to understand better."
        recheck = "4-6 weeks"
    elif tier == 2:
        if any("not documented" in c for c in criteria):
            action = "Puberty staging data missing at expected age — document Tanner stage."
        else:
            action = "Close monitoring. Repeat Tanner in 3-6 months."
        order_set = "Bone age. Optional: LH, FSH, sex steroids."
        parent_msg = "We'd like to track your child's development pattern a bit more closely."
        recheck = "3-6 months"

    return _tier_result(tier, "ATYPICAL PUBERTAL TIMING", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


def evaluate_sga(metrics: dict, patient: dict) -> dict:
    """SGA — POST-NATAL GROWTH TRAJECTORY."""
    sga = metrics.get("sga", {})

    # Data guard: only fire if born SGA confirmed
    if not sga.get("born_sga"):
        return _tier_result(1, "SGA — POST-NATAL GROWTH TRAJECTORY", [])

    criteria = ["Born SGA (<10th for GA)"]
    tier = 2  # Minimum tier for SGA patients

    current_ht_z = sga.get("current_height_z")

    if sga.get("sga_gh_eligible"):
        tier = 4
        ht_z_str = f"{current_ht_z:.2f}" if current_ht_z is not None else "?"
        criteria.append(f"GH eligible: age ≥2-4y, height z={ht_z_str}, failed catch-up, no other treatable cause")
    elif sga.get("catch_up_achieved") is False:
        if current_ht_z is not None and current_ht_z <= -2.5:
            tier = 3
            criteria.append(f"No catch-up: height z={current_ht_z:.2f} (≤ -2.5 SD) at age ≥3")
        else:
            tier = 3
            criteria.append("No catch-up growth (height still < -2 SD)")
    elif sga.get("catch_up_achieved"):
        tier = 1
        criteria.append("Catch-up achieved (height ≥ -2 SD)")

    action = ""
    order_set = ""
    recheck = "Routine well-child"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — specialty evaluation for growth treatment."
        order_set = "Endo referral with birth records, growth chart, labs, BA. GH per SGA protocol (~0.067 mg/kg/day)."
        parent_msg = "Your child may qualify for growth treatment. The specialist will discuss this in detail."
        recheck = "Endo within 4 wk"
    elif tier == 3:
        action = "Pattern warrants evaluation — assess for growth treatment eligibility."
        order_set = "IGF-1, IGFBP-3, TSH, BA, celiac. Document birth data."
        parent_msg = "Your child hasn't caught up from their small birth size. A specialist can evaluate options."
        recheck = "6-8 weeks post-labs"
    elif tier == 2:
        action = "Close monitoring through age 3-4."
        order_set = "IGF-1, bone age. Monitor GV q3-6 mo."
        parent_msg = "Your child was born small and is still catching up. We're monitoring closely."
        recheck = "3-6 months"

    return _tier_result(tier, "SGA — POST-NATAL GROWTH TRAJECTORY", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


def evaluate_divergent_trajectory(metrics: dict, patient: dict) -> dict:
    """DIVERGENT WEIGHT-HEIGHT TRAJECTORY — replaces old Cushing's evaluator.
    R1: Pattern-based trigger, not condition name.
    R3: Trajectory divergence is the alert.
    Data guard: requires ≥6 months of both weight AND height z-scores."""
    z_deltas = metrics.get("z_deltas", {})
    crossing = metrics.get("crossing", {})

    wt_delta = z_deltas.get("weight_z_delta_6mo")
    if wt_delta is None:
        wt_delta = z_deltas.get("weight_z_delta_12mo")
    ht_delta = z_deltas.get("height_z_delta_12mo")

    # Data guard: requires both weight and height trajectory data
    has_wt_data = wt_delta is not None
    has_ht_data = ht_delta is not None

    if not has_wt_data and not has_ht_data:
        return _tier_result(1, "DIVERGENT WEIGHT–HEIGHT TRAJECTORY", [],
                            parent_msg="Weight and height are growing proportionally.")

    criteria = []
    tier = 1

    # Tier 4: Divergent + abnormal cortisol (requires lab data)
    cortisol_abnormal = patient.get("cortisol_screening_abnormal", False)
    cortisol_count = patient.get("abnormal_cortisol_tests", 0)

    if cortisol_count >= 2 or patient.get("adrenal_mass_found"):
        tier = 4
        if cortisol_count >= 2:
            criteria.append(f"≥2 cortisol screening tests abnormal ({cortisol_count} abnormal)")
        if patient.get("adrenal_mass_found"):
            criteria.append("Adrenal mass incidentally found")
        if patient.get("clinical_phenotype_divergent"):
            criteria.append("Clinical phenotype: central obesity + growth failure + HTN + striae")

    # Tier 3: Weight up + height down confirmed
    elif has_wt_data and has_ht_data:
        weight_up = wt_delta > 0.3  # weight trending up
        height_down = ht_delta < -0.3  # height trending down

        if weight_up and height_down:
            tier = max(tier, 3)
            criteria.append(f"Weight z-delta {wt_delta:+.2f} (up) + height z-delta {ht_delta:+.2f} (down) — confirmed divergence")

        # Check for associated features that strengthen the pattern
        if patient.get("central_adiposity") or patient.get("striae") or patient.get("facial_changes"):
            if tier >= 3:
                criteria.append("Central obesity + facial/skin changes + striae noted")
        if patient.get("htn_in_weight_gain_context"):
            if tier >= 2:
                tier = max(tier, 3)
                criteria.append("Unexplained HTN in setting of weight gain")
        if patient.get("chronic_steroid_use"):
            tier = max(tier, 3)
            criteria.append("Chronic steroid use + growth deceleration")

    # Tier 2: Weight accelerating, height stable (not yet declining)
    if tier < 3 and has_wt_data:
        weight_up = wt_delta > 0.3
        height_stable = has_ht_data and abs(ht_delta) <= 0.3
        if weight_up and (height_stable or not has_ht_data):
            tier = max(tier, 2)
            if has_ht_data:
                criteria.append(f"Weight accelerating (z-delta {wt_delta:+.2f}), height stable (z-delta {ht_delta:+.2f})")
            else:
                criteria.append(f"Weight accelerating (z-delta {wt_delta:+.2f}), height trajectory pending")

    # Also check crossing data for divergence
    if crossing.get("trajectories_divergent") and tier < 3:
        tier = max(tier, 3)
        ht_dir = crossing.get("height_crossing_direction", "?")
        wt_dir = crossing.get("weight_crossing_direction", "?")
        criteria.append(f"Height trending {ht_dir}, weight trending {wt_dir} — divergent")

    action = ""
    order_set = ""
    recheck = "Routine well-child"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — immediate specialty evaluation recommended."
        order_set = "Endo referral. MRI pituitary. CT adrenals. Consider IPSS."
        parent_msg = "Test results indicate a hormonal pattern needing specialist evaluation."
        recheck = "Referral within 1-2 wk"
    elif tier == 3:
        action = "Pattern warrants evaluation — divergent trajectory confirmed. Cortisol evaluation indicated."
        order_set = "Divergent Trajectory Workup (Cortisol Evaluation)"
        parent_msg = "The pattern of weight gain with slower height growth warrants testing."
        recheck = "2-4 weeks for results"
    elif tier == 2:
        action = "Monitor both trajectories. Reassess in 3-6 months."
        parent_msg = "We want to watch how weight and height change relative to each other."
        recheck = "3-6 months"

    return _tier_result(tier, "DIVERGENT WEIGHT–HEIGHT TRAJECTORY", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


def evaluate_female_short_stature(metrics: dict, patient: dict) -> dict:
    """UNEXPLAINED SHORT STATURE — FEMALES.
    R1: Karyotype is standard workup step for unexplained female short stature."""
    t = _load_thresholds()["female_short_stature"]
    sex = patient.get("sex", "M")

    if sex != t["applies_to"]:
        return _tier_result(1, "UNEXPLAINED SHORT STATURE — FEMALES", [])

    ht_z = metrics.get("current", {}).get("height_z")
    if ht_z is None:
        return _tier_result(1, "UNEXPLAINED SHORT STATURE — FEMALES", ["No height data"])

    criteria = []
    tier = 1

    # Check for confirmed karyotype result
    karyotype_confirmed = patient.get("karyotype_confirmed")
    karyotype_result = patient.get("karyotype_result", "")

    # Tier 4: Karyotype confirms 45,X or mosaic variant
    if karyotype_confirmed and ("45,X" in karyotype_result or "mosaic" in karyotype_result.lower()):
        tier = 4
        criteria.append(f"Karyotype confirms {karyotype_result}")
        if patient.get("cardiac_anomaly"):
            criteria.append("Cardiac anomaly identified")

    # Tier 3: Short + additional features or very short
    elif ht_z <= t["height_z_tier_3"]:
        features = []
        if patient.get("webbed_neck"):
            features.append("webbed neck")
        if patient.get("wide_spaced_nipples"):
            features.append("wide-spaced nipples")
        if patient.get("cubitus_valgus"):
            features.append("cubitus valgus")
        if patient.get("cardiac_murmur"):
            features.append("cardiac murmur")
        if patient.get("lymphedema_history"):
            features.append("lymphedema history")

        if len(features) >= 2 or ht_z < -2.33:  # <3rd %ile or 2+ features
            tier = 3
            criteria.append(f"Female with height z={ht_z:.2f} (< 3rd %ile)")
            if features:
                criteria.append(f"Associated features: {', '.join(features)}")
        else:
            tier = 2
            criteria.append(f"Female with unexplained short stature (z={ht_z:.2f})")

    # Tier 2: Unexplained short stature, karyotype indicated
    elif ht_z <= t["height_z_tier_2"]:
        tier = 2
        criteria.append(f"Female with unexplained short stature (z={ht_z:.2f}) — karyotype indicated")

    action = ""
    order_set = ""
    recheck = "Routine well-child"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — immediate multidisciplinary referral. GH initiation evaluation."
        order_set = "Endo for GH. Cardiology. Genetics. Estrogen planning at ~12 yr."
        parent_msg = "Your daughter has a chromosomal finding that explains her growth pattern. Growth treatment and hormone support are available."
        recheck = "Endo within 2-4 wk"
    elif tier == 3:
        action = "Pattern warrants evaluation — comprehensive multisystem workup."
        order_set = "Female Short Stature — Chromosomal Workup"
        parent_msg = "We're running tests to understand your daughter's growth and features. If there's a chromosomal finding, effective treatments exist."
        recheck = "4-6 wk"
    elif tier == 2:
        action = "Karyotype recommended. This is standard of care for unexplained short stature in females."
        order_set = "Karyotype."
        parent_msg = "We'd like to run a chromosome test. This is standard for girls with unexplained short stature."
        recheck = "6-8 weeks"

    return _tier_result(tier, "UNEXPLAINED SHORT STATURE — FEMALES", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


def evaluate_metabolic_screen(metrics: dict, patient: dict) -> dict:
    """GROWTH DECELERATION — METABOLIC SCREEN.
    R1: 'Growth deceleration — metabolic screen' replaces disease-specific labels.
    3 tiers per spec (no Tier 4 — escalation goes to specific category)."""
    ht_z = metrics.get("current", {}).get("height_z")
    gv_pct = metrics.get("velocity", {}).get("velocity_percentile")
    ht_delta = metrics.get("z_deltas", {}).get("height_z_delta_12mo")
    t = _load_thresholds()["metabolic_screen"]

    trigger = False
    criteria = []

    # Check for growth deceleration without clear cause
    if ht_z is not None and ht_z <= t["height_z_trigger"]:
        trigger = True
        criteria.append(f"Height z={ht_z:.2f}")
    if gv_pct is not None and gv_pct < t["gv_percentile_trigger"]:
        trigger = True
        criteria.append(f"GV {gv_pct:.0f}th %ile")
    if ht_delta is not None and ht_delta < -t.get("height_z_delta_12mo_trigger", 0.5):
        trigger = True
        criteria.append(f"Height z-delta {ht_delta:+.2f} decline with no other explanation")

    # New symptoms
    if patient.get("fatigue") or patient.get("constipation") or patient.get("gi_complaints") or patient.get("anemia"):
        trigger = True
        symptoms = []
        if patient.get("fatigue"):
            symptoms.append("fatigue")
        if patient.get("constipation"):
            symptoms.append("constipation")
        if patient.get("gi_complaints"):
            symptoms.append("GI complaints")
        if patient.get("anemia"):
            symptoms.append("anemia")
        criteria.append(f"New symptoms: {', '.join(symptoms)}")

    if not trigger:
        return _tier_result(1, "GROWTH DECELERATION — METABOLIC SCREEN", [],
                            parent_msg="No concerns for thyroid or digestive issues.")

    # Check if labs already resulted
    tsh = patient.get("latest_tsh")
    ttg = patient.get("latest_ttg_iga")

    if tsh is not None or ttg is not None:
        # Labs have been done — check for abnormal results
        abnormal = False
        if tsh is not None and tsh > 5.0:  # Elevated TSH
            abnormal = True
            criteria.append(f"Elevated TSH: {tsh}")
        if ttg is not None and ttg > 1.0:  # Positive tTG
            abnormal = True
            criteria.append(f"Positive tTG-IgA: {ttg}")

        if abnormal:
            return _tier_result(
                3, "GROWTH DECELERATION — METABOLIC SCREEN", criteria,
                action="Abnormal results — confirmatory testing and treatment initiation.",
                order_set="Thyroid: repeat TSH/fT4, antibodies, thyroid US, start levothyroxine. Celiac: GI referral for EGD/biopsy, dietitian.",
                parent_msg="Screening found a treatable condition that may be affecting growth. Treatment is effective.",
                recheck="4-6 weeks post-treatment",
            )

    # Tier 2: screen indicated
    return _tier_result(
        t["tier_when_triggered"], "GROWTH DECELERATION — METABOLIC SCREEN", criteria,
        action="Growth deceleration pattern — screen with basic metabolic labs.",
        order_set="TSH, free T4, tTG-IgA + total IgA.",
        parent_msg="We'd like to check a few things as part of understanding your child's growth change.",
        recheck="2-4 weeks",
    )


def evaluate_disproportion(metrics: dict, patient: dict) -> dict:
    """DISPROPORTIONATE GROWTH — body segment ratios."""
    latest_meas = patient.get("latest_measurement", {})
    sitting_ht = latest_meas.get("sitting_height_cm")
    arm_span = latest_meas.get("arm_span_cm")
    height = latest_meas.get("height_cm")

    # Data guard: requires sitting height or arm span measurement
    if not height or (not sitting_ht and not arm_span):
        return _tier_result(1, "DISPROPORTIONATE GROWTH", [],
                            parent_msg="Your child's body proportions are normal.")

    criteria = []
    tier = 1

    if sitting_ht and height:
        ratio = sitting_ht / height
        # Age-specific norms — approximate thresholds for children >5yr
        if ratio > 0.58:
            tier = max(tier, 3)
            criteria.append(f"Sitting height ratio {ratio:.3f} (> 2 SD from age norm)")
        elif ratio > 0.55:
            tier = max(tier, 2)
            criteria.append(f"Sitting height ratio {ratio:.3f} (> 1 SD from age norm)")

    if arm_span and height:
        span_diff = arm_span - height
        if abs(span_diff) > 5:
            tier = max(tier, 3)
            criteria.append(f"Arm span - height = {span_diff:+.1f} cm (> 5 cm difference)")
        elif abs(span_diff) > 2:
            tier = max(tier, 2)
            criteria.append(f"Arm span - height = {span_diff:+.1f} cm (> 2 cm difference)")

    # Check for skeletal features or confirmed diagnosis
    if patient.get("confirmed_skeletal_dysplasia") or patient.get("shox_deficiency") or patient.get("achondroplasia"):
        tier = max(tier, 4)
        if patient.get("confirmed_skeletal_dysplasia"):
            criteria.append("Confirmed skeletal dysplasia")
        if patient.get("shox_deficiency"):
            criteria.append("SHOX deficiency confirmed")
        if patient.get("achondroplasia"):
            criteria.append("Achondroplasia confirmed")

    action = ""
    order_set = ""
    recheck = "Routine well-child"
    parent_msg = ""
    if tier == 4:
        action = "Urgent pattern — multidisciplinary referral (genetics + orthopedics + endocrine)."
        order_set = "Genetics, orthopedics, endo for GH if SHOX. PT assessment. Achondroplasia: vosoritide evaluation."
        parent_msg = "We have a diagnosis. A specialist team will coordinate care with possible treatment options."
        recheck = "Referral within 2-4 wk"
    elif tier == 3:
        action = "Pattern warrants evaluation — skeletal survey and genetics referral."
        order_set = "Skeletal Disproportion Evaluation"
        parent_msg = "Measurements show different proportions than typical. We'd like imaging and genetic testing."
        recheck = "4-6 weeks"
    elif tier == 2:
        action = "Formal anthropometrics. Compare to parents."
        order_set = "Measure sitting height, arm span, calculate ratios."
        parent_msg = "We're taking additional measurements to assess body proportions."
        recheck = "Recheck next visit"

    return _tier_result(tier, "DISPROPORTIONATE GROWTH", criteria, action,
                        order_set=order_set, parent_msg=parent_msg, recheck=recheck)


# ═══════════════════════════════════════════════════════════════
#  Standalone Trajectory Alert Evaluators
# ═══════════════════════════════════════════════════════════════

def evaluate_height_z_delta(metrics: dict, patient: dict) -> dict:
    """Standalone height z-delta /12mo trajectory alert (spec row).
    Tier 2 >0.5 SD, Tier 3 >1.0 SD, Tier 4 >2.0 SD.
    SUPPRESS near adult height (girls ~14y, boys ~16y)."""
    t = _load_thresholds()["height_z_delta_12mo"]
    ht_delta = metrics.get("z_deltas", {}).get("height_z_delta_12mo")

    if ht_delta is None:
        return _tier_result(1, "HEIGHT Z-DELTA /12MO", ["Insufficient longitudinal data"])

    # Physiologic deceleration near end of growth — don't flag
    if _near_adult_height(patient) and ht_delta <= 0:
        return _tier_result(1, "HEIGHT Z-DELTA /12MO",
                            ["Near adult height — stable/slowing growth is physiologic"])

    abs_delta = abs(ht_delta)
    direction = "decline" if ht_delta < 0 else "increase"
    criteria = []
    tier = 1

    if abs_delta > t["tier_4_threshold"]:
        tier = 4
        criteria.append(f"Height z-delta {ht_delta:+.2f} over 12 mo ({direction} > {t['tier_4_threshold']} SD)")
    elif abs_delta > t["tier_3_threshold"]:
        tier = 3
        criteria.append(f"Height z-delta {ht_delta:+.2f} over 12 mo ({direction} > {t['tier_3_threshold']} SD)")
    elif abs_delta > t["tier_2_threshold"]:
        tier = 2
        criteria.append(f"Height z-delta {ht_delta:+.2f} over 12 mo ({direction} > {t['tier_2_threshold']} SD)")

    action = ""
    if tier == 4:
        action = "Urgent pattern — immediate specialty evaluation recommended."
    elif tier == 3:
        action = "Pattern warrants evaluation — full growth workup."
    elif tier == 2:
        action = "Monitor trajectory. Confirm with repeat measurement."

    return _tier_result(tier, "HEIGHT Z-DELTA /12MO", criteria, action)


def evaluate_weight_z_delta(metrics: dict, patient: dict) -> dict:
    """Standalone weight z-delta /6mo trajectory alert (spec row).
    Tier 2 >0.5 SD, Tier 3 >1.0 SD, Tier 4 >2.0 SD.
    Applies to both gain and loss — flag direction."""
    t = _load_thresholds()["weight_z_delta_6mo"]
    wt_delta = metrics.get("z_deltas", {}).get("weight_z_delta_6mo")
    if wt_delta is None:
        wt_delta = metrics.get("z_deltas", {}).get("weight_z_delta_12mo")

    if wt_delta is None:
        return _tier_result(1, "WEIGHT Z-DELTA /6MO", ["Insufficient longitudinal data"])

    abs_delta = abs(wt_delta)
    direction = "loss" if wt_delta < 0 else "gain"
    criteria = []
    tier = 1

    if abs_delta > t["tier_4_threshold"]:
        tier = 4
        criteria.append(f"Weight z-delta {wt_delta:+.2f} over 6 mo ({direction} > {t['tier_4_threshold']} SD)")
    elif abs_delta > t["tier_3_threshold"]:
        tier = 3
        criteria.append(f"Weight z-delta {wt_delta:+.2f} over 6 mo ({direction} > {t['tier_3_threshold']} SD)")
    elif abs_delta > t["tier_2_threshold"]:
        tier = 2
        criteria.append(f"Weight z-delta {wt_delta:+.2f} over 6 mo ({direction} > {t['tier_2_threshold']} SD)")

    action = ""
    if tier == 4:
        action = "Urgent pattern — immediate specialty evaluation recommended."
    elif tier == 3:
        action = "Pattern warrants evaluation — full growth workup."
    elif tier == 2:
        action = "Monitor trajectory. Confirm with repeat measurement."

    return _tier_result(tier, "WEIGHT Z-DELTA /6MO", criteria, action)


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
        Dict with per-category results (keyed by slug) + overall max_tier.
    """
    results = {
        "short_stature": evaluate_short_stature(metrics, patient),
        "tall_stature": evaluate_tall_stature(metrics, patient),
        "excess_weight_gain": evaluate_excess_weight_gain(metrics, patient),
        "weight_faltering": evaluate_weight_faltering(metrics, patient),
        "growth_trajectory_change": evaluate_growth_trajectory_change(metrics, patient),
        "bone_age_discordance": evaluate_bone_age(metrics, patient),
        "atypical_pubertal_timing": evaluate_puberty(metrics, patient),
        "sga_postnatal_trajectory": evaluate_sga(metrics, patient),
        "divergent_trajectory": evaluate_divergent_trajectory(metrics, patient),
        "female_short_stature": evaluate_female_short_stature(metrics, patient),
        "metabolic_screen": evaluate_metabolic_screen(metrics, patient),
        "disproportionate_growth": evaluate_disproportion(metrics, patient),
        # Standalone trajectory alerts
        "height_z_delta": evaluate_height_z_delta(metrics, patient),
        "weight_z_delta": evaluate_weight_z_delta(metrics, patient),
    }

    # Overall highest tier
    max_tier = max(
        r["tier"] for r in results.values() if isinstance(r, dict) and "tier" in r
    )
    results["max_tier"] = max_tier
    results["max_tier_label"] = _TIER_LABELS.get(max_tier, "Unknown")

    # Flagged categories (tier >= 2)
    flagged = [k for k, v in results.items()
               if isinstance(v, dict) and v.get("tier", 0) >= 2]
    results["categories_flagged"] = flagged

    return results
