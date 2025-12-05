# PCT Circulaire Service

A Python service for downloading, extracting, and parsing medication circulaires from the Tunisian Pharmaceutical Central (PCT - Pharmacie Centrale de Tunisie).

## Features

- **PDF Download**: Automatically downloads circulaires from phct.com.tn
- **Text Extraction**: Extracts text from digital PDFs using pdfplumber
- **OCR Support**: Falls back to Tesseract OCR for scanned/image-based PDFs
- **Arabic Normalization**: Handles Arabic presentation forms and RTL text
- **Medication Parsing**: Extracts structured medication data including:
  - Code, Name, Laboratory
  - Wholesale, Pharmacy, and Public prices
  - Category (A/B/C) and margin
  - Type (new/revised), Specialty (human/veterinary), Origin (local/imported)
- **Price Calculation**: Auto-calculates missing public prices using tier-based markup ratios
- **Flexible Configuration**: Supports custom URLs, year ranges, and stop conditions

---

## Installation

### System Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-ara \
    tesseract-ocr-fra \
    poppler-utils

# macOS
brew install tesseract tesseract-lang poppler
```

### Python Dependencies

**Minimal requirements** (create `requirements.txt`):

```
requests>=2.28.0
pdfplumber>=0.9.0
pytesseract>=0.3.10
Pillow>=9.0.0
opencv-python-headless>=4.7.0
numpy>=1.21.0
```

Install with:
```bash
pip install -r requirements.txt
```

### Full Requirements (from tested environment)

```
requests==2.32.5
pdfplumber==0.11.8
pytesseract==0.3.13
Pillow==12.0.0
opencv-python-headless==4.12.0.88
numpy==2.2.6
pdfminer.six==20251107
pypdfium2==5.1.0
```

---

## Quick Start

### Command Line Usage

```bash
# Process single circulaire by index
python circulaire_service.py -i 21

# Process with specific year
python circulaire_service.py -i 21 -y 25

# Process a range and save output
python circulaire_service.py -r 1 47 -o output/

# Process local PDF file
python circulaire_service.py -f /path/to/circ2125.pdf

# Process from URL
python circulaire_service.py -u "http://www.phct.com.tn/images/DocumentsPCT/Circulaires/Circ2125.pdf"

# Check for new circulaires
python circulaire_service.py --check-new --known 1 2 3 4 5
```

### Python API Usage

```python
from circulaire_service import (
    process_circulaire,
    process_circulaire_range,
    check_for_new_circulaires
)

# Process single circulaire (downloads from web)
result = process_circulaire(index=21, year="25")

if result.success:
    print(f"Date: {result.parsed['date']}")
    print(f"Medications: {len(result.parsed['medications'])}")
    
    # Simplified format grouped by laboratory
    for entry in result.simplified:
        print(f"Lab: {entry['laboratory']}")
        for med in entry['medications']:
            print(f"  - {med['name']}: {med['sale_price']} TND")

# Process from local file
result = process_circulaire(pdf_path="/path/to/file.pdf")

# Process from URL
result = process_circulaire(pdf_url="http://example.com/circ.pdf")
```

---

## API Reference

### `process_circulaire()`

Process a single circulaire PDF.

```python
def process_circulaire(
    index: int = None,           # Circulaire index (e.g., 21 for circ2125.pdf)
    year: str = "25",            # Year suffix (default: current year)
    pdf_url: str = None,         # Direct URL to PDF
    pdf_path: str = None,        # Local file path
    pdf_content: bytes = None,   # Raw PDF bytes
    base_url: str = None,        # Custom base URL
) -> CirculaireResult
```

**Returns** `CirculaireResult`:
```python
{
    "success": True,
    "filename": "Circ2125.pdf",
    "error": None,
    "parsed": {
        "filename": "Circ2125.pdf",
        "date": "2025-05-09",
        "circulaire_number": "2025/21",
        "medications": [
            {
                "code": "303760",
                "name": "DIARETYL 2mg Gél. Bt 10",
                "laboratory": "GALIEN PHARMACEUTICALS S.A",
                "price_wholesale": 1.403,
                "price_pharmacy": 1.526,
                "price_public": 2.18,
                "category": "C",
                "margin": 0.429,
                "type": "new",
                "specialty": "human",
                "origin": "local"
            }
        ],
        "sections_found": [...]
    },
    "simplified": [
        {
            "date": "2025-05-09",
            "circulaire": "2025/21",
            "laboratory": "GALIEN PHARMACEUTICALS S.A",
            "type": "new",
            "medications": [
                {
                    "code": "303760",
                    "name": "DIARETYL 2mg Gél. Bt 10",
                    "sale_price": 2.18,
                    "pharmacy_price": 1.526,
                    "wholesale_price": 1.403,
                    "category": "C"
                }
            ]
        }
    ]
}
```

### `process_circulaire_range()`

Process multiple circulaires.

```python
def process_circulaire_range(
    start: int = 1,                      # Starting index
    end: int = 99,                       # Ending index (inclusive)
    year: str = "25",                    # Year suffix
    years: List[str] = None,             # Multiple years: ["23", "24", "25"]
    delay: float = 1.0,                  # Delay between requests (seconds)
    base_url: str = None,                # Custom base URL
    max_consecutive_failures: int = 0,   # Stop after N failures (0 = never)
) -> Dict
```

**Returns**:
```python
{
    "results": [...],           # List of CirculaireResult
    "all_parsed": [...],        # All parsed circulaires
    "all_simplified": [...],    # All simplified entries (flattened)
    "summary": {
        "total": 47,
        "successful": 47,
        "failed": 0,
        "total_medications": 124
    }
}
```

### `check_for_new_circulaires()`

Check for new circulaires on the server.

```python
def check_for_new_circulaires(
    known_indices: List[int],            # Already processed indices
    year: str = "25",                    # Year suffix
    years: List[str] = None,             # Multiple years
    max_index: int = 99,                 # Maximum index to check
    base_url: str = None,                # Custom base URL
    max_consecutive_failures: int = 20,  # Stop after N 404s
    delay: float = 0.2,                  # Delay between HEAD requests
) -> Union[List[int], Dict[str, List[int]]]
```

**Returns**: 
- `List[int]` - New indices found (single year)
- `Dict[str, List[int]]` - New indices by year (multiple years)

---

## Use Cases

### Cron Job: Check for New Circulaires

```python
from circulaire_service import check_for_new_circulaires, process_circulaire

