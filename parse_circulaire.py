#!/usr/bin/env python3
"""
Parser for Tunisian PCT Circulaires - extracts medication data from text/OCR output
"""
import re
import json
import os
from typing import Optional

# Category patterns - what we care about
# Note: Arabic text can appear in different forms:
# 1. Standard RTL: اختصاصات بشرية محلية
# 2. Reversed (from some PDF extraction): ةيلحم ةيرشب تاصاصتخا
# 3. OCR variations with different spacing

CATEGORY_PATTERNS = {
    # New medications - local human
    "new_local_human": [
        r"إختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"اختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"1[-.]?\s*إختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        r"1[-.]?\s*اختصاصات\s*بشرية\s*محلية(?!\s*\(مراجعة)",
        # Reversed forms from PDF extraction
        r"ةيلحم\s*ةيرشب\s*تاصاصتخا(?!.*راعسأ\s*ةعجارم)",
        r"ةيلحم\s*ةيرشب\s*تاصاصتخإ(?!.*راعسأ\s*ةعجارم)",
        r"1[-.]?\s*ةيلحم\s*ةيرشب\s*تاصاصتخا",
        r"1[-.]?\s*ةيلحم\s*ةيرشب\s*تاصاصتخإ",
        # OCR variations
        r"[-]?اختصاصات\s*بشري[هة]\s*محلي[هة](?!\s*\(مراجعة)",
    ],
    # New medications - imported human
    "new_imported_human": [
        r"إختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"اختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"1[-.]?\s*إختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        r"1[-.]?\s*اختصاصات\s*بشرية\s*مستوردة(?!\s*\(مراجعة)",
        # Reversed forms
        r"ةدروتسم\s*ةيرشب\s*تاصاصتخا(?!.*راعسأ\s*ةعجارم)",
        r"ةدروتسم\s*ةيرشب\s*تاصاصتخإ(?!.*راعسأ\s*ةعجارم)",
        # OCR variations
        r"[-]?اختصاصات\s*بشري[هة]\s*مستورد[هة](?!\s*\(مراجعة)",
    ],
    # New medications - veterinary
    "new_veterinary": [
        r"إختصاصات\s*بيطرية\s*مستوردة(?!\s*\(مراجعة)",
        r"اختصاصات\s*بيطرية\s*مستوردة(?!\s*\(مراجعة)",
        r"إختصاصات\s*بيطرية\s*محلية(?!\s*\(مراجعة)",
        r"اختصاصات\s*بيطرية\s*محلية(?!\s*\(مراجعة)",
        # Reversed forms - match both ا and إ endings
        r"ةدروتسم\s*ةيرطيب\s*تاصاصتخ[اإ]",
        r"ةيلحم\s*ةيرطيب\s*تاصاصتخ[اإ]",
        # OCR variations
        r"[-]?اختصاصات\s*بيطري[هة]",
    ],
    # Price revised - local human
    "revised_local_human": [
        r"إختصاصات\s*بشرية\s*محلية\s*\(مراجعة\s*أسعار\)",
        r"اختصاصات\s*بشرية\s*محلية\s*\(مراجعة\s*أسعار\)",
        r"1[-.]?\s*إختصاصات\s*بشرية\s*محلية\s*\(مراجعة",
        r"1[-.]?\s*اختصاصات\s*بشرية\s*محلية\s*\(مراجعة",
        # Reversed forms with price revision
        r"\(راعسأ\s*ةعجارم\)\s*ةيلحم\s*ةيرشب\s*تاصاصتخا",
        r"راعسأ\s*ةعجارم.*ةيلحم\s*ةيرشب\s*تاصاصتخا",
        # OCR variations
        r"[-]?اختصاصات\s*بشري[هة]\s*محلي[هة]\s*\(مراجعة",
    ],
    # Price revised - imported human
    "revised_imported_human": [
        r"إختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة\s*أسعار\)",
        r"اختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة\s*أسعار\)",
        r"2[-.]?\s*إختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة",
        r"2[-.]?\s*اختصاصات\s*بشرية\s*مستوردة\s*\(مراجعة",
        # Reversed forms
        r"\(راعسأ\s*ةعجارم\)\s*ةدروتسم\s*ةيرشب\s*تاصاصتخا",
        r"راعسأ\s*ةعجارم.*ةدروتسم\s*ةيرشب\s*تاصاصتخا",
        # OCR variations  
        r"[-]?اختصاصات\s*بشري[هة]\s*مستورد[هة]\s*\(مراجعة",
    ],
    # Price revised - veterinary
    "revised_veterinary": [
        r"إختصاصات\s*بيطرية.*\(مراجعة\s*أسعار\)",
        r"اختصاصات\s*بيطرية.*\(مراجعة\s*أسعار\)",
        # Reversed forms - match both ا and إ endings
        r"\(راعسأ\s*ةعجارم\).*ةيرطيب\s*تاصاصتخ[اإ]",
        r"راعسأ\s*ةعجارم.*ةيلحم\s*ةيرطيب\s*تاصاصتخ[اإ]",
        r"راعسأ\s*ةعجارم.*ةدروتسم\s*ةيرطيب\s*تاصاصتخ[اإ]",
    ],
}

# Patterns to detect section breaks (things we don't care about)
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

# Regex for medication line - more flexible pattern
# Format: CODE NAME ... PRICE1 PRICE2 PRICE3 [CATEGORY] [MARGIN]
MEDICATION_PATTERN = re.compile(
    r'(\d{6})\s+'  # 6-digit code
    r'(.+?)\s+'  # name (anything up to prices)
    r'(\d{1,3}[,\.]\d{3})\s+'  # price 1 (wholesale)
    r'(\d{1,3}[,\.]\d{3})\s+'  # price 2 (pharmacy) 
    r'(\d{1,3}[,\.]\d{3})\s*'  # price 3 (public)
    r'([A-C\-])?\s*'  # category (A, B, C, or -, optional)
    r'(\d[,\.]\d{3})?',  # margin (optional)
)

# Alternative pattern - simpler, just finds code and 3 prices
MEDICATION_PATTERN_ALT = re.compile(
    r'(\d{6})\s+'  # 6-digit code
    r'(.+?)\s+'  # medication name
    r'(\d+[,\.]\d+)\s+'  # price 1
    r'(\d+[,\.]\d+)\s+'  # price 2
    r'(\d+[,\.]\d+)',  # price 3
)

# Pattern for laboratory names (all caps, possibly with dots/spaces)
LABORATORY_PATTERN = re.compile(
    r'^([A-Z][A-Z\s\.\-\&\(\)]+(?:S\.?A\.?|LLC|GMBH|LTD|INC|PHARMA|LABORATORIES?|PHARMACEUTICAL[S]?)?)\s*$',
    re.MULTILINE
)

# Date pattern
DATE_PATTERN = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4})')

