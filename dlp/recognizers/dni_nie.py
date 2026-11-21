import re
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"

# Tolerates the separators people use when writing a DNI/NIE by hand or
# in forms: thousand-separator dots, spaces, or hyphens ("12.345.678-Z",
# "X 1234567 L"), as well as the no-separator format ("12345678Z").
_CANDIDATE = re.compile(
    r"\b(?:[XYZxyz][-.\s]?(?:\d[-.\s]?){7}[A-Za-z]|(?:\d[-.\s]?){7,8}[A-Za-z])\b"
)


def _control_letter(number: int) -> str:
    return _LETTERS[number % 23]


def _is_valid(raw: str) -> bool:
    clean = re.sub(r"[-.\s]", "", raw).upper()
    letter, body = clean[-1], clean[:-1]
    if body[0] in "XYZ":
        digits = body[1:]
        if not digits.isdigit() or len(digits) != 7:
            return False
        number = int(str("XYZ".index(body[0])) + digits)
    else:
        if not body.isdigit() or len(body) not in (7, 8):
            return False
        number = int(body)
    return letter == _control_letter(number)


class DniNieRecognizer(EntityRecognizer):
    """Spanish DNI and NIE: separator-tolerant regex + control-digit
    validation (checksum modulo 23, the same algorithm Presidio's own
    EsNifRecognizer/EsNieRecognizer use).

    Replaces the native recognizers because those require the number
    written with no internal separators, while in practice a DNI is often
    written with thousand-separator dots ("12.345.678-Z") or with a hyphen
    after the foreigner's letter ("X-1234567-L") — cases confirmed to be
    missed by the native ones.
    """

    ENTITY = "DNI_NIE"
    SCORE = 0.95

    def __init__(self) -> None:
        super().__init__(supported_entities=[self.ENTITY], supported_language="es", name="DniNieRecognizer")

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: List[str], nlp_artifacts: Optional[NlpArtifacts] = None
    ) -> List[RecognizerResult]:
        if self.ENTITY not in entities:
            return []
        results = []
        for match in _CANDIDATE.finditer(text):
            if _is_valid(match.group()):
                results.append(
                    RecognizerResult(
                        entity_type=self.ENTITY,
                        start=match.start(),
                        end=match.end(),
                        score=self.SCORE,
                    )
                )
        return EntityRecognizer.remove_duplicates(results)
