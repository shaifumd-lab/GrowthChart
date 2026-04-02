"""Chart data API — returns Plotly-compatible JSON for growth charts."""
from flask import Blueprint, request, jsonify, current_app
from config import (
    Standard, Indicator, PERCENTILE_LINES, PERCENTILE_ZSCORES,
    zscore_to_percentile,
)
from clinical.mph import mph_summary
from clinical.bayley_pinneau import predict_adult_height
from clinical.velocity import compute_velocity, get_velocity_reference_curves
from clinical.syndromic import get_syndromic_percentile_curves

charts_bp = Blueprint("charts", __name__)

# ── Color scheme ──────────────────────────────────────────────
# Percentile line colors (matching clinical convention)
LINE_STYLES = {
    3:  {"color": "#DC2626", "dash": "dash",  "width": 0.8},   # red
    5:  {"color": "#EA580C", "dash": "dot",   "width": 0.7},   # orange
    10: {"color": "#D97706", "dash": "dash",  "width": 0.8},   # amber
    25: {"color": "#65A30D", "dash": "dot",   "width": 0.8},   # lime
    50: {"color": "#15803D", "dash": "solid", "width": 1.8},   # green (median)
    75: {"color": "#65A30D", "dash": "dot",   "width": 0.8},   # lime
    90: {"color": "#D97706", "dash": "dash",  "width": 0.8},   # amber
    95: {"color": "#EA580C", "dash": "dot",   "width": 0.7},   # orange
    97: {"color": "#DC2626", "dash": "dash",  "width": 0.8},   # red
}

# Band fills between adjacent percentiles
BAND_COLORS = [
    (3, 5,   "rgba(254,202,202,0.35)"),   # red-200 (severe low)
    (5, 10,  "rgba(254,215,170,0.30)"),   # orange-200
    (10, 25, "rgba(254,249,195,0.30)"),   # yellow-100
    (25, 50, "rgba(209,250,229,0.40)"),   # green-100 (normal)
    (50, 75, "rgba(209,250,229,0.40)"),   # green-100
    (75, 90, "rgba(254,249,195,0.30)"),   # yellow-100
    (90, 95, "rgba(254,215,170,0.30)"),   # orange-200
    (95, 97, "rgba(254,202,202,0.35)"),   # red-200 (severe high)
]

PATIENT_COLORS = {"M": "#2563EB", "F": "#DB2777"}