# Circulaire number pattern
CIRC_NUMBER_PATTERN = re.compile(r'(?:رقم|:)\s*(\d{4})/(\d{1,2})')


def extract_date(text: str) -> Optional[str]:
    """Extract date from text, return as YYYY-MM-DD"""
    # Look for "تونس في" followed by date
    match = re.search(r'(?:تونس\s*في|في\s*:?)\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{4})', text)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
    # Try generic date pattern
    match = DATE_PATTERN.search(text)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
    return None


def extract_circulaire_number(text: str) -> Optional[str]:
    """Extract circulaire number like 2025/01"""
    match = CIRC_NUMBER_PATTERN.search(text)
    if match:
        year, num = match.groups()
        return f"{year}/{num.zfill(2)}"
    return None


def find_category_sections(text: str) -> list:
    """Find all medication category sections in the text"""
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
                    "match_text": match.group()
                })
    
    # Sort by position
    sections.sort(key=lambda x: x["start"])
    
    # Remove duplicates (overlapping matches)
    filtered = []
    for s in sections:
        if not filtered or s["start"] >= filtered[-1]["end"]:
            filtered.append(s)
    
    return filtered


def find_section_breaks(text: str) -> list:
    """Find positions where medication sections end"""
    breaks = []
    for pattern in SECTION_BREAK_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            breaks.append(match.start())
    return sorted(breaks)


def extract_laboratory_name(text_chunk: str) -> Optional[str]:
    """Extract laboratory name from a text chunk"""
    lines = text_chunk.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        # Skip empty lines and lines with Arabic
        if not line or re.search(r'[\u0600-\u06FF]', line):
            continue
        
        # Check if it looks like a laboratory name (all caps, reasonable length)
        if len(line) > 3 and line.upper() == line:
            # Clean up common suffixes/patterns
            lab_name = re.sub(r'\s+', ' ', line).strip()
            # Filter out things that aren't lab names
            if not re.match(r'^[\d\.\,\|\-\s]+$', lab_name):  # Not just numbers/punctuation
                if not re.match(r'^(Bt|Fl|Sol|Comp|Gel|mg|ml|µg)', lab_name):  # Not dosage forms
                    return lab_name
    
    return None


