#!/usr/bin/env python3
"""
Circulaire Service - Downloads, extracts, and parses PCT circulaires
Single entry point for processing circulaire PDFs into structured medication data.

Usage:
    # Process a single file by index
    result = process_circulaire(index=21, year="25")
    
    # Process a file by URL or path
    result = process_circulaire(pdf_url="http://...")
    result = process_circulaire(pdf_path="/path/to/file.pdf")
    
    # Batch process a range
    results = process_circulaire_range(start=1, end=47, year="25")

Returns:
    {
        "success": bool,
        "filename": str,
        "parsed": {...},      # Full parsed circulaire data
        "simplified": [...],  # Simplified format grouped by laboratory
        "error": str | None
    }
"""

import os
import json
import time
import re
import unicodedata
import tempfile
from typing import Optional, Dict, List, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime

# Optional imports - graceful degradation
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pytesseract
    from PIL import Image
    import cv2
    import numpy as np
    import subprocess
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = "http://www.phct.com.tn/images/DocumentsPCT/Circulaires/"
DEFAULT_YEAR = "25"

# Price tier markup ratios (pharmacy_price -> sale_price)
# Derived from analysis of actual circulaire data
PRICE_MARKUP_TIERS = [
    (25, 1.316),   # ph >= 25: 31.6% markup
    (8, 1.351),    # ph >= 8:  35.1% markup
    (3, 1.389),    # ph >= 3:  38.9% markup
    (0, 1.429),    # ph < 3:   42.9% markup
]


# ============================================================================
# ARABIC TEXT NORMALIZATION
# ============================================================================

ARABIC_PRESENTATION_FORMS = {
    '\uFE8D': '\u0627', '\uFE8E': '\u0627',
    '\uFE8F': '\u0628', '\uFE90': '\u0628', '\uFE91': '\u0628', '\uFE92': '\u0628',
    '\uFE93': '\u0629', '\uFE94': '\u0629',
    '\uFE95': '\u062A', '\uFE96': '\u062A', '\uFE97': '\u062A', '\uFE98': '\u062A',
    '\uFE99': '\u062B', '\uFE9A': '\u062B', '\uFE9B': '\u062B', '\uFE9C': '\u062B',
    '\uFE9D': '\u062C', '\uFE9E': '\u062C', '\uFE9F': '\u062C', '\uFEA0': '\u062C',
    '\uFEA1': '\u062D', '\uFEA2': '\u062D', '\uFEA3': '\u062D', '\uFEA4': '\u062D',
    '\uFEA5': '\u062E', '\uFEA6': '\u062E', '\uFEA7': '\u062E', '\uFEA8': '\u062E',
    '\uFEA9': '\u062F', '\uFEAA': '\u062F',
    '\uFEAB': '\u0630', '\uFEAC': '\u0630',
    '\uFEAD': '\u0631', '\uFEAE': '\u0631',
    '\uFEAF': '\u0632', '\uFEB0': '\u0632',
    '\uFEB1': '\u0633', '\uFEB2': '\u0633', '\uFEB3': '\u0633', '\uFEB4': '\u0633',
    '\uFEB5': '\u0634', '\uFEB6': '\u0634', '\uFEB7': '\u0634', '\uFEB8': '\u0634',
    '\uFEB9': '\u0635', '\uFEBA': '\u0635', '\uFEBB': '\u0635', '\uFEBC': '\u0635',
    '\uFEBD': '\u0636', '\uFEBE': '\u0636', '\uFEBF': '\u0636', '\uFEC0': '\u0636',
    '\uFEC1': '\u0637', '\uFEC2': '\u0637', '\uFEC3': '\u0637', '\uFEC4': '\u0637',
    '\uFEC5': '\u0638', '\uFEC6': '\u0638', '\uFEC7': '\u0638', '\uFEC8': '\u0638',
    '\uFEC9': '\u0639', '\uFECA': '\u0639', '\uFECB': '\u0639', '\uFECC': '\u0639',
    '\uFECD': '\u063A', '\uFECE': '\u063A', '\uFECF': '\u063A', '\uFED0': '\u063A',
    '\uFED1': '\u0641', '\uFED2': '\u0641', '\uFED3': '\u0641', '\uFED4': '\u0641',
    '\uFED5': '\u0642', '\uFED6': '\u0642', '\uFED7': '\u0642', '\uFED8': '\u0642',
    '\uFED9': '\u0643', '\uFEDA': '\u0643', '\uFEDB': '\u0643', '\uFEDC': '\u0643',
    '\uFEDD': '\u0644', '\uFEDE': '\u0644', '\uFEDF': '\u0644', '\uFEE0': '\u0644',
    '\uFEE1': '\u0645', '\uFEE2': '\u0645', '\uFEE3': '\u0645', '\uFEE4': '\u0645',
    '\uFEE5': '\u0646', '\uFEE6': '\u0646', '\uFEE7': '\u0646', '\uFEE8': '\u0646',
    '\uFEE9': '\u0647', '\uFEEA': '\u0647', '\uFEEB': '\u0647', '\uFEEC': '\u0647',
    '\uFEED': '\u0648', '\uFEEE': '\u0648',
    '\uFEEF': '\u0649', '\uFEF0': '\u0649',
    '\uFEF1': '\u064A', '\uFEF2': '\u064A', '\uFEF3': '\u064A', '\uFEF4': '\u064A',
    '\uFEF5': '\u0644\u0627', '\uFEF6': '\u0644\u0627',
    '\uFEF7': '\u0644\u0627', '\uFEF8': '\u0644\u0627',
    '\uFEF9': '\u0644\u0627', '\uFEFA': '\u0644\u0627',
    '\uFEFB': '\u0644\u0627', '\uFEFC': '\u0644\u0627',
    '\uFE80': '\u0621',
    '\uFE81': '\u0622', '\uFE82': '\u0622',
    '\uFE83': '\u0623', '\uFE84': '\u0623',
    '\uFE85': '\u0624', '\uFE86': '\u0624',
    '\uFE87': '\u0625', '\uFE88': '\u0625',
    '\uFE89': '\u0626', '\uFE8A': '\u0626', '\uFE8B': '\u0626', '\uFE8C': '\u0626',
    '\u0660': '0', '\u0661': '1', '\u0662': '2', '\u0663': '3', '\u0664': '4',
    '\u0665': '5', '\u0666': '6', '\u0667': '7', '\u0668': '8', '\u0669': '9',
}


