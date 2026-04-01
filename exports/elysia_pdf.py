"""
Elysia-branded PDF export for GrowthChart v2.

Generates a 2-page clinical PDF report:
  Page 1: Elysia header + Height-for-age chart + Weight-for-age chart
  Page 2: Elysia header + BMI-for-age chart + Data table

Uses matplotlib (Agg backend) for server-side chart rendering and
reportlab for PDF composition.
"""

import matplotlib
matplotlib.use("Agg")

import io
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator
from typing import List, Optional
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import Table, TableStyle
from reportlab.pdfgen import canvas

from models import Patient, Measurement
from zscore.engine import ZScoreEngine
from config import (
    Standard, Indicator, PERCENTILE_LINES, PERCENTILE_ZSCORES,
    zscore_to_percentile, APP_DIR,
)


# ── Percentile styling (from v1 charts/growth_chart.py) ─────────

PERCENTILE_LABELS = {
    3: "3rd", 5: "5th", 10: "10th", 25: "25th", 50: "50th",
    75: "75th", 90: "90th", 95: "95th", 97: "97th",
}

PCT_COLORS = {
    3:  "#DC2626",  97: "#DC2626",
    5:  "#EA580C",  95: "#EA580C",
    10: "#CA8A04",  90: "#CA8A04",
    25: "#16A34A",  75: "#16A34A",
    50: "#15803D",
}

PCT_STYLES = {
    3:  (0, (5, 4)),  97: (0, (5, 4)),
    5:  (0, (5, 3)),  95: (0, (5, 3)),
    10: (0, (4, 3)),  90: (0, (4, 3)),
    25: (0, (2, 3)),  75: (0, (2, 3)),
    50: "solid",
}

PCT_WIDTHS = {
    3: 0.9,  97: 0.9,
    5: 0.9,  95: 0.9,
    10: 0.8, 90: 0.8,
    25: 0.8, 75: 0.8,
    50: 1.6,
}

BAND_COLORS = {
    (None, 3):  "#FEE2E2",
    (3, 5):     "#FED7AA",
    (5, 10):    "#FEF9C3",
    (10, 25):   "#DCFCE7",
    (25, 50):   "#F0FDF4",
    (50, 75):   "#F0FDF4",
    (75, 90):   "#DCFCE7",
    (90, 95):   "#FEF9C3",
    (95, 97):   "#FED7AA",
    (97, None): "#FEE2E2",
}

BAND_PAIRS = [
    (None, 3), (3, 5), (5, 10), (10, 25), (25, 50),
    (50, 75), (75, 90), (90, 95), (95, 97), (97, None),
]


class _ChartColors:
    PATIENT_BOY     = "#2563EB"
    PATIENT_GIRL    = "#DB2777"
    PATIENT_BOY_BG  = "#DBEAFE"
    PATIENT_GIRL_BG = "#FCE7F3"
    BACKGROUND      = "#FAFBFC"
    GRID            = "#E5E7EB"
    TEXT            = "#374151"
    TEXT_LIGHT      = "#9CA3AF"
    AXIS            = "#6B7280"

    @staticmethod
    def patient_color(sex: str) -> str:
        return _ChartColors.PATIENT_BOY if sex == "M" else _ChartColors.PATIENT_GIRL

    @staticmethod
    def patient_bg(sex: str) -> str:
        return _ChartColors.PATIENT_BOY_BG if sex == "M" else _ChartColors.PATIENT_GIRL_BG


# ── Hebrew BiDi helper ──────────────────────────────────────────

def _bidi_wrap(text: str) -> str:
    """Make Hebrew text display correctly in matplotlib's LTR renderer."""
    if not any('\u0590' <= c <= '\u05FF' for c in text):
        return text
    parts = text.split('|')
    result = []
    for part in parts:
        part = part.strip()
        if any('\u0590' <= c <= '\u05FF' for c in part):
            words = part.split()
            reversed_words = [w[::-1] for w in reversed(words)]
            result.append(' '.join(reversed_words))
        else:
            result.append(part)
    return '  |  '.join(result)


# ── Age range calculation ───────────────────────────────────────