def clean_medication_name(name: str) -> str:
    """Clean up medication name from OCR artifacts"""
    if not name:
        return name
    # Remove leading/trailing brackets
    name = re.sub(r'^[\[\]]+|[\[\]]+$', '', name)
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def parse_medication_line(line: str, current_lab: str = None) -> Optional[dict]:
    """Parse a single medication line"""
    line = line.strip()
    if not line:
        return None
    
    # Remove RTL/LTR markers and pipe characters
    line = line.replace('\u200e', '').replace('\u200f', '')
    line = line.replace('|', ' ')
    line = re.sub(r'\s+', ' ', line).strip()
    
    # Pattern 1: Code at start (digital PDFs)
    # CODE NAME ... PRICE1 PRICE2 PRICE3 [CATEGORY] [MARGIN]
    match = MEDICATION_PATTERN.search(line)
    if match:
        code, name, price1, price2, price3, cat, margin = match.groups()
        return {
            "code": code,
            "name": clean_medication_name(name),
            "laboratory": current_lab,
            "price_wholesale": float(price1.replace(',', '.')),
            "price_pharmacy": float(price2.replace(',', '.')),
            "price_public": float(price3.replace(',', '.')),
            "category": cat if cat and cat != '-' else None,
            "margin": float(margin.replace(',', '.')) if margin else None,
        }
    
    # Pattern 2: Code at end (OCR'd PDFs - RTL text gets code at end)
    # NAME ... PRICE1 PRICE2 PRICE3 [CATEGORY] [MARGIN] CODE
    # Handles OCR artifacts: ']' after price, '_' after category, '{' before margin, '10,240' instead of '0,240'
    pattern_code_end = re.compile(
        r'^(.+?)\s+'  # name at start
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 1
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 2
        r'(\d{1,3}[,\.]\d{3})[\]\s]*'  # price 3 (with possible ] from OCR)
        r'([A-C])[_\s]*'  # category (with possible _ from OCR)
        r'[\{\[]?[01]?(\d[,\.]\d{3})[\}\]]?\s*'  # margin (OCR may add leading 1 or 0, or brackets)
        r'(\d{6})\s*$'  # code at end
    )
    match = pattern_code_end.search(line)
    if match:
        name, price1, price2, price3, cat, margin, code = match.groups()
        return {
            "code": code,
            "name": clean_medication_name(name),
            "laboratory": current_lab,
            "price_wholesale": float(price1.replace(',', '.')),
            "price_pharmacy": float(price2.replace(',', '.')),
            "price_public": float(price3.replace(',', '.')),
            "category": cat if cat and cat != '-' else None,
            "margin": float(margin.replace(',', '.')) if margin else None,
        }
    
    # Pattern 2b: Code at end with 3 prices, category is "-" (no margin)
    # NAME ... PRICE1 PRICE2 PRICE3 - CODE
    pattern_code_end_dash = re.compile(
        r'^(.+?)\s+'  # name at start
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 1
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 2
        r'(\d{1,3}[,\.]\d{3})[\]\s]*'  # price 3 (with possible ] from OCR)
        r'-\s*'  # category is -
        r'(\d{6})\s*$'  # code at end
    )
    match = pattern_code_end_dash.search(line)
    if match:
        name, price1, price2, price3, code = match.groups()
        return {
            "code": code,
            "name": clean_medication_name(name),
            "laboratory": current_lab,
            "price_wholesale": float(price1.replace(',', '.')),
            "price_pharmacy": float(price2.replace(',', '.')),
            "price_public": float(price3.replace(',', '.')),
            "category": None,  # - means no category
            "margin": None,
        }
    
    # Pattern 2c: Code at end with 3 prices but no category/margin
    # NAME ... PRICE1 PRICE2 PRICE3 CODE
    pattern_code_end_simple = re.compile(
        r'^(.+?)\s+'  # name at start
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 1
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 2
        r'(\d{1,3}[,\.]\d{3})[\]\s]+'  # price 3 (with possible ] from OCR)
        r'(\d{6})\s*$'  # code at end (directly after price3)
    )
    match = pattern_code_end_simple.search(line)
    if match:
        name, price1, price2, price3, code = match.groups()
        return {
            "code": code,
            "name": clean_medication_name(name),
            "laboratory": current_lab,
            "price_wholesale": float(price1.replace(',', '.')),
            "price_pharmacy": float(price2.replace(',', '.')),
            "price_public": float(price3.replace(',', '.')),
            "category": None,
            "margin": None,
        }
    
    # Pattern 3: Alternative - simpler pattern for code at start
    match = MEDICATION_PATTERN_ALT.search(line)
    if match:
        code, name, price1, price2, price3 = match.groups()
        cat_match = re.search(r'\s([A-C])\s', line[match.end():] if match.end() < len(line) else '')
        margin_match = re.search(r'(\d[,\.]\d{3})\s*$', line)
        
        return {
            "code": code,
            "name": clean_medication_name(name),
            "laboratory": current_lab,
            "price_wholesale": float(price1.replace(',', '.')),
            "price_pharmacy": float(price2.replace(',', '.')),
            "price_public": float(price3.replace(',', '.')),
            "category": cat_match.group(1) if cat_match else None,
            "margin": float(margin_match.group(1).replace(',', '.')) if margin_match else None,
        }
    
    # Pattern 4: Code at end, simpler
    pattern_simple_end = re.compile(
        r'^([A-Z].+?)\s+'  # name starting with letter
        r'(\d+[,\.]\d+)\s+'  # price 1
        r'(\d+[,\.]\d+)\s+'  # price 2
        r'.*?'  # anything (category, margin, etc)
        r'(\d{6})\s*$'  # code at end
    )
    match = pattern_simple_end.search(line)
    if match:
        name, price1, price2, code = match.groups()
        return {
            "code": code,
            "name": clean_medication_name(name),
            "laboratory": current_lab,
            "price_wholesale": float(price1.replace(',', '.')),
            "price_pharmacy": float(price2.replace(',', '.')),
            "price_public": None,  # Missing from OCR
            "category": None,
            "margin": None,
        }
    
    # Pattern 5: Code at end with only 2 prices (OCR missed third price)
    pattern_2prices_end = re.compile(
        r'^([A-Z].+?)\s+'  # name starting with letter
        r'(\d+[,\.]\d+)\s+'  # price 1
        r'(\d+[,\.]\d+)\s+'  # price 2
        r'([A-C\-])?\s*'  # category (optional)
        r'(\d[,\.]\d{3})?\s*'  # margin (optional)
        r'(\d{6})\s*$'  # code at end
    )
    match = pattern_2prices_end.search(line)
    if match:
        name, price1, price2, cat, margin, code = match.groups()
        return {
            "code": code,
            "name": clean_medication_name(name),
            "laboratory": current_lab,
            "price_wholesale": float(price1.replace(',', '.')),
            "price_pharmacy": float(price2.replace(',', '.')),
            "price_public": None,
            "category": cat if cat and cat != '-' else None,
            "margin": float(margin.replace(',', '.')) if margin else None,
        }
    
    # Pattern 6: NO CODE - OCR with 3 prices (code is on another line or missing)
    # NAME ... PRICE1 PRICE2 PRICE3 CATEGORY MARGIN (no code at end)
    # Clean any OCR artifacts like brackets
    clean_line = line.replace(']', '').replace('[', '')
    pattern_no_code = re.compile(
        r'^([A-Z][A-Za-z0-9\s\.\-\(\)/\+µ]+?)\s+'  # name starting with uppercase letter
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 1 (wholesale)
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 2 (pharmacy)
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 3 (public)
        r'([A-C])\s+'  # category
        r'(\d[,\.]\d{3})\s*$'  # margin at end
    )
    match = pattern_no_code.search(clean_line)
    if match:
        name, price1, price2, price3, cat, margin = match.groups()
        # Only accept if name looks like a medication (not a header or lab name)
        if re.search(r'\d+\s*(mg|ml|μg|µg|%|Comp|Bt|Fl|Sol|Gel)', name, re.IGNORECASE):
            return {
                "code": None,  # No code available
                "name": clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": float(price3.replace(',', '.')),
                "category": cat,
                "margin": float(margin.replace(',', '.')) if margin else None,
            }
    
    # Pattern 7: NO CODE - OCR with 2 prices only (missing public price)
    # NAME ... PRICE1 PRICE2 CATEGORY MARGIN (no code, no public price)
    pattern_2_prices_no_code = re.compile(
        r'^([A-Z][A-Za-z0-9\s\.\-\(\)/\+µ]+?)\s+'  # name
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 1 (wholesale)
        r'(\d{1,3}[,\.]\d{3})\s+'  # price 2 (pharmacy)
        r'([A-C])\s+'  # category
        r'(\d[,\.]\d{3})\s*$'  # margin
    )
    match = pattern_2_prices_no_code.search(clean_line)
    if match:
        name, price1, price2, cat, margin = match.groups()
        # Only accept if name looks like a medication
        if re.search(r'\d+\s*(mg|ml|μg|µg|%|Comp|Bt|Fl|Sol|Gel)', name, re.IGNORECASE):
            return {
                "code": None,  # No code available
                "name": clean_medication_name(name),
                "laboratory": current_lab,
                "price_wholesale": float(price1.replace(',', '.')),
                "price_pharmacy": float(price2.replace(',', '.')),
                "price_public": None,  # Missing from OCR
                "category": cat,
                "margin": float(margin.replace(',', '.')) if margin else None,
            }
    
    return None