@charts_bp.route("/charts/percentiles", methods=["GET"])
def get_percentiles():
    """Return percentile curve traces for Plotly.

    Query params:
        indicator: hfa, wfa, bfa (default: hfa)
        standard: CDC, WHO (default: CDC)
        sex: M, F (default: M)
        age_min: float months (default: 0)
        age_max: float months (default: 240)
        syndrome: Turner, Down (optional) — adds syndromic curves
    """
    engine = current_app.engine
    indicator = request.args.get("indicator", "hfa")
    standard = request.args.get("standard", "CDC")
    sex = request.args.get("sex", "M")
    age_min = float(request.args.get("age_min", 0))
    age_max = float(request.args.get("age_max", 240))
    syndrome = request.args.get("syndrome", "").strip()

    traces = []
    curves_data = {}  # pct -> [(age, value)]

    for pct in PERCENTILE_LINES:
        z = PERCENTILE_ZSCORES[pct]
        curve = engine.get_percentile_curve(standard, indicator, sex, z, age_min, age_max, step=1)
        if not curve:
            continue

        ages_years = [pt[0] / 12.0 for pt in curve]
        values = [pt[1] for pt in curve]
        curves_data[pct] = (ages_years, values)

        style = LINE_STYLES.get(pct, {"color": "#999", "dash": "dot", "width": 0.5})
        traces.append({
            "name": f"P{pct}" if pct != 50 else "P50 (median)",
            "x": ages_years,
            "y": values,
            "mode": "lines",
            "line": style,
            "hovertemplate": f"P{pct}: %{{y:.1f}} at %{{x:.1f}} years<extra></extra>",
            "showlegend": pct in (3, 10, 25, 50, 75, 90, 97),
        })

    # Build band fills
    bands = []
    for p_low, p_high, fillcolor in BAND_COLORS:
        if p_low in curves_data and p_high in curves_data:
            x_low, y_low = curves_data[p_low]
            x_high, y_high = curves_data[p_high]
            # Use shared x-axis (both should be same ages)
            bands.append({
                "x": x_low + x_high[::-1],
                "y": y_low + y_high[::-1],
                "fill": "toself",
                "fillcolor": fillcolor,
                "line": {"width": 0},
                "showlegend": False,
                "hoverinfo": "skip",
            })

    # ── Syndromic curves (if requested and indicator is hfa) ──
    syndromic_traces = []
    if syndrome and indicator == "hfa":
        synd_curves = get_syndromic_percentile_curves(syndrome, sex)
        if synd_curves:
            syndromic_traces = synd_curves

    y_label = Indicator.Y_LABELS.get(indicator, "Value")
    return jsonify({
        "traces": traces,
        "bands": bands,
        "syndromic_traces": syndromic_traces,
        "layout": {
            "xaxis": {
                "title": "Age (years)",
                "dtick": 1,
                "minor": {"dtick": 0.25, "showgrid": True, "gridcolor": "rgba(0,0,0,0.05)"},
                "gridcolor": "rgba(0,0,0,0.1)",
                "zeroline": False,
                "autorange": True,
            },
            "yaxis": {
                "title": y_label,
                "dtick": 10,
                "minor": {"dtick": 1, "showgrid": True, "gridcolor": "rgba(0,0,0,0.03)"},
                "gridcolor": "rgba(0,0,0,0.08)",
                "zeroline": False,
            },
            "dragmode": "zoom",
            "hovermode": "closest",
            "margin": {"l": 60, "r": 80, "t": 50, "b": 50},
            "paper_bgcolor": "#FAFBFC",
            "plot_bgcolor": "#FFFFFF",
        },
    })


@charts_bp.route("/charts/mph-curve", methods=["GET"])
def get_mph_curve():
    """Return a percentile curve matching the MPH z-score across all ages.

    The MPH (mid-parental height) defines a genetic target. We compute what
    z-score the MPH corresponds to at adult height (18y for the given standard),
    then trace that same z-score curve across all ages. This lets clinicians
    visually compare the child's growth trajectory to their genetic potential.

    Query params:
        mph: float — mid-parental height in cm (required)
        standard: CDC or WHO
        sex: M or F
    """
    engine = current_app.engine

    mph_cm = request.args.get("mph", type=float)
    if mph_cm is None:
        return jsonify({"error": "mph parameter required"}), 400

    standard = request.args.get("standard", "CDC")
    sex = request.args.get("sex", "M")

    # Compute the z-score of MPH at adult age
    # CDC goes to 240 months (20y), WHO to 228 months (19y)
    adult_age = 240 if standard == "CDC" else 228
    mph_zscore = engine.compute_zscore(mph_cm, adult_age, sex, "hfa", standard)

    if mph_zscore is None:
        # Try slightly younger ages in case the table doesn't extend exactly
        for try_age in [216, 204, 192]:
            mph_zscore = engine.compute_zscore(mph_cm, try_age, sex, "hfa", standard)
            if mph_zscore is not None:
                break

    if mph_zscore is None:
        return jsonify({"error": "Could not compute MPH z-score"}), 400

    mph_pct = zscore_to_percentile(mph_zscore)

    # Get the full curve for this z-score across all ages
    age_max = 240 if standard == "CDC" else 228
    curve = engine.get_percentile_curve(standard, "hfa", sex, mph_zscore, 0, age_max, step=1)
    if not curve:
        return jsonify({"error": "Could not generate MPH curve"}), 400

    ages_years = [pt[0] / 12.0 for pt in curve]
    values = [pt[1] for pt in curve]

    trace = {
        "name": f"MPH P{mph_pct:.0f} ({mph_cm:.1f} cm, z={mph_zscore:+.2f})",
        "x": ages_years,
        "y": values,
        "mode": "lines",
        "line": {
            "color": "rgba(107, 114, 128, 0.7)",  # grey-500
            "dash": "dot",
            "width": 2.5,
        },
        "hovertemplate": f"MPH P{mph_pct:.0f}: %{{y:.1f}} at %{{x:.1f}} years<extra></extra>",
        "showlegend": True,
    }

    return jsonify({
        "trace": trace,
        "mph_zscore": round(mph_zscore, 2),
        "mph_percentile": round(mph_pct, 1),
    })


