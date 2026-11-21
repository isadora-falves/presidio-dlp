import re
import string
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Presidio's native IbanRecognizer only allows a space or hyphen between
# the 4-character blocks ("[ -]?"), not a line break. In a document whose
# text is wrapped at some width, a long IBAN can get split right there
# (confirmed: "ES91 2100\n0418 4502 0005 1332" went undetected). This
# recognizer covers only that case: it requires an actual line break in
# the match, so it doesn't duplicate the native recognizer's work on the
# normal case.
_CANDIDATE = re.compile(r"\b[A-Z]{2}[0-9]{2}(?:[ \t\r\n-]?[A-Z0-9]{4}){2,7}\b")

_LETTERS = {ord(d): str(i) for i, d in enumerate(string.digits + string.ascii_uppercase)}


def _is_valid_iban(raw: str) -> bool:
    iban = re.sub(r"\s|-", "", raw)
    if not (15 <= len(iban) <= 34):
        return False
    rearranged = (iban[4:] + iban[:4]).translate(_LETTERS)
    try:
        return int(rearranged) % 97 == 1
    except ValueError:
        return False


class IbanLineBreakRecognizer(EntityRecognizer):
    """An IBAN split by a line break inside the number itself."""

    ENTITY = "IBAN_CODE"
    SCORE = 1.0

    def __init__(self) -> None:
        super().__init__(supported_entities=[self.ENTITY], supported_language="es", name="IbanLineBreakRecognizer")

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: List[str], nlp_artifacts: Optional[NlpArtifacts] = None
    ) -> List[RecognizerResult]:
        if self.ENTITY not in entities:
            return []
        results = []
        for match in _CANDIDATE.finditer(text):
            raw = match.group()
            if "\n" not in raw and "\r" not in raw:
                continue
            if _is_valid_iban(raw):
                results.append(
                    RecognizerResult(
                        entity_type=self.ENTITY,
                        start=match.start(),
                        end=match.end(),
                        score=self.SCORE,
                    )
                )
        return EntityRecognizer.remove_duplicates(results)
