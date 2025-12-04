#!/usr/bin/env python3
import os
import json
import time
import re
import unicodedata
import requests
import pdfplumber
import subprocess
import pytesseract
import numpy as np
from PIL import Image
import cv2

# ---------------- CONFIG ----------------
BASE_URL = "http://www.phct.com.tn/images/DocumentsPCT/Circulaires/"
OUTPUT_PDF_DIR = "output/pdf"
OUTPUT_JSON_DIR = "output/json"
YEAR_SUFFIX = "25"   # change if needed
START = 1
END = 99
DOWNLOAD_SLEEP = 1.0  # seconds between index iterations
VARIANT_SLEEP = 0.5   # between case variants
# ----------------------------------------

os.makedirs(OUTPUT_PDF_DIR, exist_ok=True)
os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)


# ---------- Arabic Presentation Forms -> Standard Arabic ----------
# Mapping from Arabic Presentation Forms to standard Arabic letters
ARABIC_PRESENTATION_FORMS = {
    # Alef variants
    '\uFE8D': '\u0627', '\uFE8E': '\u0627',  # ALEF
    '\uFE8F': '\u0628', '\uFE90': '\u0628', '\uFE91': '\u0628', '\uFE92': '\u0628',  # BEH
    '\uFE93': '\u0629', '\uFE94': '\u0629',  # TEH MARBUTA
    '\uFE95': '\u062A', '\uFE96': '\u062A', '\uFE97': '\u062A', '\uFE98': '\u062A',  # TEH
    '\uFE99': '\u062B', '\uFE9A': '\u062B', '\uFE9B': '\u062B', '\uFE9C': '\u062B',  # THEH
    '\uFE9D': '\u062C', '\uFE9E': '\u062C', '\uFE9F': '\u062C', '\uFEA0': '\u062C',  # JEEM
    '\uFEA1': '\u062D', '\uFEA2': '\u062D', '\uFEA3': '\u062D', '\uFEA4': '\u062D',  # HAH
    '\uFEA5': '\u062E', '\uFEA6': '\u062E', '\uFEA7': '\u062E', '\uFEA8': '\u062E',  # KHAH
    '\uFEA9': '\u062F', '\uFEAA': '\u062F',  # DAL
    '\uFEAB': '\u0630', '\uFEAC': '\u0630',  # THAL
    '\uFEAD': '\u0631', '\uFEAE': '\u0631',  # REH
    '\uFEAF': '\u0632', '\uFEB0': '\u0632',  # ZAIN
    '\uFEB1': '\u0633', '\uFEB2': '\u0633', '\uFEB3': '\u0633', '\uFEB4': '\u0633',  # SEEN
    '\uFEB5': '\u0634', '\uFEB6': '\u0634', '\uFEB7': '\u0634', '\uFEB8': '\u0634',  # SHEEN
    '\uFEB9': '\u0635', '\uFEBA': '\u0635', '\uFEBB': '\u0635', '\uFEBC': '\u0635',  # SAD
    '\uFEBD': '\u0636', '\uFEBE': '\u0636', '\uFEBF': '\u0636', '\uFEC0': '\u0636',  # DAD
    '\uFEC1': '\u0637', '\uFEC2': '\u0637', '\uFEC3': '\u0637', '\uFEC4': '\u0637',  # TAH
    '\uFEC5': '\u0638', '\uFEC6': '\u0638', '\uFEC7': '\u0638', '\uFEC8': '\u0638',  # ZAH
    '\uFEC9': '\u0639', '\uFECA': '\u0639', '\uFECB': '\u0639', '\uFECC': '\u0639',  # AIN
    '\uFECD': '\u063A', '\uFECE': '\u063A', '\uFECF': '\u063A', '\uFED0': '\u063A',  # GHAIN
    '\uFED1': '\u0641', '\uFED2': '\u0641', '\uFED3': '\u0641', '\uFED4': '\u0641',  # FEH
    '\uFED5': '\u0642', '\uFED6': '\u0642', '\uFED7': '\u0642', '\uFED8': '\u0642',  # QAF
    '\uFED9': '\u0643', '\uFEDA': '\u0643', '\uFEDB': '\u0643', '\uFEDC': '\u0643',  # KAF
    '\uFEDD': '\u0644', '\uFEDE': '\u0644', '\uFEDF': '\u0644', '\uFEE0': '\u0644',  # LAM
    '\uFEE1': '\u0645', '\uFEE2': '\u0645', '\uFEE3': '\u0645', '\uFEE4': '\u0645',  # MEEM
    '\uFEE5': '\u0646', '\uFEE6': '\u0646', '\uFEE7': '\u0646', '\uFEE8': '\u0646',  # NOON
    '\uFEE9': '\u0647', '\uFEEA': '\u0647', '\uFEEB': '\u0647', '\uFEEC': '\u0647',  # HEH
    '\uFEED': '\u0648', '\uFEEE': '\u0648',  # WAW
    '\uFEEF': '\u0649', '\uFEF0': '\u0649',  # ALEF MAKSURA
    '\uFEF1': '\u064A', '\uFEF2': '\u064A', '\uFEF3': '\u064A', '\uFEF4': '\u064A',  # YEH
    # LAM-ALEF ligatures
    '\uFEF5': '\u0644\u0627', '\uFEF6': '\u0644\u0627',  # LAM ALEF MADDA
    '\uFEF7': '\u0644\u0627', '\uFEF8': '\u0644\u0627',  # LAM ALEF HAMZA ABOVE
    '\uFEF9': '\u0644\u0627', '\uFEFA': '\u0644\u0627',  # LAM ALEF HAMZA BELOW
    '\uFEFB': '\u0644\u0627', '\uFEFC': '\u0644\u0627',  # LAM ALEF
    # Hamza variants
    '\uFE80': '\u0621',  # HAMZA
    '\uFE81': '\u0622', '\uFE82': '\u0622',  # ALEF MADDA
    '\uFE83': '\u0623', '\uFE84': '\u0623',  # ALEF HAMZA ABOVE
    '\uFE85': '\u0624', '\uFE86': '\u0624',  # WAW HAMZA
    '\uFE87': '\u0625', '\uFE88': '\u0625',  # ALEF HAMZA BELOW
    '\uFE89': '\u0626', '\uFE8A': '\u0626', '\uFE8B': '\u0626', '\uFE8C': '\u0626',  # YEH HAMZA
    # Arabic-Indic digits (keep as-is or map to Western)
    '\u0660': '0', '\u0661': '1', '\u0662': '2', '\u0663': '3', '\u0664': '4',
    '\u0665': '5', '\u0666': '6', '\u0667': '7', '\u0668': '8', '\u0669': '9',
}

