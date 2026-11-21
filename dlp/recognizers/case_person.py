import re
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngine

_UPPER_WORD = r"[A-ZÁÉÍÓÚÑÜ]{2,}(?:[-'][A-ZÁÉÍÓÚÑÜ]{2,})?"
# A capitalized-initial word (the normal shape of a name: "Isadora",
# "FOnseca", "ISADORA"...). Deliberately excludes lowercase words ("con",
# "de", "y"...), so "MORENO, con DNI..." isn't confused with "SURNAME,
# GivenName".
_GIVEN_WORD = r"[A-ZÁÉÍÓÚÑÜ][A-Za-zÁÉÍÓÚÑÜáéíóúñü]+(?:[-'][A-Za-zÁÉÍÓÚÑÜáéíóúñü]{2,})?"

# "SURNAME(S), GivenName(s)": a common format in official forms and
# registries (records, minutes, signatures). The surname in uppercase
# comes first, separated by a comma.
_SURNAME_COMMA = re.compile(
    rf"\b({_UPPER_WORD}(?:\s+{_UPPER_WORD}){{0,2}}),\s+({_GIVEN_WORD}(?:\s+{_GIVEN_WORD}){{0,2}})\b"
)

_PARTICLES = {"de", "del", "la", "las", "los", "y"}
_EXTENDABLE_POS = {"PROPN", "NOUN"}

# Short, all-uppercase acronyms from this same assignment's own domain
# (document/finance/security terms), excluded from ever acting as a name
# anchor. Confirmed bug: "Los DNI, NIE e IBAN incluidos..." matched the
# "SURNAME, GivenName" shape (two uppercase words separated by a comma);
# re-normalized to "Nie Dni" and re-queried, spaCy's NER judged that a
# plausible two-word person name and confirmed the false match.
_STOPWORDS = {
    "dni", "nie", "nif", "cif", "iban", "pin", "cvv", "otp", "pdf",
    "api", "jwt", "uuid", "sms", "gps", "iva", "adn", "secret",
}

# Honorifics that act as an anchor even when not uppercase: "Titular: Dra.
# Carlos Mendoza Pérez, con documento..." (no verb after it, a
# form/registry-style sentence) wasn't detected by the native
# SpacyRecognizer — only when a verb was nearby ("Dra. Isadora Alves
# firmó...", confirmed in bitácora ADR-20).
_HONORIFICS = {"sr", "sra", "srta", "dr", "dra", "d", "dña", "lic", "ing", "prof", "sto", "sta"}

# A "Label:" at the start of a line (form/registry style: "Titular:
# GivenName Surname, con documento..."). Confirmed: this breaks the
# native NER even for a well-written name with a verb after it
# ("Titular: Ana del Carmen Vázquez-Puig, reside en Madrid." goes
# undetected; "El titular es Ana..." doesn't). The cause seems to be the
# ":" itself at the start of the "sentence" as far as the parser is
# concerned, not the shape of the name. Used as a forced anchor for the
# word right after it, even in normal upper/lowercase.
_LABEL_COLON = re.compile(r"(?m)^[ \t]*[A-ZÁÉÍÓÚÑÜ][\wÁÉÍÓÚÑÜáéíóúñü]*:[ \t]*")


def _title_case(text: str) -> str:
    return " ".join(
        word.lower() if word.lower() in _PARTICLES else
        "-".join(part[:1].upper() + part[1:].lower() for part in word.split("-"))
        for word in text.split(" ")
    )


def _is_anchor(token_text: str) -> bool:
    letters_only = token_text.replace("-", "")
    if letters_only.lower() in _STOPWORDS:
        return False
    if len(letters_only) >= 2 and letters_only.isalpha() and letters_only.isupper():
        return True
    return token_text.rstrip(".").lower() in _HONORIFICS


def _is_word(token_text: str) -> bool:
    # spaCy keeps a compound surname ("Vázquez-Puig") as a single
    # hyphenated token — without tolerating that here, the run used to
    # get cut right there.
    return len(token_text) >= 2 and token_text.replace("-", "").isalpha()


