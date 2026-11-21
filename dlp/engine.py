from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import PhoneRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from dlp.filters import (
    drop_person_in_addresses,
    drop_person_with_digits,
    drop_phone_inside_iban,
    trim_person_honorifics,
    trim_trailing_whitespace,
)
from dlp.recognizers.case_person import CasePersonRecognizer
from dlp.recognizers.dni_nie import DniNieRecognizer
from dlp.recognizers.iban_linebreak import IbanLineBreakRecognizer
from dlp.recognizers.secret import SecretRecognizer
from dlp.recognizers.self_intro_person import SelfIntroPersonRecognizer

LANGUAGE = "es"

# Entity type detected by Presidio -> exact label required by the assignment.
ENTITY_LABEL_MAP = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "DNI_NIE": "DNI_NIE",
    "IBAN_CODE": "IBAN",
    "SECRET": "SECRET",
}

# Spanish context words to boost the PhoneRecognizer's confidence score.
_PHONE_CONTEXT = ["teléfono", "móvil", "celular", "llamar", "tel", "fijo", "whatsapp"]

# The assignment asks us to recognize phone numbers from all of Europe, not
# just Spain (same scope as IBAN, which already covers all 76 countries in
# its own registry without any restriction on our side). ISO region codes
# for `phonenumbers`. Each region was tested against a battery of "this is
# NOT a phone number" values (postal codes, IPs, reference numbers, a
# dotted DNI without a valid control letter, a UUID, bare digit runs of
# 4-10 digits) and 11 were excluded for producing real false positives —
# almost all small countries whose national numbers are just a handful of
# bare digits with no area code, the same shape as a DNI, a reference
# number, or a postal code:
#   - LU (Luxembourg): accepts almost any bare 4-5 digit run as "valid"
#     ("4502", "8742", "46100"...), even at leniency=3.
#   - DK (Denmark): Danish numbers are 8 bare digits, same shape as a DNI
#     without its control letter or an internal reference ("87654321").
#   - NO (Norway): matched a 5-digit postal code.
#   - FO (Faroe Islands): matched an IP address inside a connection string.
#   - CY, GI, LV, MT: 8 bare digits, same shape as a DNI ("22334455").
#   - MC (Monaco): 8 bare digits, matched a DNI with dots and an invalid
#     control letter ("33.445.566-C" — the DNI itself was correctly left
#     untouched, but the digits alone were tagged PHONE).
#   - AD (Andorra): matched bare 6-digit runs ("111111", "123456").
#   - PL (Poland): 9 bare digits — the exact same shape as a valid Spanish
#     mobile number ("612345678"), which is far more likely in a Spanish
#     document and would otherwise get fought over by two regions.
_EUROPE_REGIONS = (
    "AL", "AT", "BA", "BE", "BG", "BY", "CH", "CZ", "DE", "EE",
    "ES", "FI", "FR", "GB", "GR", "HR", "HU", "IE", "IS", "IT", "LI",
    "LT", "MD", "ME", "MK", "NL", "PT", "RO",
    "RS", "RU", "SE", "SI", "SK", "SM", "TR", "UA", "VA", "XK",
)


