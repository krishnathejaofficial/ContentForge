"""
download_fonts.py — Download required Google Fonts into assets/fonts/.
Run once: python download_fonts.py
"""
import sys
import urllib.request
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Multiple source fallbacks per font
FONTS = {
    "Inter-Bold.ttf": [
        "https://github.com/rsms/inter/raw/main/src/static/Inter-Bold.ttf",
        "https://github.com/rsms/inter/raw/main/docs/font-files/Inter-Bold.ttf",
        "https://fonts.gstatic.com/s/inter/v13/UcCO3FwrK3iLTeHuS_fvQtMwCp50KnMw2boKoduKmMEVuBAsAZ9jiA.woff2",
    ],
    "Roboto-Regular.ttf": [
        "https://github.com/google/fonts/raw/main/ofl/roboto/static/Roboto-Regular.ttf",
        "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Regular.ttf",
        "https://github.com/openmaptiles/fonts/raw/master/roboto/Roboto-Regular.ttf",
    ],
    "BebasNeue-Regular.ttf": [
        "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf",
    ],
}

FONTS_DIR = Path("assets/fonts")
FONTS_DIR.mkdir(parents=True, exist_ok=True)

for filename, urls in FONTS.items():
    dest = FONTS_DIR / filename
    if dest.exists():
        print(f"  [OK] Already exists: {filename}")
        continue
    downloaded = False
    for url in urls:
        print(f"  [...] Trying: {url.split('/')[-1]} ({filename})...")
        try:
            urllib.request.urlretrieve(url, dest)
            print(f"  [OK] Saved: {dest}")
            downloaded = True
            break
        except Exception as e:
            print(f"  [skip] {e}")
    if not downloaded:
        print(f"  [FAIL] Could not download {filename}. Get it manually from: https://fonts.google.com")

print("\n[OK] Font download complete.")
print(f"     Fonts in: {FONTS_DIR.resolve()}")