def is_laboratory_line(line: str) -> bool:
    """Check if a line is likely a laboratory name"""
    # Clean RTL/LTR markers
    line = line.replace('\u200e', '').replace('\u200f', '').strip()
    
    if not line or len(line) < 4:
        return False
    
    # Skip lines with lots of numbers (prices, codes)
    digit_count = sum(1 for c in line if c.isdigit())
    if digit_count > 3:
        return False
    
    # Skip lines that are mostly Arabic
    arabic_count = sum(1 for c in line if '\u0600' <= c <= '\u06FF')
    if arabic_count > len(line) * 0.3:
        return False
    
    # Skip dosage forms and common non-lab patterns
    skip_patterns = [
        r'^(Bt|BT|Fl|FL|Sol|SOL|Comp|COMP|Gel|GEL|Ser|SER|Pde|mg|ml|μg|µg)\b',
        r'^\d',  # starts with digit
        r'^[\|\-\.\s]+$',  # just punctuation
        r'(mois|Vie|AMM|EXP)',  # common text in med descriptions
    ]
    for pattern in skip_patterns:
        if re.match(pattern, line, re.IGNORECASE):
            return False
    
    # Must contain letters
    if not re.search(r'[A-Za-z]', line):
        return False
    
    # Likely a lab name if it contains common pharma suffixes
    if re.search(r'(PHARMA|PHARM|LAB|S\.?A\.?\.?|LLC|GMBH|LTD|INC|SANTE|HEALTH|SCIENCES?|INDUSTRIES?)\b', line, re.IGNORECASE):
        return True
    
    # Or if it's all caps and reasonable length (excluding spaces/punctuation)
    alpha_chars = re.sub(r'[^A-Za-z]', '', line)
    if alpha_chars.upper() == alpha_chars and 3 <= len(alpha_chars) <= 60:
        # But not if it's a medication name pattern
        if not re.search(r'\d+\s*(mg|ml|μg|µg|%)', line, re.IGNORECASE):
            return True
    
    return False