def normalize_arabic(text: str) -> str:
    """Convert Arabic Presentation Forms to standard Arabic."""
    if not text:
        return text
    result = []
    for char in text:
        if char in ARABIC_PRESENTATION_FORMS:
            result.append(ARABIC_PRESENTATION_FORMS[char])
        else:
            result.append(unicodedata.normalize('NFKC', char))
    return ''.join(result)


# ============================================================================
# CATEGORY PATTERNS
# ============================================================================

CATEGORY_PATTERNS = {
    "new_local_human": [
        r"إختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"اختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"1[-.]?\s*إختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"1[-.]?\s*اختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"ةيلحم\s*ةيرشب\s*تاصاصتخا(?!.*راعسأ\s*ةعجارم)",
        r"ةيلحم\s*ةيرشب\s*تاصاصتخإ(?!.*راعسأ\s*ةعجارم)",
        r"[-]?اختصاصات\s*بشري[هة]\s*محلي[هة](?!\s*\(مراجعة)",
    ],
    "new_imported_human": [
        r"إختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"اختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"1[-.]?\s*إختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"1[-.]?\s*اختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"ةدروتسم\s*ةيرشب\s*تاصاصتخا(?!.*راعسأ\s*ةعجارم)",
        r"ةدروتسم\s*ةيرشب\s*تاصاصتخإ(?!.*راعسأ\s*ةعجارم)",
        r"[-]?اختصاصات\s*بشري[هة]\s*مستورد[هة](?!\s*\(مراجعة)",
    ],
    "new_veterinary": [
        r"إختصاصات\s*بيطرية\s*مستوردة(?!\s*\(مراجعة)",
        r"اختصاصات\s*بيطرية\s*مستوردة(?!\s*\(مراجعة)",
        r"إختصاصات\s*بيطرية\s*محلية(?!\s*\(مراجعة)",
        r"اختصاصات\s*بيطرية\s*محلية(?!\s*\(مراجعة)",
        r"ةدروتسم\s*ةيرطيب\s*تاصاصتخ[اإ]",
        r"ةيلحم\s*ةيرطيب\s*تاصاصتخ[اإ]",
        r"[-]?اختصاصات\s*بيطري[هة]",
    ],
    "revised_local_human": [
        r"إختصاصات\s*بشرية\s*محلية\s*\(مراجعة\s*أسعار\)",
        r"اختصاصات\s*بشرية\s*محلية\s*\(مراجعة\s*أسعار\)",
        r"1[-.]?\s*إختصاصات\s*بشرية\s*محلية\s*\(مراجعة",
        r"1[-.]?\s*اختصاصات\s*بشرية\s*محلية\s*\(مراجعة",
        r"\)راعسأ\s*ةعجارم\(\s*ةيلحم\s*ةيرشب\s*تاصاصتخ[اإ]",
        r"راعسأ\s*ةعجارم.*ةيلحم\s*ةيرشب\s*تاصاصتخ[اإ]",
        r"[-]?اختصاصات\s*بشري[هة]\s*محلي[هة]\s*\(مراجعة",
    ],
    "revised_imported_human": [
        r"إختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة\s*أسعار\)",
        r"اختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة\s*أسعار\)",
        r"2[-.]?\s*إختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة",
        r"2[-.]?\s*اختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة",
        r"\)راعسأ\s*ةعجارم\(\s*ةدروتسم\s*ةيرشب\s*تاصاصتخ[اإ]",
        r"راعسأ\s*ةعجارم.*ةدروتسم\s*ةيرشب\s*تاصاصتخ[اإ]",
        r"[-]?اختصاصات\s*بشري[هة]\s*مستورد[هة]\s*\(مراجعة",
    ],
    "revised_veterinary": [
        r"إختصاصات\s*بيطرية.*\(مراجعة\s*أسعار\)",
        r"اختصاصات\s*بيطرية.*\(مراجعة\s*أسعار\)",
        r"\)راعسأ\s*ةعجارم\(.*ةيرطيب\s*تاصاصتخ[اإ]",
        r"راعسأ\s*ةعجارم.*ةيلحم\s*ةيرطيب\s*تاصاصتخ[اإ]",
        r"راعسأ\s*ةعجارم.*ةدروتسم\s*ةيرطيب\s*تاصاصتخ[اإ]",
    ],
}

