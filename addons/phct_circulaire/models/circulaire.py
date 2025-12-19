# coding: utf-8
from odoo import models, fields, api, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
import logging
import os
import json
import base64
import requests
import re
import unicodedata
import tempfile
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# Maximum circulaire number to check (01 to MAX_CIRCULAIRE_NUMBER)
MAX_CIRCULAIRE_NUMBER = 49

# Try OCR imports - graceful degradation
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning('pdfplumber not available')

try:
    import pytesseract
    from PIL import Image
    import cv2
    import numpy as np
    import subprocess
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    logger.warning('OCR dependencies not available')

# ============================================================================
# CONSTANTS AND HELPERS
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

PRICE_MARKUP_TIERS = [
    (25, 1.316), (8, 1.351), (3, 1.389), (0, 1.429),
]

CATEGORY_PATTERNS = {
    "new_local_human": [
        r"إختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"اختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"[-\d]+\s*إختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"[-\d]+\s*اختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"1[-.]?\s*إختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"1[-.]?\s*اختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"ةيلحم\s*ةيرشب\s*تاصاصتخا(?!.*راعسأ\s*ةعجارم)",
        r"ةيلحم\s*ةيرشب\s*تاصاصتخإ(?!.*راعسأ\s*ةعجارم)",
        r"[-]?اختصاصات\s*بشري[هة]\s*محلي[هة](?!\s*\(مراجعة)",
    ],
    "new_imported_human": [
        r"إختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"اختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"[-\d]+\s*إختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"[-\d]+\s*اختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"1[-.]?\s*إختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"1[-.]?\s*اختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"ةدروتسم\s*ةيرشب\s*تاصاصتخا(?!.*راعسأ\s*ةعجارم)",
        r"ةدروتسم\s*ةيرشب\s*تاصاصتخإ(?!.*راعسأ\s*ةعجارم)",
        r"[-]?اختصاصات\s*بشري[هة]\s*مستورد[هة](?!\s*\(مراجعة)",
    ],
    "new_veterinary": [
        r"إختصاصات\s*بيطرية\s*مستوردة(?!\s*\(مراجعة)",
        r"اختصاصات\s*بيطرية\s*مستوردة(?!\s*\(مراجعة)",
        r"[-\d]+\s*إختصاصات\s*بيطرية\s*مستوردة(?!\s*\(مراجعة)",
        r"[-\d]+\s*اختصاصات\s*بيطرية\s*مستوردة(?!\s*\(مراجعة)",
        r"إختصاصات\s*بيطرية\s*محلية(?!\s*\(مراجعة)",
        r"اختصاصات\s*بيطرية\s*محلية(?!\s*\(مراجعة)",
        r"[-\d]+\s*إختصاصات\s*بيطرية\s*محلية(?!\s*\(مراجعة)",
        r"[-\d]+\s*اختصاصات\s*بيطرية\s*محلية(?!\s*\(مراجعة)",
        r"ةدروتسم\s*ةيرطيب\s*تاصاصتخ[اإ]",
        r"ةيلحم\s*ةيرطيب\s*تاصاصتخ[اإ]",
        r"[-]?اختصاصات\s*بيطري[هة]",
    ],
    "revised_local_human": [
        r"إختصاصات\s*بشرية\s*محلية\s*\(مراجعة\s*أسعار\)",
        r"اختصاصات\s*بشرية\s*محلية\s*\(مراجعة\s*أسعار\)",
        r"[-\d]+\s*إختصاصات\s*بشرية\s*محلية\s*\(مراجعة",
        r"[-\d]+\s*اختصاصات\s*بشرية\s*محلية\s*\(مراجعة",
        r"1[-.]?\s*إختصاصات\s*بشرية\s*محلية\s*\(مراجعة",
        r"1[-.]?\s*اختصاصات\s*بشرية\s*محلية\s*\(مراجعة",
        r"\)راعسأ\s*ةعجارم\(\s*ةيلحم\s*ةيرشب\s*تاصاصتخ[اإ]",
        r"راعسأ\s*ةعجارم.*ةيلحم\s*ةيرشب\s*تاصاصتخ[اإ]",
        r"[-]?اختصاصات\s*بشري[هة]\s*محلي[هة]\s*\(مراجعة",
    ],
    "revised_imported_human": [
        r"إختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة\s*أسعار\)",
        r"اختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة\s*أسعار\)",
        r"[-\d]+\s*إختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة",
        r"[-\d]+\s*اختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة",
        r"2[-.]?\s*إختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة",
        r"2[-.]?\s*اختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة",
        r"\)راعسأ\s*ةعجارم\(\s*ةدروتسم\s*ةيرشب\s*تاصاصتخ[اإ]",
        r"راعسأ\s*ةعجارم.*ةدروتسم\s*ةيرشب\s*تاصاصتخ[اإ]",
        r"[-]?اختصاصات\s*بشري[هة]\s*مستورد[هة]\s*\(مراجعة",
    ],
    "revised_veterinary": [
        r"إختصاصات\s*بيطرية.*\(مراجعة\s*أسعار\)",
        r"اختصاصات\s*بيطرية.*\(مراجعة\s*أسعار\)",
        r"[-\d]+\s*إختصاصات\s*بيطرية.*\(مراجعة",
        r"[-\d]+\s*اختصاصات\s*بيطرية.*\(مراجعة",
        r"\)راعسأ\s*ةعجارم\(.*ةيرطيب\s*تاصاصتخ[اإ]",
        r"راعسأ\s*ةعجارم.*ةيلحم\s*ةيرطيب\s*تاصاصتخ[اإ]",
        r"راعسأ\s*ةعجارم.*ةدروتسم\s*ةيرطيب\s*تاصاصتخ[اإ]",
    ],
}

