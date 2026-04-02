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

# ── 0. Kill any running GrowthChart processes ─────────────────────────────
Write-Host "[0/6] Stopping running GrowthChart processes..." -ForegroundColor Yellow
Get-Process -Name "GrowthChart" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Write-Host "      OK" -ForegroundColor Green

# ── 1. Install / upgrade PyInstaller ────────────────────────────────────────
Write-Host "[1/6] Installing PyInstaller..." -ForegroundColor Yellow
pip install --upgrade pyinstaller | Out-Null
Write-Host "      OK" -ForegroundColor Green

# ── 2. Clean previous build ─────────────────────────────────────────────────
Write-Host "[2/6] Cleaning old build..." -ForegroundColor Yellow
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
Write-Host "      OK" -ForegroundColor Green

# ── 3. Run PyInstaller ───────────────────────────────────────────────────────
Write-Host "[3/6] Building executable (this takes 1-2 minutes)..." -ForegroundColor Yellow

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
    --add-data "cds;cds" `
    --hidden-import "pdfplumber" `
    --hidden-import "pdfminer" `
    --hidden-import "pdfminer.high_level" `
    --hidden-import "openpyxl" `
    --hidden-import "reportlab" `
    --hidden-import "PIL" `
    --hidden-import "PIL.Image" `
    --hidden-import "bidi" `
    --hidden-import "bidi.algorithm" `
    --hidden-import "arabic_reshaper" `
    --hidden-import "flask" `
    --hidden-import "flask_cors" `
    --hidden-import "jinja2" `
    --hidden-import "werkzeug" `
    --hidden-import "markupsafe" `
    --hidden-import "itsdangerous" `
    --hidden-import "blinker" `
    --hidden-import "click" `
    --hidden-import "sqlite3" `
    --hidden-import "cv2" `
    --hidden-import "pytesseract" `
    --noconsole `
    main.py

Write-Host "      OK" -ForegroundColor Green

# ── 4. Create USB-ready folder ──────────────────────────────────────────────
Write-Host "[4/6] Preparing USB package..." -ForegroundColor Yellow

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

# ── 5. Copy to USB with retry ────────────────────────────────────────────────
Write-Host "[5/6] Checking for USB drive..." -ForegroundColor Yellow

$usbDrive = $null
foreach ($drive in Get-PSDrive -PSProvider FileSystem) {
    if ($drive.Root -match "^[D-Z]:\\" -and (Get-Volume -DriveLetter $drive.Name -ErrorAction SilentlyContinue).DriveType -eq "Removable") {
        $usbDrive = $drive.Root
        break
    }
}

if ($usbDrive) {
    Write-Host "      Found USB at $usbDrive" -ForegroundColor Green
    $usbTarget = Join-Path $usbDrive "GrowthChart"

    # Kill any running GrowthChart from USB before copying
    Get-Process -Name "GrowthChart" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2

    # Retry copy up to 3 times
    $retries = 3
    for ($i = 1; $i -le $retries; $i++) {
        try {
            if (Test-Path $usbTarget) { Remove-Item -Recurse -Force $usbTarget }
            Copy-Item -Recurse "$USB_PKG" "$usbTarget" -Force
            Write-Host "      Copied to $usbTarget" -ForegroundColor Green
            break
        } catch {
            Write-Host "      Copy attempt $i/$retries failed: $_" -ForegroundColor Yellow
            if ($i -lt $retries) { Start-Sleep -Seconds 3 }
            else { Write-Host "      MANUAL COPY REQUIRED: copy dist\GrowthChart_USB\ to USB" -ForegroundColor Red }
        }
    }
} else {
    Write-Host "      No USB drive detected. Copy dist\GrowthChart_USB\ manually." -ForegroundColor Yellow
}

# ── 6. Summary ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  BUILD COMPLETE" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Output folder: dist\GrowthChart_USB\" -ForegroundColor White
Write-Host ""
Write-Host "  TO USE:" -ForegroundColor Cyan
Write-Host "    1. Copy  dist\GrowthChart_USB\  to your USB drive"
Write-Host "    2. Also copy  growthchart.db  to the same folder"
Write-Host "    3. Double-click  'Launch GrowthChart.bat'"
Write-Host ""
Write-Host "  SECURITY:" -ForegroundColor Yellow
Write-Host "    Encrypt the USB drive with BitLocker to protect patient data."
Write-Host ""
