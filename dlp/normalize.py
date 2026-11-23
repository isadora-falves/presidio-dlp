import unicodedata

# Letters from another script that a reader sees as a Latin letter or a
# digit, but that none of our ASCII-only regexes ([A-Z], \d...) ever
# match on their own. Confirmed in a stress test built on purpose
# (examples/01_archivo_trampa_105_casos.txt): Cyrillic "О"/"о" and Greek
# "Ο" standing in for Latin "O", Arabic-Indic digits standing in for
# 0-9, etc. This list is curated from characters actually seen tried
# against the engine, not the full Unicode confusables table.
_CONFUSABLES = {
    "О": "O", "о": "o",  # Cyrillic capital/small O (U+041E/U+043E)
    "Ο": "O",            # Greek capital Omicron (U+039F)
    "Ε": "E",            # Greek capital Epsilon (U+0395)
    "Β": "B",            # Greek capital Beta (U+0392)
    "Ζ": "Z",            # Greek capital Zeta (U+0396)
    "І": "I",            # Cyrillic Byelorussian-Ukrainian I (U+0406)
    "Ѕ": "S",            # Cyrillic Dze (U+0405)
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",  # Arabic-Indic digits
}


def normalize_with_map(text: str):
    """Fold common Unicode evasion tricks to plain ASCII before analysis,
    returning (normalized_text, index_map) where index_map[i] is the
    original-text index that normalized_text[i] came from — so a span
    found in the normalized text can still be applied to the original,
    unmodified text afterwards (map_span does that translation).

    Three independent tricks, each confirmed in the stress test above:
    - A letter from another script that LOOKS like a Latin letter or
      digit (Cyrillic "О", Arabic-Indic digits...) — folded via the
      curated table above, or via per-character NFKC for the cases
      Unicode itself treats as compatibility variants (full-width
      digits/letters, "mathematical bold" digits).
    - An invisible "format" character (zero-width space, word joiner,
      soft hyphen, a directional-embedding mark...) inserted between
      digits, or even inside a keyword like "pass<ZWSP>word", breaking
      a regex that expects them contiguous — dropped entirely (Unicode
      general category "Cf").
    - Exotic whitespace (thin space, no-break space) used as a
      digit-group separator — folded to a plain ASCII space (general
      category "Zs"), which the existing separator-tolerant regexes
      already accept via \\s.

    Deliberately NOT handled (needs semantic reconstruction, not
    normalization, and doesn't appear in realistic documents — see the
    bitácora for the full reasoning): digits spelled out as words,
    base64/JSON/HTML-encoded values, or a secret split across two
    variables or two sentences.
    """
    out_chars = []
    index_map = []
    for i, c in enumerate(text):
        category = unicodedata.category(c)
        if category == "Cf":
            continue
        if category == "Zs" and c != " ":
            replacement = " "
        elif c in _CONFUSABLES:
            replacement = _CONFUSABLES[c]
        else:
            n = unicodedata.normalize("NFKC", c)
            replacement = n if len(n) == 1 else c
        out_chars.append(replacement)
        index_map.append(i)
    return "".join(out_chars), index_map


def map_span(index_map, start: int, end: int, original_len: int):
    """Translate a (start, end) span found in the normalized text back
    to the matching span in the original text."""
    orig_start = index_map[start] if start < len(index_map) else original_len
    orig_end = index_map[end - 1] + 1 if end - 1 < len(index_map) else original_len
    return orig_start, orig_end
