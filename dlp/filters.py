import re

# Words and abbreviations that precede a street name in Spain (Calle Goya,
# Avda. Dalí, Pza. Colón...). spaCy's NER often tags the street name as
# PERSON when it coincides with a real surname (Goya, Dalí, Colón...), so
# this is used as a context guard to discard that false positive, without
# inventing a new label the assignment doesn't ask for.
#
# Abbreviation sources: Spanish address abbreviation guide
# (https://www.52spain.com/d/79835) and CIEE's Spanish street guide
# (https://www.ciee.org/go-abroad/work/teach-english-abroad/blog/your-guide-spanish-street-abbreviations).
_ONE_WORD_INDICATORS = {
    "calle", "c/",
    "avenida", "avda.", "avda", "av.", "av",
    "plaza", "pza.", "pza", "pl.", "pl",
    "paseo", "pº", "po.", "po",
    "rambla",
    "bulevar", "bulevard",
    "carretera", "ctra.", "ctra",
    "glorieta",
    "travesía", "travesia", "trav.",
    "callejón", "callejon", "cjón.", "cjon.",
    "camino", "cno.", "cno",
    "ronda", "rda.", "rda",
    "vía", "via",
    "urbanización", "urbanizacion", "urb.", "urb",
    "polígono", "poligono", "pol.",
    "autovía", "autovia",
    "cuesta",
    "pasaje", "pje.", "pje",
}
_TWO_WORD_INDICATORS = {"gran vía", "gran via"}


# Example: _words_before("Vive en la Calle Goya", 17, 2) -> ["la", "Calle"]
def _words_before(text: str, pos: int, count: int):
    prefix = text[:pos].rstrip()
    return re.findall(r"[^\s,]+", prefix)[-count:]


def is_address_context(text: str, start: int) -> bool:
    """True if `start` comes right after a street-type indicator.

    Example: is_address_context("Vive en la Calle Goya", 17) -> True
    (17 is where "Goya" starts).
    """
    words = _words_before(text, start, 2)
    if not words:
        return False
    if words[-1].lower().strip(".,") in _ONE_WORD_INDICATORS:
        return True
    if len(words) == 2 and " ".join(w.lower().strip(".,") for w in words) in _TWO_WORD_INDICATORS:
        return True
    return False


def drop_person_in_addresses(text: str, results: list) -> list:
    """Drop PERSON results that start right after a street-type word.

    Example: "Vive en la Calle Goya" with a PERSON result on "Goya" ->
    that result is dropped (it's a street name, not a person).
    """
    return [
        r for r in results
        if not (r.entity_type == "PERSON" and is_address_context(text, r.start))
    ]


def drop_person_with_digits(text: str, results: list) -> list:
    """Drop PERSON results that contain a digit or an underscore.

    A real name never has either; when they show up it's because the
    native SpacyRecognizer confused an unknown alphanumeric code with a
    proper noun — confirmed with "AAA123456" (the Spanish passport
    format) and, scanning a Python source file for the Parte 2 git hook,
    "DB_IBAN" (an identifier, tagged PERSON at 0.85 just for being an
    all-caps word next to "=").

    Example: "DB_IBAN" tagged PERSON -> dropped; "Carlos" tagged PERSON
    -> kept (no digit, no underscore).
    """
    return [
        r for r in results
        if not (
            r.entity_type == "PERSON"
            and any(c.isdigit() or c == "_" for c in text[r.start:r.end])
        )
    ]


# "D." and "Dña." already fall outside the PERSON span (confirmed), but
# "Sra."/"Dra." (with a period, from the native SpacyRecognizer) and
# "SRA"/"DRA" without a period (from CasePersonRecognizer) were
# mistakenly included inside the span.
_HONORIFIC_PREFIX = re.compile(
    r"^(?:sr|sra|srta|dr|dra|d|dña|lic|ing|prof|sta)\.?\s+", re.IGNORECASE
)


