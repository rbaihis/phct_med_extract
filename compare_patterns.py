#!/usr/bin/env python3
"""Compare pattern vs actual text"""

# What we found in PDF: ةيرطيب (position 9-14 in "ةدروتسم ةيرطيب تاصاصتخإ")
actual_vet = "ةيرطيب"
print("Actual veterinary word from PDF:")
print(f"Text: {actual_vet}")
print(f"Repr: {repr(actual_vet)}")
for i, char in enumerate(actual_vet):
    print(f"  [{i}] {char} = U+{ord(char):04X}")

# What our pattern is looking for
pattern_vet = "بيطرية"  # From the regex patterns
print("\n\nPattern is searching for:")
print(f"Text: {pattern_vet}")
print(f"Repr: {repr(pattern_vet)}")
for i, char in enumerate(pattern_vet):
    print(f"  [{i}] {char} = U+{ord(char):04X}")

# The key is: RTL text is reversed!
# Standard (LTR order in source): بيطرية = b y T r y h
# Reversed (RTL in PDF): ةيرطيب = h y r T y b

print("\n\n=== THE ISSUE ===")
print("Standard LTR order: ب ي ط ر ي ة")
print("Reversed RTL order: ة ي ر ط ي ب")
print("\nOur patterns match standard LTR, but PDF text is in reversed RTL!")