@charts_bp.route("/charts/patient-data", methods=["GET"])
def get_patient_data():
    """Return patient measurement data as a Plotly trace.

    Enhanced with:
    - MPH target range band (age 18-20)
    - Bone age markers (diamond in purple)
    - Bayley-Pinneau predicted adult height (star at age 18)
    """
    db = current_app.db
    engine = current_app.engine
    patient_id = request.args.get("patient_id", type=int)
    indicator = request.args.get("indicator", "hfa")
    standard = request.args.get("standard", "CDC")

    if not patient_id:
        return jsonify({"error": "patient_id required"}), 400

    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    measurements = db.get_measurements(patient_id)
    if not measurements:
        return jsonify({"trace": None, "patient_name": f"{patient.first_name} {patient.last_name}"})

    # Determine measurement field based on indicator
    field_map = {"hfa": "height_cm", "wfa": "weight_kg", "bfa": "bmi"}
    field = field_map.get(indicator, "height_cm")

    ages_years = []
    values = []
    z_labels = []
    hover_texts = []
    bone_age_x = []
    bone_age_y = []
    bone_age_labels = []
    # Track latest bone age + height for Bayley-Pinneau
    latest_ba_measurement = None

    for m in measurements:
        if not patient.birth_date or not m.date:
            continue
        m.compute_age(patient.birth_date)
        if indicator == "bfa":
            m.compute_bmi()

        val = getattr(m, field, None)
        if not val or not m.age_months or m.age_months <= 0:
            continue

        z = engine.compute_zscore(val, m.age_months, patient.sex, indicator, standard)
        pct = round(zscore_to_percentile(z), 1) if z is not None else None

        age_years = m.age_months / 12.0
        ages_years.append(age_years)
        values.append(val)

        z_str = f"{z:+.2f}" if z is not None else "—"
        z_labels.append(z_str)

        pct_str = f"{pct:.1f}%" if pct is not None else ""
        hover_texts.append(
            f"<b>{m.date.strftime('%d/%m/%Y')}</b><br>"
            f"Age: {m.age_str}<br>"
            f"{Indicator.Y_LABELS.get(indicator, 'Value')}: {val:.1f}<br>"
            f"SDS: {z_str}<br>"
            f"Percentile: {pct_str}"
        )

        # Bone age point (if available)
        bone_age = getattr(m, "bone_age_years", None)
        if bone_age and indicator == "hfa" and m.height_cm:
            bone_age_x.append(bone_age)
            bone_age_y.append(m.height_cm)
            ba_z = engine.compute_zscore(m.height_cm, bone_age * 12, patient.sex, indicator, standard)
            ba_z_str = f"{ba_z:+.2f}" if ba_z is not None else "—"
            bone_age_labels.append(f"BA {ba_z_str}")
            # Track latest for BP prediction
            latest_ba_measurement = {
                "height_cm": m.height_cm,
                "bone_age_years": bone_age,
            }

    sex_label = "Boys" if patient.sex == "M" else "Girls"
    color = PATIENT_COLORS.get(patient.sex, "#2563EB")

    result = {
        "trace": {
            "name": f"{patient.first_name} {patient.last_name}",
            "x": ages_years,
            "y": values,
            "text": z_labels,
            "textposition": "top center",
            "textfont": {"size": 10, "color": color},
            "mode": "lines+markers+text",
            "line": {"color": color, "width": 2},
            "marker": {"color": color, "size": 8, "line": {"width": 1, "color": "white"}},
            "hovertemplate": "%{customdata}<extra></extra>",
            "customdata": hover_texts,
        },
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "sex": patient.sex,
        "sex_label": sex_label,
        "birth_date": patient.birth_date.isoformat() if patient.birth_date else None,
        "standard": standard,
        "indicator": indicator,
        "indicator_label": Indicator.LABELS.get(indicator, indicator),
        "syndrome": patient.syndrome or "",
    }

    # Add bone age trace if we have data
    if bone_age_x:
        result["bone_age_trace"] = {
            "name": "Height-for-Bone-Age",
            "x": bone_age_x,
            "y": bone_age_y,
            "text": bone_age_labels,
            "textposition": "top center",
            "textfont": {"size": 9, "color": "#9333EA"},
            "mode": "markers+text",
            "marker": {"color": "#9333EA", "size": 10, "symbol": "diamond",
                        "line": {"width": 1.5, "color": "white"}},
            "showlegend": True,
            "hovertemplate": "Bone Age: %{x:.1f}y<br>Height: %{y:.1f}cm<br>%{text}<extra></extra>",
        }

    # ── MPH target height band (Phase 12) ─────────────────────
    if indicator == "hfa":
        mph_info = mph_summary(
            patient.father_height_cm,
            patient.mother_height_cm,
            patient.sex,
            patient.mph_cm if patient.mph_user_edited else None,
        )
        if mph_info:
            result["mph"] = mph_info
            # Target height band shape (horizontal band at age 18-20)
            result["target_height_shape"] = {
                "type": "rect",
                "xref": "x",
                "yref": "y",
                "x0": 18,
                "x1": 20,
                "y0": mph_info["range_low"],
                "y1": mph_info["range_high"],
                "fillcolor": "rgba(107, 114, 128, 0.12)",
                "line": {"color": "rgba(107, 114, 128, 0.5)", "width": 1, "dash": "dot"},
            }
            # MPH line annotation
            result["mph_annotation"] = {
                "x": 19,
                "y": mph_info["mph"],
                "text": f"MPH {mph_info['mph']:.1f}",
                "showarrow": False,
                "font": {"size": 10, "color": "#6B7280"},
                "bgcolor": "rgba(255,255,255,0.8)",
            }

    # ── Bayley-Pinneau PAH (Phase 14) ─────────────────────────
    if indicator == "hfa" and latest_ba_measurement:
        bp_result = predict_adult_height(
            latest_ba_measurement["height_cm"],
            latest_ba_measurement["bone_age_years"],
            patient.sex,
        )
        if bp_result:
            result["pah"] = bp_result
            result["pah_trace"] = {
                "name": f"PAH {bp_result['pah']:.1f} cm",
                "x": [18],
                "y": [bp_result["pah"]],
                "mode": "markers+text",
                "text": [f"PAH {bp_result['pah']:.1f}"],
                "textposition": "top center",
                "textfont": {"size": 9, "color": "#B45309"},
                "marker": {
                    "color": "#B45309",
                    "size": 12,
                    "symbol": "star",
                    "line": {"width": 1, "color": "white"},
                },
                "showlegend": True,
                "hovertemplate": (
                    f"Predicted Adult Height: {bp_result['pah']:.1f} cm<br>"
                    f"Range: {bp_result['confidence_range'][0]:.1f}–{bp_result['confidence_range'][1]:.1f} cm<br>"
                    f"% achieved: {bp_result['pct_achieved']:.1f}%"
                    "<extra></extra>"
                ),
            }

    # ── GH therapy start line ──────────────────────────────────
    if patient.gh_start_date and patient.birth_date:
        gh_age_days = (patient.gh_start_date - patient.birth_date).days
        gh_age_years = gh_age_days / 365.25
        result["gh_line"] = {
            "age_years": gh_age_years,
            "date": patient.gh_start_date.isoformat(),
        }

    return jsonify(result)


