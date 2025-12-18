#!/usr/bin/env python3
"""Test script to examine PDF 45 and debug veterinary section detection"""

import sys
sys.path.insert(0, '/home/seif/Other_Healio/probing_phct/phct_med_extract')

from circulaire_service import process_circulaire, normalize_arabic
from parse_circulaire import CATEGORY_PATTERNS
import requests
import pdfplumber
import re

# Download PDF 45
print("Downloading Circ4525.pdf...")
url = 'http://www.phct.com.tn/images/DocumentsPCT/Circulaires/Circ4525.pdf'
resp = requests.get(url, timeout=20)
pdf_path = '/tmp/test_circ4525.pdf'
with open(pdf_path, 'wb') as f:
    f.write(resp.content)
print(f"Downloaded {len(resp.content)} bytes\n")

# Extract and normalize text
print("Extracting text...")
with pdfplumber.open(pdf_path) as pdf:
    text = ''
    for page in pdf.pages:
        text += normalize_arabic(page.extract_text() or '') + '\n'

print(f"Total text length: {len(text)} chars\n")

# Show text snippet around position 171 (where the human section was found)
print("=== Text from position 100-600 ===")
print(text[100:600])
print("\n=== Full text (first 1000 chars) ===")
print(repr(text[:1000]))

# Test ALL category patterns to see what matches
print("\n\n=== TESTING ALL CATEGORY PATTERNS ===")
for category, patterns in CATEGORY_PATTERNS.items():
    print(f"\n{category}:")
    found_any = False
    for pattern in patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            found_any = True
            for match in matches:
                print(f"  ✓ Pattern: {pattern[:50]}...")
                print(f"    Position: {match.start()}-{match.end()}")
                print(f"    Matched text: {repr(match.group(0))}")
                print(f"    Context: {repr(text[max(0, match.start()-20):match.end()+20])}")
    if not found_any:
        print(f"  ✗ NO MATCHES")

# Now test the full processing
print("\n\n=== FULL TEXT ===")
print(text)
print("\n\n=== RUNNING FULL PROCESSING ===")
result = process_circulaire(pdf_path=pdf_path)
parsed = result.parsed if hasattr(result, 'parsed') else result
print(f"Medications found: {len(parsed['medications']) if 'medications' in parsed else 0}")
print(f"Sections found: {parsed.get('sections_found', [])}")
print("\nMedications:")
if 'medications' in parsed:
    for med in parsed['medications']:
        print(f"  - {med['code']}: {med['name'][:40]}... ({med['specialty']}/{med['origin']})")
