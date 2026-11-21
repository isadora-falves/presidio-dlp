import re
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"

# Tolera los separadores con los que la gente escribe un DNI/NIE a mano o en
# formularios: puntos de millar, espacios o guiones ("12.345.678-Z",
# "X 1234567 L"), además del formato sin separadores ("12345678Z").
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
    """DNI y NIE españoles: regex tolerante a separadores + validación por
    dígito de control (checksum módulo 23, mismo algoritmo que usan
    EsNifRecognizer/EsNieRecognizer de Presidio).

    Sustituye a los recognizers nativos porque estos exigen el documento
    sin separadores internos, y en la práctica el DNI se escribe a menudo
    con puntos de millar ("12.345.678-Z") o con guion tras la letra de
    extranjero ("X-1234567-L") — casos que se comprobaron sin cubrir.
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