def _compute_age_range(engine: ZScoreEngine, measurements: List[Measurement],
                       sex: str, indicator: str, standard: str):
    """Compute the display age range for a chart, returning (age_min, age_max) in months."""
    engine.ensure_loaded(standard)
    ref_min, ref_max = engine.get_age_range(standard, indicator, sex)

    if measurements:
        m_ages = [m.age_months for m in measurements if m.age_months is not None]
        if m_ages:
            data_min, data_max = min(m_ages), max(m_ages)
            span = max(data_max - data_min, 24)
            age_min = max(ref_min, data_min - span * 0.3)
            age_max = min(ref_max, data_max + span * 0.3)
            if age_max - age_min < 24:
                mid = (data_min + data_max) / 2
                age_min = max(ref_min, mid - 18)
                age_max = min(ref_max, mid + 18)
        else:
            age_min, age_max = ref_min, min(ref_max, 60)
    else:
        age_min, age_max = ref_min, min(ref_max, 60)

    if age_max <= age_min:
        age_min, age_max = 0, 60
    return age_min, age_max


# ── Midi gridlines ──────────────────────────────────────────────

def _draw_midi_gridlines(ax, interval):
    """Draw medium-weight gridlines at a specific y-interval (e.g. every 5cm)."""
    ylim = ax.get_ylim()
    start = int(ylim[0] / interval) * interval
    for val in np.arange(start, ylim[1] + interval, interval):
        if val % (interval * 2) != 0:
            ax.axhline(y=val, color='#D1D5DB', linewidth=0.5,
                       alpha=0.5, zorder=0)


# ── Core chart rendering onto a matplotlib Axes ─────────────────

