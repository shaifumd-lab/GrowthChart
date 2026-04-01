"""
GrowthChart — Pediatric Growth Monitoring Application

A standalone desktop app that:
1. Imports clinic summary PDFs and scanned growth tables
2. Extracts birth date, measurement dates, height, weight via OCR + text
3. Computes WHO/CDC z-scores and percentiles
4. Plots growth charts with reference curves
5. Saves patients locally in SQLite

Usage:
    python main.py
"""

import sys
import os

# Ensure the project root is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.app import GrowthChartApp


def main():
    app = GrowthChartApp()
    app.mainloop()


if __name__ == "__main__":
    main()
