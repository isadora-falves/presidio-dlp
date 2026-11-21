import re
import string
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Presidio's native IbanRecognizer only allows a space or hyphen between
# the 4-character blocks ("[ -]?"), not a line break or a dot. Two real
# gaps confirmed: an IBAN wrapped across a line break in a document
# ("ES91 2100\n0418 4502 0005 1332"), and one written with dots as
# thousand-style separators ("ES47.2100.1800.0502.0005.1332", valid
# checksum, went undetected). This recognizer covers only separators the
# native one rejects, so it never duplicates its work on the normal case.
_CANDIDATE = re.compile(r"\b[A-Z]{2}[0-9]{2}(?:[ \t\r\n.-]?[A-Z0-9]{4}){2,7}\b")

_LETTERS = {ord(d): str(i) for i, d in enumerate(string.digits + string.ascii_uppercase)}


def _is_valid_iban(raw: str) -> bool:
    iban = re.sub(r"[\s.-]", "", raw)
    if not (15 <= len(iban) <= 34):
        return False
    rearranged = (iban[4:] + iban[:4]).translate(_LETTERS)
    try:
        return int(rearranged) % 97 == 1
    except ValueError:
        return False


class IbanLineBreakRecognizer(EntityRecognizer):
    """An IBAN written with a separator the native recognizer rejects: a
    line break, or a dot, inside the number itself."""

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
            if not any(c in raw for c in "\n\r."):
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