def _render_chart_on_ax(ax, engine: ZScoreEngine,
                        measurements: List[Measurement],
                        sex: str, indicator: str, standard: str,
                        patient_name: str, birth_date_str: str,
                        font_scale: float = 1.0):
    """Render a complete growth chart on the given axes."""
    age_min, age_max = _compute_age_range(engine, measurements, sex, indicator, standard)

    # Style
    ax.set_facecolor("#FFFFFF")
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(_ChartColors.AXIS)
    ax.spines['bottom'].set_color(_ChartColors.AXIS)
    ax.tick_params(colors=_ChartColors.AXIS, labelsize=8 * font_scale)
    ax.grid(True, which='major', alpha=0.3, color=_ChartColors.GRID, linewidth=0.5)
    ax.minorticks_on()
    ax.grid(True, which='minor', alpha=0.12, color=_ChartColors.GRID, linewidth=0.3)

    # Fetch percentile curves
    pct_curves = {}
    for pct in PERCENTILE_LINES:
        curve = engine.get_percentile_curve_for_chart(
            standard, indicator, sex, pct, age_min=age_min, age_max=age_max)
        if curve:
            pct_curves[pct] = curve

    # Draw colored bands
    common_ages = np.arange(age_min, age_max + 0.5, 0.5)
    for p_lo, p_hi in BAND_PAIRS:
        color = BAND_COLORS.get((p_lo, p_hi), "#FFFFFF")
        if p_lo is None and p_hi in pct_curves:
            c = pct_curves[p_hi]
            v_hi = np.interp(common_ages, [p[0] for p in c], [p[1] for p in c])
            ax.fill_between(common_ages / 12, v_hi * 0.85, v_hi,
                            color=color, alpha=0.5, linewidth=0, zorder=1)
        elif p_hi is None and p_lo in pct_curves:
            c = pct_curves[p_lo]
            v_lo = np.interp(common_ages, [p[0] for p in c], [p[1] for p in c])
            ax.fill_between(common_ages / 12, v_lo, v_lo * 1.15,
                            color=color, alpha=0.5, linewidth=0, zorder=1)
        elif p_lo in pct_curves and p_hi in pct_curves:
            c_lo, c_hi = pct_curves[p_lo], pct_curves[p_hi]
            v_lo = np.interp(common_ages, [p[0] for p in c_lo], [p[1] for p in c_lo])
            v_hi = np.interp(common_ages, [p[0] for p in c_hi], [p[1] for p in c_hi])
            ax.fill_between(common_ages / 12, v_lo, v_hi,
                            color=color, alpha=0.5, linewidth=0, zorder=1)

    # Draw percentile lines
    for pct in PERCENTILE_LINES:
        curve = pct_curves.get(pct)
        if not curve:
            continue
        ages = [p[0] / 12 for p in curve]
        vals = [p[1] for p in curve]
        ax.plot(ages, vals,
                color=PCT_COLORS.get(pct, "#999"),
                linestyle=PCT_STYLES.get(pct, "solid"),
                linewidth=PCT_WIDTHS.get(pct, 1.0),
                alpha=0.75, zorder=2)
        if ages:
            ax.annotate(PERCENTILE_LABELS.get(pct, f"P{pct}"),
                        xy=(ages[-1], vals[-1]),
                        xytext=(4, 0), textcoords="offset points",
                        fontsize=5.5 * font_scale,
                        color=PCT_COLORS.get(pct, "#999"),
                        va="center", ha="left", alpha=0.8,
                        fontweight="bold" if pct == 50 else "normal")

    # Draw patient data points
    if measurements:
        pt_color = _ChartColors.patient_color(sex)
        pt_bg = _ChartColors.patient_bg(sex)
        data_points = []
        for m in measurements:
            if m.age_months is None:
                continue
            val = None
            if indicator == Indicator.HEIGHT_FOR_AGE and m.height_cm:
                val = m.height_cm
            elif indicator == Indicator.WEIGHT_FOR_AGE and m.weight_kg:
                val = m.weight_kg
            elif indicator == Indicator.BMI_FOR_AGE and m.bmi:
                val = m.bmi
            if val is not None:
                data_points.append((m.age_months / 12, val, m))

        if data_points:
            ages_d = [p[0] for p in data_points]
            vals_d = [p[1] for p in data_points]
            ax.plot(ages_d, vals_d, color=pt_color, linewidth=1.8,
                    alpha=0.8, zorder=4)
            ax.scatter(ages_d, vals_d, c=pt_color, s=40, zorder=5,
                       edgecolors="white", linewidths=1.5)
            # Z-score annotations
            for age_y, val, m in data_points:
                z_val = None
                if indicator == Indicator.HEIGHT_FOR_AGE:
                    z_val = m.height_zscore
                elif indicator == Indicator.WEIGHT_FOR_AGE:
                    z_val = m.weight_zscore
                elif indicator == Indicator.BMI_FOR_AGE:
                    z_val = m.bmi_zscore
                if z_val is not None:
                    ax.annotate(
                        f"{z_val:+.2f}",
                        xy=(age_y, val),
                        xytext=(0, 8), textcoords="offset points",
                        fontsize=6 * font_scale, fontweight="bold",
                        color=pt_color, ha="center", va="bottom",
                        bbox=dict(boxstyle="round,pad=0.15",
                                  facecolor="white", edgecolor=pt_color,
                                  alpha=0.8, linewidth=0.6),
                        zorder=7)

    # Labels and title
    indicator_label = Indicator.LABELS.get(indicator, indicator)
    sex_label = "Boys" if sex == "M" else "Girls"
    std_label = standard
    if patient_name:
        title = f"{_bidi_wrap(patient_name)}  |  {indicator_label}  ·  {sex_label}  ·  {std_label}"
    else:
        title = f"{indicator_label}  ·  {sex_label}  ·  {std_label}"
    ax.set_title(title, fontsize=10 * font_scale, fontweight="bold",
                 color=_ChartColors.TEXT, pad=8)
    ax.set_xlabel(Indicator.X_LABELS.get(indicator, "Age"),
                  fontsize=9 * font_scale, color=_ChartColors.TEXT)
    ax.set_ylabel(Indicator.Y_LABELS.get(indicator, "Value"),
                  fontsize=9 * font_scale, color=_ChartColors.TEXT)

    # Axis limits
    ax.set_xlim(age_min / 12, age_max / 12)
    all_vals = []
    for pct in [3, 97]:
        for _, v in pct_curves.get(pct, []):
            all_vals.append(v)
    if measurements:
        for m in measurements:
            if m.age_months is not None:
                val = None
                if indicator == Indicator.HEIGHT_FOR_AGE and m.height_cm:
                    val = m.height_cm
                elif indicator == Indicator.WEIGHT_FOR_AGE and m.weight_kg:
                    val = m.weight_kg
                elif indicator == Indicator.BMI_FOR_AGE and m.bmi:
                    val = m.bmi
                if val:
                    all_vals.append(val)
    if all_vals:
        y_min = min(all_vals) * 0.92
        y_max = max(all_vals) * 1.08
        if indicator == Indicator.BMI_FOR_AGE:
            y_min, y_max = max(y_min, 10), min(y_max, 40)
        elif indicator == Indicator.HEIGHT_FOR_AGE:
            y_min = max(y_min, 40)
        elif indicator == Indicator.WEIGHT_FOR_AGE:
            y_min = max(y_min, 1)
        ax.set_ylim(y_min, y_max)

    # 3-tier gridlines
    if indicator == Indicator.HEIGHT_FOR_AGE:
        ax.yaxis.set_major_locator(MultipleLocator(10))
        ax.yaxis.set_minor_locator(MultipleLocator(1))
        _draw_midi_gridlines(ax, 5)
    elif indicator == Indicator.WEIGHT_FOR_AGE:
        ax.yaxis.set_major_locator(MultipleLocator(10))
        ax.yaxis.set_minor_locator(MultipleLocator(1))
        _draw_midi_gridlines(ax, 5)
    elif indicator == Indicator.BMI_FOR_AGE:
        ax.yaxis.set_major_locator(MultipleLocator(5))
        ax.yaxis.set_minor_locator(MultipleLocator(1))
    ax.xaxis.set_minor_locator(MultipleLocator(0.5))
    ax.xaxis.set_major_locator(MultipleLocator(1))


