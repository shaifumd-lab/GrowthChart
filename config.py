"""Application configuration and constants."""
import os
import sys
import math
from pathlib import Path

# Paths
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent

DATA_DIR = APP_DIR / "data"
DB_PATH = APP_DIR / "growthchart.db"

# Tesseract OCR path (Windows default)
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Application
APP_NAME = "GrowthChart"
APP_VERSION = "1.1.0"

# Chart reference standards
class Standard:
    WHO = "WHO"
    CDC = "CDC"

# Indicator types
class Indicator:
    HEIGHT_FOR_AGE = "hfa"
    WEIGHT_FOR_AGE = "wfa"
    BMI_FOR_AGE = "bfa"
    WEIGHT_FOR_HEIGHT = "wfh"

    LABELS = {
        "hfa": "Height-for-Age",
        "wfa": "Weight-for-Age",
        "bfa": "BMI-for-Age",
        "wfh": "Weight-for-Height",
    }
    Y_LABELS = {
        "hfa": "Height (cm)",
        "wfa": "Weight (kg)",
        "bfa": "BMI (kg/m²)",
        "wfh": "Weight (kg)",
    }
    X_LABELS = {
        "hfa": "Age (years)",
        "wfa": "Age (years)",
        "bfa": "Age (years)",
        "wfh": "Height (cm)",
    }

# ── CDC/WHO Standard Percentile Lines ──────────────────────
# These are the 9 standard percentile lines shown on official CDC charts
PERCENTILE_LINES = [3, 5, 10, 25, 50, 75, 90, 95, 97]

# Exact z-scores corresponding to each percentile (from inverse normal CDF)
PERCENTILE_ZSCORES = {
    3:  -1.88079,
    5:  -1.64485,
    10: -1.28155,
    25: -0.67449,
    50:  0.0,
    75:  0.67449,
    90:  1.28155,
    95:  1.64485,
    97:  1.88079,
}

# Z-score to percentile mapping
def zscore_to_percentile(z):
    """Convert z-score to percentile using the standard normal CDF."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2))) * 100

def percentile_to_zscore(p):
    """Convert percentile to approximate z-score."""
    from statistics import NormalDist
    return NormalDist().inv_cdf(p / 100)
