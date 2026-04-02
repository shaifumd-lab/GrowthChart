# growthGuard — Pediatric Growth CDS

Clinical decision support for pediatric growth monitoring. Plots measurements on WHO and CDC growth charts with accurate z-score and percentile calculations, pattern-based clinical alerts, and Bayley-Pinneau predicted adult height. Runs entirely on your local machine — patient data never leaves your computer.

## Features

### Growth Charts
- **WHO standards** (0-5 years) and **WHO references** (5-19 years) with official LMS data
- **CDC 2000 charts** (0-20 years) with official published percentile validation
- Interactive Plotly.js charts with drag-to-zoom, hover tooltips, and double-click reset
- Percentile curves: P3, P5, P10, P25, P50, P75, P90, P95, P97 with colored bands
- Height-for-age, weight-for-age, and BMI-for-age indicators
- Switch between WHO and CDC standards with one click

### Growth Velocity
- Annualized height velocity (cm/year) computed between consecutive measurements
- Tanner-based velocity reference percentile curves (P3-P97) for boys and girls
- Covers ages 1-18 (boys) and 1-16 (girls) including pubertal growth spurt

### Mid-Parental Height (MPH)
- Automatic MPH calculation from parental heights (Tanner method)
- MPH percentile curve overlay — tracks the genetic target across all ages as a grey dotted line
- Target height range band (MPH +/- 8.5 cm boys, +/- 7.5 cm girls)
- MPH marker on the right edge of the chart with exact value annotation
- Manual override for user-edited MPH values

### Bone Age & Predicted Adult Height
- Bone age entry per measurement (manual or extracted from clinic letters)
- Height-for-bone-age markers on growth charts
- Bayley-Pinneau predicted adult height (PAH) calculation
- PAH projected at adult age with comparison to target height range

### GH Therapy Tracking
- GH start date field with vertical purple marker on growth charts
- Visual timeline showing when growth hormone therapy began relative to measurements

### Syndromic Growth Charts
- Turner syndrome (Lyon et al.) height references overlaid on standard charts
- Down syndrome (Zemel 2015) height, weight, and BMI references
- Both standard and syndrome-specific curves shown together for comparison

### Data Import

#### PDF Clinic Letters
- Extracts patient name, date of birth, and measurements from Hebrew clinic letters
- Dual extraction: digital text via pdfplumber, scanned documents via Tesseract OCR
- Hebrew RTL text handling with automatic character reversal correction
- Parental height extraction from letter text
- Bone age extraction from letter text
- Validation: age-appropriate height/weight ranges, confidence scoring, unit detection

#### Image OCR
- Import from photos of clinic letters, data tables, or handwritten notes
- Accepts JPG, PNG, BMP, TIFF files
- Image preprocessing: EXIF auto-rotation, adaptive thresholding, upscaling for OCR
- Hebrew + English Tesseract OCR with same extraction pipeline as PDF

#### Chart Digitizer
- Extract data points from photos of paper growth charts
- 4-point axis calibration (click known values on X and Y axes)
- Automatic point detection using OpenCV color analysis (default mode)
- Manual click-to-digitize as fallback for unusual chart formats
- Zoomable canvas with pan support
- Points exported directly as patient measurements

#### Excel and CSV
- Smart column detection: fuzzy matching of Hebrew and English headers
- Data-type heuristic fallback when headers are ambiguous
- Automatic unit detection and conversion (meters to cm, grams to kg)
- Editable preview table before import

#### Batch Import
- Multi-file upload and folder upload
- ZIP archive extraction and processing
- Two modes: assign all files to one patient, or auto-detect patients from file contents
- Patient matching across imports (ID, name + DOB, fuzzy Hebrew name matching)

### Data Export

#### Elysia Branded PDF Report
- Two-page A4 report with clinic header logo
- Page 1: height and weight charts with all measurements plotted
- Page 2: BMI chart and measurement data table
- RTL Hebrew support in exported text

#### Chart Image Export
- Export current chart view as PNG with descriptive filename

### Patient Management
- Patient database with name, DOB, sex, MRN, parental heights, syndrome, GH start date
- Search-as-you-type patient list
- Patient deduplication and merging across import sessions
- Fuzzy Hebrew name matching with final-form letter normalization

### User Interface
- Single-page web application served locally in your browser
- Hebrew RTL text rendered natively by the browser
- Responsive layout with sidebar patient list and main chart area
- Font size adjustment (12-24 px)
- Help documentation accessible from the app

## Web Version (PWA)

A Progressive Web App version runs entirely in the browser with zero installation. Access it from any machine with Chrome or Edge. All computation happens client-side in JavaScript. Patient data is stored in the browser's IndexedDB and can be synced to a local folder via the File System Access API. Data never touches any server.

## Privacy & Data Security

All patient data is stored in a local SQLite database on your machine. The application runs as a local web server — no data is transmitted to any external service. The source code on GitHub contains no patient data.

For multi-machine use: carry the database file on an encrypted USB drive, or use a peer-to-peer sync tool like Syncthing.

## Quick Start

### Prerequisites
- Python 3.10 or later
- Tesseract OCR with Hebrew language pack (for PDF/image import)

### Install & Run
```bash
git clone https://github.com/shaifumd-lab/GrowthChart.git
cd GrowthChart
pip install -r requirements.txt
python main.py
```

The app opens automatically in your default browser at `http://localhost:5000`.

### Tesseract OCR (optional, for import features)

Windows:
```
winget install UB-Mannheim.TesseractOCR
```

## Z-Score Accuracy

The z-score engine is validated against official CDC published percentile values across all indicators, ages, and both sexes. The QI test suite contains 1140 test cases and achieves 100% pass rate (z-score within 0.02 SD, percentile within 0.5%).

```bash
python tests/test_zscore_qi.py
# Expected: 1140/1140 passed (100.0%)
```

## Data Sources

| Source | Coverage | Origin |
|--------|----------|--------|
| CDC 2000 | 0-20 years, height/weight/BMI | [cdc.gov/growthcharts](https://www.cdc.gov/growthcharts/) |
| WHO Standards | 0-5 years, length/height/weight/BMI | [who.int](https://www.who.int/tools/child-growth-standards) |
| WHO References | 5-19 years, height/weight/BMI | [who.int](https://www.who.int/tools/growth-reference-data-for-5to19-years) |
| Velocity | 1-18 years, height velocity | Tanner et al. |
| Turner syndrome | Height-for-age | Lyon et al. |
| Down syndrome | Height/weight/BMI | Zemel et al. 2015 |

## Technology

- **Backend**: Python, Flask, SQLite (WAL mode)
- **Frontend**: Vanilla JavaScript, Plotly.js 2.35, Tailwind CSS
- **Import**: pdfplumber, pytesseract, OpenCV, openpyxl
- **Export**: reportlab, matplotlib (Agg backend)
- **Z-scores**: LMS method (Box-Cox power exponential)
- **PWA**: IndexedDB, File System Access API, Tesseract.js, pdf.js, jsPDF

## License

MIT

## Acknowledgments

Built for pediatric endocrinology practice at Elysia Clinic. Growth standards data from WHO and CDC.
