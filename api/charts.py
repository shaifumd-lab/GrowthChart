"""Chart data API — returns Plotly-compatible JSON for growth charts."""
from flask import Blueprint, request, jsonify, current_app
from config import (
    Standard, Indicator, PERCENTILE_LINES, PERCENTILE_ZSCORES,
    zscore_to_percentile,
)

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
    """Return percentile curve traces for Plotly."""
    engine = current_app.engine
    indicator = request.args.get("indicator", "hfa")
    standard = request.args.get("standard", "CDC")
    sex = request.args.get("sex", "M")
    age_min = float(request.args.get("age_min", 0))
    age_max = float(request.args.get("age_max", 240))

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

    y_label = Indicator.Y_LABELS.get(indicator, "Value")
    return jsonify({
        "traces": traces,
        "bands": bands,
        "layout": {
            "xaxis": {
                "title": "Age (years)",
                "dtick": 1,
                "minor": {"dtick": 0.25, "showgrid": True, "gridcolor": "rgba(0,0,0,0.05)"},
                "gridcolor": "rgba(0,0,0,0.1)",
                "zeroline": False,
                "range": [age_min / 12.0, age_max / 12.0],
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
            "margin": {"l": 60, "r": 30, "t": 50, "b": 50},
            "paper_bgcolor": "#FAFBFC",
            "plot_bgcolor": "#FFFFFF",
        },
    })


@charts_bp.route("/charts/patient-data", methods=["GET"])
def get_patient_data():
    """Return patient measurement data as a Plotly trace."""
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

    return jsonify(result)
