# GrowthChart — Build Portable USB Executable
# Run this script at home to produce a self-contained folder you copy to USB.
# No Python or installation needed on the target computer.
#
# Usage:
#   cd C:\Users\primu\Projects\GrowthChart
#   powershell -ExecutionPolicy Bypass -File build_portable.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  GrowthChart — Portable Build" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Install / upgrade PyInstaller ────────────────────────────────────────
Write-Host "[1/5] Installing PyInstaller..." -ForegroundColor Yellow
pip install --upgrade pyinstaller | Out-Null
Write-Host "      OK" -ForegroundColor Green

# ── 2. Clean previous build ─────────────────────────────────────────────────
Write-Host "[2/5] Cleaning old build..." -ForegroundColor Yellow
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
Write-Host "      OK" -ForegroundColor Green

# ── 3. Run PyInstaller ───────────────────────────────────────────────────────
Write-Host "[3/5] Building executable (this takes 1-2 minutes)..." -ForegroundColor Yellow

pyinstaller `
    --onedir `
    --name "GrowthChart" `
    --add-data "static;static" `
    --add-data "data;data" `
    --add-data "zscore;zscore" `
    --add-data "api;api" `
    --add-data "clinical;clinical" `
    --add-data "importers;importers" `
    --add-data "exports;exports" `
    --hidden-import "pdfplumber" `
    --hidden-import "openpyxl" `
    --hidden-import "reportlab" `
    --hidden-import "PIL" `
    --hidden-import "bidi" `
    --hidden-import "arabic_reshaper" `
    --hidden-import "flask" `
    --hidden-import "flask_cors" `
    --noconsole `
    main.py

Write-Host "      OK" -ForegroundColor Green

# ── 4. Create USB-ready folder ──────────────────────────────────────────────
Write-Host "[4/5] Preparing USB package..." -ForegroundColor Yellow

$USB_PKG = "dist\GrowthChart_USB"
if (Test-Path $USB_PKG) { Remove-Item -Recurse -Force $USB_PKG }
New-Item -ItemType Directory -Path $USB_PKG | Out-Null

# Copy the built app
Copy-Item -Recurse "dist\GrowthChart\*" "$USB_PKG\"

# Create empty folders that the app expects
New-Item -ItemType Directory -Force -Path "$USB_PKG\uploads" | Out-Null

# Create the launcher batch file (double-click this on any PC)
$launcher = @"
@echo off
cd /d "%~dp0"
start "" GrowthChart.exe
"@
Set-Content -Path "$USB_PKG\Launch GrowthChart.bat" -Value $launcher -Encoding ASCII

Write-Host "      OK" -ForegroundColor Green

# ── 5. Summary ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  BUILD COMPLETE" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Output folder: dist\GrowthChart_USB\" -ForegroundColor White
Write-Host ""
Write-Host "  COPY TO USB:" -ForegroundColor Cyan
Write-Host "    1. Copy entire  dist\GrowthChart_USB\  folder to your USB drive"
Write-Host "    2. Also copy    growthchart.db          to the USB drive (your patient data)"
Write-Host "    3. Also copy    uploads\                to the USB drive (imported files)"
Write-Host ""
Write-Host "  AT WORK:" -ForegroundColor Cyan
Write-Host "    - Double-click  'Launch GrowthChart.bat'  on the USB drive"
Write-Host "    - App opens in your browser automatically"
Write-Host "    - All data stays on the USB — nothing touches the work PC"
Write-Host ""
Write-Host "  SECURITY REMINDER:" -ForegroundColor Yellow
Write-Host "    Encrypt the USB drive with BitLocker (right-click drive > Turn on BitLocker)"
Write-Host "    to protect patient data if the USB is ever lost."
Write-Host ""