def parse_medications_from_section(text: str, section_info: dict) -> list:
    """Parse all medications from a section of text"""
    medications = []
    current_lab = None
    pending_lab_lines = []  # For multi-line lab names
    
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Clean RTL markers early
        clean_line = line.replace('\u200e', '').replace('\u200f', '').strip()
        
        # Check if this is a laboratory line
        if is_laboratory_line(clean_line):
            # Check if this continues a previous lab name
            # (lab names that span multiple lines typically end with AND, &, or are all caps continuation)
            if pending_lab_lines and (
                pending_lab_lines[-1].rstrip().endswith('AND') or
                pending_lab_lines[-1].rstrip().endswith('&') or
                (clean_line.isupper() and len(clean_line.split()) <= 3)
            ):
                pending_lab_lines.append(clean_line)
            else:
                # Start new lab name - save previous if exists
                if pending_lab_lines:
                    current_lab = ' '.join(pending_lab_lines)
                pending_lab_lines = [clean_line]
            continue
        
        # If we have pending lab lines and this isn't a lab line, finalize the lab name
        if pending_lab_lines:
            current_lab = ' '.join(pending_lab_lines)
            pending_lab_lines = []
        
        # Try to parse as medication
        med = parse_medication_line(line, current_lab)
        if med:
            med["type"] = section_info.get("type", "new")
            med["specialty"] = section_info.get("specialty", "human")
            med["origin"] = section_info.get("origin", "local")
            
            # Try to calculate missing price_public from price_pharmacy
            # Using price-tier based markup ratios derived from actual data:
            # - ph >= 25: ratio 1.316 (31.6% markup)
            # - ph 8-25:  ratio 1.351 (35.1% markup)
            # - ph 3-8:   ratio 1.389 (38.9% markup)
            # - ph < 3:   ratio 1.429 (42.9% markup)
            if med.get("price_public") is None and med.get("price_pharmacy"):
                ph = med["price_pharmacy"]
                if ph >= 25:
                    ratio = 1.316
                elif ph >= 8:
                    ratio = 1.351
                elif ph >= 3:
                    ratio = 1.389
                else:
                    ratio = 1.429
                calculated = ph * ratio
                # Round to 3 decimal places
                med["price_public"] = round(calculated, 3)
                med["price_public_calculated"] = True
            
            medications.append(med)
    
    # Don't forget last pending lab
    if pending_lab_lines:
        current_lab = ' '.join(pending_lab_lines)
    
    return medications


