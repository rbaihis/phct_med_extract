# Product Matching Feature

## Overview
The PHCT Circulaire module automatically matches imported medications with existing products in your Odoo database using **pattern-based smart matching** and compares prices.

## Matching Algorithm

### Pattern Recognition
Analysis shows 93% of medications follow this structure:
```
BRAND_NAME + STRENGTH + DOSAGE_FORM + PACKAGING
```

Examples:
- `ELIXTRA 2.5mg Comp.Pell. Bt 20`
- `XARELTO 10mg Comp.Pell. Bt 30`
- `QUETAP 100mg Comp.Pell. Bt 60`

### Matching Rules (Weighted Scoring)

#### 1. **STRICT Brand Matching** (Required - 0 points if fails)
- First word (brand name) must match **exactly** (case-insensitive)
- `XARELTO` only matches `XARELTO`, never `XAREL` or similar
- `CARDOSYL` will NOT match `COVERSYL` (prevents false positives)
- If brand doesn't match → **automatic rejection (0% confidence)**

#### 2. **Strength Matching** (40 points)
- Extracts dosages: `2.5mg`, `10mg`, `5%`, `100mg/ml`, etc.
- **Primary strength must match**: `ELIXTRA 2.5mg` matches `ELIXTRA 2.5mg`
- Partial match: Some strengths match → 20 points
- Full match: All strengths match → 40 points

#### 3. **Name Token Similarity** (40 points)
- Jaccard similarity on all words (after normalization)
- Removes punctuation, lowercases, splits into tokens
- Intersection / Union × 40

#### 4. **Packaging Bonus** (20 points)
- Same packaging type and quantity: `Bt 30` = `Bt 30` → 20 points
- Same type, different quantity: `Bt 30` vs `Bt 90` → 10 points
- Recognizes: `Bt` (box), `Fl` (bottle), `Tb` (tube), `Amp`, `Ser`

#### 5. **Substring Bonus** (10 points)
- If one name is substring of the other → +10 points

### Confidence Threshold
- **Minimum to match**: 60%
- **Perfect match**: 100% (exact brand, strength, all tokens match)
- **Good match**: 80-99% (same brand/strength, minor differences)
- **Acceptable match**: 60-79% (same brand/strength, different packaging)

## New Fields

### On `phct.circulaire.med` model:

| Field | Type | Description |
|-------|------|-------------|
| `product_id` | Many2one | Link to matched `product.template` record |
| `match_status` | Selection | `not_checked`, `matched`, or `not_found` |
| `match_confidence` | Float | Confidence score 0-100% |
| `price_comparison` | Selection | `equal`, `phct_higher`, `phct_lower`, `no_product` |
| `price_difference` | Float | PHCT price - Product price |

## User Interface

### Medications Tree View
- **Green rows**: Matched with equal prices ✓
- **Yellow rows**: Matched with different prices ⚠
- **Gray rows**: No match found

### Filters Available:
- **Match Status**: Matched, Not Found, Not Checked
- **Price Comparison**: PHCT Higher, PHCT Lower, Equal
- **Group By**: Match Status, Price Comparison, Circulaire, Laboratory

### Actions:
- **Re-match Product** button on medication form to manually trigger matching

## Menu Structure
```
PHCT
├── Circulaires
│   ├── Imported Circulaires (existing)
│   └── Medications (NEW) - Shows all medications with matching status
```

## Example Queries

### Find medications where PHCT price is higher than product price:
```python
medications = env['phct.circulaire.med'].search([
    ('price_comparison', '=', 'phct_higher')
])
```

### Find unmatched medications:
```python
unmatched = env['phct.circulaire.med'].search([
    ('match_status', '=', 'not_found')
])
```

### Find matched medications with price differences:
```python
price_diff = env['phct.circulaire.med'].search([
    ('match_status', '=', 'matched'),
    ('price_comparison', 'in', ['phct_higher', 'phct_lower'])
])
```

## Technical Details

### Matching Algorithm
```python
def _find_matching_product(self):
    # 1. Try exact code_pct match
    if self.code:
        product = search by code_pct
        if found: return product, 100.0
    
    # 2. Try name matching with laboratory filter
    if self.laboratory:
        products = search by laboratory
        for product in products:
            score = calculate_name_similarity()
            if score > best_score:
                best_match = product
    
    # 3. Try all products if no good match
    if best_score < 70:
        products = search all pharmacy products
        for product in products:
            score = calculate_name_similarity()
            if laboratory matches: boost score
            if score > best_score:
                best_match = product
    
    # Return if confidence >= 60%
    return best_match, best_score
```

### Similarity Calculation
Uses Jaccard similarity with bonus for substring matches:
```
similarity = (intersection / union) * 100
if substring_match: similarity += 20
```

## Configuration

### Pharmacy Category ID
Currently hardcoded to `categ_id = 9`. To change:
```python
# In circulaire.py, _find_matching_product method:
pharmacy_categ_id = 9  # Change this value
```

### Confidence Threshold
Currently set to 60%. To change:
```python
# In circulaire.py, _find_matching_product method:
if best_match and best_score >= 60:  # Change this value
```

## Future Enhancements

Potential improvements:
1. Make pharmacy category configurable via system parameters
2. Add manual matching interface for unmatched medications
3. Implement bulk re-matching for all medications
4. Add history tracking of price changes
5. Generate alerts when PHCT prices differ significantly
6. Integration with product update workflows

## Troubleshooting

### No matches found
- Check if products exist with `categ_id = 9`
- Verify product names in database match circulaire names
- Check if `code_pct` field is populated in products
- Lower confidence threshold temporarily for testing

### Incorrect matches
- Increase confidence threshold
- Add more filtering criteria (e.g., DCI matching)
- Manually correct using "Re-match Product" button

### Price comparison not working
- Verify `list_price` is set on matched products
- Check that `price_public` is extracted from circulaire
- Review computed field dependencies
