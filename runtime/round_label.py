"""Parse only the known round-header ROI, after independent scene validation."""
import re

def parse_round_label(value):
 if not isinstance(value,str):return None
 compact=''.join(value.split())
 # Actual Windows OCR omitted the first/last Chinese glyph and returned '3 回'.
 # Still require the round unit; an unrelated bare number is never sufficient.
 match=re.fullmatch(r'(?:第)?([1-9][0-9]?)(?:回合|回)',compact)
 return int(match.group(1))if match else None