SECTION_BREAK_PATTERNS = [
    r"إعلام", r"قرار\s*سحب", r"ARRET\s*DE\s*COMMERCIALISATION",
    r"CHANGEMENT\s*DE\s*DENOMINATION", r"AVIS\s*DE\s*DISPONIBILITE",
    r"CHANGEMENT\s*DU\s*TABLEAU", r"retrait\s*du\s*commerce", r"Lot\s*à\s*retirer",
]

MEDICATION_PATTERN = re.compile(
    r'(\d{6})\s+(.+?)\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s*([A-C\-])?\s*(\d[,\.]\d{3})?'
)
MEDICATION_PATTERN_ALT = re.compile(
    r'(\d{6})\s+(.+?)\s+(\d+[,\.]\d+)\s+(\d+[,\.]\d+)\s+(\d+[,\.]\d+)'
)
DATE_PATTERN = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4})')
CIRC_NUMBER_PATTERN = re.compile(r'(?:رقم|:)\s*(\d{4})/(\d{1,2})')


def normalize_arabic(text):
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
# MODELS
# ============================================================================

class PhctCirculaire(models.Model):
    _name = 'phct.circulaire'
    _description = 'PHCT Circulaire Data Extraction'
    _order = 'id desc'

    filename = fields.Char(string='Filename', required=True)
    circulaire_number = fields.Integer(string='Circulaire Number', required=True)
    year = fields.Integer(string='Year', required=True)
    date = fields.Date(string='Circulaire Date')
    circulaire_ref = fields.Char(string='Circulaire Ref')
    pdf_url = fields.Char(string='PDF URL')
    file_data = fields.Binary(string='PDF File', attachment=True)
    parsed = fields.Text(string='Parsed JSON')
    simplified = fields.Text(string='Simplified JSON')
    sections_found = fields.Text(string='Sections Found (JSON)')
    medications_count = fields.Integer(string='Medications Count')
    ocr_used = fields.Boolean(string='OCR Used', default=False)
    medication_ids = fields.One2many('phct.circulaire.med', 'circulaire_id', string='Medications')
    
    # Computed display fields
    new_medication_count = fields.Integer(string='New Medications', compute='_compute_medication_stats', store=True)
    revised_count = fields.Integer(string='Revised Prices', compute='_compute_medication_stats', store=True)
    not_found_count = fields.Integer(string='Not Found in DB', compute='_compute_medication_stats', store=True)
    matched_100_count = fields.Integer(string='Matched 100%', compute='_compute_medication_stats', store=True)
    matched_partial_count = fields.Integer(string='Matched Partial', compute='_compute_medication_stats', store=True)
    ocr_verify_recommended = fields.Boolean(string='Verify Manually (OCR)', compute='_compute_ocr_verify', store=True)
    
    @api.depends('medication_ids', 'medication_ids.type', 'medication_ids.match_status', 'medication_ids.match_confidence')
    def _compute_medication_stats(self):
        """Compute medication statistics based on type and match status."""
        for record in self:
            meds = record.medication_ids
            # Count new medications (type contains 'new')
            record.new_medication_count = len(meds.filtered(lambda m: m.type and 'new' in m.type.lower()))
            # Count revised medications (type contains 'revised')
            record.revised_count = len(meds.filtered(lambda m: m.type and 'revised' in m.type.lower()))
            # Count not found products
            record.not_found_count = len(meds.filtered(lambda m: m.match_status == 'not_found'))
            # Count matched 100%
            record.matched_100_count = len(meds.filtered(lambda m: m.match_confidence == 100.0))
            # Count matched partial (>0% and <100%)
            record.matched_partial_count = len(meds.filtered(lambda m: 0 < m.match_confidence < 100.0))
    
    @api.depends('ocr_used')
    def _compute_ocr_verify(self):
        """Recommend manual verification when OCR was used."""
        for record in self:
            record.ocr_verify_recommended = record.ocr_used

    # =============================================================================
    # PDF EXTRACTION
    # =============================================================================

    def _preprocess_for_ocr(self, image_path):
        if not HAS_OCR:
            return image_path
        try:
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
        except Exception:
            return image_path

    def _ocr_page(self, pdf_path, page_number):
        if not HAS_OCR:
            logger.debug('OCR requested but HAS_OCR=False')
            return ""
        
        # Use /tmp for temp files to avoid permission issues
        temp_dir = tempfile.gettempdir()
        temp_prefix = os.path.join(temp_dir, f"odoo_ocr_page_{page_number}_{os.getpid()}")
        temp_png = f"{temp_prefix}.png"
        
        logger.info('Running OCR on page %d of %s', page_number, os.path.basename(pdf_path))
        
        try:
            result = subprocess.run(
                ["pdftoppm", pdf_path, temp_prefix, "-png", "-r", "300",
                 "-f", str(page_number), "-l", str(page_number), "-singlefile"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
            )
            if result.returncode != 0:
                logger.warning('pdftoppm failed with code %d: %s', result.returncode, result.stderr.decode())
                return ""
        except Exception as e:
            logger.exception('pdftoppm exception: %s', e)
            return ""
        
        if not os.path.exists(temp_png):
            logger.warning('OCR temp file not created: %s', temp_png)
            return ""
        
        clean_png = self._preprocess_for_ocr(temp_png)
        text = ""
        try:
            img = Image.open(clean_png)
            text = pytesseract.image_to_string(img, lang="ara+fra+eng", config="--psm 6")
            logger.info('OCR extracted %d characters from page %d', len(text), page_number)
        except Exception as e:
            logger.exception('OCR extraction failed: %s', e)
        
        # Clean up temp files
        for f in [temp_png, clean_png]:
            try:
                if os.path.exists(f) and f != temp_png:  # Don't delete if same file
                    os.remove(f)
            except Exception:
                pass
        try:
            if os.path.exists(temp_png):
                os.remove(temp_png)
        except Exception:
            pass
        
        return normalize_arabic(text)

    def _page_has_chars(self, page):
        try:
            chars = getattr(page, "chars", None)
            if chars is None:
                objs = page.objects if hasattr(page, "objects") else {}
                chars = objs.get("char", [])
            return bool(chars)
        except Exception:
            return False

    def _count_arabic_letters(self, s):
        count = 0
        for c in s:
            if "\u0600" <= c <= "\u06FF" or "\uFB50" <= c <= "\uFDFF" or "\uFE70" <= c <= "\uFEFF":
                count += 1
        return count

    def _extract_text_from_pdf(self, pdf_path):
        """Extract text from PDF. Returns (text, ocr_used_flag)."""
        if not HAS_PDFPLUMBER:
            raise Exception('pdfplumber required')
        full_text = ""
        ocr_pages = []
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                for pg_num, page in enumerate(pdf.pages, start=1):
                    raw = page.extract_text() or ""
                    has_chars = self._page_has_chars(page)
                    arabic_count = self._count_arabic_letters(raw)
                    
                    # Decide if OCR is needed
                    needs_ocr = (not has_chars) or len(raw.strip()) < 5 or arabic_count < 3
                    
                    if needs_ocr:
                        logger.info('Page %d needs OCR (has_chars=%s, text_len=%d, arabic=%d)', 
                                   pg_num, has_chars, len(raw.strip()), arabic_count)
                        page_text = self._ocr_page(pdf_path, pg_num)
                        ocr_pages.append(pg_num)
                    else:
                        page_text = normalize_arabic(raw)
                    
                    full_text += page_text + "\n"
                
                if ocr_pages:
                    logger.info('Used OCR on %d pages: %s', len(ocr_pages), ocr_pages)
        except Exception as e:
            logger.exception('Error extracting PDF: %s', e)
        
        return full_text, bool(ocr_pages)

    # =============================================================================
    # PARSER
    # =============================================================================

    def _extract_date(self, text):
        match = re.search(r'(?:تونس\s*في|في\s*:?)\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{4})', text)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        match = DATE_PATTERN.search(text)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return None

    def _extract_circulaire_number(self, text):
        match = CIRC_NUMBER_PATTERN.search(text)
        if match:
            year, num = match.groups()
            return f"{year}/{num.zfill(2)}"
        return None

    def _find_category_sections(self, text):
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
                        "matched_text": match.group(0),  # Add for debugging
                    })
        sections.sort(key=lambda x: x["start"])
        
        # Log all found sections before filtering
        logger.info('Found %d section matches before filtering', len(sections))
        for s in sections:
            logger.info('  Section at pos %d: %s (%s)', s["start"], s["matched_text"], s["specialty"])
        
        filtered = []
        for s in sections:
            if not filtered or s["start"] >= filtered[-1]["end"]:
                filtered.append(s)
            else:
                logger.info('  Filtered out overlapping section: %s at pos %d', s["matched_text"], s["start"])
        
        logger.info('After filtering: %d sections remaining', len(filtered))
        return filtered

    def _find_section_breaks(self, text):
        breaks = []
        for pattern in SECTION_BREAK_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                breaks.append(match.start())
        return sorted(breaks)

    def _clean_medication_name(self, name):
        if not name:
            return name
        name = re.sub(r'^[\[\]]+|[\[\]]+$', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def _is_laboratory_line(self, line):
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

    def _calculate_sale_price(self, pharmacy_price):
        for threshold, ratio in PRICE_MARKUP_TIERS:
            if pharmacy_price >= threshold:
                return round(pharmacy_price * ratio, 3)
        return round(pharmacy_price * PRICE_MARKUP_TIERS[-1][1], 3)

    def _parse_medication_line(self, line, current_lab=None):
        line = line.strip()
        if not line:
            return None
        line = line.replace('\u200e', '').replace('\u200f', '').replace('|', ' ')
        line = re.sub(r'\s+', ' ', line).strip()
        
        # Pattern 1
        match = MEDICATION_PATTERN.search(line)
        if match:
            code, name, price1, price2, price3, cat, margin = match.groups()
            return {
                "code": code,
                "name": self._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": cat if cat and cat != '-' else None,
                "margin": float(margin.replace(',', '.')) if margin else None,
            }
        
        # Pattern 2
        pattern_code_end = re.compile(
            r'^(.+?)\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})[\]\s]*'
            r'([A-C])[_\s]*[\{\[]?[01]?(\d[,\.]\d{3})[\}\]]?\s*(\d{6})\s*$'
        )
        match = pattern_code_end.search(line)
        if match:
            name, price1, price2, price3, cat, margin, code = match.groups()
            return {
                "code": code,
                "name": self._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": cat if cat and cat != '-' else None,
                "margin": float(margin.replace(',', '.')) if margin else None,
            }
        
        # Pattern 2b
        pattern_code_end_dash = re.compile(
            r'^(.+?)\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})[\]\s]*-\s*(\d{6})\s*$'
        )
        match = pattern_code_end_dash.search(line)
        if match:
            name, price1, price2, price3, code = match.groups()
            return {
                "code": code,
                "name": self._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": None,
                "margin": None,
            }
        
        # Pattern 2c
        pattern_code_end_simple = re.compile(
            r'^(.+?)\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})\s+(\d{1,3}[,\.]\d{3})[\]\s]+(\d{6})\s*$'
        )
        match = pattern_code_end_simple.search(line)
        if match:
            name, price1, price2, price3, code = match.groups()
            return {
                "code": code,
                "name": self._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": None,
                "margin": None,
            }
        
        # Pattern 3
        match = MEDICATION_PATTERN_ALT.search(line)
        if match:
            code, name, price1, price2, price3 = match.groups()
            cat_match = re.search(r'\s([A-C])\s', line[match.end():] if match.end() < len(line) else '')
            margin_match = re.search(r'(\d[,\.]\d{3})\s*$', line)
            return {
                "code": code,
                "name": self._clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": cat_match.group(1) if cat_match else None,
                "margin": float(margin_match.group(1).replace(',', '.')) if margin_match else None,
            }
        
        # Additional patterns omitted for brevity - add if needed
        return None

    def _parse_medications_from_section(self, text, section_info):
        medications = []
        current_lab = None
        pending_lab_lines = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            clean_line = line.replace('\u200e', '').replace('\u200f', '').strip()
            if self._is_laboratory_line(clean_line):
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
            med = self._parse_medication_line(line, current_lab)
            if med:
                med["type"] = section_info.get("type", "new")
                med["specialty"] = section_info.get("specialty", "human")
                med["origin"] = section_info.get("origin", "local")
                if med.get("price_public") is None and med.get("price_pharmacy"):
                    med["price_public"] = self._calculate_sale_price(med["price_pharmacy"])
                    med["price_public_calculated"] = True
                medications.append(med)
        return medications

    def _parse_circulaire_text(self, text, filename):
        result = {
            "filename": filename,
            "date": self._extract_date(text),
            "circulaire_number": self._extract_circulaire_number(text),
            "medications": [],
            "sections_found": [],
        }
        sections = self._find_category_sections(text)
        section_breaks = self._find_section_breaks(text)
        
        for i, section in enumerate(sections):
            # ONLY process human medication sections - skip veterinary
            if section.get("specialty") == "veterinary":
                logger.debug('Skipping veterinary section in %s', filename)
                continue
            
            # Find where this section ends: at the start of the NEXT section (human OR vet)
            section_end = len(text)
            if i + 1 < len(sections):
                # End at the start of the very next section (regardless of type)
                section_end = sections[i + 1]["start"]
            
            # Also check for section breaks (announcements, withdrawals, etc)
            for brk in section_breaks:
                if brk > section["end"] and brk < section_end:
                    section_end = brk
                    break
            
            section_text = text[section["end"]:section_end]
            meds = self._parse_medications_from_section(section_text, section)
            result["sections_found"].append({
                "type": section["type"],
                "specialty": section["specialty"],
                "origin": section["origin"],
                "medications_count": len(meds),
            })
            result["medications"].extend(meds)
        return result

    def _create_simplified(self, parsed):
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

    # =============================================================================
    # CONFIG AND CRON
    # =============================================================================

    def _get_base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'phct_circulaire.base_url',
            'http://www.phct.com.tn/images/DocumentsPCT/Circulaires/'
        )

    def _get_default_year(self):
        """Derive year from current UTC date (e.g., 2025 -> '25')."""
        return datetime.utcnow().strftime('%y')

    @api.model
    def fetch_and_process_circulaires(self):
        """Main cron: scan all circulaire numbers for current year starting from last processed."""
        # Get current year from UTC time
        current_year = int(self._get_default_year())
        
        # Get last processed circulaire to determine starting point
        last = self.search([('year', '=', current_year)], order='circulaire_number desc', limit=1)
        if last:
            start_number = last.circulaire_number + 1
            logger.info('Resuming from circulaire number %02d for year %02d', start_number, current_year)
        else:
            start_number = 1
            logger.info('Starting fresh scan for year %02d', current_year)

        base_url = self._get_base_url()
        found_count = 0

        # Scan from start_number to MAX_CIRCULAIRE_NUMBER
        for num in range(start_number, MAX_CIRCULAIRE_NUMBER + 1):
            # Try both filename formats
            found = False
            for prefix in ('Circ', 'circ'):
                filename = f"{prefix}{num:02d}{current_year:02d}.pdf"
                url = base_url + filename
                logger.info('Trying %s', url)
                
                try:
                    resp = requests.get(url, timeout=20)
                except Exception:
                    logger.exception('Request failed for %s', url)
                    continue

                if resp.status_code != 200 or not resp.content:
                    logger.debug('Not found %s (status=%s)', url, resp.status_code)
                    continue

                # Found a valid PDF
                found = True
                found_count += 1
                logger.info('Found circulaire: %s', filename)

                try:
                    vals = {
                        'filename': filename,
                        'circulaire_number': num,
                        'year': current_year,
                        'pdf_url': url,
                        'file_data': base64.b64encode(resp.content).decode('ascii'),
                    }

                    parsed = None
                    simplified = None
                    ocr_used = False

                    tmp_path = os.path.join('/tmp', filename)
                    with open(tmp_path, 'wb') as fh:
                        fh.write(resp.content)
                    try:
                        text, ocr_used = self._extract_text_from_pdf(tmp_path)
                        if text and len(text.strip()) > 50:
                            parsed = self._parse_circulaire_text(text, filename)
                            simplified = self._create_simplified(parsed)
                    except Exception:
                        logger.exception('Parser failed for %s', tmp_path)

                    if parsed is not None:
                        vals['parsed'] = json.dumps(parsed, ensure_ascii=False)
                        vals['ocr_used'] = ocr_used
                        if parsed.get('date'):
                            vals['date'] = parsed.get('date')
                        if parsed.get('circulaire_number'):
                            vals['circulaire_ref'] = parsed.get('circulaire_number')
                        secs = parsed.get('sections_found')
                        if secs is not None:
                            vals['sections_found'] = json.dumps(secs, ensure_ascii=False)
                        meds = parsed.get('medications') or []
                        vals['medications_count'] = len(meds)

                    if simplified is not None:
                        vals['simplified'] = json.dumps(simplified, ensure_ascii=False)

                    # Only save circulaires that have medications (meet our criteria)
                    if parsed and isinstance(parsed, dict):
                        meds = parsed.get('medications') or []
                        if meds:
                            # Create the circulaire record
                            rec = self.create(vals)
                            
                            # Create medication records
                            Med = self.env['phct.circulaire.med']
                            for m in meds:
                                try:
                                    raw = json.dumps(m, ensure_ascii=False)
                                    Med.create({
                                        'circulaire_id': rec.id,
                                        'code': m.get('code'),
                                        'name': m.get('name'),
                                        'laboratory': m.get('laboratory'),
                                        'price_wholesale': m.get('price_wholesale'),
                                        'price_pharmacy': m.get('price_pharmacy'),
                                        'price_public': m.get('price_public'),
                                        'sale_price': m.get('price_public'),
                                        'price_public_calculated': bool(m.get('price_public_calculated')),
                                        'category': m.get('category'),
                                        'margin': m.get('margin'),
                                        'type': m.get('type'),
                                        'specialty': m.get('specialty'),
                                        'origin': m.get('origin'),
                                        'data': raw,
                                    })
                                except Exception:
                                    logger.exception('Failed creating medication for %s', m)

                            logger.info('Stored circulaire %s (id=%s) with %d medications', filename, rec.id, len(meds))
                        else:
                            logger.info('Skipping circulaire %s - no medications found', filename)
                except Exception:
                    logger.exception('Failed storing circulaire %s', filename)
                
                # Break after processing this number (found in one of the prefixes)
                break
            
            if not found:
                logger.debug('Circulaire number %02d not found, continuing scan', num)
            
            # Sleep 1 second between requests to be respectful to the server
            time.sleep(1)

        if found_count > 0:
            logger.info('Cron completed: %d new circulaires processed', found_count)
        else:
            logger.info('Cron completed: no new circulaires found')
        
        return True


