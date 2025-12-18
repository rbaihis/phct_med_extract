#!/usr/bin/env python3
"""Debug section boundaries"""

import sys
sys.path.insert(0, '/home/seif/Other_Healio/probing_phct/phct_med_extract')

from circulaire_service import normalize_arabic, CirculaireParser
import requests
import pdfplumber

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

sections = CirculaireParser._find_category_sections(text)
print(f"Found {len(sections)} sections:\n")

for i, section in enumerate(sections):
    print(f"Section {i}:")
    print(f"  Type: {section['type']}")
    print(f"  Specialty: {section['specialty']}")
    print(f"  Origin: {section['origin']}")
    print(f"  Start: {section['start']}")
    print(f"  End: {section['end']}")
    
    # Calculate section_end as the code does
    section_end = len(text)
    if i + 1 < len(sections):
        section_end = min(section_end, sections[i + 1]["start"])
    
    print(f"  Section text end (calculated): {section_end}")
    print(f"  Section text snippet: {repr(text[section['end']:section_end][:100])}")
    print()
