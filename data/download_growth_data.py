"""
Download official WHO and CDC growth reference data files.

Run this script to replace the manually-created CSV files with the official
data directly from WHO and CDC servers.

Usage:
    python download_growth_data.py

Requirements:
    pip install requests
"""
import os
import requests
import sys

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

CDC_FILES = {
    "cdc_statage.csv": "https://www.cdc.gov/growthcharts/data/zscore/statage.csv",
    "cdc_wtage.csv": "https://www.cdc.gov/growthcharts/data/zscore/wtage.csv",
    "cdc_bmiage.csv": "https://www.cdc.gov/growthcharts/data/zscore/bmiage.csv",
    "cdc_lenageinf.csv": "https://www.cdc.gov/growthcharts/data/zscore/lenageinf.csv",
    "cdc_wtageinf.csv": "https://www.cdc.gov/growthcharts/data/zscore/wtageinf.csv",
    "cdc_hcageinf.csv": "https://www.cdc.gov/growthcharts/data/zscore/hcageinf.csv",
}

# WHO Child Growth Standards (0-5 years) - tab-separated text files
WHO_0_5_BASE = "https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards"
WHO_0_5_FILES = {
    # Length/height-for-age
    "who_lhfa_boys_0_5_official.txt": f"{WHO_0_5_BASE}/indicators/length-height-for-age/lhfa_boys_0-to-5-years_zscores.xlsx",
    "who_lhfa_girls_0_5_official.txt": f"{WHO_0_5_BASE}/indicators/length-height-for-age/lhfa_girls_0-to-5-years_zscores.xlsx",
    # Weight-for-age
    "who_wfa_boys_0_5_official.txt": f"{WHO_0_5_BASE}/indicators/weight-for-age/wfa-boys-zscore-expanded-tables.xlsx",
    "who_wfa_girls_0_5_official.txt": f"{WHO_0_5_BASE}/indicators/weight-for-age/wfa-girls-zscore-expanded-tables.xlsx",
    # BMI-for-age
    "who_bfa_boys_0_5_official.txt": f"{WHO_0_5_BASE}/indicators/body-mass-index-for-age/bfa-boys-zscore-expanded-tables.xlsx",
    "who_bfa_girls_0_5_official.txt": f"{WHO_0_5_BASE}/indicators/body-mass-index-for-age/bfa-girls-zscore-expanded-tables.xlsx",
}

# WHO Growth Reference (5-19 years)
WHO_5_19_BASE = "https://cdn.who.int/media/docs/default-source/child-growth/growth-reference-5-19-years"
WHO_5_19_FILES = {
    # Height-for-age
    "who_hfa_boys_5_19_official.txt": f"{WHO_5_19_BASE}/height-for-age-(5-19-years)/hfa-boys-z-who-2007-exp.xlsx",
    "who_hfa_girls_5_19_official.txt": f"{WHO_5_19_BASE}/height-for-age-(5-19-years)/hfa-girls-z-who-2007-exp.xlsx",
    # BMI-for-age
    "who_bfa_boys_5_19_official.txt": f"{WHO_5_19_BASE}/bmi-for-age-(5-19-years)/bfa-boys-z-who-2007-exp.xlsx",
    "who_bfa_girls_5_19_official.txt": f"{WHO_5_19_BASE}/bmi-for-age-(5-19-years)/bfa-girls-z-who-2007-exp.xlsx",
}

# Alternative WHO URLs (plain text/tab-delimited) that may be more accessible
WHO_ALT_URLS = {
    "who_lhfa_boys_0_5": [
        "https://www.who.int/tools/child-growth-standards/standards/length-height-for-age",
        "https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/length-height-for-age/tab_lhfa_boys_p_0_5.txt",
        "https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/length-height-for-age/lhfa_boys_p_exp.txt",
    ],
}


def download_file(url, filename, timeout=30):
    """Download a file from URL, return True on success."""
    filepath = os.path.join(DATA_DIR, filename)
    try:
        print(f"  Downloading {filename}...")
        print(f"    URL: {url}")
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(resp.content)
            size = len(resp.content)
            print(f"    OK ({size:,} bytes)")
            return True
        else:
            print(f"    FAILED (HTTP {resp.status_code})")
            return False
    except Exception as e:
        print(f"    ERROR: {e}")
        return False


def main():
    print("=" * 60)
    print("Growth Chart Data Downloader")
    print("=" * 60)

    results = {"success": [], "failed": []}

    # Download CDC files
    print("\n--- CDC Growth Charts (2000) ---")
    for filename, url in CDC_FILES.items():
        if download_file(url, filename):
            results["success"].append(filename)
        else:
            results["failed"].append(filename)

    # Try WHO xlsx files (these contain LMS tables)
    print("\n--- WHO Child Growth Standards (0-5 years) ---")
    for filename, url in WHO_0_5_FILES.items():
        if download_file(url, filename):
            results["success"].append(filename)
        else:
            results["failed"].append(filename)

    print("\n--- WHO Growth Reference (5-19 years) ---")
    for filename, url in WHO_5_19_FILES.items():
        if download_file(url, filename):
            results["success"].append(filename)
        else:
            results["failed"].append(filename)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Successful: {len(results['success'])}")
    for f in results["success"]:
        print(f"    + {f}")
    print(f"  Failed: {len(results['failed'])}")
    for f in results["failed"]:
        print(f"    - {f}")

    if results["failed"]:
        print("\nNote: Some downloads failed. The manually-created CSV files")
        print("in this directory contain approximate LMS values from published")
        print("WHO/CDC references and can be used as a fallback.")
        print("\nYou may also try downloading manually from:")
        print("  CDC: https://www.cdc.gov/growthcharts/zscore.htm")
        print("  WHO 0-5: https://www.who.int/tools/child-growth-standards/standards")
        print("  WHO 5-19: https://www.who.int/tools/growth-reference-data-for-5to19-years/indicators")

    return 0 if not results["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