# ── Render a single chart to PNG bytes ──────────────────────────

def render_chart_to_png(engine: ZScoreEngine,
                        measurements: List[Measurement],
                        sex: str, indicator: str, standard: str,
                        patient_name: str = "",
                        birth_date_str: str = "",
                        font_scale: float = 1.0,
                        figsize=(10, 7), dpi=150) -> bytes:
    """Render a single chart and return PNG bytes."""
    fig = Figure(figsize=figsize, dpi=dpi)
    fig.set_facecolor(_ChartColors.BACKGROUND)
    ax = fig.add_subplot(111)

    _render_chart_on_ax(ax, engine, measurements, sex, indicator, standard,
                        patient_name, birth_date_str, font_scale)
    fig.tight_layout(pad=1.5)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=dpi,
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Data table rendering to PNG for reportlab ───────────────────

def _render_data_table_png(measurements: List[Measurement],
                           font_scale: float = 1.0,
                           dpi: int = 150) -> Optional[bytes]:
    """Render the measurement data table as a PNG image for embedding in PDF."""
    valid = [m for m in measurements
             if m.age_months is not None and (m.height_cm or m.weight_kg)]
    if not valid:
        return None

    headers = ['Date', 'Age', 'Ht cm', 'Wt kg', 'BMI',
               'Ht-SDS', 'Ht %ile', 'Wt-SDS', 'Wt %ile',
               'BMI-SDS', 'BMI %ile']

    def fmt_z(z):
        return f"{z:+.2f}" if z is not None else "\u2014"

    def fmt_p(z):
        if z is not None:
            return f"{zscore_to_percentile(z):.1f}"
        return "\u2014"

    rows = []
    z_values = []  # Track z-score values per row for coloring
    for m in valid:
        rows.append([
            m.date.strftime("%d/%m/%Y") if m.date else "\u2014",
            m.age_str,
            f"{m.height_cm:.1f}" if m.height_cm else "\u2014",
            f"{m.weight_kg:.1f}" if m.weight_kg else "\u2014",
            f"{m.bmi:.1f}" if m.bmi else "\u2014",
            fmt_z(m.height_zscore),
            fmt_p(m.height_zscore),
            fmt_z(m.weight_zscore),
            fmt_p(m.weight_zscore),
            fmt_z(m.bmi_zscore),
            fmt_p(m.bmi_zscore),
        ])
        z_values.append({
            5: m.height_zscore,  # Ht-SDS column index
            7: m.weight_zscore,  # Wt-SDS column index
            9: m.bmi_zscore,     # BMI-SDS column index
        })

    # Calculate figure size based on row count
    row_height = 0.35 * font_scale
    header_height = 0.45 * font_scale
    fig_height = header_height + row_height * len(rows) + 0.3
    fig_width = 10

    fig = Figure(figsize=(fig_width, fig_height), dpi=dpi)
    fig.set_facecolor("white")
    ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
    ax.axis('off')

    table = ax.table(
        cellText=rows,
        colLabels=headers,
        loc='center',
        cellLoc='center',
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7 * font_scale)
    table.scale(1.0, 1.4 * font_scale)

    # Style header row
    for j in range(len(headers)):
        cell = table[0, j]
        cell.set_facecolor('#0891B2')
        cell.set_text_props(color='white', fontweight='bold')
        cell.set_edgecolor('#E5E7EB')

    # Style data rows with z-score coloring
    for i in range(len(rows)):
        for j in range(len(headers)):
            cell = table[i + 1, j]
            cell.set_facecolor('#F9FAFB' if i % 2 == 0 else '#FFFFFF')
            cell.set_edgecolor('#E5E7EB')
            # Color z-score columns
            if j in z_values[i] and z_values[i][j] is not None:
                z = z_values[i][j]
                if z < -2 or z > 2:
                    cell.get_text().set_color('#DC2626')  # red
                elif z < -1 or z > 1:
                    cell.get_text().set_color('#EA580C')  # orange
                else:
                    cell.get_text().set_color('#16A34A')  # green

    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=dpi,
                facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Main PDF generator ──────────────────────────────────────────

