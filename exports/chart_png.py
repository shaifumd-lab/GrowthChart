"""
Individual chart PNG export for GrowthChart v2.

Generates standalone PNG images of growth charts for download.
"""

import matplotlib
matplotlib.use("Agg")

from datetime import date
from typing import List

from models import Patient, Measurement
from zscore.engine import ZScoreEngine
from config import Indicator

from exports.elysia_pdf import render_chart_to_png


def generate_chart_png(
    patient: Patient,
    measurements: List[Measurement],
    engine: ZScoreEngine,
    indicator: str = "hfa",
    standard: str = "CDC",
    font_scale: float = 1.0,
) -> bytes:
    """
    Generate a single chart PNG for download.

    Returns: PNG bytes.
    """
    sex = patient.sex
    name = patient.full_name or ""
    birth_str = patient.birth_date.strftime("%d/%m/%Y") if patient.birth_date else ""

    # Enrich measurements with computed fields
    for m in measurements:
        m.compute_age(patient.birth_date)
        m.compute_bmi()
        if m.age_months is not None:
            if m.height_cm:
                m.height_zscore = engine.compute_zscore(
                    m.height_cm, m.age_months, sex, Indicator.HEIGHT_FOR_AGE, standard)
                if m.height_zscore is not None:
                    m.height_percentile = engine.compute_percentile(m.height_zscore)
            if m.weight_kg:
                m.weight_zscore = engine.compute_zscore(
                    m.weight_kg, m.age_months, sex, Indicator.WEIGHT_FOR_AGE, standard)
                if m.weight_zscore is not None:
                    m.weight_percentile = engine.compute_percentile(m.weight_zscore)
            if m.bmi:
                m.bmi_zscore = engine.compute_zscore(
                    m.bmi, m.age_months, sex, Indicator.BMI_FOR_AGE, standard)
                if m.bmi_zscore is not None:
                    m.bmi_percentile = engine.compute_percentile(m.bmi_zscore)

    # Sort by date
    measurements = sorted(measurements, key=lambda m: m.date or date.min)

    return render_chart_to_png(
        engine, measurements, sex, indicator, standard,
        name, birth_str, font_scale,
        figsize=(10, 7), dpi=150,
    )


def get_chart_filename(patient: Patient, indicator: str, standard: str) -> str:
    """
    Generate an informative filename for chart export.

    Returns filename like 'אבירם_עמרם_HeightForAge_CDC_20260401.png'
    """
    indicator_names = {
        "hfa": "HeightForAge",
        "wfa": "WeightForAge",
        "bfa": "BMIForAge",
        "wfh": "WeightForHeight",
    }
    ind_name = indicator_names.get(indicator, indicator)

    # Build name parts
    parts = []
    name = f"{patient.first_name}_{patient.last_name}".strip("_")
    if name:
        parts.append(name)
    parts.append(ind_name)
    parts.append(standard)
    parts.append(date.today().strftime("%Y%m%d"))

    filename = "_".join(parts) + ".png"
    # Sanitize: remove any path-unsafe characters except Hebrew, underscores, dots, dashes
    safe = ""
    for ch in filename:
        if ch.isalnum() or ch in ('_', '-', '.') or '\u0590' <= ch <= '\u05FF':
            safe += ch
        else:
            safe += '_'
    return safe