def _build_analyzer() -> AnalyzerEngine:
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": LANGUAGE, "model_name": "es_core_news_md"}],
        }
    )
    nlp_engine = provider.create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=[LANGUAGE])

    # The default PhoneRecognizer doesn't include the ES region (nor the
    # rest of Europe): replace it with one configured for all of Europe.
    analyzer.registry.remove_recognizer("PhoneRecognizer")
    analyzer.registry.add_recognizer(
        PhoneRecognizer(
            supported_language=LANGUAGE,
            supported_regions=_EUROPE_REGIONS,
            context=_PHONE_CONTEXT,
        )
    )

    # The native IbanRecognizer only accepts the code in uppercase. Forcing
    # re.IGNORECASE was tried, but its regex uses [A-Z0-9]{4} to delimit the
    # IBAN's blocks: without distinguishing case, short Spanish words
    # ("para", "la"...) count as "one more block" and the match overflows
    # into the next sentence. The change was dropped — in practice an IBAN
    # is almost always written in uppercase anyway (ISO convention).

    # The native ES_NIF/ES_NIE recognizers don't tolerate separators
    # (thousand-separator dots, a hyphen after the foreigner's letter);
    # they're replaced by our own recognizer.
    analyzer.registry.remove_recognizer("EsNifRecognizer")
    analyzer.registry.remove_recognizer("EsNieRecognizer")
    analyzer.registry.add_recognizer(DniNieRecognizer())

    analyzer.registry.add_recognizer(SecretRecognizer())
    analyzer.registry.add_recognizer(CasePersonRecognizer(nlp_engine=nlp_engine, language=LANGUAGE))
    analyzer.registry.add_recognizer(SelfIntroPersonRecognizer())
    analyzer.registry.add_recognizer(IbanLineBreakRecognizer())

    return analyzer


_analyzer: AnalyzerEngine | None = None
_anonymizer: AnonymizerEngine | None = None


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        _analyzer = _build_analyzer()
    return _analyzer


def _get_anonymizer() -> AnonymizerEngine:
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = AnonymizerEngine()
    return _anonymizer


def _split_paragraphs(text: str) -> list[tuple[int, int]]:
    """(start, end) spans for each paragraph: consecutive non-blank lines,
    cut at every blank line. Analyzing paragraph by paragraph (instead of
    the whole document in one go) prevents a name at one point in the text
    from flipping its prediction just because of unrelated content in a
    distant paragraph — confirmed with an 800-line document: well-written
    names that worked fine in isolation went undetected inside the full
    document. We don't cut on sentences (periods) because "Titular: Dr.
    Ana Muñoz Rubio" has a period right after "Dr." — cutting there would
    separate the honorific from the name.
    """
    spans = []
    para_start = None
    pos = 0
    for line in text.splitlines(keepends=True):
        line_start = pos
        pos += len(line)
        if line.strip() == "":
            if para_start is not None:
                spans.append((para_start, line_start))
                para_start = None
        elif para_start is None:
            para_start = line_start
    if para_start is not None:
        spans.append((para_start, len(text)))
    return spans or [(0, len(text))]


def find_entities(text: str) -> list[tuple[int, int, str]]:
    """Analyze `text` and return (start, end, label) tuples, already
    filtered and remapped to the assignment's 6 labels, without
    anonymizing yet. Used by both `anonymize_text` and `eval.py`, so the
    latter can compare against a gold standard without having to
    re-derive positions from the final anonymized text.
    """
    analyzer = _get_analyzer()
    results = []
    for start, end in _split_paragraphs(text):
        chunk_results = analyzer.analyze(
            text=text[start:end],
            language=LANGUAGE,
            entities=list(ENTITY_LABEL_MAP.keys()),
        )
        for r in chunk_results:
            r.start += start
            r.end += start
        results.extend(chunk_results)

    results = trim_trailing_whitespace(text, results)
    results = drop_person_in_addresses(text, results)
    results = drop_person_with_digits(text, results)
    results = drop_phone_inside_iban(results)
    results = trim_person_honorifics(text, results)
    for result in results:
        result.entity_type = ENTITY_LABEL_MAP[result.entity_type]
    return [(r.start, r.end, r.entity_type) for r in results]


def anonymize_text(text: str) -> str:
    """Replace sensitive data in `text` with its <TAG> labels."""
    anonymizer = _get_anonymizer()

    results = [
        RecognizerResult(entity_type=label, start=start, end=end, score=1.0)
        for start, end, label in find_entities(text)
    ]

    operators = {
        label: OperatorConfig("replace", {"new_value": f"<{label}>"})
        for label in set(ENTITY_LABEL_MAP.values())
    }

    anonymized = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
    return anonymized.text
