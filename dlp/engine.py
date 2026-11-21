from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import PhoneRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from dlp.filters import drop_person_in_addresses, drop_person_with_digits, trim_person_honorifics
from dlp.recognizers.case_person import CasePersonRecognizer
from dlp.recognizers.dni_nie import DniNieRecognizer
from dlp.recognizers.iban_linebreak import IbanLineBreakRecognizer
from dlp.recognizers.secret import SecretRecognizer

LANGUAGE = "es"

# Entidad detectada por Presidio -> etiqueta exacta exigida por el enunciado.
ENTITY_LABEL_MAP = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "DNI_NIE": "DNI_NIE",
    "IBAN_CODE": "IBAN",
    "SECRET": "SECRET",
}

# Contexto en español para reforzar la confianza del PhoneRecognizer.
_PHONE_CONTEXT = ["teléfono", "móvil", "celular", "llamar", "tel", "fijo", "whatsapp"]


def _build_analyzer() -> AnalyzerEngine:
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": LANGUAGE, "model_name": "es_core_news_md"}],
        }
    )
    nlp_engine = provider.create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=[LANGUAGE])

    # El PhoneRecognizer por defecto no incluye la región ES: se sustituye
    # por uno configurado para España.
    analyzer.registry.remove_recognizer("PhoneRecognizer")
    analyzer.registry.add_recognizer(
        PhoneRecognizer(
            supported_language=LANGUAGE,
            supported_regions=("ES",),
            context=_PHONE_CONTEXT,
        )
    )

    # El IbanRecognizer nativo solo acepta el código en mayúsculas. Se probó
    # a forzar re.IGNORECASE, pero la regex usa [A-Z0-9]{4} para delimitar
    # los bloques del IBAN: sin distinguir mayúsculas, palabras españolas
    # cortas ("para", "la"...) cuentan como "un bloque más" y el match se
    # desborda hacia la frase siguiente. Se descartó el cambio — en la
    # práctica el IBAN casi siempre se escribe en mayúsculas (convención ISO).

    # ES_NIF/ES_NIE nativos no toleran separadores (puntos de millar, guion
    # tras la letra de extranjero); se sustituyen por un recognizer propio.
    analyzer.registry.remove_recognizer("EsNifRecognizer")
    analyzer.registry.remove_recognizer("EsNieRecognizer")
    analyzer.registry.add_recognizer(DniNieRecognizer())

    analyzer.registry.add_recognizer(SecretRecognizer())
    analyzer.registry.add_recognizer(CasePersonRecognizer(nlp_engine=nlp_engine, language=LANGUAGE))
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


def find_entities(text: str) -> list[tuple[int, int, str]]:
    """Analiza `text` y devuelve (inicio, fin, etiqueta) ya filtrados y
    remapeados a las 6 etiquetas del enunciado, sin anonimizar todavía.
    Lo usa `anonymize_text` y también `eval.py` para comparar contra un
    gabarito sin tener que re-derivar las posiciones desde el texto final.
    """
    analyzer = _get_analyzer()
    results = analyzer.analyze(
        text=text,
        language=LANGUAGE,
        entities=list(ENTITY_LABEL_MAP.keys()),
    )
    results = drop_person_in_addresses(text, results)
    results = drop_person_with_digits(text, results)
    results = trim_person_honorifics(text, results)
    for result in results:
        result.entity_type = ENTITY_LABEL_MAP[result.entity_type]
    return [(r.start, r.end, r.entity_type) for r in results]


def anonymize_text(text: str) -> str:
    """Sustituye en `text` los datos sensibles por sus etiquetas <TAG>."""
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