def generate_elysia_pdf(
    patient: Patient,
    measurements: List[Measurement],
    engine: ZScoreEngine,
    standard: str = "CDC",
    header_image_path: str = None,
    font_scale: float = 1.0,
) -> bytes:
    """
    Generate a 2-page Elysia-branded PDF report.

    Page 1: Header image + Height-for-age chart + Weight-for-age chart
    Page 2: Header image + BMI-for-age chart + Data table

    Returns: PDF bytes ready for download.
    """
    if header_image_path is None:
        default_path = os.path.join(str(APP_DIR), "assets", "elysia_header.png")
        if os.path.exists(default_path):
            header_image_path = default_path

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

    # Sort measurements by date
    measurements = sorted(measurements, key=lambda m: m.date or date.min)

    # A4 page dimensions
    page_w, page_h = A4  # 595.27, 841.89 points

    # Render chart images
    chart_dpi = 150
    chart_figsize_half = (7.5, 4.2)   # For half-page charts (height/weight)
    chart_figsize_large = (7.5, 5.5)  # For BMI (larger)

    ht_png = render_chart_to_png(
        engine, measurements, sex, Indicator.HEIGHT_FOR_AGE, standard,
        name, birth_str, font_scale, figsize=chart_figsize_half, dpi=chart_dpi)

    wt_png = render_chart_to_png(
        engine, measurements, sex, Indicator.WEIGHT_FOR_AGE, standard,
        name, birth_str, font_scale, figsize=chart_figsize_half, dpi=chart_dpi)

    bmi_png = render_chart_to_png(
        engine, measurements, sex, Indicator.BMI_FOR_AGE, standard,
        name, birth_str, font_scale, figsize=chart_figsize_large, dpi=chart_dpi)

    table_png = _render_data_table_png(measurements, font_scale, dpi=chart_dpi)

    # Build PDF with reportlab
    pdf_buf = io.BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=A4)

    # ── PAGE 1: Header + Height + Weight ────────────────────
    _draw_header(c, header_image_path, page_w, page_h)

    # Height chart: top ~42% of content area (below header)
    ht_buf = io.BytesIO(ht_png)
    from reportlab.lib.utils import ImageReader
    ht_img = ImageReader(ht_buf)

    # Content area: from 8% header down to bottom
    content_top = page_h * 0.90   # below header
    chart_height = page_h * 0.40
    chart_width = page_w * 0.94
    x_margin = page_w * 0.03

    # Height chart
    ht_y = content_top - chart_height
    c.drawImage(ht_img, x_margin, ht_y, width=chart_width, height=chart_height,
                preserveAspectRatio=True, anchor='n')

    # Weight chart: below height with small gap
    gap = page_h * 0.02
    wt_y = ht_y - gap - chart_height
    wt_buf = io.BytesIO(wt_png)
    wt_img = ImageReader(wt_buf)
    c.drawImage(wt_img, x_margin, wt_y, width=chart_width, height=chart_height,
                preserveAspectRatio=True, anchor='n')

    c.showPage()

    # ── PAGE 2: Header + BMI + Data Table ───────────────────
    _draw_header(c, header_image_path, page_w, page_h)

    # BMI chart: ~50% of content area
    bmi_height = page_h * 0.48
    bmi_y = content_top - bmi_height
    bmi_buf = io.BytesIO(bmi_png)
    bmi_img = ImageReader(bmi_buf)
    c.drawImage(bmi_img, x_margin, bmi_y, width=chart_width, height=bmi_height,
                preserveAspectRatio=True, anchor='n')

    # Data table: bottom ~35%
    if table_png:
        table_height = page_h * 0.34
        table_y = bmi_y - gap - table_height
        if table_y < 10:
            table_y = 10
            table_height = bmi_y - gap - 10
        tbl_buf = io.BytesIO(table_png)
        tbl_img = ImageReader(tbl_buf)
        c.drawImage(tbl_img, x_margin, table_y,
                    width=chart_width, height=table_height,
                    preserveAspectRatio=True, anchor='n')

    c.showPage()
    c.save()

    pdf_buf.seek(0)
    return pdf_buf.read()


def _draw_header(c, header_image_path, page_w, page_h):
    """Draw the Elysia header image at the top of a page."""
    if header_image_path and os.path.exists(header_image_path):
        from reportlab.lib.utils import ImageReader
        header_img = ImageReader(header_image_path)
        header_height = page_h * 0.08
        header_y = page_h - header_height - 5
        header_width = page_w * 0.96
        header_x = page_w * 0.02
        c.drawImage(header_img, header_x, header_y,
                    width=header_width, height=header_height,
                    preserveAspectRatio=True, anchor='n')