@charts_bp.route("/charts/velocity", methods=["GET"])
def get_velocity():
    """Return growth velocity chart data as Plotly JSON.

    Query params:
        patient_id: int (required)
        standard: CDC, WHO (default: CDC)
    """
    db = current_app.db
    patient_id = request.args.get("patient_id", type=int)
    standard = request.args.get("standard", "CDC")

    if not patient_id:
        return jsonify({"error": "patient_id required"}), 400

    patient = db.get_patient(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    if not patient.birth_date:
        return jsonify({"error": "Patient has no birth date"}), 400

    measurements = db.get_measurements(patient_id)
    if len(measurements) < 2:
        return jsonify({
            "trace": None,
            "patient_name": f"{patient.first_name} {patient.last_name}",
            "message": "Need at least 2 height measurements to compute velocity",
        })

    # Convert measurements to dicts for velocity computation
    meas_dicts = []
    for m in measurements:
        meas_dicts.append({
            "date": m.date.isoformat() if m.date else None,
            "height_cm": m.height_cm,
        })

    velocities = compute_velocity(meas_dicts, patient.birth_date)
    if not velocities:
        return jsonify({
            "trace": None,
            "patient_name": f"{patient.first_name} {patient.last_name}",
            "message": "Insufficient height data for velocity computation",
        })

    color = PATIENT_COLORS.get(patient.sex, "#2563EB")
    sex_label = "Boys" if patient.sex == "M" else "Girls"

    ages = [v["midpoint_age_years"] for v in velocities]
    vels = [v["velocity_cm_year"] for v in velocities]
    hover_texts = []
    for v in velocities:
        hover_texts.append(
            f"<b>Velocity: {v['velocity_cm_year']:.1f} cm/yr</b><br>"
            f"Age: {v['midpoint_age_years']:.1f} years<br>"
            f"Period: {v['date_start']} → {v['date_end']}<br>"
            f"Interval: {v['interval_months']:.0f} months"
        )

    patient_trace = {
        "name": f"{patient.first_name} {patient.last_name}",
        "x": ages,
        "y": vels,
        "mode": "lines+markers+text",
        "text": [f"{v:.1f}" for v in vels],
        "textposition": "top center",
        "textfont": {"size": 10, "color": color},
        "line": {"color": color, "width": 2.5},
        "marker": {"color": color, "size": 9, "line": {"width": 1.5, "color": "white"}},
        "hovertemplate": "%{customdata}<extra></extra>",
        "customdata": hover_texts,
    }

    # Get reference percentile curves with color bands
    ref_traces = get_velocity_reference_curves(patient.sex)

    # All traces: bands first, then reference lines, then patient data on top
    all_traces = ref_traces + [patient_trace]

    layout = {
        "xaxis": {
            "title": "Age (years)",
            "dtick": 1,
            "minor": {"dtick": 0.5, "showgrid": True, "gridcolor": "rgba(0,0,0,0.03)"},
            "gridcolor": "rgba(0,0,0,0.08)",
            "zeroline": False,
            "autorange": True,
        },
        "yaxis": {
            "title": "Height Velocity (cm/year)",
            "dtick": 2,
            "minor": {"dtick": 1, "showgrid": True, "gridcolor": "rgba(0,0,0,0.03)"},
            "gridcolor": "rgba(0,0,0,0.08)",
            "zeroline": False,
            "rangemode": "nonnegative",
        },
        "dragmode": "zoom",
        "hovermode": "closest",
        "margin": {"l": 60, "r": 30, "t": 50, "b": 50},
        "paper_bgcolor": "#FAFBFC",
        "plot_bgcolor": "#FFFFFF",
        "showlegend": True,
        "legend": {
            "x": 1, "y": 1, "xanchor": "right",
            "bgcolor": "rgba(255,255,255,0.8)",
            "bordercolor": "rgba(0,0,0,0.1)",
            "borderwidth": 1,
            "font": {"size": 10},
        },
    }

    return jsonify({
        "traces": all_traces,
        "layout": layout,
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "sex": patient.sex,
        "sex_label": sex_label,
        "velocities": velocities,
    })
