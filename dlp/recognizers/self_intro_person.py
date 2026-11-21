import re
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# A first name used alone, with no surname, gives spaCy's NER very little
# signal: it catches some ("Carlos explicó que...") and misses others
# ("Hola! Soy Pedro.") with no clear pattern between them (LIM-4 in the
# log). Widening detection to any capitalized word would risk tagging
# ordinary words that happen to sit at the start of a sentence. Instead,
# this recognizer only fires right after one of a small, fixed set of
# Spanish self-introduction phrases — a context specific enough that a
# capitalized word there is reliably a name, not a sentence-initial noun.
#
# The negative lookahead skips a SECOND capitalized word right after the
# first: that shape ("Soy Pedro Martínez") is a full name, already
# covered by the native SpacyRecognizer/CasePersonRecognizer, so this
# recognizer only ever adds the single-word case those two miss.
_PATTERN = re.compile(
    r"\b(?:soy|me llamo|mi nombre es|me presento como)\s+"
    r"(?P<person>[A-Za-zÁÉÍÓÚÑáéíóúñ]+)(?!\s+[A-ZÁÉÍÓÚÑ])",
    re.IGNORECASE,
)


class SelfIntroPersonRecognizer(EntityRecognizer):
    """A bare first name right after a fixed Spanish self-introduction phrase."""

    ENTITY = "PERSON"
    SCORE = 0.85

    def __init__(self) -> None:
        super().__init__(supported_entities=[self.ENTITY], supported_language="es", name="SelfIntroPersonRecognizer")

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: List[str], nlp_artifacts: Optional[NlpArtifacts] = None
    ) -> List[RecognizerResult]:
        if self.ENTITY not in entities:
            return []
        results = []
        for match in _PATTERN.finditer(text):
            start, end = match.span("person")
            if not text[start].isupper():
                continue
            results.append(
                RecognizerResult(entity_type=self.ENTITY, start=start, end=end, score=self.SCORE)
            )
        return EntityRecognizer.remove_duplicates(results)