def trim_person_honorifics(text: str, results: list) -> list:
    """Trim a leading honorific ("Sra.", "DRA"...) off a PERSON span.

    Example: "Sra. María López" tagged PERSON -> span trimmed to just
    "María López" ("Sra." stays outside, untouched).
    """
    for r in results:
        if r.entity_type == "PERSON":
            m = _HONORIFIC_PREFIX.match(text[r.start:r.end])
            if m:
                r.start += m.end()
    return results


# The native SpacyRecognizer sometimes merges a leading "Hola" into the
# PERSON span itself — confirmed: "Hola Laura," and "Hola Carlos," both
# tag the whole "Hola <Name>" as one PERSON, not just the name. Other
# greetings tried ("Saludos", "Querida", "Buenos días") didn't show the
# same merge, so this is scoped to the one word actually seen doing it.
_GREETING_PREFIX = re.compile(r"^hola\s+", re.IGNORECASE)


def trim_person_greeting(text: str, results: list) -> list:
    """Trim a leading "Hola " off a PERSON span.

    Example: "Hola Laura," tagged PERSON as a whole -> span trimmed to
    just "Laura" ("Hola " stays outside, untouched).
    """
    for r in results:
        if r.entity_type == "PERSON":
            m = _GREETING_PREFIX.match(text[r.start:r.end])
            if m:
                r.start += m.end()
    return results


# Words that precede a product/reference code, not a person's document
# number. A checksum-valid DNI shape isn't unique to a real DNI: an
# 8-digit product code can pass the same mod-23 checksum purely by
# coincidence (confirmed: "Producto 12345678Z: teclado inalámbrico" and
# four more codes in the same list — all five pass the checksum, none is
# a real person's document). Checksum alone can't tell them apart here;
# context can.
_PRODUCT_ONE_WORD = {
    "producto", "productos", "artículo", "articulo", "artículos", "articulos",
    "referencia", "ref.", "ref", "modelo", "sku", "pedido", "pedidos",
}
_PRODUCT_PHRASES = {
    "código de producto", "codigo de producto",
    "número de pedido", "numero de pedido",
}

# A connector (verb or punctuation) is allowed between the indicator and
# the number itself ("el código de producto ES 12345678Z"), the same
# idea as SECRET's own connector handling.
_PRODUCT_CONTEXT = re.compile(
    r"(?:"
    + "|".join(re.escape(w) for w in sorted(_PRODUCT_ONE_WORD | _PRODUCT_PHRASES, key=len, reverse=True))
    + r")\s*(?:es|son|era|eran|fue|fueron|:|=)?\s*$",
    re.IGNORECASE,
)


def is_product_context(text: str, start: int) -> bool:
    """True if `start` is a product/reference-code number: a product
    indicator word right before it, directly or through a connector.

    Example: is_product_context("Producto 12345678Z", 9) -> True
    (9 is where the number right after "Producto" starts).
    """
    return bool(_PRODUCT_CONTEXT.search(text[:start]))


def drop_dni_nie_in_product_context(text: str, results: list) -> list:
    """Drop DNI_NIE results that start right after a product/reference word.

    Example: "Producto 12345678Z: teclado inalámbrico" with a DNI_NIE
    result on the number right after "Producto" -> that result is
    dropped (checksum-valid by coincidence, but it's a product code,
    not a document number).
    """
    return [
        r for r in results
        if not (r.entity_type == "DNI_NIE" and is_product_context(text, r.start))
    ]


# Fixed, known English words that occasionally get mistaken for a person
# name by the native SpacyRecognizer when they show up capitalized outside
# any Spanish sentence context (a code comment, a docstring, an HTTP
# header example). Confirmed: "Authorization: Bearer <token>" tagged
# "Bearer" itself as PERSON at the default score, inside the Parte 2
# integration test files (a realistic case: that exact header appears in
# any API client's docstring/example).
_NON_PERSON_WORDS = {"bearer"}


def drop_known_non_person_words(text: str, results: list) -> list:
    """Drop PERSON results whose text is a fixed, known non-name word.

    Example: "Authorization: Bearer <token>" with a PERSON result on
    "Bearer" -> that result is dropped.
    """
    return [
        r for r in results
        if not (r.entity_type == "PERSON" and text[r.start:r.end].strip().lower() in _NON_PERSON_WORDS)
    ]


