"""
Application theme and styling constants.
Clean, medical-professional aesthetic with customtkinter.
"""

# ── Color Palette ─────────────────────────────────────────────

class Colors:
    # Primary (teal medical accent)
    PRIMARY        = "#0891B2"
    PRIMARY_DARK   = "#0E7490"
    PRIMARY_LIGHT  = "#CFFAFE"

    # Surface & background
    BG             = "#F8FAFC"
    SURFACE        = "#FFFFFF"
    SURFACE_ALT    = "#F1F5F9"

    # Text
    TEXT           = "#1E293B"
    TEXT_SECONDARY = "#64748B"
    TEXT_MUTED     = "#94A3B8"
    TEXT_ON_PRIMARY= "#FFFFFF"

    # Borders
    BORDER         = "#E2E8F0"
    BORDER_LIGHT   = "#F1F5F9"

    # Semantic
    SUCCESS        = "#059669"
    WARNING        = "#D97706"
    DANGER         = "#DC2626"
    INFO           = "#2563EB"

    # Gender
    BOY            = "#2563EB"
    BOY_LIGHT      = "#DBEAFE"
    GIRL           = "#DB2777"
    GIRL_LIGHT     = "#FCE7F3"

    # Sidebar
    SIDEBAR_BG     = "#F1F5F9"
    SIDEBAR_HOVER  = "#E2E8F0"
    SIDEBAR_ACTIVE = "#DBEAFE"


# ── Typography ────────────────────────────────────────────────

class Fonts:
    FAMILY         = "Segoe UI"
    FAMILY_MONO    = "Consolas"

    # (family, size, weight)
    TITLE          = (FAMILY, 18, "bold")
    HEADING        = (FAMILY, 14, "bold")
    SUBHEADING     = (FAMILY, 12, "bold")
    BODY           = (FAMILY, 11)
    BODY_BOLD      = (FAMILY, 11, "bold")
    SMALL          = (FAMILY, 10)
    SMALL_BOLD     = (FAMILY, 10, "bold")
    TINY           = (FAMILY, 9)
    MONO           = (FAMILY_MONO, 11)
    ZSCORE         = (FAMILY_MONO, 13, "bold")


# ── Layout Constants ──────────────────────────────────────────

class Layout:
    SIDEBAR_WIDTH  = 280
    PAD_XS         = 4
    PAD_SM         = 8
    PAD_MD         = 12
    PAD_LG         = 16
    PAD_XL         = 24
    CORNER_RADIUS  = 8
    BUTTON_HEIGHT  = 36
    INPUT_HEIGHT   = 36
    ROW_HEIGHT     = 40
    ICON_SIZE      = 20
