# utils/arabic.py
"""
Utilities for handling Arabic text display and normalization.
"""

import arabic_reshaper
from bidi.algorithm import get_display


def display_arabic(text: str) -> str:
    """Convert Arabic text for proper RTL display in output."""
    if not text:
        return ""
    reshaped_text = arabic_reshaper.reshape(text)
    return get_display(reshaped_text)


def normalize_arabic_text(text: str) -> str:
    """
    Normalize Arabic text by:
    - Removing diacritics (tashkeel)
    - Standardizing hamzas and alifs
    - Collapsing whitespace
    """
    import unicodedata
    import re

    if not text:
        return ""

    # Normalize and remove diacritics
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = unicodedata.normalize('NFC', text)

    # Normalize alifs and hamzas
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'ؤ', 'و', text)
    text = re.sub(r'ئ', 'ي', text)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text