class PhctCirculaireMed(models.Model):
    _name = 'phct.circulaire.med'
    _description = 'Circulaire Medication'

    circulaire_id = fields.Many2one('phct.circulaire', string='Circulaire', ondelete='cascade')
    code = fields.Char(string='Code')
    name = fields.Char(string='Name')
    laboratory = fields.Char(string='Laboratory')
    price_wholesale = fields.Float(string='Wholesale Price')
    price_pharmacy = fields.Float(string='Pharmacy Price')
    price_public = fields.Float(string='Public / Sale Price')
    sale_price = fields.Float(string='Sale Price')
    price_public_calculated = fields.Boolean(string='Public Price Calculated')
    category = fields.Char(string='Category')
    margin = fields.Float(string='Margin')
    type = fields.Char(string='Type')
    specialty = fields.Char(string='Specialty')
    origin = fields.Char(string='Origin')
    data = fields.Text(string='Raw Medication JSON')
    
    # Product matching fields
    product_id = fields.Many2one('product.template', string='Matched Product', 
                                 help='Product found in database matching this medication')
    manual_product_id = fields.Many2one('product.template', string='Manual Product Selection',
                                        help='Manually select a product if auto-match is incorrect or needs verification')
    search_term = fields.Char(string='Search Products', 
                              help='Type to search for products in the database')
    search_results_ids = fields.Many2many('product.template', 
                                          'phct_med_product_search_rel', 
                                          'medication_id', 'product_id',
                                          string='Search Results', 
                                          compute='_compute_search_results',
                                          help='Products matching the search term')
    match_status = fields.Selection([
        ('not_checked', 'Not Checked'),
        ('matched', 'Matched'),
        ('not_found', 'Not Found'),
    ], string='Match Status', default='not_checked', help='Status of product matching')
    price_difference = fields.Float(string='Price Difference', 
                                    help='Difference between PHCT price and product list_price (PHCT - Product)')
    price_comparison = fields.Selection([
        ('equal', 'Equal'),
        ('phct_higher', 'PHCT Higher'),
        ('phct_lower', 'PHCT Lower'),
        ('no_product', 'No Product Match'),
    ], string='Price Comparison', default='no_product',
       help='Comparison of PHCT sale price vs product list_price')
    match_confidence = fields.Float(string='Match Confidence %', 
                                    help='Confidence score of the product match (0-100)')
    
    # Computed display fields
    circulaire_display = fields.Char(string='Circulaire', compute='_compute_circulaire_display', store=True)
    
    @api.depends('search_term')
    def _compute_search_results(self):
        """Search for products based on search term."""
        for record in self:
            if record.search_term and len(record.search_term) >= 3:
                # Search in product name using ilike (case-insensitive)
                domain = [
                    ('categ_id', '=', 9),  # Pharmacy category
                    '|', '|',
                    ('name', 'ilike', record.search_term),
                    ('default_code', 'ilike', record.search_term),
                    ('description', 'ilike', record.search_term),
                ]
                products = self.env['product.template'].search(domain, limit=20, order='name')
                record.search_results_ids = products
            else:
                record.search_results_ids = False
    
    @api.depends('circulaire_id', 'circulaire_id.circulaire_number', 'circulaire_id.year')
    def _compute_circulaire_display(self):
        """Display circulaire as 'number/year' format."""
        for record in self:
            if record.circulaire_id:
                record.circulaire_display = f"{record.circulaire_id.circulaire_number}/{record.circulaire_id.year}"
            else:
                record.circulaire_display = ''
    
    @api.onchange('manual_product_id')
    def _onchange_manual_product(self):
        """When user manually selects a product, update product_id and recalculate prices."""
        if self.manual_product_id:
            self.product_id = self.manual_product_id
            self.match_status = 'matched'
            self.match_confidence = 100.0  # Manual selection is 100% confident
            self._calculate_price_comparison()
    
    def action_select_search_result(self):
        """Action to select a product from search results (called from tree view button)."""
        # This will be triggered from a button on search results
        # The context will contain the product_id to select
        if self.env.context.get('select_product_id'):
            product_id = self.env.context.get('select_product_id')
            product = self.env['product.template'].browse(product_id)
            if product:
                self.write({
                    'product_id': product.id,
                    'manual_product_id': product.id,
                    'match_status': 'matched',
                    'match_confidence': 100.0,
                })
                self._calculate_price_comparison()
                return {'type': 'ir.actions.act_window_close'}
    
    def _calculate_price_comparison(self):
        """Calculate price comparison with matched product."""
        if not self.product_id or not self.price_public:
            self.price_difference = 0.0
            self.price_comparison = 'no_product'
            return
        
        product_price = self.product_id.list_price or 0.0
        phct_price = self.price_public or 0.0
        
        self.price_difference = phct_price - product_price
        
        # Consider prices equal if difference is less than 0.01
        if abs(self.price_difference) < 0.01:
            self.price_comparison = 'equal'
        elif self.price_difference > 0:
            self.price_comparison = 'phct_higher'
        else:
            self.price_comparison = 'phct_lower'
    
    def _normalize_text(self, text):
        """Normalize text for comparison: lowercase, remove extra spaces, punctuation."""
        if not text:
            return ''
        import re
        # Remove common punctuation and extra spaces
        text = re.sub(r'[®™©\-_/,\.\(\)\[\]]', ' ', text.lower())
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _extract_medication_components(self, name):
        """Extract structured components from medication name.
        
        Pattern: BRAND_NAME STRENGTH DOSAGE_FORM PACKAGING
        Example: ELIXTRA 2.5mg Comp.Pell. Bt 20
        
        Returns: dict with brand, strengths, forms, packaging
        """
        import re
        
        if not name:
            return {}
        
        parts = name.split()
        brand = parts[0].lower() if parts else ''
        
        # Extract strengths (numbers with units: mg, g, μg, %, ml, dose)
        strength_pattern = r'\d+(?:\.\d+)?(?:mg|g|μg|%|ml|dose)'
        strengths = re.findall(strength_pattern, name, re.IGNORECASE)
        strengths = [s.lower() for s in strengths]
        
        # Extract packaging (Bt, Fl, Tb, Amp, Ser with numbers)
        packaging_pattern = r'(Bt|Fl|Tb|Amp|Ser)\s*\d+'
        packaging = re.findall(packaging_pattern, name, re.IGNORECASE)
        packaging = [p.lower().replace(' ', '') for p in packaging]
        
        return {
            'brand': brand,
            'strengths': strengths,
            'packaging': packaging,
            'normalized': self._normalize_text(name)
        }
    
    def _calculate_name_similarity(self, name1, name2):
        """Calculate similarity score between two names (0-100).
        
        STRICT RULE: First word (brand name) must match exactly (case-insensitive).
        ENHANCED: Also considers strength and packaging for better accuracy.
        """
        if not name1 or not name2:
            return 0.0
        
        # Extract components from both names
        comp1 = self._extract_medication_components(name1)
        comp2 = self._extract_medication_components(name2)
        
        if not comp1 or not comp2:
            return 0.0
        
        # RULE 1: Brand name (first word) must match exactly
        if comp1['brand'] != comp2['brand']:
            return 0.0
        
        # Brand matches! Now calculate detailed similarity
        score = 0.0
        
        # RULE 2: Strength matching (very important - 40 points)
        if comp1['strengths'] and comp2['strengths']:
            # Check if primary strength matches (first strength)
            if comp1['strengths'][0] == comp2['strengths'][0]:
                score += 40
            # Check if any strengths match
            elif set(comp1['strengths']) & set(comp2['strengths']):
                score += 20
        elif not comp1['strengths'] and not comp2['strengths']:
            # Both have no strength info (rare but possible)
            score += 20
        
        # RULE 3: Token-based similarity for rest of name (40 points)
        norm1 = comp1['normalized']
        norm2 = comp2['normalized']
        
        tokens1 = set(norm1.split())
        tokens2 = set(norm2.split())
        
        if tokens1 and tokens2:
            intersection = len(tokens1 & tokens2)
            union = len(tokens1 | tokens2)
            
            if union > 0:
                jaccard = (intersection / union)
                score += jaccard * 40
        
        # RULE 4: Packaging bonus (20 points)
        if comp1['packaging'] and comp2['packaging']:
            # Same packaging type and quantity
            if comp1['packaging'] == comp2['packaging']:
                score += 20
            # Same packaging type, different quantity (still good)
            elif any(p1[:2] == p2[:2] for p1 in comp1['packaging'] for p2 in comp2['packaging']):
                score += 10
        elif not comp1['packaging'] and not comp2['packaging']:
            # Both missing packaging info
            score += 10
        
        # RULE 5: Substring bonus
        if norm1 in norm2 or norm2 in norm1:
            score = min(100.0, score + 10)
        
        return min(100.0, score)
    
    def _find_matching_product(self):
        """Find matching product in database using smart matching.
        
        Returns: (product_record, confidence_score)
        """
        Product = self.env['product.template']
        
        # Category ID 9 is for pharmacy products based on user's SQL query
        pharmacy_categ_id = 9
        base_domain = [('categ_id', '=', pharmacy_categ_id), ('active', '=', True)]
        
        best_match = None
        best_score = 0.0
        
        # Strategy 1: Exact code_pct match (highest priority)
        if self.code:
            products = Product.search(base_domain + [('code_pct', '=', self.code)])
            if products:
                logger.info('Found exact code_pct match for %s: %s', self.code, products[0].name)
                return products[0], 100.0
        
        # Strategy 2: Name matching with laboratory filter
        if self.name:
            # First try with laboratory filter if available
            if self.laboratory:
                lab_domain = base_domain + [('labo', 'ilike', self.laboratory)]
                lab_products = Product.search(lab_domain)
                
                for product in lab_products:
                    score = self._calculate_name_similarity(self.name, product.name)
                    if score > best_score:
                        best_score = score
                        best_match = product
            
            # If no good match with laboratory, try all products
            if best_score < 70:
                all_products = Product.search(base_domain)
                
                for product in all_products:
                    score = self._calculate_name_similarity(self.name, product.name)
                    
                    # Boost score if laboratory also matches
                    if self.laboratory and product.labo:
                        lab_similarity = self._calculate_name_similarity(self.laboratory, product.labo)
                        if lab_similarity > 70:
                            score = min(100.0, score + 10)
                    
                    if score > best_score:
                        best_score = score
                        best_match = product
        
        if best_match and best_score >= 60:  # Minimum confidence threshold
            logger.info('Found fuzzy match for "%s": %s (score: %.1f%%)', 
                       self.name, best_match.name, best_score)
            return best_match, best_score
        
        logger.info('No suitable match found for "%s" (best score: %.1f%%)', self.name, best_score)
        return None, 0.0
    
    def match_with_product(self):
        """Try to match this medication with a product in the database."""
        for rec in self:
            product, confidence = rec._find_matching_product()
            
            if product:
                rec.write({
                    'product_id': product.id,
                    'match_status': 'matched',
                    'match_confidence': confidence,
                })
                # Calculate price comparison after matching
                rec._calculate_price_comparison()
            else:
                rec.write({
                    'product_id': False,
                    'match_status': 'not_found',
                    'match_confidence': 0.0,
                    'price_comparison': 'no_product',
                    'price_difference': 0.0,
                })
        
        return True
    
    def action_bulk_rematch(self):
        """Bulk action to re-match selected medications.
        
        Use this after adding new products to the database to find matches
        for previously unmatched medications without re-running the cronjob.
        """
        matched_count = 0
        still_not_found = 0
        
        for rec in self:
            old_status = rec.match_status
            rec.match_with_product()
            
            if rec.match_status == 'matched' and old_status != 'matched':
                matched_count += 1
            elif rec.match_status == 'not_found':
                still_not_found += 1
        
        # Show result message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Re-matching Complete'),
                'message': _('New matches: %d, Still not found: %d') % (matched_count, still_not_found),
                'type': 'success' if matched_count > 0 else 'info',
                'sticky': False,
            }
        }
    
    @api.model
    def action_rematch_all_unmatched(self):
        """Re-match all medications that are currently not matched.
        
        Call this after bulk product imports to automatically find new matches.
        """
        unmatched = self.search([('match_status', '=', 'not_found')])
        
        if not unmatched:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Unmatched Medications'),
                    'message': _('All medications are already matched or checked.'),
                    'type': 'info',
                    'sticky': False,
                }
            }
        
        matched_count = 0
        for med in unmatched:
            med.match_with_product()
            if med.match_status == 'matched':
                matched_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Re-matching Complete'),
                'message': _('Found %d new matches out of %d unmatched medications') % (matched_count, len(unmatched)),
                'type': 'success' if matched_count > 0 else 'warning',
                'sticky': True,
            }
        }
    
    def action_create_product(self):
        """Open product creation form pre-filled with medication data.
        
        Allows user to create a new product from this medication by pre-filling
        the form with available data (name, code, lab, price).
        User can then complete missing fields and save.
        """
        self.ensure_one()
        
        # Prepare default values for product creation
        default_values = {
            'name': self.name,
            'categ_id': 9,  # Pharmacy category
            'list_price': self.price_public or 0.0,
            'type': 'product',
            'detailed_type': 'product',
        }
        
        # Add code_pct if available
        if self.code:
            default_values['code_pct'] = self.code
        
        # Add laboratory if available
        if self.laboratory:
            default_values['labo'] = self.laboratory
        
        # Return action to open product form
        return {
            'name': _('Create Product from %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'view_mode': 'form',
            'view_id': False,
            'target': 'new',  # Open in dialog
            'context': {
                'default_name': default_values['name'],
                'default_categ_id': default_values['categ_id'],
                'default_list_price': default_values['list_price'],
                'default_code_pct': default_values.get('code_pct', False),
                'default_labo': default_values.get('labo', False),
                'default_type': default_values['type'],
                'default_detailed_type': default_values['detailed_type'],
                # Store medication ID to link after creation
                'phct_medication_id': self.id,
            }
        }
    
    def action_update_product(self):
        """Open linked product form for updating.
        
        Opens the matched product in edit mode, allowing user to update
        the product information (especially price) based on medication data.
        """
        self.ensure_one()
        
        if not self.product_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Product Linked'),
                    'message': _('This medication is not matched to any product. Use \"Create Product\" instead.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Show suggested updates in context
        updates = []
        if self.price_public and abs(self.product_id.list_price - self.price_public) > 0.01:
            updates.append(_('Price: %s → %s') % (self.product_id.list_price, self.price_public))
        
        context_msg = ''
        if updates:
            context_msg = _('Suggested updates: ') + ', '.join(updates)
        
        return {
            'name': _('Update Product: %s') % self.product_id.name,
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'view_id': False,
            'target': 'new',
            'context': {
                'phct_suggested_price': self.price_public,
                'phct_medication_id': self.id,
                'form_view_initial_mode': 'edit',
            },
            'help': context_msg,
        }
    
    @api.model
    def create(self, vals):
        """Override create to automatically match products."""
        record = super(PhctCirculaireMed, self).create(vals)
        # Auto-match with product after creation
        try:
            record.match_with_product()
        except Exception as e:
            logger.warning('Failed to auto-match product for %s: %s', record.name, e)
        return record