SECTION_BREAK_PATTERNS = [
    r"إعلام",
    r"قرار\s*سحب",
    r"ARRET\s*DE\s*COMMERCIALISATION",
    r"CHANGEMENT\s*DE\s*DENOMINATION",
    r"AVIS\s*DE\s*DISPONIBILITE",
    r"CHANGEMENT\s*DU\s*TABLEAU",
    r"retrait\s*du\s*commerce",
    r"Lot\s*à\s*retirer",
]

# Medication line patterns
MEDICATION_PATTERN = re.compile(
    r'(\d{6})\s+(.+?)\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s*([A-C\-])?\s*(\d[,\.]\d{3})?'
)

MEDICATION_PATTERN_ALT = re.compile(
    r'(\d{6})\s+(.+?)\s+(\d+[,\.]\d+)\s+(\d+[,\.]\d+)\s+(\d+[,\.]\d+)'
)

DATE_PATTERN = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4})')
CIRC_NUMBER_PATTERN = re.compile(r'(?:رقم|:)\s*(\d{4})/(\d{1,2})')


# ============================================================================
# PDF EXTRACTION
# ============================================================================

class PDFExtractor:
    """Handles PDF downloading and text extraction."""
    
    @staticmethod
    def download(url: str, dest_path: str = None, timeout: int = 30) -> Optional[str]:
        """Download PDF from URL. Returns path to downloaded file."""
        if not HAS_REQUESTS:
            raise ImportError("requests library required for downloading")
        
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
                if dest_path is None:
                    fd, dest_path = tempfile.mkstemp(suffix=".pdf")
                    os.close(fd)
                with open(dest_path, "wb") as f:
                    f.write(r.content)
                return dest_path
        except Exception as e:
            print(f"Download error: {e}")
        return None
    
    @staticmethod
    def _preprocess_for_ocr(image_path: str) -> str:
        """Preprocess image for better OCR results."""
        if not HAS_OCR:
            return image_path
        
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return image_path
        
        img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_LINEAR)
        img = cv2.fastNlMeansDenoising(img, h=30)
        _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        img = cv2.filter2D(img, -1, kernel)
        
        clean_path = image_path.replace(".png", "_clean.png")
        cv2.imwrite(clean_path, img)
        return clean_path
    
    @staticmethod
    def _ocr_page(pdf_path: str, page_number: int) -> str:
        """OCR a single page of a PDF."""
        if not HAS_OCR:
            return ""
        
        temp_prefix = f"temp_page_{page_number}_{os.getpid()}"
        temp_png = f"{temp_prefix}.png"
        
        try:
            result = subprocess.run(
                ["pdftoppm", pdf_path, temp_prefix, "-png", "-r", "300", 
                 "-f", str(page_number), "-l", str(page_number), "-singlefile"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
            )
            if result.returncode != 0:
                return ""
        except Exception:
            return ""
        
        if not os.path.exists(temp_png):
            return ""
        
        clean_png = PDFExtractor._preprocess_for_ocr(temp_png)
        text = ""
        try:
            img = Image.open(clean_png)
            text = pytesseract.image_to_string(img, lang="ara+fra+eng", config="--psm 6")
        except Exception:
            pass
        
        # Cleanup
        for f in [temp_png, clean_png]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        
        return normalize_arabic(text)
    
    @staticmethod
    def _page_has_chars(page) -> bool:
        """Check if a pdfplumber page has extractable characters."""
        try:
            chars = getattr(page, "chars", None)
            if chars is None:
                objs = page.objects if hasattr(page, "objects") else {}
                chars = objs.get("char", [])
            return bool(chars)
        except Exception:
            return False
    
    @staticmethod
    def _count_arabic_letters(s: str) -> int:
        """Count Arabic letters including presentation forms."""
        count = 0
        for c in s:
            if "\u0600" <= c <= "\u06FF" or "\uFB50" <= c <= "\uFDFF" or "\uFE70" <= c <= "\uFEFF":
                count += 1
        return count
    
    @staticmethod
    def extract_text(pdf_path: str) -> str:
        """Extract text from PDF, using OCR when necessary."""
        if not HAS_PDFPLUMBER:
            raise ImportError("pdfplumber library required for PDF extraction")
        
        full_text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for pg_num, page in enumerate(pdf.pages, start=1):
                    raw = page.extract_text() or ""
                    has_chars = PDFExtractor._page_has_chars(page)
                    arabic_count = PDFExtractor._count_arabic_letters(raw)
                    
                    if (not has_chars) or len(raw.strip()) < 5 or arabic_count < 3:
                        page_text = PDFExtractor._ocr_page(pdf_path, pg_num)
                    else:
                        page_text = normalize_arabic(raw)
                    
                    full_text += page_text + "\n"
        except Exception as e:
            print(f"Error extracting PDF: {e}")
        
        return full_text


# ============================================================================
# PARSER
# ============================================================================

class CirculaireParser:
    """Parses extracted text into structured medication data."""
    
    @staticmethod
    def _extract_date(text: str) -> Optional[str]:
        """Extract date from text, return as YYYY-MM-DD."""
        match = re.search(r'(?:تونس\s*في|في\s*:?)\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{4})', text)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        match = DATE_PATTERN.search(text)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return None
    
    @staticmethod
    def _extract_circulaire_number(text: str) -> Optional[str]:
        """Extract circulaire number like 2025/01."""
        match = CIRC_NUMBER_PATTERN.search(text)
        if match:
            year, num = match.groups()
            return f"{year}/{num.zfill(2)}"
        return None
    
    @staticmethod
    def _find_category_sections(text: str) -> list:
        """Find all medication category sections in the text."""
        sections = []
        for category, patterns in CATEGORY_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    section_type = "new" if "new" in category else "revised"
                    specialty = "veterinary" if "veterinary" in category else "human"
                    origin = "local" if "local" in category else "imported"
                    sections.append({
                        "start": match.start(),
                        "end": match.end(),
                        "type": section_type,
                        "specialty": specialty,
                        "origin": origin,
                        "category": category,
                    })
        
        sections.sort(key=lambda x: x["start"])
        filtered = []
        for s in sections:
            if not filtered or s["start"] >= filtered[-1]["end"]:
                filtered.append(s)
        return filtered
    
    @staticmethod
    def _find_section_breaks(text: str) -> list:
        """Find positions where medication sections end."""
        breaks = []
        for pattern in SECTION_BREAK_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                breaks.append(match.start())
        return sorted(breaks)
    
    @staticmethod
    def _clean_medication_name(name: str) -> str:
        """Clean up medication name from OCR artifacts."""
        if not name:
            return name
        name = re.sub(r'^[\[\]]+|[\[\]]+$', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name
    
    @staticmethod
    def _is_laboratory_line(line: str) -> bool:
        """Check if a line is likely a laboratory name."""
        line = line.replace('\u200e', '').replace('\u200f', '').strip()
        if not line or len(line) < 4:
            return False
        
        digit_count = sum(1 for c in line if c.isdigit())
        if digit_count > 3:
            return False
        
        arabic_count = sum(1 for c in line if '\u0600' <= c <= '\u06FF')
        if arabic_count > len(line) * 0.3:
            return False
        
        skip_patterns = [
            r'^(Bt|BT|Fl|FL|Sol|SOL|Comp|COMP|Gel|GEL|Ser|SER|Pde|mg|ml|μg|µg)\b',
            r'^\d', r'^[\|\-\.\s]+$', r'(mois|Vie|AMM|EXP)',
        ]
        for pattern in skip_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                return False
        
        if not re.search(r'[A-Za-z]', line):
            return False
        
        if re.search(r'(PHARMA|PHARM|LAB|S\.?A\.?\.?|LLC|GMBH|LTD|INC|SANTE|HEALTH|SCIENCES?|INDUSTRIES?)\b', line, re.IGNORECASE):
            return True
        
        alpha_chars = re.sub(r'[^A-Za-z]', '', line)
        if alpha_chars.upper() == alpha_chars and 3 <= len(alpha_chars) <= 60:
            if not re.search(r'\d+\s*(mg|ml|μg|µg|%)', line, re.IGNORECASE):
                return True
        
        return False
    
    @staticmethod
    def _calculate_sale_price(pharmacy_price: float) -> float:
        """Calculate sale price from pharmacy price using tier-based markup."""
        for threshold, ratio in PRICE_MARKUP_TIERS:
            if pharmacy_price >= threshold:
                return round(pharmacy_price * ratio, 3)
        return round(pharmacy_price * PRICE_MARKUP_TIERS[-1][1], 3)
    
    @staticmethod
    def _parse_medication_line(line: str, current_lab: str = None) -> Optional[dict]:
        """Parse a single medication line."""
        line = line.strip()
        if not line:
            return None
        
        line = line.replace('\u200e', '').replace('\u200f', '').replace('|', ' ')
        line = re.sub(r'\s+', ' ', line).strip()
        
        # Pattern 1: Code at start (digital PDFs)
        match = MEDICATION_PATTERN.search(line)
        if match:
            code, name, price1, price2, price3, cat, margin = match.groups()
            return {
                "code": code,
                "name": CirculaireParser._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": cat if cat and cat != '-' else None,
                "margin": float(margin.replace(',', '.')) if margin else None,
            }
        
        # Pattern 2: Code at end with 3 prices and category/margin
        pattern_code_end = re.compile(
            r'^(.+?)\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})[\]\s]*'
            r'([A-C])[_\s]*[\{\[]?[01]?(\d[,\.]\d{3})[\}\]]?\s*(\d{6})\s*$'
        )
        match = pattern_code_end.search(line)
        if match:
            name, price1, price2, price3, cat, margin, code = match.groups()
            return {
                "code": code,
                "name": CirculaireParser._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": cat if cat and cat != '-' else None,
                "margin": float(margin.replace(',', '.')) if margin else None,
            }
        
        # Pattern 2b: Code at end with 3 prices, category is "-"
        pattern_code_end_dash = re.compile(
            r'^(.+?)\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})[\]\s]*-\s*(\d{6})\s*$'
        )
        match = pattern_code_end_dash.search(line)
        if match:
            name, price1, price2, price3, code = match.groups()
            return {
                "code": code,
                "name": CirculaireParser._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": None,
                "margin": None,
            }
        
        # Pattern 2c: Code at end with 3 prices, no category/margin
        pattern_code_end_simple = re.compile(
            r'^(.+?)\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})[\]\s]+(\d{6})\s*$'
        )
        match = pattern_code_end_simple.search(line)
        if match:
            name, price1, price2, price3, code = match.groups()
            return {
                "code": code,
                "name": CirculaireParser._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": None,
                "margin": None,
            }
        
        # Pattern 3: Alternative simpler pattern for code at start
        match = MEDICATION_PATTERN_ALT.search(line)
        if match:
            code, name, price1, price2, price3 = match.groups()
            cat_match = re.search(r'\s([A-C])\s', line[match.end():] if match.end() < len(line) else '')
            margin_match = re.search(r'(\d[,\.]\d{3})\s*$', line)
            return {
                "code": code,
                "name": CirculaireParser._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": cat_match.group(1) if cat_match else None,
                "margin": float(margin_match.group(1).replace(',', '.')) if margin_match else None,
            }
        
        # Pattern 4: Code at end, simpler (2 prices captured)
        pattern_simple_end = re.compile(r'^([A-Z].+?)\s+(\d+[,\.]\d+)\s+(\d+[,\.]\d+)\s+.*?(\d{6})\s*$')
        match = pattern_simple_end.search(line)
        if match:
            name, price1, price2, code = match.groups()
            return {
                "code": code,
                "name": CirculaireParser._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": None,
                "category": None,
                "margin": None,
            }
        
        # Pattern 5: Code at end with 2 prices
        pattern_2prices_end = re.compile(
            r'^([A-Z].+?)\s+(\d+[,\.]\d+)\s+(\d+[,\.]\d+)\s+([A-C\-])?\s*(\d[,\.]\d{3})?\s*(\d{6})\s*$'
        )
        match = pattern_2prices_end.search(line)
        if match:
            name, price1, price2, cat, margin, code = match.groups()
            return {
                "code": code,
                "name": CirculaireParser._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": None,
                "category": cat if cat and cat != '-' else None,
                "margin": float(margin.replace(',', '.')) if margin else None,
            }
        
        # Pattern 6: NO CODE - 3 prices with category/margin
        clean_line = line.replace(']', '').replace('[', '')
        pattern_no_code = re.compile(
            r'^([A-Z][A-Za-z0-9\s\.\-\(\)/\+µ]+?)\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s+'
            r'(\d{1,3}[,\.]\d{3})\s+([A-C])\s+(\d[,\.]\d{3})\s*$'
        )
        match = pattern_no_code.search(clean_line)
        if match:
            name, price1, price2, price3, cat, margin = match.groups()
            if re.search(r'\d+\s*(mg|ml|μg|µg|%|Comp|Bt|Fl|Sol|Gel)', name, re.IGNORECASE):
                return {
                    "code": None,
                    "name": CirculaireParser._clean_medication_name(name),
                    "laboratory": current_lab,
                    "price_wholesale": float(price1.replace(',', '.')),
                    "price_pharmacy": float(price2.replace(',', '.')),
                    "price_public": float(price3.replace(',', '.')),
                    "category": cat,
                    "margin": float(margin.replace(',', '.')) if margin else None,
                }
        
        # Pattern 7: NO CODE - 2 prices with category/margin
        pattern_2_prices_no_code = re.compile(
            r'^([A-Z][A-Za-z0-9\s\.\-\(\)/\+µ]+?)\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s+'
            r'([A-C])\s+(\d[,\.]\d{3})\s*$'
        )
        match = pattern_2_prices_no_code.search(clean_line)
        if match:
            name, price1, price2, cat, margin = match.groups()
            if re.search(r'\d+\s*(mg|ml|μg|µg|%|Comp|Bt|Fl|Sol|Gel)', name, re.IGNORECASE):
                return {
                    "code": None,
                    "name": CirculaireParser._clean_medication_name(name),
                    "laboratory": current_lab,
                    "price_wholesale": float(price1.replace(',', '.')),
                    "price_pharmacy": float(price2.replace(',', '.')),
                    "price_public": None,
                    "category": cat,
                    "margin": float(margin.replace(',', '.')) if margin else None,
                }
        
        return None
    
    @staticmethod
    def _parse_medications_from_section(text: str, section_info: dict) -> list:
        """Parse all medications from a section of text."""
        medications = []
        current_lab = None
        pending_lab_lines = []
        
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            clean_line = line.replace('\u200e', '').replace('\u200f', '').strip()
            
            if CirculaireParser._is_laboratory_line(clean_line):
                if pending_lab_lines and (
                    pending_lab_lines[-1].rstrip().endswith('AND') or
                    pending_lab_lines[-1].rstrip().endswith('&') or
                    (clean_line.isupper() and len(clean_line.split()) <= 3)
                ):
                    pending_lab_lines.append(clean_line)
                else:
                    if pending_lab_lines:
                        current_lab = ' '.join(pending_lab_lines)
                    pending_lab_lines = [clean_line]
                continue
            
            if pending_lab_lines:
                current_lab = ' '.join(pending_lab_lines)
                pending_lab_lines = []
            
            med = CirculaireParser._parse_medication_line(line, current_lab)
            if med:
                med["type"] = section_info.get("type", "new")
                med["specialty"] = section_info.get("specialty", "human")
                med["origin"] = section_info.get("origin", "local")
                
                # Calculate missing sale price
                if med.get("price_public") is None and med.get("price_pharmacy"):
                    med["price_public"] = CirculaireParser._calculate_sale_price(med["price_pharmacy"])
                    med["price_public_calculated"] = True
                
                medications.append(med)
        
        return medications
    
    @staticmethod
    def parse(text: str, filename: str = None) -> dict:
        """Parse circulaire text into structured data."""
        result = {
            "filename": filename,
            "date": CirculaireParser._extract_date(text),
            "circulaire_number": CirculaireParser._extract_circulaire_number(text),
            "medications": [],
            "sections_found": [],
        }
        
        sections = CirculaireParser._find_category_sections(text)
        section_breaks = CirculaireParser._find_section_breaks(text)
        
        for i, section in enumerate(sections):
            # ONLY process human medication sections - skip veterinary
            if section.get("specialty") == "veterinary":
                continue
            
            section_end = len(text)
            if i + 1 < len(sections):
                section_end = min(section_end, sections[i + 1]["start"])
            for brk in section_breaks:
                if brk > section["end"] and brk < section_end:
                    section_end = brk
                    break
            
            section_text = text[section["end"]:section_end]
            meds = CirculaireParser._parse_medications_from_section(section_text, section)
            
            result["sections_found"].append({
                "type": section["type"],
                "specialty": section["specialty"],
                "origin": section["origin"],
                "medications_count": len(meds),
            })
            result["medications"].extend(meds)
        
        return result


# ============================================================================
# SERVICE API
# ============================================================================

@dataclass
class CirculaireResult:
    """Result of processing a single circulaire."""
    success: bool
    filename: str
    parsed: Optional[dict] = None
    simplified: Optional[list] = None
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


def _create_simplified(parsed: dict) -> list:
    """Create simplified format grouped by laboratory."""
    if not parsed or not parsed.get('medications'):
        return []
    
    simplified = []
    meds_by_lab = {}
    
    for med in parsed['medications']:
        lab = (med.get('laboratory') or 'Unknown').replace('\u200e', '').replace('\u200f', '').strip()
        if lab not in meds_by_lab:
            meds_by_lab[lab] = []
        meds_by_lab[lab].append({
            'code': med['code'],
            'name': med['name'],
            'price_public': med['price_public'],
            'price_pharmacy': med['price_pharmacy'],
            'price_wholesale': med['price_wholesale'],
            'category': med['category'],
            'type': med['type'],
        })
    
    for lab, meds in meds_by_lab.items():
        types = set(m['type'] for m in meds)
        entry_type = 'revised' if 'revised' in types else 'new'
        
        simplified.append({
            'date': parsed['date'],
            'circulaire': parsed['circulaire_number'] or (parsed['filename'].replace('.json', '').replace('.pdf', '') if parsed['filename'] else None),
            'laboratory': lab,
            'type': entry_type,
            'medications': [{
                'code': m['code'],
                'name': m['name'],
                'sale_price': m['price_public'],
                'pharmacy_price': m['price_pharmacy'],
                'wholesale_price': m['price_wholesale'],
                'category': m['category'],
            } for m in meds]
        })
    
    return simplified


def process_circulaire(
    index: int = None,
    year: str = DEFAULT_YEAR,
    pdf_url: str = None,
    pdf_path: str = None,
    pdf_content: bytes = None,
    base_url: str = None,
) -> CirculaireResult:
    """
    Process a single circulaire and return structured data.
    
    Args:
        index: Circulaire index number (e.g., 21 for circ2125.pdf)
        year: Year suffix (default "25" for 2025)
        pdf_url: Direct URL to PDF
        pdf_path: Local path to PDF file
        pdf_content: Raw PDF bytes
        base_url: Custom base URL (defaults to phct.com.tn)
    
    Returns:
        CirculaireResult with parsed data and simplified format
    """
    filename = None
    temp_file = None
    
    try:
        # Determine source and get PDF path
        if pdf_path and os.path.exists(pdf_path):
            filename = os.path.basename(pdf_path)
        elif pdf_url:
            filename = pdf_url.split('/')[-1]
            pdf_path = PDFExtractor.download(pdf_url)
            if not pdf_path:
                return CirculaireResult(success=False, filename=filename, error="Failed to download PDF")
            temp_file = pdf_path
        elif pdf_content:
            fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
            os.write(fd, pdf_content)
            os.close(fd)
            temp_file = pdf_path
            filename = f"circulaire_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        elif index is not None:
            # Try different case variants
            effective_base_url = base_url or BASE_URL
            base = f"{index:02d}{year}.pdf"
            for prefix in ["circ", "Circ", "CIRC"]:
                fname = f"{prefix}{base}"
                url = effective_base_url + fname
                pdf_path = PDFExtractor.download(url)
                if pdf_path:
                    filename = fname
                    temp_file = pdf_path
                    break
            if not pdf_path:
                return CirculaireResult(success=False, filename=f"circ{base}", error="File not found on server")
        else:
            return CirculaireResult(success=False, filename="", error="No source provided")
        
        # Extract text
        text = PDFExtractor.extract_text(pdf_path)
        if not text or len(text.strip()) < 50:
            return CirculaireResult(success=False, filename=filename, error="Failed to extract text from PDF")
        
        # Parse
        parsed = CirculaireParser.parse(text, filename)
        simplified = _create_simplified(parsed)
        
        return CirculaireResult(
            success=True,
            filename=filename,
            parsed=parsed,
            simplified=simplified,
        )
    
    except Exception as e:
        return CirculaireResult(success=False, filename=filename or "", error=str(e))
    
    finally:
        # Cleanup temp file
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


def process_circulaire_range(
    start: int = 1,
    end: int = 99,
    year: str = DEFAULT_YEAR,
    years: List[str] = None,
    delay: float = 1.0,
    base_url: str = None,
    max_consecutive_failures: int = 0,
) -> Dict[str, Any]:
    """
    Process a range of circulaires.
    
    Args:
        start: Starting index
        end: Ending index (inclusive)
        year: Year suffix (ignored if years is provided)
        years: List of year suffixes to process (e.g., ["24", "25", "26"])
        delay: Delay between requests in seconds
        base_url: Custom base URL (defaults to phct.com.tn)
        max_consecutive_failures: Stop after N consecutive failures (0 = never stop)
    
    Returns:
        {
            "results": [CirculaireResult, ...],
            "all_parsed": [...],
            "all_simplified": [...],
            "summary": {
                "total": int,
                "successful": int,
                "failed": int,
                "total_medications": int,
            }
        }
    """
    results = []
    all_parsed = []
    all_simplified = []
    
    # Support year range
    year_list = years if years else [year]
    
    for yr in year_list:
        consecutive_failures = 0
        
        for i in range(start, end + 1):
            result = process_circulaire(index=i, year=yr, base_url=base_url)
            results.append(result)
            
            if result.success and result.parsed:
                all_parsed.append(result.parsed)
                if result.simplified:
                    all_simplified.extend(result.simplified)
                consecutive_failures = 0  # Reset on success
            else:
                consecutive_failures += 1
                
                # Stop if too many consecutive failures
                if max_consecutive_failures > 0 and consecutive_failures >= max_consecutive_failures:
                    break
            
            if delay > 0 and i < end:
                time.sleep(delay)
    
    total_meds = sum(len(r.parsed.get('medications', [])) for r in results if r.parsed)
    
    return {
        "results": [r.to_dict() for r in results],
        "all_parsed": all_parsed,
        "all_simplified": all_simplified,
        "summary": {
            "total": len(results),
            "successful": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "total_medications": total_meds,
        }
    }


def check_for_new_circulaires(
    known_indices: List[int],
    year: str = DEFAULT_YEAR,
    years: List[str] = None,
    max_index: int = 99,
    base_url: str = None,
    max_consecutive_failures: int = 20,
    delay: float = 0.2,
) -> Union[List[int], Dict[str, List[int]]]:
    """
    Check for new circulaires that aren't in the known list.
    
    Args:
        known_indices: List of already processed circulaire indices
        year: Year suffix (ignored if years is provided)
        years: List of year suffixes to check (e.g., ["24", "25"])
        max_index: Maximum index to check
        base_url: Custom base URL (defaults to phct.com.tn)
        max_consecutive_failures: Stop checking after N consecutive 404s (default 20)
        delay: Delay between HEAD requests in seconds
    
    Returns:
        List[int] if single year, or Dict[year, List[int]] if multiple years
    """
    effective_base_url = base_url or BASE_URL
    year_list = years if years else [year]
    known_set = set(known_indices)
    
    results_by_year = {}
    
    for yr in year_list:
        new_indices = []
        consecutive_failures = 0
        
        for i in range(1, max_index + 1):
            if i in known_set:
                consecutive_failures = 0  # Known file counts as "exists"
                continue
            
            # Quick check if file exists
            found = False
            base = f"{i:02d}{yr}.pdf"
            for prefix in ["circ", "Circ", "CIRC"]:
                url = effective_base_url + f"{prefix}{base}"
                try:
                    r = requests.head(url, timeout=5)
                    if r.status_code == 200:
                        new_indices.append(i)
                        found = True
                        consecutive_failures = 0
                        break
                except Exception:
                    pass
            
            if not found:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    break  # Stop checking this year
            
            if delay > 0:
                time.sleep(delay)
        
        results_by_year[yr] = new_indices
    
    # Return simple list if single year, dict if multiple
    if len(year_list) == 1:
        return results_by_year[year_list[0]]
    return results_by_year


# ============================================================================
# CLI
# ============================================================================

def main():
    """Command-line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Process PCT Circulaires")
    parser.add_argument("--index", "-i", type=int, help="Process single circulaire by index")
    parser.add_argument("--range", "-r", nargs=2, type=int, metavar=("START", "END"), help="Process range of circulaires")
    parser.add_argument("--year", "-y", default=DEFAULT_YEAR, help=f"Year suffix (default: {DEFAULT_YEAR})")
    parser.add_argument("--url", "-u", help="Process from URL")
    parser.add_argument("--file", "-f", help="Process local PDF file")
    parser.add_argument("--output", "-o", help="Output directory for JSON files")
    parser.add_argument("--check-new", action="store_true", help="Check for new circulaires")
    parser.add_argument("--known", nargs="*", type=int, default=[], help="Known circulaire indices (for --check-new)")
    
    args = parser.parse_args()
    
    if args.check_new:
        new = check_for_new_circulaires(args.known, args.year)
        if new:
            print(f"New circulaires found: {new}")
        else:
            print("No new circulaires found")
        return
    
    if args.index:
        result = process_circulaire(index=args.index, year=args.year)
    elif args.range:
        batch = process_circulaire_range(start=args.range[0], end=args.range[1], year=args.year)
        print(f"Summary: {batch['summary']}")
        if args.output:
            os.makedirs(args.output, exist_ok=True)
            with open(os.path.join(args.output, "_all_circulaires.json"), "w", encoding="utf-8") as f:
                json.dump(batch["all_parsed"], f, ensure_ascii=False, indent=2)
            with open(os.path.join(args.output, "_simplified.json"), "w", encoding="utf-8") as f:
                json.dump(batch["all_simplified"], f, ensure_ascii=False, indent=2)
            print(f"Saved to {args.output}")
        return
    elif args.url:
        result = process_circulaire(pdf_url=args.url)
    elif args.file:
        result = process_circulaire(pdf_path=args.file)
    else:
        parser.print_help()
        return
    
    if result.success:
        print(f"✅ Processed: {result.filename}")
        print(f"   Medications: {len(result.parsed.get('medications', []))}")
        print(f"   Laboratory entries: {len(result.simplified or [])}")
        
        if args.output:
            os.makedirs(args.output, exist_ok=True)
            base = result.filename.replace('.pdf', '').replace('.json', '')
            with open(os.path.join(args.output, f"{base}_parsed.json"), "w", encoding="utf-8") as f:
                json.dump(result.parsed, f, ensure_ascii=False, indent=2)
            with open(os.path.join(args.output, f"{base}_simplified.json"), "w", encoding="utf-8") as f:
                json.dump(result.simplified, f, ensure_ascii=False, indent=2)
    else:
        print(f"❌ Failed: {result.filename}")
        print(f"   Error: {result.error}")


if __name__ == "__main__":
    main()
