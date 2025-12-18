# PHCT Circulaire Odoo Module

Self-contained Odoo 15 module that fetches PHCT circulaire PDFs, extracts/parses
medication data (with OCR support), and stores results in the database.

## Features
- All parsing logic embedded (no external script dependencies).
- Stores filename/year state in DB (continues from last processed circulaire).
- Configurable base URL via `ir.config_parameter`.
- Auto-detects year from current UTC date.
- Supports OCR for scanned PDFs (requires system dependencies).
- Stores full parsed JSON, simplified JSON, and medication lines.

## Installation
1. Ensure module is under Odoo addons path (already at `phct_med_extract/addons/phct_circulaire`).
2. Install required Python packages in the Odoo container:
   ```bash
   pip install pdfplumber requests pytesseract pillow opencv-python-headless numpy
   ```
3. Install system dependencies for OCR:
   ```bash
   apt-get update && apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-ara tesseract-ocr-fra
   ```
4. Restart Odoo, update app list, install "PHCT Circulaire (Importer)".

## Configuration
- Base URL: Settings → Technical → Parameters → System Parameters → key `phct_circulaire.base_url`.
  - Default: `http://www.phct.com.tn/images/DocumentsPCT/Circulaires/`

## Usage
- Cron runs hourly to check for new circulaires.
- Manually run: Settings → Technical → Automation → Scheduled Actions → "Fetch PHCT Circulaires" → Run Manually.
- View results: PHCT → Circulaires → Imported Circulaires.

## Docker Container Commands
```bash
# Install dependencies inside container
docker exec -it odoo_phct_gst bash
pip install pdfplumber requests pytesseract pillow opencv-python-headless numpy
apt-get update && apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-ara tesseract-ocr-fra
exit

# Restart container
docker restart odoo_phct_gst

# Run cron manually via Odoo shell
docker exec -it odoo_phct_gst odoo shell -d <your_db>
# then: env['phct.circulaire'].fetch_and_process_circulaires()
```