# Get known indices from your database
known = [1, 2, 3, ..., 47]

# Check for new files (stops after 20 consecutive 404s)
new_indices = check_for_new_circulaires(
    known_indices=known,
    year="25",
    max_consecutive_failures=20,
    delay=0.2
)

# Process and save new ones
for idx in new_indices:
    result = process_circulaire(index=idx, year="25")
    if result.success:
        # Save to database
        save_to_db(result.simplified)
```

### Process Multiple Years

```python
batch = process_circulaire_range(
    start=1,
    end=99,
    years=[f"{y:02d}" for y in range(20, 27)],  # 2020-2026
    delay=1.0,
    max_consecutive_failures=20
)

print(f"Found {batch['summary']['total_medications']} medications")
```

### Odoo Integration

```python
# In your Odoo cron job or controller
from circulaire_service import process_circulaire, check_for_new_circulaires

class CirculaireCron(models.Model):
    _name = 'circulaire.cron'
    
    def check_new_circulaires(self):
        # Get known circulaire indices from Odoo
        known = self.env['circulaire.record'].search([]).mapped('index')
        
        # Check for new
        new_indices = check_for_new_circulaires(known, year="25")
        
        for idx in new_indices:
            result = process_circulaire(index=idx, year="25")
            if result.success:
                for entry in result.simplified:
                    # Create/update records in Odoo
                    self.env['medication.record'].create({
                        'date': entry['date'],
                        'laboratory': entry['laboratory'],
                        'type': entry['type'],
                        # ... map medications
                    })
```

---

## Price Calculation

When `price_public` is missing from OCR output, it's calculated using tier-based markup ratios derived from actual circulaire data:

| Pharmacy Price | Markup Ratio | Example |
|---------------|--------------|---------|
| ≥ 25 TND | 1.316 (31.6%) | 30 → 39.48 |
| ≥ 8 TND | 1.351 (35.1%) | 10 → 13.51 |
| ≥ 3 TND | 1.389 (38.9%) | 5 → 6.95 |
| < 3 TND | 1.429 (42.9%) | 2 → 2.86 |

---

## Output Formats

### Parsed Format (Full)
Complete extraction with all metadata, useful for archiving.

### Simplified Format
Grouped by laboratory, ideal for database import:
```json
[
  {
    "date": "2025-05-09",
    "circulaire": "2025/21",
    "laboratory": "GALIEN PHARMACEUTICALS S.A",
    "type": "new",
    "medications": [
      {
        "code": "303760",
        "name": "DIARETYL 2mg Gél. Bt 10",
        "sale_price": 2.18,
        "pharmacy_price": 1.526,
        "wholesale_price": 1.403,
        "category": "C"
      }
    ]
  }
]
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `BASE_URL` | phct.com.tn URL | Source URL for PDFs |
| `DEFAULT_YEAR` | "25" | Year suffix for filenames |
| `delay` | 1.0 | Seconds between requests |
| `max_consecutive_failures` | 20 | Stop after N failures |

---

## Troubleshooting

### OCR Not Working
```bash
# Check Tesseract is installed
tesseract --version

# Check Arabic language pack
tesseract --list-langs | grep ara
```

### PDF Conversion Failing
```bash
# Check poppler-utils
pdftoppm -v
```

### Missing Dependencies
```bash
pip install pdfplumber pytesseract opencv-python-headless Pillow requests numpy
```

---

## License

Internal use only.

## Author

Created for Healio medication database integration.
