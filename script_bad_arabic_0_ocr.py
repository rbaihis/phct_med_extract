import os
import json
import time
import requests
import pdfplumber
import subprocess
import pytesseract
from PIL import Image

BASE_URL = "http://www.phct.com.tn/images/DocumentsPCT/Circulaires/"
OUTPUT_PDF_DIR = "output/pdf"
OUTPUT_JSON_DIR = "output/json"

# Delay between downloads (prevents timeouts and bans)
DOWNLOAD_SLEEP = 1.0   # 1 second between requests

os.makedirs(OUTPUT_PDF_DIR, exist_ok=True)
os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)


def download_pdf(url, path, retries=3):
    """Download PDF with retries and avoid crashes on timeout."""
    for attempt in range(1, retries+1):
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", ""):
                with open(path, "wb") as f:
                    f.write(r.content)
                print("Downloaded:", path)
                return True
            return False
        except Exception as e:
            print(f"⚠ Download error (attempt {attempt}/{retries}):", e)
            time.sleep(2)

    return False


def extract_text_from_pdf(pdf_path):
    data = {"text": "", "tables": []}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""

                # OCR fallback for scanned PDFs
                if len(text.strip()) < 10:
                    print(" → Scanned PDF, applying OCR:", pdf_path)
                    text += ocr_page(pdf_path, page.page_number)

                data["text"] += text + "\n"

                # Extract tables if available
                tables = page.extract_tables()
                if tables:
                    data["tables"].extend(tables)

    except Exception as e:
        print("Error reading", pdf_path, ":", e)

    return data


def ocr_page(pdf_path, page_number):
    """Handle scanned PDF pages via OCR."""
    temp_image = f"temp_page_{page_number}.png"

    try:
        subprocess.run(
            ["pdftoppm", pdf_path, "temp_page", "-png", "-f", str(page_number), "-singlefile"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20
        )
    except subprocess.TimeoutExpired:
        print("⚠ OCR conversion timeout:", pdf_path)
        return ""

    if not os.path.exists(temp_image):
        return ""

    img = Image.open(temp_image)
    text = pytesseract.image_to_string(img, lang="ara+fra+eng")
    os.remove(temp_image)
    return text


def save_json(data, pdf_name):
    out = os.path.join(OUTPUT_JSON_DIR, pdf_name.replace(".pdf", ".json"))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Saved JSON:", out)


def main():
    for i in range(1, 100):
        base_name = f"{i:02d}25.pdf"

        variants = [
            "circ" + base_name,
            "Circ" + base_name,
            "CIRC" + base_name,
        ]

        found = False

        for fname in variants:
            url = BASE_URL + fname
            pdf_path = os.path.join(OUTPUT_PDF_DIR, fname)

            # Already downloaded?
            if os.path.exists(pdf_path):
                print("⏩ Skipping already downloaded file:", fname)
                extracted = extract_text_from_pdf(pdf_path)
                save_json(extracted, fname)
                found = True
                break

            # Try downloading
            if download_pdf(url, pdf_path):
                print("✔ Found file using:", fname)
                extracted = extract_text_from_pdf(pdf_path)
                save_json(extracted, fname)
                found = True
                break

            # Sleep between variants
            time.sleep(0.5)

        if not found:
            print("✘ File not found for index:", i)

        # Sleep between numbers (protect from timeout / rate limit)
        time.sleep(DOWNLOAD_SLEEP)


if __name__ == "__main__":
    main()