def parse_circulaire(raw_text: str, filename: str = None) -> dict:
    """Parse a complete circulaire text into structured data"""
    result = {
        "filename": filename,
        "date": extract_date(raw_text),
        "circulaire_number": extract_circulaire_number(raw_text),
        "medications": [],
        "sections_found": [],
    }
    
    # Find all category sections
    sections = find_category_sections(raw_text)
    section_breaks = find_section_breaks(raw_text)
    
    for i, section in enumerate(sections):
        # Determine section end
        section_end = len(raw_text)
        
        # End at next section
        if i + 1 < len(sections):
            section_end = min(section_end, sections[i + 1]["start"])
        
        # End at section break
        for brk in section_breaks:
            if brk > section["end"] and brk < section_end:
                section_end = brk
                break
        
        # Extract section text
        section_text = raw_text[section["end"]:section_end]
        
        # Parse medications from this section
        meds = parse_medications_from_section(section_text, section)
        
        result["sections_found"].append({
            "type": section["type"],
            "specialty": section["specialty"],
            "origin": section["origin"],
            "medications_count": len(meds),
        })
        
        result["medications"].extend(meds)
    
    return result


def process_json_file(json_path: str) -> dict:
    """Process a JSON file from the extraction step"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    text = data.get("text", "")
    filename = os.path.basename(json_path)
    
    return parse_circulaire(text, filename)


def main():
    """Process all JSON files in output/json directory"""
    import glob
    
    json_dir = "output/json"
    output_dir = "output/parsed"
    os.makedirs(output_dir, exist_ok=True)
    
    all_results = []
    
    for json_path in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        print(f"Processing: {json_path}")
        try:
            result = process_json_file(json_path)
            
            # Save individual parsed result
            out_path = os.path.join(output_dir, os.path.basename(json_path))
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            print(f"  → Found {len(result['medications'])} medications in {len(result['sections_found'])} sections")
            all_results.append(result)
            
        except Exception as e:
            print(f"  ⚠ Error: {e}")
    
    # Save combined results
    combined_path = os.path.join(output_dir, "_all_circulaires.json")
    with open(combined_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    # Create simplified output grouped by circulaire
    simplified = []
    for r in all_results:
        if not r['medications']:
            continue
            
        # Group medications by laboratory and type
        meds_by_lab = {}
        for med in r['medications']:
            lab = med.get('laboratory') or 'Unknown'
            # Clean lab name (remove RTL markers)
            lab = lab.replace('\u200e', '').replace('\u200f', '').strip()
            
            if lab not in meds_by_lab:
                meds_by_lab[lab] = []
            
            meds_by_lab[lab].append({
                'code': med['code'],
                'name': med['name'],
                'price_public': med['price_public'],
                'price_pharmacy': med['price_pharmacy'],
                'price_wholesale': med['price_wholesale'],
                'category': med['category'],
                'type': med['type'],  # 'new' or 'revised'
            })
        
        # Create entry for each laboratory
        for lab, meds in meds_by_lab.items():
            # Determine overall type
            types = set(m['type'] for m in meds)
            entry_type = 'revised' if 'revised' in types else 'new'
            
            simplified.append({
                'date': r['date'],
                'circulaire': r['circulaire_number'] or r['filename'].replace('.json', ''),
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
    
    # Save simplified format
    simplified_path = os.path.join(output_dir, "_simplified.json")
    with open(simplified_path, 'w', encoding='utf-8') as f:
        json.dump(simplified, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Processed {len(all_results)} files")
    print(f"💾 Combined results saved to: {combined_path}")
    print(f"💾 Simplified results saved to: {simplified_path}")
    
    # Summary
    total_meds = sum(len(r['medications']) for r in all_results)
    print(f"📊 Total medications found: {total_meds}")
    print(f"📊 Total laboratory entries: {len(simplified)}")


if __name__ == "__main__":
    main()
