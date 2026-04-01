# 📊 GrowthChart

A local desktop application for pediatric endocrinologists to plot and analyze child growth data using **WHO** and **CDC** growth standards.

## Features

- **Interactive growth charts** — Plotly.js with drag-to-zoom, hover tooltips, responsive design
- **WHO & CDC standards** — toggle between reference systems, 9 percentile curves (P3–P97)
- **Height, Weight, BMI** charts with colored percentile bands
- **Z-score computation** — validated against official CDC published values (1140/1140 QI tests pass)
- **Hebrew RTL support** — native browser rendering for Israeli clinic data
- **PDF import** — extract patient data from Hebrew clinic letters (OCR + text extraction)
- **Excel/CSV import** — smart column detection for Hebrew and English headers
- **Patient database** — local SQLite, all data stays on your machine
- **Elysia branded PDF export** — 2-page clinical report with logo header

## Privacy

**All patient data stays local.** The SQLite database (`growthchart.db`) is never uploaded or shared. Each installation maintains its own independent patient database.

## Quick Start

### Prerequisites
- Python 3.10+ ([python.org](https://www.python.org/downloads/))
- Tesseract OCR (optional, for scanned PDFs): [UB-Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki)

### Install & Run

```bash
git clone https://github.com/YOUR_USERNAME/GrowthChart.git
cd GrowthChart
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
python main.py
```

The app opens automatically in your browser at `http://127.0.0.1:5000`.

## Growth Reference Data

The app bundles official LMS reference tables:
- **CDC** — downloaded from [cdc.gov/growthcharts](https://www.cdc.gov/growthcharts/zscore-data-files.htm)
- **WHO** — downloaded from [who.int/tools/child-growth-standards](https://www.who.int/tools/child-growth-standards)

## Z-Score Accuracy

The z-score engine is validated against the CDC's own published percentile values (P3, P5, P10, P25, P50, P75, P90, P95, P97) across all indicators, ages, and sexes. Run the QI suite:

```bash
python tests/test_zscore_qi.py
```

Expected output: `1140/1140 passed (100.0%)`

## License

MIT

## Acknowledgments

Built for pediatric endocrinology practice. Growth standards data © WHO and CDC.
