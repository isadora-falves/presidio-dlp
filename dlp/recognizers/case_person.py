import re
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngine

_UPPER_WORD = r"[A-ZÁÉÍÓÚÑÜ]{2,}(?:[-'][A-ZÁÉÍÓÚÑÜ]{2,})?"
# Palabra con inicial mayúscula (forma normal de nombre: "Isadora",
# "FOnseca", "ISADORA"...). Excluye a propósito palabras en minúscula
# ("con", "de", "y"...), para que "MORENO, con DNI..." no se confunda con
# "APELLIDO, Nombre".
_GIVEN_WORD = r"[A-ZÁÉÍÓÚÑÜ][A-Za-zÁÉÍÓÚÑÜáéíóúñü]+(?:[-'][A-Za-zÁÉÍÓÚÑÜáéíóúñü]{2,})?"

# "APELLIDO(S), Nombre(s)": formato habitual en formularios y listados
# oficiales (registros, actas, firmas). El apellido en mayúsculas va
# primero, separado por una coma.
_SURNAME_COMMA = re.compile(
    rf"\b({_UPPER_WORD}(?:\s+{_UPPER_WORD}){{0,2}}),\s+({_GIVEN_WORD}(?:\s+{_GIVEN_WORD}){{0,2}})\b"
)

_PARTICLES = {"de", "del", "la", "las", "los", "y"}
_EXTENDABLE_POS = {"PROPN", "NOUN"}


def _title_case(text: str) -> str:
    return " ".join(
        word.lower() if word.lower() in _PARTICLES else
        "-".join(part[:1].upper() + part[1:].lower() for part in word.split("-"))
        for word in text.split(" ")
    )


def _is_anchor(token_text: str) -> bool:
    return len(token_text) >= 2 and token_text.isalpha() and token_text.isupper()


def _is_word(token_text: str) -> bool:
    return len(token_text) >= 2 and token_text.isalpha()


def _adjacent(prev_token, token) -> bool:
    gap = token.idx - (prev_token.idx + len(prev_token.text))
    return 0 <= gap <= 1


def _build_windows(tokens):
    """Agrupa, alrededor de cada palabra en MAYÚSCULAS, las palabras vecinas
    que son sustantivo/nombre propio (o también mayúsculas), deteniéndose en
    el primer verbo, adverbio, determinante, etc. Evita que una racha se
    extienda hacia palabras corrientes de la frase ("DRA llegó temprano
    hoy" -> solo "DRA", no toda la frase)."""
    n = len(tokens)
    used = [False] * n
    windows = []
    for i, tok in enumerate(tokens):
        if used[i] or not _is_anchor(tok.text):
            continue
        lo = i
        while (
            lo - 1 >= 0
            and not used[lo - 1]
            and _is_word(tokens[lo - 1].text)
            and (_is_anchor(tokens[lo - 1].text) or tokens[lo - 1].pos_ in _EXTENDABLE_POS)
            and _adjacent(tokens[lo - 1], tokens[lo])
        ):
            lo -= 1
        hi = i
        while (
            hi + 1 < n
            and not used[hi + 1]
            and _is_word(tokens[hi + 1].text)
            and (_is_anchor(tokens[hi + 1].text) or tokens[hi + 1].pos_ in _EXTENDABLE_POS)
            and _adjacent(tokens[hi], tokens[hi + 1])
        ):
            hi += 1
        if hi > lo:
            for k in range(lo, hi + 1):
                used[k] = True
            windows.append((tokens[lo].idx, tokens[hi].idx + len(tokens[hi].text)))
    return windows


class CasePersonRecognizer(EntityRecognizer):
    """Nombres con mayúsculas/minúsculas irregulares o con el apellido antes
    del nombre (formularios, membretes, firmas, listados "APELLIDO, Nombre").

    El NER de spaCy espera el texto en su capitalización natural ("Nombre
    Apellido"); falla con nombres todo en mayúsculas, con mayúsculas y
    minúsculas mezcladas en la misma racha, o con el apellido primero
    seguido de coma. Se agrupan las palabras candidatas usando las propias
    etiquetas gramaticales de spaCy (solo sustantivo/nombre propio se
    encadena junto a una palabra en mayúsculas — un verbo o adverbio corta
    la racha), se normaliza a Capitalizado, y se reconsulta al motor de
    NLP: solo se etiqueta si esa segunda consulta encuentra PERSON de 2 o
    más palabras dentro del texto normalizado (puede ser una parte, no
    necesariamente toda la racha).
    """

    ENTITY = "PERSON"
    SCORE = 0.85

    def __init__(self, nlp_engine: NlpEngine, language: str = "es") -> None:
        self._nlp_engine = nlp_engine
        self._language = language
        super().__init__(
            supported_entities=[self.ENTITY], supported_language=language, name="CasePersonRecognizer"
        )

    def load(self) -> None:
        pass

    def _confirmed_spans(self, normalized: str):
        artifacts = self._nlp_engine.process_text(normalized, self._language)
        return [
            (e.start_char, e.end_char)
            for e in artifacts.entities
            if e.label_ == "PERSON" and " " in normalized[e.start_char:e.end_char].strip()
        ]

    def analyze(
        self, text: str, entities: List[str], nlp_artifacts: Optional[NlpArtifacts] = None
    ) -> List[RecognizerResult]:
        if self.ENTITY not in entities or nlp_artifacts is None:
            return []

        results = []

        # Caso 1: "APELLIDO(S), Nombre(s)" -> se reordena para verificar.
        for match in _SURNAME_COMMA.finditer(text):
            surname, given = match.group(1), match.group(2)
            normalized = f"{_title_case(given)} {_title_case(surname)}"
            if self._confirmed_spans(normalized):
                results.append(
                    RecognizerResult(
                        entity_type=self.ENTITY,
                        start=match.start(),
                        end=match.end(),
                        score=self.SCORE,
                    )
                )

        # Caso 2: racha (acotada por gramática) con mayúsculas/minúsculas
        # mezcladas, con o sin el apellido primero, sin coma.
        tokens = list(nlp_artifacts.tokens)
        for win_start, win_end in _build_windows(tokens):
            run_text = text[win_start:win_end]
            normalized = _title_case(run_text)
            for start_rel, end_rel in self._confirmed_spans(normalized):
                results.append(
                    RecognizerResult(
                        entity_type=self.ENTITY,
                        start=win_start + start_rel,
                        end=win_start + end_rel,
                        score=self.SCORE,
                    )
                )

        return EntityRecognizer.remove_duplicates(results)
