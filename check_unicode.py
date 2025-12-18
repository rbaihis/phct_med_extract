#!/usr/bin/env python3
"""Check exact Unicode of the veterinary text"""

import sys
import unicodedata
sys.path.insert(0, '/home/seif/Other_Healio/probing_phct/phct_med_extract')

from circulaire_service import normalize_arabic
import requests
import pdfplumber
import re

# Download PDF 45
url = 'http://www.phct.com.tn/images/DocumentsPCT/Circulaires/Circ4525.pdf'
resp = requests.get(url, timeout=20)
pdf_path = '/tmp/test_circ4525.pdf'
with open(pdf_path, 'wb') as f:
    f.write(resp.content)

# Extract text
with pdfplumber.open(pdf_path) as pdf:
    text = ''
    for page in pdf.pages:
        text += normalize_arabic(page.extract_text() or '')

# Find veterinary text
for match in re.finditer(r'.{0,30}رطيب.{0,30}', text):
    vet_text = match.group(0)
    print(f"\nFound veterinary text at position {match.start()}:")
    print(f"Text: {vet_text}")
    print(f"Repr: {repr(vet_text)}")
    print("Unicode codepoints:")
    for i, char in enumerate(vet_text):
        if char.strip():
            print(f"  [{i}] {char} = U+{ord(char):04X} ({unicodedata.name(char, 'UNKNOWN')})")