def normalize_arabic(text: str) -> str:
    """
    Convert Arabic Presentation Forms (U+FE70-U+FEFF, U+FB50-U+FDFF) to standard Arabic (U+0600-U+06FF).
    This fixes the disconnected letters issue from PDF extraction.
    """
    if not text:
        return text
    
    result = []
    for char in text:
        # Check presentation forms mapping first
        if char in ARABIC_PRESENTATION_FORMS:
            result.append(ARABIC_PRESENTATION_FORMS[char])
        else:
            # Use Unicode NFKC normalization for other forms
            normalized = unicodedata.normalize('NFKC', char)
            result.append(normalized)
    
    return ''.join(result)


# ---------- Download with retries ----------
def download_pdf(url: str, path: str, retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", ""):
                with open(path, "wb") as f:
                    f.write(r.content)
                print("Downloaded:", path)
                return True
            return False
        except Exception as e:
            print(f"⚠ Download error (attempt {attempt}/{retries}) for {url}: {e}")
            time.sleep(2)
    return False


# ---------- OCR preprocessing ----------
def preprocess_for_ocr(image_path: str) -> str:
    """
    Reads image_path (png), upscales, denoises, thresholds, sharpens, writes cleaned image.
    Returns cleaned image path.
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return image_path

    # Upscale 2x
    img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_LINEAR)

    # Denoise
    img = cv2.fastNlMeansDenoising(img, h=30)

    # Otsu threshold (binarize)
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Sharpen kernel
    kernel = np.array([[0, -1, 0],
                       [-1, 5, -1],
                       [0, -1, 0]])
    img = cv2.filter2D(img, -1, kernel)

    clean_path = image_path.replace(".png", "_clean.png")
    cv2.imwrite(clean_path, img)
    return clean_path


# ---------- OCR one page ----------
def ocr_page(pdf_path: str, page_number: int) -> str:
    """
    Convert page -> png (300 DPI), preprocess, run pytesseract, return text.
    """
    # pdftoppm with -singlefile creates "prefix.png" (not "prefix-1.png")
    temp_prefix = f"temp_page_{page_number}"
    temp_png = f"{temp_prefix}.png"
    
    try:
        result = subprocess.run(
            ["pdftoppm", pdf_path, temp_prefix, "-png", "-r", "300", "-f", str(page_number), "-l", str(page_number), "-singlefile"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
        )
        if result.returncode != 0:
            print(f"⚠ pdftoppm error: {result.stderr.decode()}")
    except subprocess.TimeoutExpired:
        print("⚠ pdftoppm timeout for", pdf_path)
        return ""
    except Exception as e:
        print(f"⚠ pdftoppm exception: {e}")
        return ""

    if not os.path.exists(temp_png):
        print(f"⚠ PNG not created: {temp_png}")
        return ""

    clean_png = preprocess_for_ocr(temp_png)
    try:
        img = Image.open(clean_png)
        text = pytesseract.image_to_string(img, lang="ara+fra+eng", config="--psm 6")
    except Exception as e:
        print("⚠ pytesseract error:", e)
        text = ""

    # cleanup
    try:
        os.remove(temp_png)
    except Exception:
        pass
    try:
        if clean_png != temp_png and os.path.exists(clean_png):
            os.remove(clean_png)
    except Exception:
        pass

    # Normalize Arabic text from OCR (OCR usually returns standard Arabic)
    return normalize_arabic(text)


# ---------- page has extractable chars? ----------
def page_has_chars(page) -> bool:
    # pdfplumber page has attribute .chars in page.objects or page.chars
    try:
        # prefer page.chars if available
        chars = getattr(page, "chars", None)
        if chars is None:
            objs = page.objects if hasattr(page, "objects") else {}
            chars = objs.get("char", [])
        return bool(chars)
    except Exception:
        return False


# ---------- detect arabic letter count ----------
def count_arabic_letters(s: str) -> int:
    """Count Arabic letters including presentation forms"""
    count = 0
    for c in s:
        # Standard Arabic range
        if "\u0600" <= c <= "\u06FF":
            count += 1
        # Arabic Presentation Forms-A
        elif "\uFB50" <= c <= "\uFDFF":
            count += 1
        # Arabic Presentation Forms-B
        elif "\uFE70" <= c <= "\uFEFF":
            count += 1
    return count


# ---------- extract text + tables from a pdf path ----------
def extract_text_from_pdf(pdf_path: str) -> dict:
    result = {"text": "", "tables": []}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for pg_num, page in enumerate(pdf.pages, start=1):
                raw = page.extract_text() or ""

                # If page has no char objects, force OCR (vector glyphs / no ToUnicode)
                has_chars = page_has_chars(page)

                arabic_count = count_arabic_letters(raw)

                # Heuristic: if no extractable text OR too few Arabic chars -> OCR
                if (not has_chars) or len(raw.strip()) < 5 or arabic_count < 3:
                    print(f" → Forcing OCR for page {pg_num} (has_chars={has_chars}, len={len(raw.strip())}, arabic_count={arabic_count})")
                    page_text = ocr_page(pdf_path, pg_num)
                else:
                    # Normalize Arabic presentation forms to standard Arabic
                    page_text = normalize_arabic(raw)

                result["text"] += page_text + "\n"

                # Attempt table extraction (pdfplumber works for many digital tables)
                try:
                    tables = page.extract_tables()
                    if tables:
                        # Normalize Arabic in tables too
                        normalized_tables = []
                        for table in tables:
                            normalized_table = []
                            for row in table:
                                normalized_row = [normalize_arabic(cell) if cell else cell for cell in row]
                                normalized_table.append(normalized_row)
                            normalized_tables.append(normalized_table)
                        result["tables"].extend(normalized_tables)
                except Exception:
                    pass

    except Exception as e:
        print("❌ Error opening PDF:", pdf_path, ":", e)
    return result


# ---------- save json ----------
def save_json(data: dict, pdf_name: str):
    out = os.path.join(OUTPUT_JSON_DIR, pdf_name.replace(".pdf", ".json"))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print("💾 Saved JSON:", out)


# ---------- main loop ----------
def main():
    for i in range(START, END + 1):
        base = f"{i:02d}{YEAR_SUFFIX}.pdf"
        case_variants = [f"circ{base}", f"Circ{base}", f"CIRC{base}"]
        found = False

        for fname in case_variants:
            url = BASE_URL + fname
            pdf_path = os.path.join(OUTPUT_PDF_DIR, fname)

            # resume-safe: if pdf exists, skip download and re-extract
            if os.path.exists(pdf_path):
                print("⏩ Already downloaded:", fname)
                data = extract_text_from_pdf(pdf_path)
                save_json(data, fname)
                found = True
                break

            if download_pdf(url, pdf_path):
                print("✔ Downloaded:", fname)
                data = extract_text_from_pdf(pdf_path)
                save_json(data, fname)
                found = True
                break

            time.sleep(VARIANT_SLEEP)

        if not found:
            print(f"✘ No file found for index {i:02d}")

        time.sleep(DOWNLOAD_SLEEP)

    print("✅ Completed scanning.")


if __name__ == "__main__":
    main()