# Presidio's native EmailRecognizer explicitly allows "=" inside the local
# part of an address (its own regex: "[!#$%&'*+\-/=?^_`{|}~\w]", an RFC
# 5322 edge case) — confirmed: a plain ".env"-style assignment (a variable
# name, then "=", then an address) gets swallowed whole as a single
# "email", variable name included, because nothing stops the match before
# the "=". A real email essentially never contains "=" in its local part,
# so the span is trimmed to start right after the last "=" before the "@".
def trim_email_key_prefix(text: str, results: list) -> list:
    """Trim a leading "VARIABLE=" off an EMAIL span.

    Example: "DESTINO=ana@ejemplo.com" tagged as one whole EMAIL span ->
    trimmed to just "ana@ejemplo.com" ("DESTINO=" stays outside, untouched).
    """
    for r in results:
        if r.entity_type == "EMAIL_ADDRESS":
            span = text[r.start:r.end]
            at = span.find("@")
            if at != -1:
                last_eq = span.rfind("=", 0, at)
                if last_eq != -1:
                    r.start += last_eq + 1
    return results


# A "user@host" shape right after "scheme://" is the authority part of a
# URL, not a real email — confirmed: "smtps://apikey@smtp.ejemplo.com:587"
# tags "apikey@smtp.ejemplo.com" as EMAIL, indistinguishable on its own
# from a real address. Only the "scheme://" immediately before it (no
# whitespace in between) reveals what it actually is.
def drop_email_in_url(text: str, results: list) -> list:
    """Drop EMAIL results that are the user-info part of a URL.

    Example: "smtps://usuario@servidor.com" with an EMAIL result on
    "usuario@servidor.com" -> that result is dropped.
    """
    kept = []
    for r in results:
        if r.entity_type == "EMAIL_ADDRESS":
            back = max(text.rfind(" ", 0, r.start), text.rfind("\n", 0, r.start), text.rfind("\t", 0, r.start))
            if "://" in text[back + 1:r.start]:
                continue
        kept.append(r)
    return kept


def drop_phone_inside_iban(results: list) -> list:
    """Drop PHONE results whose span falls entirely inside an IBAN.

    After widening the PhoneRecognizer to all of Europe (not just Spain),
    some country (confirmed: Germany) accepts as "valid" a chunk of an
    IBAN split by a line break ("0418 4502 0005 1332", inside "ES91
    2100\\n0418 4502 0005 1332") — Presidio doesn't drop overlaps between
    different entity types on its own.

    Example: a PHONE result fully contained inside an already-found
    IBAN result -> the PHONE result is dropped, the IBAN one stays.
    """
    iban_spans = [(r.start, r.end) for r in results if r.entity_type == "IBAN_CODE"]
    return [
        r for r in results
        if not (
            r.entity_type == "PHONE_NUMBER"
            and any(r.start >= s and r.end <= e for s, e in iban_spans)
        )
    ]


def trim_trailing_whitespace(text: str, results: list) -> list:
    """Trim leading/trailing whitespace off any result's span.

    When a chunk given to the analyzer ends right after a line break
    (paragraph-by-paragraph analysis, see ADR-23), the native
    SpacyRecognizer sometimes stretches a PERSON span to swallow that
    trailing "\\n" — confirmed: "Nombre: Miguel Torres\\n" tagged
    "Miguel Torres\\n" as PERSON, and replacing it ate the blank line
    that was supposed to separate it from the next field. No entity
    should ever start or end on whitespace.

    Example: "Miguel Torres\\n" tagged PERSON as a whole -> span
    trimmed to just "Miguel Torres" (the trailing "\\n" stays outside).
    """
    for r in results:
        while r.end > r.start and text[r.end - 1].isspace():
            r.end -= 1
        while r.end > r.start and text[r.start].isspace():
            r.start += 1
    return results
