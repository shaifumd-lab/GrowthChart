"""
Main application window for GrowthChart.

Layout:
┌──────────────────────────────────────────────────────────────┐
│  ■ GrowthChart           [Search...]     [Import PDF]  [+]  │
├───────────┬──────────────────────────────────────────────────┤
│           │  ┌ Patient Header ──────────────────────────┐   │
│  Patient  │  │ Name · DOB · Age · Sex    [Edit] [Del]   │   │
│  List     │  └──────────────────────────────────────────┘   │
│           │  ┌ Chart Controls ──────────────────────────┐   │
│  [search] │  │ [Height] [Weight] [BMI]   WHO ⟷ CDC     │   │
│           │  └──────────────────────────────────────────┘   │
│  Patient1 │  ┌──────────────────────────────────────────┐   │
│  Patient2 │  │                                          │   │
│ >Patient3 │  │         GROWTH CHART (matplotlib)        │   │
│  Patient4 │  │                                          │   │
│           │  │                                          │   │
│           │  └──────────────────────────────────────────┘   │
│           │  ┌ Measurements Table ──────────────────────┐   │
│           │  │ Date | Age | Ht | Wt | BMI | SDS  [+ ▾] │   │
│           │  │ ···                                      │   │
│           │  └──────────────────────────────────────────┘   │
└───────────┴──────────────────────────────────────────────────┘
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter as tk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import date, datetime
from typing import Optional, List

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Standard, Indicator, APP_NAME, APP_VERSION
from database import (init_db, get_all_patients, save_patient, delete_patient,
                      get_measurements, save_measurement, save_measurements_batch,
                      delete_measurement, search_patients)
from models import Patient, Measurement
from zscore.engine import ZScoreEngine
from charts.growth_chart import GrowthChartRenderer
from pdf.extractor import PDFExtractor
from ui.theme import Colors, Fonts, Layout


class GrowthChartApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # ── Window Setup ──────────────────────────────────
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1280x800")
        self.minsize(900, 600)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # ── State ─────────────────────────────────────────
        self.current_patient: Optional[Patient] = None
        self.current_measurements: List[Measurement] = []
        self.current_standard = Standard.CDC
        self.current_indicator = Indicator.HEIGHT_FOR_AGE

        # ── Services ──────────────────────────────────────
        init_db()
        self.engine = ZScoreEngine()
        self.chart_renderer = GrowthChartRenderer(self.engine)
        self.pdf_extractor = PDFExtractor()

        # Pre-load both standards
        self.engine.load_standard(Standard.WHO)
        self.engine.load_standard(Standard.CDC)

        # ── Build UI ──────────────────────────────────────
        self._build_toolbar()
        self._build_main_area()
        self._refresh_patient_list()

        # ── Keyboard shortcuts ────────────────────────────
        self.bind("<Control-n>", lambda e: self._on_new_patient())
        self.bind("<Control-i>", lambda e: self._on_import_pdf())
        self.bind("<Control-f>", lambda e: self.search_entry.focus())

    # ══════════════════════════════════════════════════════
    #  TOOLBAR
    # ══════════════════════════════════════════════════════

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, height=50, fg_color=Colors.SURFACE,
                               corner_radius=0)
        toolbar.pack(fill="x", side="top")
        toolbar.pack_propagate(False)

        # App icon + title
        title_lbl = ctk.CTkLabel(toolbar, text=f"📊 {APP_NAME}",
                                 font=ctk.CTkFont(*Fonts.HEADING),
                                 text_color=Colors.PRIMARY)
        title_lbl.pack(side="left", padx=(Layout.PAD_LG, Layout.PAD_XL))

        # Buttons (right side)
        btn_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        btn_frame.pack(side="right", padx=Layout.PAD_LG)

        ctk.CTkButton(btn_frame, text="＋ Patient", width=110,
                      height=Layout.BUTTON_HEIGHT,
                      fg_color=Colors.PRIMARY,
                      hover_color=Colors.PRIMARY_DARK,
                      command=self._on_new_patient,
                      font=ctk.CTkFont(*Fonts.SMALL_BOLD)
                      ).pack(side="right", padx=4)

        ctk.CTkButton(btn_frame, text="📄 Import", width=100,
                      height=Layout.BUTTON_HEIGHT,
                      fg_color=Colors.SURFACE_ALT,
                      hover_color=Colors.BORDER,
                      text_color=Colors.TEXT,
                      border_width=1, border_color=Colors.BORDER,
                      command=self._on_import_pdf,
                      font=ctk.CTkFont(*Fonts.SMALL)
                      ).pack(side="right", padx=4)

        # Separator line
        sep = ctk.CTkFrame(self, height=1, fg_color=Colors.BORDER)
        sep.pack(fill="x", side="top")

    # ══════════════════════════════════════════════════════
    #  MAIN AREA (sidebar + content)
    # ══════════════════════════════════════════════════════

    def _build_main_area(self):
        main = ctk.CTkFrame(self, fg_color=Colors.BG, corner_radius=0)
        main.pack(fill="both", expand=True)

        # ── Sidebar (patient list) ────────────────────────
        self.sidebar = ctk.CTkFrame(main, width=Layout.SIDEBAR_WIDTH,
                                    fg_color=Colors.SIDEBAR_BG,
                                    corner_radius=0)
        self.sidebar.pack(fill="y", side="left")
        self.sidebar.pack_propagate(False)

        self._build_sidebar()

        # Vertical separator
        sep = ctk.CTkFrame(main, width=1, fg_color=Colors.BORDER)
        sep.pack(fill="y", side="left")

        # ── Content area ──────────────────────────────────
        self.content = ctk.CTkFrame(main, fg_color=Colors.BG, corner_radius=0)
        self.content.pack(fill="both", expand=True, side="left")

        self._build_content()

    # ══════════════════════════════════════════════════════
    #  SIDEBAR
    # ══════════════════════════════════════════════════════

    def _build_sidebar(self):
        # Search
        search_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        search_frame.pack(fill="x", padx=Layout.PAD_SM, pady=(Layout.PAD_SM, 4))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._on_search())
        self.search_entry = ctk.CTkEntry(
            search_frame, placeholder_text="🔍  Search patients...",
            textvariable=self.search_var,
            height=32, corner_radius=Layout.CORNER_RADIUS,
            font=ctk.CTkFont(*Fonts.SMALL),
            fg_color=Colors.SURFACE,
            border_color=Colors.BORDER,
        )
        self.search_entry.pack(fill="x")

        # Patient list (scrollable)
        self.patient_list_frame = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent",
            scrollbar_button_color=Colors.BORDER,
            scrollbar_button_hover_color=Colors.TEXT_MUTED,
        )
        self.patient_list_frame.pack(fill="both", expand=True,
                                     padx=Layout.PAD_XS, pady=Layout.PAD_XS)

        self.patient_buttons: List[ctk.CTkButton] = []

    def _refresh_patient_list(self, query: str = ""):
        """Refresh the sidebar patient list."""
        # Clear existing
        for btn in self.patient_buttons:
            btn.destroy()
        self.patient_buttons.clear()

        patients = search_patients(query) if query else get_all_patients()

        if not patients:
            lbl = ctk.CTkLabel(self.patient_list_frame,
                              text="No patients yet.\nClick '＋ Patient' to add one.",
                              font=ctk.CTkFont(*Fonts.SMALL),
                              text_color=Colors.TEXT_MUTED,
                              justify="center")
            lbl.pack(pady=40)
            self.patient_buttons.append(lbl)
            return

        for p in patients:
            is_active = (self.current_patient and
                        self.current_patient.id == p.id)
            sex_icon = "♂" if p.sex == "M" else "♀"
            sex_color = Colors.BOY if p.sex == "M" else Colors.GIRL

            btn_frame = ctk.CTkFrame(self.patient_list_frame,
                                     fg_color=Colors.SIDEBAR_ACTIVE if is_active
                                             else "transparent",
                                     corner_radius=Layout.CORNER_RADIUS,
                                     height=50)
            btn_frame.pack(fill="x", pady=1)
            btn_frame.pack_propagate(False)

            # Make the frame clickable
            inner = ctk.CTkFrame(btn_frame, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=Layout.PAD_SM,
                      pady=Layout.PAD_XS)

            name_lbl = ctk.CTkLabel(inner,
                                    text=f"{sex_icon} {p.full_name or 'Unnamed'}",
                                    font=ctk.CTkFont(*Fonts.SMALL_BOLD),
                                    text_color=Colors.TEXT,
                                    anchor="w")
            name_lbl.pack(fill="x", anchor="w")

            detail_text = p.age_str
            if p.medical_record_number:
                detail_text += f"  ·  {p.medical_record_number}"

            detail_lbl = ctk.CTkLabel(inner,
                                      text=detail_text,
                                      font=ctk.CTkFont(*Fonts.TINY),
                                      text_color=Colors.TEXT_MUTED,
                                      anchor="w")
            detail_lbl.pack(fill="x", anchor="w")

            # Bind click to all elements
            pid = p.id
            for widget in [btn_frame, inner, name_lbl, detail_lbl]:
                widget.bind("<Button-1>", lambda e, _id=pid: self._select_patient(_id))
                widget.bind("<Enter>", lambda e, f=btn_frame:
                           f.configure(fg_color=Colors.SIDEBAR_HOVER)
                           if not (self.current_patient and
                                   self.current_patient.id == pid)
                           else None)
                widget.bind("<Leave>", lambda e, f=btn_frame, _id=pid:
                           f.configure(fg_color=Colors.SIDEBAR_ACTIVE
                                      if (self.current_patient and
                                          self.current_patient.id == _id)
                                      else "transparent"))

            self.patient_buttons.append(btn_frame)

    # ══════════════════════════════════════════════════════
    #  CONTENT AREA
    # ══════════════════════════════════════════════════════

    def _build_content(self):
        # ── Patient Header ────────────────────────────────
        self.header_frame = ctk.CTkFrame(self.content, fg_color=Colors.SURFACE,
                                         corner_radius=0, height=70)
        self.header_frame.pack(fill="x")
        self.header_frame.pack_propagate(False)
        self._build_patient_header()

        # ── Chart Controls ────────────────────────────────
        controls = ctk.CTkFrame(self.content, fg_color=Colors.SURFACE_ALT,
                                corner_radius=0, height=45)
        controls.pack(fill="x")
        controls.pack_propagate(False)
        self._build_chart_controls(controls)

        # Separator
        ctk.CTkFrame(self.content, height=1,
                     fg_color=Colors.BORDER).pack(fill="x")

        # ── Chart Area ────────────────────────────────────
        chart_frame = ctk.CTkFrame(self.content, fg_color=Colors.SURFACE,
                                   corner_radius=0)
        chart_frame.pack(fill="both", expand=True)

        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.fig.set_facecolor(Colors.BG)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True,
                                         padx=Layout.PAD_SM,
                                         pady=Layout.PAD_SM)

        # ── Measurements Table ────────────────────────────
        self.table_frame = ctk.CTkFrame(self.content, fg_color=Colors.SURFACE,
                                        corner_radius=0, height=180)
        self.table_frame.pack(fill="x", side="bottom")
        self.table_frame.pack_propagate(False)
        self._build_measurements_table()

        # Show empty state
        self._show_empty_state()

    def _build_patient_header(self):
        """Build the patient info header."""
        inner = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=Layout.PAD_LG,
                  pady=Layout.PAD_SM)

        # Left side: patient info
        info_left = ctk.CTkFrame(inner, fg_color="transparent")
        info_left.pack(side="left", fill="y")

        self.patient_name_lbl = ctk.CTkLabel(
            info_left, text="Select a patient",
            font=ctk.CTkFont(*Fonts.HEADING),
            text_color=Colors.TEXT)
        self.patient_name_lbl.pack(anchor="w")

        self.patient_detail_lbl = ctk.CTkLabel(
            info_left, text="or import a PDF to get started",
            font=ctk.CTkFont(*Fonts.SMALL),
            text_color=Colors.TEXT_MUTED)
        self.patient_detail_lbl.pack(anchor="w")

        # Right side: action buttons
        btn_right = ctk.CTkFrame(inner, fg_color="transparent")
        btn_right.pack(side="right", fill="y")

        self.edit_btn = ctk.CTkButton(
            btn_right, text="✏️ Edit", width=70,
            height=30, corner_radius=6,
            fg_color=Colors.SURFACE_ALT,
            hover_color=Colors.BORDER,
            text_color=Colors.TEXT,
            border_width=1, border_color=Colors.BORDER,
            font=ctk.CTkFont(*Fonts.SMALL),
            command=self._on_edit_patient)
        self.edit_btn.pack(side="left", padx=2)

        self.add_meas_btn = ctk.CTkButton(
            btn_right, text="＋ Measurement", width=110,
            height=30, corner_radius=6,
            fg_color=Colors.PRIMARY,
            hover_color=Colors.PRIMARY_DARK,
            font=ctk.CTkFont(*Fonts.SMALL_BOLD),
            command=self._on_add_measurement)
        self.add_meas_btn.pack(side="left", padx=2)

        self.add_data_btn = ctk.CTkButton(
            btn_right, text="📂 Add Data", width=90,
            height=30, corner_radius=6,
            fg_color=Colors.PRIMARY_LIGHT,
            hover_color=Colors.PRIMARY,
            text_color=Colors.TEXT,
            font=ctk.CTkFont(*Fonts.SMALL_BOLD),
            command=self._on_add_data_to_patient)
        self.add_data_btn.pack(side="left", padx=2)

        self.export_btn = ctk.CTkButton(
            btn_right, text="💾 Export", width=80,
            height=30, corner_radius=6,
            fg_color=Colors.SURFACE_ALT,
            hover_color=Colors.BORDER,
            text_color=Colors.TEXT,
            border_width=1, border_color=Colors.BORDER,
            font=ctk.CTkFont(*Fonts.SMALL),
            command=self._on_export_chart)
        self.export_btn.pack(side="left", padx=2)

        self.elysia_btn = ctk.CTkButton(
            btn_right, text="📄 Elysia", width=80,
            height=30, corner_radius=6,
            fg_color="#F9A8D4",
            hover_color="#F472B6",
            text_color="#831843",
            font=ctk.CTkFont(*Fonts.SMALL_BOLD),
            command=self._on_export_elysia)
        self.elysia_btn.pack(side="left", padx=2)

    def _build_chart_controls(self, parent):
        """Build chart type selector and standard toggle."""
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=Layout.PAD_LG)

        # Left: indicator tabs
        tab_frame = ctk.CTkFrame(inner, fg_color="transparent")
        tab_frame.pack(side="left", fill="y", pady=6)

        self.indicator_buttons = {}
        for ind, label in [
            (Indicator.HEIGHT_FOR_AGE, "📏 Height"),
            (Indicator.WEIGHT_FOR_AGE, "⚖️ Weight"),
            (Indicator.BMI_FOR_AGE, "📊 BMI"),
        ]:
            btn = ctk.CTkButton(
                tab_frame, text=label, width=90, height=30,
                corner_radius=6,
                fg_color=Colors.PRIMARY if ind == self.current_indicator
                         else "transparent",
                hover_color=Colors.PRIMARY_LIGHT,
                text_color=Colors.TEXT_ON_PRIMARY if ind == self.current_indicator
                          else Colors.TEXT,
                font=ctk.CTkFont(*Fonts.SMALL_BOLD),
                command=lambda i=ind: self._set_indicator(i))
            btn.pack(side="left", padx=2)
            self.indicator_buttons[ind] = btn

        # Right: standard toggle (WHO / CDC)
        toggle_frame = ctk.CTkFrame(inner, fg_color="transparent")
        toggle_frame.pack(side="right", fill="y", pady=6)

        self.standard_var = tk.StringVar(value=self.current_standard)

        ctk.CTkLabel(toggle_frame, text="Standard:",
                    font=ctk.CTkFont(*Fonts.SMALL),
                    text_color=Colors.TEXT_SECONDARY
                    ).pack(side="left", padx=(0, 6))

        is_cdc = self.current_standard == Standard.CDC
        self.who_btn = ctk.CTkButton(
            toggle_frame, text="WHO", width=55, height=28,
            corner_radius=6,
            fg_color=Colors.SURFACE if is_cdc else Colors.PRIMARY,
            hover_color=Colors.PRIMARY_DARK,
            text_color=Colors.TEXT if is_cdc else Colors.TEXT_ON_PRIMARY,
            border_width=1 if is_cdc else 0,
            border_color=Colors.BORDER,
            font=ctk.CTkFont(*Fonts.SMALL_BOLD),
            command=lambda: self._set_standard(Standard.WHO))
        self.who_btn.pack(side="left", padx=1)

        self.cdc_btn = ctk.CTkButton(
            toggle_frame, text="CDC", width=55, height=28,
            corner_radius=6,
            fg_color=Colors.PRIMARY if is_cdc else Colors.SURFACE,
            hover_color=Colors.PRIMARY_DARK,
            text_color=Colors.TEXT_ON_PRIMARY if is_cdc else Colors.TEXT,
            border_width=0 if is_cdc else 1,
            border_color=Colors.BORDER,
            font=ctk.CTkFont(*Fonts.SMALL_BOLD),
            command=lambda: self._set_standard(Standard.CDC))
        self.cdc_btn.pack(side="left", padx=1)

    def _build_measurements_table(self):
        """Build the measurements data table."""
        # Header
        header = ctk.CTkFrame(self.table_frame, fg_color=Colors.SURFACE_ALT,
                              height=30, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        cols = [("Date", 90), ("Age", 60), ("Ht cm", 65),
                ("Wt kg", 60), ("BMI", 55),
                ("Ht-SDS", 60), ("Ht %ile", 55),
                ("Wt-SDS", 60), ("Wt %ile", 55),
                ("BMI-SDS", 60), ("BMI %ile", 55), ("", 30)]

        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="both", expand=True, padx=Layout.PAD_SM)

        for col_name, width in cols:
            ctk.CTkLabel(header_inner, text=col_name, width=width,
                        font=ctk.CTkFont(*Fonts.TINY),
                        text_color=Colors.TEXT_MUTED,
                        anchor="center").pack(side="left")

        # Scrollable rows
        self.table_scroll = ctk.CTkScrollableFrame(
            self.table_frame, fg_color="transparent",
            scrollbar_button_color=Colors.BORDER,
        )
        self.table_scroll.pack(fill="both", expand=True)

        self.measurement_rows = []

    def _refresh_measurements_table(self):
        """Refresh the measurements table with current data."""
        for w in self.measurement_rows:
            w.destroy()
        self.measurement_rows.clear()

        if not self.current_measurements:
            lbl = ctk.CTkLabel(self.table_scroll,
                              text="No measurements yet",
                              font=ctk.CTkFont(*Fonts.SMALL),
                              text_color=Colors.TEXT_MUTED)
            lbl.pack(pady=10)
            self.measurement_rows.append(lbl)
            return

        for i, m in enumerate(self.current_measurements):
            bg = Colors.SURFACE if i % 2 == 0 else Colors.SURFACE_ALT
            row = ctk.CTkFrame(self.table_scroll, fg_color=bg,
                              height=32, corner_radius=0)
            row.pack(fill="x")
            row.pack_propagate(False)

            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=Layout.PAD_SM)

            date_str = m.date.strftime("%d/%m/%Y") if m.date else "—"
            ht_pct = f"{m.height_percentile:.0f}" if m.height_percentile is not None else "—"
            wt_pct = f"{m.weight_percentile:.0f}" if m.weight_percentile is not None else "—"
            bmi_pct = f"{m.bmi_percentile:.0f}" if m.bmi_percentile is not None else "—"
            vals = [
                (date_str, 90),
                (m.age_str, 60),
                (f"{m.height_cm:.1f}" if m.height_cm else "—", 65),
                (f"{m.weight_kg:.1f}" if m.weight_kg else "—", 60),
                (f"{m.bmi:.1f}" if m.bmi else "—", 55),
                (m.height_sds_str, 60),
                (ht_pct, 55),
                (m.weight_sds_str, 60),
                (wt_pct, 55),
                (m.bmi_sds_str, 60),
                (bmi_pct, 55),
            ]

            for text, width in vals:
                color = Colors.TEXT
                # Color z-scores
                if text.startswith("+") or text.startswith("-"):
                    try:
                        z = float(text)
                        if abs(z) >= 2:
                            color = Colors.DANGER
                        elif abs(z) >= 1:
                            color = Colors.WARNING
                        else:
                            color = Colors.SUCCESS
                    except ValueError:
                        pass

                ctk.CTkLabel(inner, text=text, width=width,
                            font=ctk.CTkFont(*Fonts.SMALL),
                            text_color=color,
                            anchor="center").pack(side="left")

            # Delete button
            del_btn = ctk.CTkButton(inner, text="✕", width=24, height=24,
                                    fg_color="transparent",
                                    hover_color="#FEE2E2",
                                    text_color=Colors.TEXT_MUTED,
                                    font=ctk.CTkFont(*Fonts.SMALL),
                                    command=lambda mid=m.id: self._on_delete_measurement(mid))
            del_btn.pack(side="left")

            self.measurement_rows.append(row)

    # ══════════════════════════════════════════════════════
    #  STATE MANAGEMENT
    # ══════════════════════════════════════════════════════

    def _select_patient(self, patient_id: int):
        """Select a patient and load their data."""
        from database import get_patient
        self.current_patient = get_patient(patient_id)
        if not self.current_patient:
            return

        # Load measurements
        self.current_measurements = get_measurements(patient_id)

        # Compute z-scores for each measurement
        self._compute_all_zscores()

        # Update UI
        self._update_patient_header()
        self._refresh_measurements_table()
        self._refresh_chart()
        self._refresh_patient_list(self.search_var.get())

    def _compute_all_zscores(self):
        """Compute z-scores and percentiles using the selected standard."""
        if not self.current_patient or not self.current_patient.birth_date:
            return

        std = self.current_standard
        for m in self.current_measurements:
            m.compute_age(self.current_patient.birth_date)
            m.compute_bmi()

            # Reset all computed values
            m.height_zscore = m.weight_zscore = m.bmi_zscore = None
            m.height_percentile = m.weight_percentile = m.bmi_percentile = None

            if m.age_months is None:
                continue

            sex = self.current_patient.sex

            # Height z-score
            if m.height_cm:
                z = self.engine.compute_zscore(
                    m.height_cm, m.age_months, sex,
                    Indicator.HEIGHT_FOR_AGE, std)
                m.height_zscore = z
                if z is not None:
                    m.height_percentile = self.engine.compute_percentile(z)

            # Weight z-score
            if m.weight_kg:
                z = self.engine.compute_zscore(
                    m.weight_kg, m.age_months, sex,
                    Indicator.WEIGHT_FOR_AGE, std)
                m.weight_zscore = z
                if z is not None:
                    m.weight_percentile = self.engine.compute_percentile(z)

            # BMI z-score
            if m.bmi:
                z = self.engine.compute_zscore(
                    m.bmi, m.age_months, sex,
                    Indicator.BMI_FOR_AGE, std)
                m.bmi_zscore = z
                if z is not None:
                    m.bmi_percentile = self.engine.compute_percentile(z)

    def _update_patient_header(self):
        """Update the patient header with current patient info."""
        if not self.current_patient:
            self.patient_name_lbl.configure(text="Select a patient")
            self.patient_detail_lbl.configure(text="or import a PDF to get started")
            return

        p = self.current_patient
        sex_icon = "♂" if p.sex == "M" else "♀"
        self.patient_name_lbl.configure(
            text=f"{sex_icon}  {p.full_name or 'Unnamed Patient'}")

        details = []
        if p.birth_date:
            details.append(f"DOB: {p.birth_date.strftime('%d/%m/%Y')}")
        if p.age_str:
            details.append(f"Age: {p.age_str}")
        if p.medical_record_number:
            details.append(f"MRN: {p.medical_record_number}")

        # Latest z-scores with standard label
        if self.current_measurements:
            last = self.current_measurements[-1]
            std_label = self.current_standard
            if last.height_zscore is not None:
                pct = f" ({last.height_percentile:.0f}%ile)" if last.height_percentile else ""
                details.append(f"Ht-SDS: {last.height_zscore:+.2f}{pct} [{std_label}]")

        self.patient_detail_lbl.configure(text="  ·  ".join(details))

    def _refresh_chart(self):
        """Redraw the growth chart."""
        if not self.current_patient:
            self._show_empty_state()
            return

        self.chart_renderer.create_chart(
            fig=self.fig,
            measurements=self.current_measurements,
            sex=self.current_patient.sex,
            indicator=self.current_indicator,
            standard=self.current_standard,
            patient_name=self.current_patient.full_name,
            birth_date_str=(self.current_patient.birth_date.strftime("%d/%m/%Y")
                          if self.current_patient.birth_date else ""),
        )
        self.canvas.draw()

    def _show_empty_state(self):
        """Show placeholder when no patient is selected."""
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(Colors.BG)
        self.fig.set_facecolor(Colors.BG)
        ax.text(0.5, 0.5, "Select a patient or import a PDF\nto view growth charts",
               transform=ax.transAxes, ha="center", va="center",
               fontsize=14, color=Colors.TEXT_MUTED, alpha=0.6)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        self.canvas.draw()

    def _set_indicator(self, indicator: str):
        """Switch chart indicator (height/weight/BMI)."""
        self.current_indicator = indicator
        for ind, btn in self.indicator_buttons.items():
            if ind == indicator:
                btn.configure(fg_color=Colors.PRIMARY,
                            text_color=Colors.TEXT_ON_PRIMARY)
            else:
                btn.configure(fg_color="transparent",
                            text_color=Colors.TEXT)
        self._refresh_chart()

    def _set_standard(self, standard: str):
        """Switch between WHO and CDC standards."""
        self.current_standard = standard
        self.engine.ensure_loaded(standard)

        if standard == Standard.WHO:
            self.who_btn.configure(fg_color=Colors.PRIMARY,
                                  text_color=Colors.TEXT_ON_PRIMARY,
                                  border_width=0)
            self.cdc_btn.configure(fg_color=Colors.SURFACE,
                                  text_color=Colors.TEXT,
                                  border_width=1)
        else:
            self.cdc_btn.configure(fg_color=Colors.PRIMARY,
                                  text_color=Colors.TEXT_ON_PRIMARY,
                                  border_width=0)
            self.who_btn.configure(fg_color=Colors.SURFACE,
                                  text_color=Colors.TEXT,
                                  border_width=1)

        # Recompute z-scores with new standard
        self._compute_all_zscores()
        self._refresh_measurements_table()
        self._refresh_chart()

    def _on_search(self):
        query = self.search_var.get().strip()
        self._refresh_patient_list(query)

    # ══════════════════════════════════════════════════════
    #  DIALOGS
    # ══════════════════════════════════════════════════════

    def _on_new_patient(self):
        """Open dialog to create a new patient."""
        dialog = PatientDialog(self, title="New Patient")
        self.wait_window(dialog)
        if dialog.result:
            patient = dialog.result
            save_patient(patient)
            self._refresh_patient_list()
            self._select_patient(patient.id)

    def _on_edit_patient(self):
        """Open dialog to edit current patient."""
        if not self.current_patient:
            return
        dialog = PatientDialog(self, title="Edit Patient",
                              patient=self.current_patient)
        self.wait_window(dialog)
        if dialog.result:
            save_patient(dialog.result)
            self._select_patient(dialog.result.id)

    def _on_add_measurement(self):
        """Open dialog to add a measurement."""
        if not self.current_patient:
            messagebox.showinfo("No Patient", "Please select a patient first.")
            return
        dialog = MeasurementDialog(self, patient=self.current_patient)
        self.wait_window(dialog)
        if dialog.result:
            dialog.result.patient_id = self.current_patient.id
            save_measurement(dialog.result)
            self._select_patient(self.current_patient.id)

    def _on_delete_measurement(self, measurement_id: int):
        if messagebox.askyesno("Delete", "Delete this measurement?"):
            delete_measurement(measurement_id)
            if self.current_patient:
                self._select_patient(self.current_patient.id)

    def _on_import_pdf(self):
        """Import patient data from PDF, Excel, or CSV."""
        filepath = filedialog.askopenfilename(
            title="Import Growth Data",
            filetypes=[
                ("All Supported", "*.pdf;*.xlsx;*.xls;*.csv;*.tsv"),
                ("PDF Files", "*.pdf"),
                ("Excel Files", "*.xlsx;*.xls"),
                ("CSV/TSV Files", "*.csv;*.tsv"),
                ("All Files", "*.*"),
            ]
        )
        if not filepath:
            return

        self._import_file(filepath, target_patient=None)

    def _on_add_data_to_patient(self):
        """Import additional measurements for the current patient."""
        if not self.current_patient:
            return
        filepath = filedialog.askopenfilename(
            title=f"Add data for {self.current_patient.full_name}",
            filetypes=[
                ("All Supported", "*.pdf;*.xlsx;*.xls;*.csv;*.tsv"),
                ("PDF Files", "*.pdf"),
                ("Excel Files", "*.xlsx;*.xls"),
                ("CSV/TSV Files", "*.csv;*.tsv"),
                ("All Files", "*.*"),
            ]
        )
        if not filepath:
            return

        self._import_file(filepath, target_patient=self.current_patient)

    def _import_file(self, filepath: str, target_patient=None):
        """Import data from any supported file type."""
        ext = filepath.lower().rsplit('.', 1)[-1] if '.' in filepath else ''

        try:
            if ext == 'pdf':
                data = self.pdf_extractor.extract_from_pdf(filepath)
            elif ext in ('xlsx', 'xls', 'csv', 'tsv'):
                data = self._extract_from_spreadsheet(filepath)
            else:
                messagebox.showerror("Import Error",
                                    f"Unsupported file type: .{ext}")
                return
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to read file:\n{e}")
            return

        # If adding to existing patient, pre-fill patient info
        if target_patient:
            data.first_name = data.first_name or target_patient.first_name
            data.last_name = data.last_name or target_patient.last_name
            data.birth_date = data.birth_date or target_patient.birth_date
            data.sex = data.sex or target_patient.sex
            data.medical_record_number = (data.medical_record_number
                                         or target_patient.medical_record_number)

        dialog = ImportReviewDialog(self, extracted_data=data,
                                   existing_patient=target_patient)
        self.wait_window(dialog)

        if target_patient and dialog.result_measurements:
            # Append measurements to existing patient
            for m in dialog.result_measurements:
                m.patient_id = target_patient.id
            save_measurements_batch(dialog.result_measurements)
            self._refresh_patient_list()
            self._select_patient(target_patient.id)
        elif dialog.result_patient and dialog.result_measurements:
            # New patient
            patient = dialog.result_patient
            save_patient(patient)
            for m in dialog.result_measurements:
                m.patient_id = patient.id
            save_measurements_batch(dialog.result_measurements)
            self._refresh_patient_list()
            self._select_patient(patient.id)

    def _extract_from_spreadsheet(self, filepath: str):
        """Extract measurements from Excel or CSV files."""
        from pdf.extractor import ExtractedPatientData, ExtractedMeasurement
        import csv
        from datetime import datetime

        data = ExtractedPatientData(source_file=filepath)
        ext = filepath.lower().rsplit('.', 1)[-1]

        rows = []
        if ext in ('xlsx', 'xls'):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(filepath, read_only=True)
                ws = wb.active
                all_rows = list(ws.iter_rows(values_only=True))
                wb.close()
                if all_rows:
                    # First row as headers
                    headers = [str(c).strip().lower() if c else '' for c in all_rows[0]]
                    for r in all_rows[1:]:
                        row_dict = {}
                        for i, val in enumerate(r):
                            if i < len(headers):
                                row_dict[headers[i]] = val
                        rows.append(row_dict)
            except Exception as e:
                raise ValueError(f"Cannot read Excel file: {e}")
        else:
            # CSV/TSV
            delimiter = '\t' if ext == 'tsv' else ','
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                if reader.fieldnames:
                    reader.fieldnames = [fn.strip().lower() for fn in reader.fieldnames]
                for row in reader:
                    rows.append(row)

        # Map columns to height/weight/date
        # Support common column names
        date_cols = ['date', 'תאריך', 'measurement_date', 'visit_date', 'exam_date']
        ht_cols = ['height', 'height_cm', 'ht', 'ht_cm', 'גובה', 'length', 'stature', 'cm']
        wt_cols = ['weight', 'weight_kg', 'wt', 'wt_kg', 'משקל', 'kg', 'mass']
        age_cols = ['age', 'age_months', 'agemos', 'גיל', 'age_years']

        def find_col(row_dict, candidates):
            for c in candidates:
                if c in row_dict and row_dict[c] is not None:
                    val = str(row_dict[c]).strip()
                    if val:
                        return val
            return None

        for row in rows:
            # Normalize keys
            norm_row = {str(k).strip().lower(): v for k, v in row.items()}

            d_str = find_col(norm_row, date_cols)
            h_str = find_col(norm_row, ht_cols)
            w_str = find_col(norm_row, wt_cols)
            age_str = find_col(norm_row, age_cols)

            if not h_str and not w_str:
                continue

            # Parse date
            meas_date = None
            if d_str:
                from datetime import date as date_cls
                # Try common date formats
                for fmt in ["%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y",
                           "%d-%m-%Y", "%Y/%m/%d"]:
                    try:
                        meas_date = datetime.strptime(str(d_str).strip(), fmt).date()
                        break
                    except (ValueError, TypeError):
                        continue
                # openpyxl may return datetime objects directly
                if meas_date is None and hasattr(d_str, 'date'):
                    meas_date = d_str if isinstance(d_str, date_cls) else d_str.date()
                elif meas_date is None:
                    try:
                        from datetime import date as dt_date
                        meas_date = datetime.strptime(
                            str(d_str).split()[0], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        pass

            # Parse height
            height = None
            if h_str:
                try:
                    height = float(str(h_str).replace(',', '.'))
                    if 0.4 <= height <= 2.2:
                        height = round(height * 100, 1)  # meters → cm
                    elif not (30 <= height <= 220):
                        height = None
                except (ValueError, TypeError):
                    pass

            # Parse weight
            weight = None
            if w_str:
                try:
                    weight = float(str(w_str).replace(',', '.'))
                    if not (1 <= weight <= 300):
                        weight = None
                except (ValueError, TypeError):
                    pass

            if height or weight:
                em = ExtractedMeasurement(
                    date=meas_date,
                    height_cm=height,
                    weight_kg=weight,
                    confidence=0.9 if meas_date else 0.5,
                    raw_text=str(row)
                )
                data.measurements.append(em)

        data.raw_text = f"Spreadsheet: {len(data.measurements)} rows parsed"
        return data

    def _on_export_chart(self):
        """Export current chart to file."""
        if not self.current_patient:
            return
        filepath = filedialog.asksaveasfilename(
            title="Export Chart",
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("PDF Document", "*.pdf")],
            initialfile=f"{self.current_patient.full_name.replace(' ', '_')}_{Indicator.LABELS.get(self.current_indicator, 'chart').replace('-', '').replace(' ', '')}_{self.current_standard}"
        )
        if filepath:
            self.chart_renderer.export_chart(
                filepath,
                measurements=self.current_measurements,
                sex=self.current_patient.sex,
                indicator=self.current_indicator,
                standard=self.current_standard,
                patient_name=self.current_patient.full_name,
                birth_date_str=(self.current_patient.birth_date.strftime("%d/%m/%Y")
                              if self.current_patient.birth_date else ""),
            )
            messagebox.showinfo("Exported", f"Chart saved to:\n{filepath}")

    def _on_export_elysia(self):
        """Export Elysia-branded PDF with height + weight + BMI charts."""
        if not self.current_patient:
            return
        from config import APP_DIR
        header_path = str(APP_DIR / "assets" / "elysia_header.png")

        safe_name = self.current_patient.full_name.replace(' ', '_')
        filepath = filedialog.asksaveasfilename(
            title="Export Elysia Chart",
            defaultextension=".pdf",
            filetypes=[("PDF Document", "*.pdf")],
            initialfile=f"elysia_chart_{safe_name}"
        )
        if filepath:
            self.chart_renderer.export_elysia_pdf(
                filepath,
                measurements=self.current_measurements,
                sex=self.current_patient.sex,
                standard=self.current_standard,
                patient_name=self.current_patient.full_name,
                birth_date_str=(self.current_patient.birth_date.strftime("%d/%m/%Y")
                              if self.current_patient.birth_date else ""),
                header_image_path=header_path,
            )
            messagebox.showinfo("Exported", f"Elysia chart saved to:\n{filepath}")


# ══════════════════════════════════════════════════════════════
#  PATIENT DIALOG
# ══════════════════════════════════════════════════════════════

class PatientDialog(ctk.CTkToplevel):
    """Dialog for creating or editing a patient."""

    def __init__(self, parent, title="Patient", patient: Optional[Patient] = None):
        super().__init__(parent)
        self.title(title)
        self.geometry("420x400")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: Optional[Patient] = None
        self.patient = patient or Patient()

        self._build_form()
        self.after(100, self.first_name_entry.focus)

    def _build_form(self):
        pad = Layout.PAD_LG

        # First name
        ctk.CTkLabel(self, text="First Name",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD)).pack(
                    anchor="w", padx=pad, pady=(pad, 2))
        self.first_name_entry = ctk.CTkEntry(self, height=36)
        self.first_name_entry.pack(fill="x", padx=pad)
        self.first_name_entry.insert(0, self.patient.first_name)

        # Last name
        ctk.CTkLabel(self, text="Last Name",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD)).pack(
                    anchor="w", padx=pad, pady=(pad, 2))
        self.last_name_entry = ctk.CTkEntry(self, height=36)
        self.last_name_entry.pack(fill="x", padx=pad)
        self.last_name_entry.insert(0, self.patient.last_name)

        # Birth date
        ctk.CTkLabel(self, text="Birth Date (DD/MM/YYYY)",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD)).pack(
                    anchor="w", padx=pad, pady=(pad, 2))
        self.birth_date_entry = ctk.CTkEntry(self, height=36,
                                             placeholder_text="DD/MM/YYYY")
        self.birth_date_entry.pack(fill="x", padx=pad)
        if self.patient.birth_date:
            self.birth_date_entry.insert(
                0, self.patient.birth_date.strftime("%d/%m/%Y"))

        # Sex
        ctk.CTkLabel(self, text="Sex",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD)).pack(
                    anchor="w", padx=pad, pady=(pad, 2))
        self.sex_var = tk.StringVar(value=self.patient.sex)
        sex_frame = ctk.CTkFrame(self, fg_color="transparent")
        sex_frame.pack(fill="x", padx=pad)
        ctk.CTkRadioButton(sex_frame, text="♂ Male", variable=self.sex_var,
                          value="M", font=ctk.CTkFont(*Fonts.SMALL)
                          ).pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(sex_frame, text="♀ Female", variable=self.sex_var,
                          value="F", font=ctk.CTkFont(*Fonts.SMALL)
                          ).pack(side="left")

        # MRN
        ctk.CTkLabel(self, text="Medical Record Number (optional)",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD)).pack(
                    anchor="w", padx=pad, pady=(pad, 2))
        self.mrn_entry = ctk.CTkEntry(self, height=36)
        self.mrn_entry.pack(fill="x", padx=pad)
        self.mrn_entry.insert(0, self.patient.medical_record_number)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad, pady=pad)

        ctk.CTkButton(btn_frame, text="Cancel", width=90,
                      fg_color=Colors.SURFACE_ALT,
                      hover_color=Colors.BORDER,
                      text_color=Colors.TEXT,
                      command=self.destroy).pack(side="right", padx=4)

        ctk.CTkButton(btn_frame, text="Save", width=90,
                      fg_color=Colors.PRIMARY,
                      hover_color=Colors.PRIMARY_DARK,
                      command=self._save).pack(side="right", padx=4)

    def _save(self):
        # Parse birth date
        bd_text = self.birth_date_entry.get().strip()
        birth_date = None
        if bd_text:
            for fmt in ["%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d"]:
                try:
                    birth_date = datetime.strptime(bd_text, fmt).date()
                    break
                except ValueError:
                    continue
            if birth_date is None:
                messagebox.showerror("Invalid Date",
                                   "Please enter a valid date (DD/MM/YYYY)")
                return

        self.patient.first_name = self.first_name_entry.get().strip()
        self.patient.last_name = self.last_name_entry.get().strip()
        self.patient.birth_date = birth_date
        self.patient.sex = self.sex_var.get()
        self.patient.medical_record_number = self.mrn_entry.get().strip()

        self.result = self.patient
        self.destroy()


# ══════════════════════════════════════════════════════════════
#  MEASUREMENT DIALOG
# ══════════════════════════════════════════════════════════════

class MeasurementDialog(ctk.CTkToplevel):
    """Dialog for adding a single measurement."""

    def __init__(self, parent, patient: Patient):
        super().__init__(parent)
        self.title("Add Measurement")
        self.geometry("380x320")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.patient = patient
        self.result: Optional[Measurement] = None
        self._build_form()

    def _build_form(self):
        pad = Layout.PAD_LG

        ctk.CTkLabel(self, text=f"Patient: {self.patient.full_name}",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD),
                    text_color=Colors.TEXT_SECONDARY).pack(
                    anchor="w", padx=pad, pady=(pad, 8))

        # Date
        ctk.CTkLabel(self, text="Date (DD/MM/YYYY)",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD)).pack(
                    anchor="w", padx=pad, pady=(4, 2))
        self.date_entry = ctk.CTkEntry(self, height=36,
                                       placeholder_text="DD/MM/YYYY")
        self.date_entry.pack(fill="x", padx=pad)
        self.date_entry.insert(0, date.today().strftime("%d/%m/%Y"))

        # Height
        ctk.CTkLabel(self, text="Height (cm)",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD)).pack(
                    anchor="w", padx=pad, pady=(Layout.PAD_SM, 2))
        self.height_entry = ctk.CTkEntry(self, height=36,
                                         placeholder_text="e.g., 98.5")
        self.height_entry.pack(fill="x", padx=pad)

        # Weight
        ctk.CTkLabel(self, text="Weight (kg)",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD)).pack(
                    anchor="w", padx=pad, pady=(Layout.PAD_SM, 2))
        self.weight_entry = ctk.CTkEntry(self, height=36,
                                         placeholder_text="e.g., 15.2")
        self.weight_entry.pack(fill="x", padx=pad)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad, pady=pad)

        ctk.CTkButton(btn_frame, text="Cancel", width=90,
                      fg_color=Colors.SURFACE_ALT,
                      hover_color=Colors.BORDER,
                      text_color=Colors.TEXT,
                      command=self.destroy).pack(side="right", padx=4)

        ctk.CTkButton(btn_frame, text="Add", width=90,
                      fg_color=Colors.PRIMARY,
                      hover_color=Colors.PRIMARY_DARK,
                      command=self._save).pack(side="right", padx=4)

        self.after(100, self.height_entry.focus)

    def _save(self):
        # Parse date
        d_text = self.date_entry.get().strip()
        meas_date = None
        for fmt in ["%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d"]:
            try:
                meas_date = datetime.strptime(d_text, fmt).date()
                break
            except ValueError:
                continue
        if not meas_date:
            messagebox.showerror("Invalid Date", "Please enter a valid date.")
            return

        # Parse height & weight
        height = None
        weight = None
        h_text = self.height_entry.get().strip()
        w_text = self.weight_entry.get().strip()

        if h_text:
            try:
                height = float(h_text)
            except ValueError:
                messagebox.showerror("Invalid", "Height must be a number.")
                return

        if w_text:
            try:
                weight = float(w_text)
            except ValueError:
                messagebox.showerror("Invalid", "Weight must be a number.")
                return

        if not height and not weight:
            messagebox.showerror("Missing Data",
                               "Please enter at least height or weight.")
            return

        self.result = Measurement(
            date=meas_date,
            height_cm=height,
            weight_kg=weight,
        )
        self.destroy()


# ══════════════════════════════════════════════════════════════
#  IMPORT REVIEW DIALOG
# ══════════════════════════════════════════════════════════════

class ImportReviewDialog(ctk.CTkToplevel):
    """Dialog to review and confirm data extracted from a PDF or spreadsheet."""

    def __init__(self, parent, extracted_data, existing_patient=None):
        super().__init__(parent)
        self.existing_patient = existing_patient
        title = "Add Data to Patient" if existing_patient else "Review Imported Data"
        self.title(title)
        self.geometry("700x600")
        self.transient(parent)
        self.grab_set()

        self.data = extracted_data
        self.result_patient: Optional[Patient] = None
        self.result_measurements: List[Measurement] = []

        self._build_ui()

    def _build_ui(self):
        pad = Layout.PAD_LG

        # Title
        ctk.CTkLabel(self, text="Review Extracted Data",
                    font=ctk.CTkFont(*Fonts.HEADING)).pack(
                    padx=pad, pady=(pad, 8), anchor="w")

        ctk.CTkLabel(self, text=f"Source: {self.data.source_file}",
                    font=ctk.CTkFont(*Fonts.TINY),
                    text_color=Colors.TEXT_MUTED).pack(
                    padx=pad, anchor="w")

        # Patient info section
        info_frame = ctk.CTkFrame(self, fg_color=Colors.SURFACE_ALT,
                                  corner_radius=8)
        info_frame.pack(fill="x", padx=pad, pady=Layout.PAD_SM)

        ctk.CTkLabel(info_frame, text="Patient Information",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD)).pack(
                    anchor="w", padx=pad, pady=(8, 4))

        fields_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        fields_frame.pack(fill="x", padx=pad, pady=(0, 8))

        # Name
        row = ctk.CTkFrame(fields_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text="Name:", width=80,
                    font=ctk.CTkFont(*Fonts.SMALL)).pack(side="left")
        self.name_entry = ctk.CTkEntry(row, height=30)
        self.name_entry.pack(side="left", fill="x", expand=True)
        name = f"{self.data.first_name} {self.data.last_name}".strip()
        self.name_entry.insert(0, name)

        # Birth date
        row = ctk.CTkFrame(fields_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text="DOB:", width=80,
                    font=ctk.CTkFont(*Fonts.SMALL)).pack(side="left")
        self.dob_entry = ctk.CTkEntry(row, height=30,
                                      placeholder_text="DD/MM/YYYY")
        self.dob_entry.pack(side="left", fill="x", expand=True)
        if self.data.birth_date:
            self.dob_entry.insert(0, self.data.birth_date.strftime("%d/%m/%Y"))

        # Sex
        row = ctk.CTkFrame(fields_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text="Sex:", width=80,
                    font=ctk.CTkFont(*Fonts.SMALL)).pack(side="left")
        self.sex_var = tk.StringVar(value=self.data.sex or "M")
        ctk.CTkRadioButton(row, text="M", variable=self.sex_var, value="M",
                          font=ctk.CTkFont(*Fonts.SMALL)).pack(side="left", padx=4)
        ctk.CTkRadioButton(row, text="F", variable=self.sex_var, value="F",
                          font=ctk.CTkFont(*Fonts.SMALL)).pack(side="left", padx=4)

        # Measurements section
        ctk.CTkLabel(self, text="Extracted Measurements",
                    font=ctk.CTkFont(*Fonts.SMALL_BOLD)).pack(
                    anchor="w", padx=pad, pady=(Layout.PAD_SM, 4))

        if not self.data.measurements:
            ctk.CTkLabel(self, text="No measurements found in PDF.",
                        font=ctk.CTkFont(*Fonts.SMALL),
                        text_color=Colors.WARNING).pack(padx=pad, anchor="w")
        else:
            meas_scroll = ctk.CTkScrollableFrame(self, height=200)
            meas_scroll.pack(fill="both", expand=True, padx=pad, pady=4)

            self.meas_vars = []  # (check_var, date_entry, ht_entry, wt_entry)
            for em in self.data.measurements:
                row = ctk.CTkFrame(meas_scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)

                var = tk.BooleanVar(value=True)
                ctk.CTkCheckBox(row, text="", variable=var, width=24
                               ).pack(side="left", padx=4)

                d_entry = ctk.CTkEntry(row, width=100, height=28)
                d_entry.pack(side="left", padx=2)
                if em.date:
                    d_entry.insert(0, em.date.strftime("%d/%m/%Y"))

                h_entry = ctk.CTkEntry(row, width=80, height=28,
                                       placeholder_text="Ht cm")
                h_entry.pack(side="left", padx=2)
                if em.height_cm:
                    h_entry.insert(0, f"{em.height_cm:.1f}")

                w_entry = ctk.CTkEntry(row, width=80, height=28,
                                       placeholder_text="Wt kg")
                w_entry.pack(side="left", padx=2)
                if em.weight_kg:
                    w_entry.insert(0, f"{em.weight_kg:.1f}")

                # Confidence indicator
                conf_color = Colors.SUCCESS if em.confidence > 0.7 else Colors.WARNING
                ctk.CTkLabel(row, text=f"({em.confidence:.0%})",
                            font=ctk.CTkFont(*Fonts.TINY),
                            text_color=conf_color).pack(side="left", padx=4)

                self.meas_vars.append((var, d_entry, h_entry, w_entry))

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad, pady=pad)

        ctk.CTkButton(btn_frame, text="Cancel", width=100,
                      fg_color=Colors.SURFACE_ALT,
                      hover_color=Colors.BORDER,
                      text_color=Colors.TEXT,
                      command=self.destroy).pack(side="right", padx=4)

        ctk.CTkButton(btn_frame, text="Import Selected", width=130,
                      fg_color=Colors.PRIMARY,
                      hover_color=Colors.PRIMARY_DARK,
                      command=self._import).pack(side="right", padx=4)

    def _import(self):
        # Parse patient info
        name_parts = self.name_entry.get().strip().split(maxsplit=1)
        first = name_parts[0] if name_parts else ""
        last = name_parts[1] if len(name_parts) > 1 else ""

        dob_text = self.dob_entry.get().strip()
        birth_date = None
        if dob_text:
            for fmt in ["%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"]:
                try:
                    birth_date = datetime.strptime(dob_text, fmt).date()
                    break
                except ValueError:
                    continue

        self.result_patient = Patient(
            first_name=first,
            last_name=last,
            birth_date=birth_date,
            sex=self.sex_var.get(),
            medical_record_number=self.data.medical_record_number,
        )

        # Parse measurements
        self.result_measurements = []
        for var, d_entry, h_entry, w_entry in self.meas_vars:
            if not var.get():
                continue

            d_text = d_entry.get().strip()
            meas_date = None
            for fmt in ["%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"]:
                try:
                    meas_date = datetime.strptime(d_text, fmt).date()
                    break
                except ValueError:
                    continue
            if not meas_date:
                continue

            height = None
            weight = None
            h_text = h_entry.get().strip()
            w_text = w_entry.get().strip()
            try:
                height = float(h_text) if h_text else None
            except ValueError:
                pass
            try:
                weight = float(w_text) if w_text else None
            except ValueError:
                pass

            if height or weight:
                self.result_measurements.append(Measurement(
                    date=meas_date,
                    height_cm=height,
                    weight_kg=weight,
                    source_pdf=self.data.source_file,
                ))

        self.destroy()
