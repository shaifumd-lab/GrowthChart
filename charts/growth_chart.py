"""
Growth chart renderer using matplotlib.

Creates clinical-quality growth charts matching CDC/WHO standard layout:
- 9 standard percentile lines: 3, 5, 10, 25, 50, 75, 90, 95, 97
- Clinical color bands between percentile zones
- Patient data points with z-score annotations
- Export to PNG/PDF
"""

import matplotlib
matplotlib.use("TkAgg")

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np
from typing import List, Optional
from models import Measurement
from zscore.engine import ZScoreEngine
from config import Standard, Indicator, PERCENTILE_LINES


# ── Percentile Line Styling (matches CDC standard charts) ────

PERCENTILE_LABELS = {
    3: "3rd", 5: "5th", 10: "10th", 25: "25th", 50: "50th",
    75: "75th", 90: "90th", 95: "95th", 97: "97th",
}

# Line colors per percentile
PCT_COLORS = {
    3:  "#DC2626",  97: "#DC2626",  # red — extremes
    5:  "#EA580C",  95: "#EA580C",  # orange
    10: "#CA8A04",  90: "#CA8A04",  # yellow/gold
    25: "#16A34A",  75: "#16A34A",  # green
    50: "#15803D",                   # dark green — median
}

# Line styles per percentile
PCT_STYLES = {
    3:  (0, (5, 4)),  97: (0, (5, 4)),  # dashed
    5:  (0, (5, 3)),  95: (0, (5, 3)),  # dashed
    10: (0, (4, 3)),  90: (0, (4, 3)),  # dashed
    25: (0, (2, 3)),  75: (0, (2, 3)),  # dotted
    50: "solid",
}

# Line widths per percentile
PCT_WIDTHS = {
    3: 0.9,  97: 0.9,
    5: 0.9,  95: 0.9,
    10: 0.8, 90: 0.8,
    25: 0.8, 75: 0.8,
    50: 1.6,  # bold median
}

# Band fill colors between adjacent percentile pairs
BAND_COLORS = {
    (None, 3):  "#FEE2E2",  # red-100 — severe low
    (3, 5):     "#FED7AA",  # orange-200 — warning low
    (5, 10):    "#FEF9C3",  # yellow-100 — monitor low
    (10, 25):   "#DCFCE7",  # green-100 — low-normal
    (25, 50):   "#F0FDF4",  # green-50 — normal
    (50, 75):   "#F0FDF4",  # green-50 — normal
    (75, 90):   "#DCFCE7",  # green-100 — high-normal
    (90, 95):   "#FEF9C3",  # yellow-100 — monitor high
    (95, 97):   "#FED7AA",  # orange-200 — warning high
    (97, None): "#FEE2E2",  # red-100 — severe high
}

# UI colors
class ChartColors:
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
        return ChartColors.PATIENT_BOY if sex == "M" else ChartColors.PATIENT_GIRL

    @staticmethod
    def patient_bg(sex: str) -> str:
        return ChartColors.PATIENT_BOY_BG if sex == "M" else ChartColors.PATIENT_GIRL_BG


# ── Hebrew BiDi Helper ────────────────────────────────────────

def _bidi_wrap(text: str) -> str:
    """Make Hebrew text display correctly in matplotlib's LTR renderer.
    Matplotlib renders all text left-to-right, character by character.
    For Hebrew to appear correct, we must:
    1. Reverse each Hebrew word's characters (so LTR rendering shows RTL letters)
    2. Reverse the word order (so first Hebrew word appears on the right)
    """
    if not any('\u0590' <= c <= '\u05FF' for c in text):
        return text

    # Process pipe-separated segments independently
    parts = text.split('|')
    result = []
    for part in parts:
        part = part.strip()
        if any('\u0590' <= c <= '\u05FF' for c in part):
            words = part.split()
            # Reverse each word's chars, then reverse word order
            reversed_words = [w[::-1] for w in reversed(words)]
            result.append(' '.join(reversed_words))
        else:
            result.append(part)
    return '  |  '.join(result)


