import re

# Palabras y abreviaturas que anteceden el nombre de una vía en España (Calle
# Goya, Avda. Dalí, Pza. Colón...). spaCy suele etiquetar el nombre de la vía
# como PERSON cuando coincide con un apellido real (Goya, Dalí, Colón...),
# así que se usa como guardia de contexto para descartar ese falso positivo,
# sin inventar una etiqueta nueva que el enunciado no pide.
#
# Fuentes de las abreviaturas: guía de abreviaturas de direcciones españolas
# (https://www.52spain.com/d/79835) y guía de calles en español de CIEE
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


def _words_before(text: str, pos: int, count: int):
    prefix = text[:pos].rstrip()
    return re.findall(r"[^\s,]+", prefix)[-count:]


def is_address_context(text: str, start: int) -> bool:
    """True si `start` viene justo después de un indicador de tipo de vía."""
    words = _words_before(text, start, 2)
    if not words:
        return False
    if words[-1].lower().strip(".,") in _ONE_WORD_INDICATORS:
        return True
    if len(words) == 2 and " ".join(w.lower().strip(".,") for w in words) in _TWO_WORD_INDICATORS:
        return True
    return False


def drop_person_in_addresses(text: str, results: list) -> list:
    """Quita resultados PERSON cuyo inicio cae justo tras un tipo de vía."""
    return [
        r for r in results
        if not (r.entity_type == "PERSON" and is_address_context(text, r.start))
    ]


def drop_person_with_digits(text: str, results: list) -> list:
    """Quita resultados PERSON que contienen algún dígito.

    Un nombre real nunca lleva dígitos; cuando aparecen es porque el
    SpacyRecognizer nativo confundió un código alfanumérico desconocido
    (comprobado: "AAA123456", formato de pasaporte español, se marcaba
    como PERSON) con un nombre propio.
    """
    return [
        r for r in results
        if not (r.entity_type == "PERSON" and any(c.isdigit() for c in text[r.start:r.end]))
    ]


# "D." y "Dña." ya quedan fuera del span de PERSON (probado), pero "Sra."/
# "Dra." (con punto, del SpacyRecognizer nativo) y "SRA"/"DRA" sin punto
# (del CasePersonRecognizer) se incluían dentro del span por error.
_HONORIFIC_PREFIX = re.compile(
    r"^(?:sr|sra|srta|dr|dra|d|dña|lic|ing|prof|sta)\.?\s+", re.IGNORECASE
)


def trim_person_honorifics(text: str, results: list) -> list:
    """Recorta un honorífico inicial ("Sra.", "DRA"...) del span de PERSON."""
    for r in results:
        if r.entity_type == "PERSON":
            m = _HONORIFIC_PREFIX.match(text[r.start:r.end])
            if m:
                r.start += m.end()
    return results