def _adjacent(prev_token, token) -> bool:
    gap = token.idx - (prev_token.idx + len(prev_token.text))
    return 0 <= gap <= 1


def _extendable(token_text: str, pos: str) -> bool:
    # Particles (de/del/la...) aren't a noun/proper noun to the parser,
    # but they are part of the name ("Ana DEL Carmen", "María DE LA
    # Torre"): without this, the run used to get cut right at the particle.
    return _is_anchor(token_text) or pos in _EXTENDABLE_POS or token_text.lower() in _PARTICLES


def _label_colon_anchors(text: str, tokens) -> set:
    """Indices of the tokens right after a "Label:" at the start of a
    line — forced as an anchor even when not uppercase nor an honorific.
    Only if spaCy already tags it PROPN: that way "Titular: El hombre..."
    doesn't force "El" (a determiner) as if it were a name."""
    anchors = set()
    for match in _LABEL_COLON.finditer(text):
        for i, tok in enumerate(tokens):
            if tok.idx >= match.end():
                if tok.pos_ in _EXTENDABLE_POS:
                    anchors.add(i)
                break
    return anchors


def _build_windows(text: str, tokens):
    """Group, around each uppercase/honorific word (or the word right
    after a "Label:"), the neighboring words that are a noun/proper
    noun/particle, stopping at the first verb, adverb, determiner, etc.
    Prevents a run from extending into ordinary sentence words ("DRA
    llegó temprano hoy" -> just "DRA", not the whole sentence)."""
    n = len(tokens)
    forced = _label_colon_anchors(text, tokens)
    used = [False] * n
    windows = []
    for i, tok in enumerate(tokens):
        if used[i] or not (_is_anchor(tok.text) or i in forced):
            continue
        lo = i
        while (
            lo - 1 >= 0
            and not used[lo - 1]
            and _is_word(tokens[lo - 1].text)
            and _extendable(tokens[lo - 1].text, tokens[lo - 1].pos_)
            and _adjacent(tokens[lo - 1], tokens[lo])
        ):
            lo -= 1
        hi = i
        while (
            hi + 1 < n
            and not used[hi + 1]
            and _is_word(tokens[hi + 1].text)
            and _extendable(tokens[hi + 1].text, tokens[hi + 1].pos_)
            and _adjacent(tokens[hi], tokens[hi + 1])
        ):
            hi += 1
        if hi > lo:
            for k in range(lo, hi + 1):
                used[k] = True
            windows.append((tokens[lo].idx, tokens[hi].idx + len(tokens[hi].text)))
    return windows


class CasePersonRecognizer(EntityRecognizer):
    """Names with irregular upper/lowercase, or with the surname before
    the given name (forms, letterheads, signatures, "SURNAME, GivenName"
    listings).

    spaCy's NER expects text in its natural capitalization ("GivenName
    Surname"); it fails on names written fully in uppercase, with
    upper/lowercase mixed within the same run, or with the surname first
    followed by a comma. Candidate words are grouped using spaCy's own
    grammatical tags (only a noun/proper noun chains onto an uppercase
    word — a verb or adverb cuts the run), normalized to Capitalized
    case, and re-queried against the NLP engine: it's only tagged if that
    second query finds a 2+ word PERSON inside the normalized text (which
    may be a part of the run, not necessarily the whole thing).
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

        # Case 1: "SURNAME(S), GivenName(s)" -> reordered before verifying.
        for match in _SURNAME_COMMA.finditer(text):
            surname, given = match.group(1), match.group(2)
            words = surname.split() + given.split()
            if any(w.lower() in _STOPWORDS for w in words):
                continue
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

        # Case 2: a grammar-bounded run with mixed upper/lowercase, with
        # or without the surname first, with no comma.
        tokens = list(nlp_artifacts.tokens)
        for win_start, win_end in _build_windows(text, tokens):
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