# ── Chart Renderer ────────────────────────────────────────────

class GrowthChartRenderer:
    """Renders growth charts with percentile curves and patient data."""

    def __init__(self, engine: ZScoreEngine):
        self.engine = engine

    def create_chart(self, fig: Figure,
                     measurements: List[Measurement],
                     sex: str,
                     indicator: str = Indicator.HEIGHT_FOR_AGE,
                     standard: str = Standard.WHO,
                     patient_name: str = "",
                     birth_date_str: str = "") -> None:
        fig.clear()
        ax = fig.add_subplot(111)

        # ── Style ────────────────────────────────────────
        fig.set_facecolor(ChartColors.BACKGROUND)
        ax.set_facecolor("#FFFFFF")
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(ChartColors.AXIS)
        ax.spines['bottom'].set_color(ChartColors.AXIS)
        ax.spines['left'].set_linewidth(0.8)
        ax.spines['bottom'].set_linewidth(0.8)
        ax.tick_params(colors=ChartColors.AXIS, labelsize=10)
        # Major gridlines
        ax.grid(True, which='major', alpha=0.35, color=ChartColors.GRID, linewidth=0.6)
        # Minor gridlines (for 5cm/1kg ticks)
        ax.minorticks_on()
        ax.grid(True, which='minor', alpha=0.15, color=ChartColors.GRID, linewidth=0.4)
        ax.tick_params(which='minor', length=3, color=ChartColors.AXIS)

        # ── Determine age range ──────────────────────────
        self.engine.ensure_loaded(standard)
        ref_min, ref_max = self.engine.get_age_range(standard, indicator, sex)

        if measurements:
            m_ages = [m.age_months for m in measurements if m.age_months is not None]
            if m_ages:
                data_min = min(m_ages)
                data_max = max(m_ages)
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

        # ── Fetch percentile curves ──────────────────────
        pct_curves = {}
        for pct in PERCENTILE_LINES:
            curve = self.engine.get_percentile_curve_for_chart(
                standard, indicator, sex, pct,
                age_min=age_min, age_max=age_max)
            if curve:
                pct_curves[pct] = curve

        # ── Draw filled bands between percentile pairs ───
        band_pairs = [
            (None, 3), (3, 5), (5, 10), (10, 25), (25, 50),
            (50, 75), (75, 90), (90, 95), (95, 97), (97, None)
        ]

        # Build a common age grid for interpolation
        common_ages = np.arange(age_min, age_max + 0.5, 0.5)

        for p_lo, p_hi in band_pairs:
            color = BAND_COLORS.get((p_lo, p_hi), "#FFFFFF")

            if p_lo is None and p_hi in pct_curves:
                # Below lowest percentile: fill from very low to P3
                c = pct_curves[p_hi]
                ages_c = np.array([p[0] for p in c])
                vals_c = np.array([p[1] for p in c])
                v_hi = np.interp(common_ages, ages_c, vals_c)
                # Use P3 * 0.85 as lower bound
                v_lo = v_hi * 0.85
                ax.fill_between(common_ages / 12, v_lo, v_hi,
                               color=color, alpha=0.5, linewidth=0, zorder=1)

            elif p_hi is None and p_lo in pct_curves:
                # Above highest percentile: fill from P97 to P97 * 1.15
                c = pct_curves[p_lo]
                ages_c = np.array([p[0] for p in c])
                vals_c = np.array([p[1] for p in c])
                v_lo = np.interp(common_ages, ages_c, vals_c)
                v_hi = v_lo * 1.15
                ax.fill_between(common_ages / 12, v_lo, v_hi,
                               color=color, alpha=0.5, linewidth=0, zorder=1)

            elif p_lo in pct_curves and p_hi in pct_curves:
                c_lo = pct_curves[p_lo]
                c_hi = pct_curves[p_hi]
                ages_lo = np.array([p[0] for p in c_lo])
                vals_lo = np.array([p[1] for p in c_lo])
                ages_hi = np.array([p[0] for p in c_hi])
                vals_hi = np.array([p[1] for p in c_hi])
                v_lo = np.interp(common_ages, ages_lo, vals_lo)
                v_hi = np.interp(common_ages, ages_hi, vals_hi)
                ax.fill_between(common_ages / 12, v_lo, v_hi,
                               color=color, alpha=0.5, linewidth=0, zorder=1)

        # ── Draw percentile lines ────────────────────────
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

            # Label at right end
            if ages and vals:
                label = PERCENTILE_LABELS.get(pct, f"P{pct}")
                ax.annotate(
                    label,
                    xy=(ages[-1], vals[-1]),
                    xytext=(5, 0), textcoords="offset points",
                    fontsize=6.5,
                    color=PCT_COLORS.get(pct, "#999"),
                    va="center", ha="left", alpha=0.85,
                    fontweight="bold" if pct == 50 else "normal")

        # ── Draw patient data points ─────────────────────
        if measurements:
            color = ChartColors.patient_color(sex)
            bg = ChartColors.patient_bg(sex)

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
                ages = [p[0] for p in data_points]
                vals = [p[1] for p in data_points]

                # Connecting line
                ax.plot(ages, vals, color=color, linewidth=2.0,
                        alpha=0.8, zorder=4, solid_capstyle="round")

                # Data points
                ax.scatter(ages, vals, c=color, s=60, zorder=5,
                          edgecolors="white", linewidths=2)

                # Highlight most recent
                if len(ages) > 0:
                    ax.scatter([ages[-1]], [vals[-1]], c=bg, s=100, zorder=6,
                              edgecolors=color, linewidths=2.5)

                # Z-score annotations (2 decimal places)
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
                            xytext=(0, 12), textcoords="offset points",
                            fontsize=7.5, fontweight="bold",
                            color=color, ha="center", va="bottom",
                            bbox=dict(boxstyle="round,pad=0.2",
                                     facecolor="white", edgecolor=color,
                                     alpha=0.85, linewidth=0.8),
                            zorder=7)

        # ── Labels and title ─────────────────────────────
        indicator_label = Indicator.LABELS.get(indicator, indicator)
        y_label = Indicator.Y_LABELS.get(indicator, "Value")
        x_label = Indicator.X_LABELS.get(indicator, "Age")
        sex_label = "Boys" if sex == "M" else "Girls"
        std_label = "WHO" if standard == Standard.WHO else "CDC"

        ax.set_xlabel(x_label, fontsize=12, color=ChartColors.TEXT,
                     fontweight="medium", labelpad=8)
        ax.set_ylabel(y_label, fontsize=12, color=ChartColors.TEXT,
                     fontweight="medium", labelpad=8)

        # Build title — apply BiDi wrapping for Hebrew names
        title_parts = [f"{indicator_label}  ·  {sex_label}  ·  {std_label}"]
        if patient_name:
            title_parts.insert(0, _bidi_wrap(patient_name))

        ax.set_title("  |  ".join(title_parts),
                    fontsize=13, fontweight="bold", color=ChartColors.TEXT,
                    pad=14)

        if birth_date_str:
            ax.text(0.99, 1.02, f"DOB: {birth_date_str}",
                   transform=ax.transAxes, fontsize=9,
                   color=ChartColors.TEXT_LIGHT, ha="right", va="bottom")

        # ── Y-axis limits from P3 and P97 curves ────────
        ax.set_xlim(age_min / 12, age_max / 12)

        all_vals = []
        for pct in [3, 97]:
            curve = pct_curves.get(pct, [])
            for _, v in curve:
                all_vals.append(v)
        # Include patient data in range
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
                y_min = max(y_min, 10)
                y_max = min(y_max, 40)
            elif indicator == Indicator.HEIGHT_FOR_AGE:
                y_min = max(y_min, 40)
            elif indicator == Indicator.WEIGHT_FOR_AGE:
                y_min = max(y_min, 1)
            ax.set_ylim(y_min, y_max)

        # 3-tier grid: major (labeled), midi (5cm lines), minor (1cm ticks)
        from matplotlib.ticker import MultipleLocator, AutoMinorLocator
        if indicator == Indicator.HEIGHT_FOR_AGE:
            ax.yaxis.set_major_locator(MultipleLocator(10))
            ax.yaxis.set_minor_locator(MultipleLocator(1))
            # Draw midi gridlines at 5cm intervals
            self._draw_midi_gridlines(ax, 'y', 5, age_min / 12, age_max / 12)
        elif indicator == Indicator.WEIGHT_FOR_AGE:
            ax.yaxis.set_major_locator(MultipleLocator(10))
            ax.yaxis.set_minor_locator(MultipleLocator(1))
            self._draw_midi_gridlines(ax, 'y', 5, age_min / 12, age_max / 12)
        elif indicator == Indicator.BMI_FOR_AGE:
            ax.yaxis.set_major_locator(MultipleLocator(5))
            ax.yaxis.set_minor_locator(MultipleLocator(1))

        ax.xaxis.set_minor_locator(MultipleLocator(0.5))
        ax.xaxis.set_major_locator(MultipleLocator(1))

        fig.tight_layout(pad=1.5)

    @staticmethod
    def _draw_midi_gridlines(ax, axis, interval, x_min=None, x_max=None):
        """Draw medium-weight gridlines at a specific interval (e.g. every 5cm)."""
        if axis == 'y':
            ylim = ax.get_ylim()
            start = int(ylim[0] / interval) * interval
            for val in np.arange(start, ylim[1] + interval, interval):
                if val % (interval * 2) != 0:  # skip values that are major gridlines
                    ax.axhline(y=val, color='#D1D5DB', linewidth=0.5,
                              alpha=0.5, zorder=0)

    def _draw_data_table(self, fig, measurements, sex, standard,
                         patient_name, birth_date_str, rect):
        """Draw a measurements data table on the figure at the given rect."""
        import math
        from config import zscore_to_percentile

        ax_tbl = fig.add_axes(rect)
        ax_tbl.axis('off')

        if not measurements:
            ax_tbl.text(0.5, 0.5, "No measurements", ha='center', va='center',
                       fontsize=9, color='#999')
            return

        # Filter measurements that have data
        valid = [m for m in measurements if m.age_months is not None
                 and (m.height_cm or m.weight_kg)]
        if not valid:
            return

        # Build table data
        headers = ['Date', 'Age', 'Ht cm', 'Wt kg', 'BMI', 'Ht-SDS',
                   'Ht %ile', 'Wt-SDS', 'Wt %ile', 'BMI-SDS', 'BMI %ile']
        rows = []
        for m in valid:
            def fmt_z(z):
                return f"{z:+.2f}" if z is not None else "—"
            def fmt_p(z):
                if z is not None:
                    return f"{zscore_to_percentile(z):.1f}"
                return "—"
            rows.append([
                m.date.strftime("%d/%m/%Y") if m.date else "—",
                m.age_str,
                f"{m.height_cm:.1f}" if m.height_cm else "—",
                f"{m.weight_kg:.1f}" if m.weight_kg else "—",
                f"{m.bmi:.1f}" if m.bmi else "—",
                fmt_z(m.height_zscore),
                fmt_p(m.height_zscore),
                fmt_z(m.weight_zscore),
                fmt_p(m.weight_zscore),
                fmt_z(m.bmi_zscore),
                fmt_p(m.bmi_zscore),
            ])

        table = ax_tbl.table(
            cellText=rows,
            colLabels=headers,
            loc='center',
            cellLoc='center',
        )
        table.auto_set_font_size(False)
        table.set_fontsize(7)
        table.scale(1.0, 1.4)

        # Style header row
        for j, key in enumerate(headers):
            cell = table[0, j]
            cell.set_facecolor('#0891B2')
            cell.set_text_props(color='white', fontweight='bold')
            cell.set_edgecolor('#E5E7EB')

        # Style data rows
        for i in range(len(rows)):
            for j in range(len(headers)):
                cell = table[i + 1, j]
                cell.set_facecolor('#F9FAFB' if i % 2 == 0 else '#FFFFFF')
                cell.set_edgecolor('#E5E7EB')
                # Color z-scores
                if headers[j].endswith('SDS'):
                    txt = cell.get_text().get_text()
                    try:
                        z = float(txt)
                        if z < -2:
                            cell.get_text().set_color('#DC2626')
                        elif z < -1:
                            cell.get_text().set_color('#EA580C')
                    except ValueError:
                        pass

    def export_chart(self, filepath: str, *args, **kwargs):
        """Render and export chart to file."""
        fig = Figure(figsize=(10, 7), dpi=150)
        self.create_chart(fig, *args, **kwargs)
        fig.savefig(filepath, bbox_inches="tight", dpi=150)
        plt.close(fig)

    def export_elysia_pdf(self, filepath: str,
                          measurements: List[Measurement],
                          sex: str, standard: str,
                          patient_name: str = "",
                          birth_date_str: str = "",
                          header_image_path: str = "") -> None:
        """
        Export Elysia-branded PDF report:
        Page 1: Header logo + Height chart + Weight chart
        Page 2: Header logo + BMI chart
        """
        from matplotlib.backends.backend_pdf import PdfPages
        from PIL import Image
        import os

        with PdfPages(filepath) as pdf:
            # ── PAGE 1: Header + Height + Weight + Data Table ─
            fig1 = Figure(figsize=(8.27, 11.69), dpi=150)  # A4

            # Header image (top 8%)
            if header_image_path and os.path.exists(header_image_path):
                ax_header = fig1.add_axes([0.02, 0.91, 0.96, 0.08])
                img = Image.open(header_image_path)
                ax_header.imshow(img, aspect='auto')
                ax_header.axis('off')

            # Height chart: y=0.50 to y=0.89 (39% of page)
            ax_ht = fig1.add_axes([0.09, 0.50, 0.86, 0.39])
            self._draw_chart_on_ax(fig1, ax_ht, measurements, sex,
                                   Indicator.HEIGHT_FOR_AGE, standard,
                                   patient_name, birth_date_str)

            # Weight chart: y=0.04 to y=0.43 (39% of page, 7% gap)
            ax_wt = fig1.add_axes([0.09, 0.04, 0.86, 0.39])
            self._draw_chart_on_ax(fig1, ax_wt, measurements, sex,
                                   Indicator.WEIGHT_FOR_AGE, standard,
                                   patient_name, birth_date_str)

            pdf.savefig(fig1)
            plt.close(fig1)

            # ── PAGE 2: Header + BMI + Data Table ────────
            fig2 = Figure(figsize=(8.27, 11.69), dpi=150)

            if header_image_path and os.path.exists(header_image_path):
                ax_header2 = fig2.add_axes([0.02, 0.91, 0.96, 0.08])
                img2 = Image.open(header_image_path)
                ax_header2.imshow(img2, aspect='auto')
                ax_header2.axis('off')

            # BMI chart (large)
            ax_bmi = fig2.add_axes([0.09, 0.35, 0.86, 0.53])
            self._draw_chart_on_ax(fig2, ax_bmi, measurements, sex,
                                   Indicator.BMI_FOR_AGE, standard,
                                   patient_name, birth_date_str)

            # Data table at bottom
            self._draw_data_table(fig2, measurements, sex, standard,
                                  patient_name, birth_date_str,
                                  rect=[0.05, 0.02, 0.90, 0.30])

            pdf.savefig(fig2)
            plt.close(fig2)

    def _draw_chart_on_ax(self, fig, ax, measurements, sex, indicator,
                          standard, patient_name, birth_date_str):
        """Draw a chart directly on a given axes (for multi-chart PDF pages)."""
        from matplotlib.ticker import MultipleLocator

        # Style
        ax.set_facecolor("#FFFFFF")
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(ChartColors.AXIS)
        ax.spines['bottom'].set_color(ChartColors.AXIS)
        ax.tick_params(colors=ChartColors.AXIS, labelsize=8)
        ax.grid(True, which='major', alpha=0.3, color=ChartColors.GRID, linewidth=0.5)
        ax.minorticks_on()
        ax.grid(True, which='minor', alpha=0.12, color=ChartColors.GRID, linewidth=0.3)

        # Age range
        self.engine.ensure_loaded(standard)
        ref_min, ref_max = self.engine.get_age_range(standard, indicator, sex)

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

        # Fetch percentile curves
        pct_curves = {}
        for pct in PERCENTILE_LINES:
            curve = self.engine.get_percentile_curve_for_chart(
                standard, indicator, sex, pct, age_min=age_min, age_max=age_max)
            if curve:
                pct_curves[pct] = curve

        # Draw bands
        common_ages = np.arange(age_min, age_max + 0.5, 0.5)
        band_pairs = [
            (None, 3), (3, 5), (5, 10), (10, 25), (25, 50),
            (50, 75), (75, 90), (90, 95), (95, 97), (97, None)]
        for p_lo, p_hi in band_pairs:
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
                           fontsize=5.5, color=PCT_COLORS.get(pct, "#999"),
                           va="center", ha="left", alpha=0.8,
                           fontweight="bold" if pct == 50 else "normal")

        # Patient data
        if measurements:
            color = ChartColors.patient_color(sex)
            bg = ChartColors.patient_bg(sex)
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
                ax.plot(ages_d, vals_d, color=color, linewidth=1.8,
                        alpha=0.8, zorder=4)
                ax.scatter(ages_d, vals_d, c=color, s=40, zorder=5,
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
                        ax.annotate(f"{z_val:+.2f}",
                                   xy=(age_y, val),
                                   xytext=(0, 8), textcoords="offset points",
                                   fontsize=6, fontweight="bold", color=color,
                                   ha="center", va="bottom",
                                   bbox=dict(boxstyle="round,pad=0.15",
                                            facecolor="white", edgecolor=color,
                                            alpha=0.8, linewidth=0.6),
                                   zorder=7)

        # Labels
        indicator_label = Indicator.LABELS.get(indicator, indicator)
        sex_label = "Boys" if sex == "M" else "Girls"
        std_label = standard
        title = f"{_bidi_wrap(patient_name)}  |  {indicator_label}  ·  {sex_label}  ·  {std_label}" if patient_name else f"{indicator_label}  ·  {sex_label}  ·  {std_label}"
        ax.set_title(title, fontsize=10, fontweight="bold", color=ChartColors.TEXT, pad=8)
        ax.set_xlabel(Indicator.X_LABELS.get(indicator, "Age"), fontsize=9, color=ChartColors.TEXT)
        ax.set_ylabel(Indicator.Y_LABELS.get(indicator, "Value"), fontsize=9, color=ChartColors.TEXT)

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

        # 3-tier gridlines: 1cm minor, 5cm midi, 10cm major
        if indicator == Indicator.HEIGHT_FOR_AGE:
            ax.yaxis.set_major_locator(MultipleLocator(10))
            ax.yaxis.set_minor_locator(MultipleLocator(1))
            self._draw_midi_gridlines(ax, 'y', 5, age_min / 12, age_max / 12)
        elif indicator == Indicator.WEIGHT_FOR_AGE:
            ax.yaxis.set_major_locator(MultipleLocator(10))
            ax.yaxis.set_minor_locator(MultipleLocator(1))
            self._draw_midi_gridlines(ax, 'y', 5, age_min / 12, age_max / 12)
        elif indicator == Indicator.BMI_FOR_AGE:
            ax.yaxis.set_major_locator(MultipleLocator(5))
            ax.yaxis.set_minor_locator(MultipleLocator(1))
        ax.xaxis.set_minor_locator(MultipleLocator(0.5))
        ax.xaxis.set_major_locator(MultipleLocator(1))
