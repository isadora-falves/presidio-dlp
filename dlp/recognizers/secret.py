import re
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Only the VALUE (the "secret" group) gets tagged, never the keyword next
# to it: in "La contraseña es Tr0ub4dor&3." only "Tr0ub4dor&3" should be
# replaced, leaving "La contraseña es" untouched.
# Words that unambiguously identify a secret on their own. "código" is left
# out on purpose: it's only a secret when paired with a qualifier (código
# postal, código de barras, código de producto are NOT secrets).
_KEYWORDS = (
    r"contraseñas?|claves?|passwords?|pass|pwd|passwd|"
    r"tokens?|api[_-]?keys?|secrets?|credenciales?|pines?|pin|"
    r"passphrase|frase\s+de\s+paso"
)

# Short, closed-list qualifiers (not just any filler word) that often sit
# between the keyword and the value: "el token DE ACCESO es X", "la clave
# MAESTRA es Y". Keeping this list closed avoids false positives on
# phrases like "la contraseña antigua ya no es válida".
_QUALIFIERS = (
    r"de\s+acceso|de\s+sesión|de\s+administrador|de\s+red|de\s+seguridad|"
    r"de\s+(?:la|su|tu|mi)\s+tarjeta|de\s+prueba|maestra|temporal|nueva|actual|anterior"
)

# "código" is never tagged on its own: it only counts as a secret when
# glued to one of these qualifiers (unlike código postal/de barras/etc.).
_CODE_QUALIFIERS = r"secretos?|de\s+verificaci[oó]n|de\s+acceso|de\s+seguridad|otp|pin"

# "número" isn't tagged alone either (número de teléfono, de pedido, de
# cuenta...): it only counts as a secret as a CVV synonym ("número de
# seguridad de la tarjeta").
_NUMERO_QUALIFIERS = r"de\s+seguridad(?:\s+de\s+la\s+tarjeta)?"

# Optional suffix after the qualifier, e.g. "código secreto DE RESPALDO es...".
_SUFFIX = r"(?:\s+de\s+respaldo\b)?"


def _value_tail(min_len: int) -> str:
    # The leading [\"']? covers JSON ("password": "value"): the closing
    # quote of the key arrives before the colon. The optional "que ..."
    # clause covers a relative clause between the keyword and the
    # connector ("la contraseña QUE ME DIERON es X", "la clave QUE
    # UTILIZABA era Y") — confirmed missed without it. "era"/"eran"/
    # "fue"/"fueron" cover the past tense of "ser" ("la clave... ERA X"),
    # which "es"/"son" alone don't.
    #
    # The \b around the word connectors is critical: without it, the
    # greedy "que ..." clause above can shrink its last \w+ one letter at
    # a time until it lands exactly on an "es" hidden inside a later
    # word — confirmed: "...era Carlos_Test#2026" matched the "es" inside
    # "Test", splitting the value into just "t#2026". ":"/"=" don't need
    # it (punctuation can't hide inside a \w+ word).
    return (
        r"[\"']?(?:\s+que\s+\w+(?:\s+\w+){0,5})?"
        r"\s*(?:\b(?:es|son|era|eran|fue|fueron)\b|:|=)\s*[:=]?\s*"
        rf'[\"\'“]?(?P<secret>[^\s\"\'”.,;]{{{min_len},}})[\"\'”]?'
    )


# A CVV is usually just 3 digits (4 on Amex): it needs its own, shorter
# minimum length than the rest of the secrets.
_VALUE_TAIL = _value_tail(4)
_VALUE_TAIL_SHORT = _value_tail(3)

def _looks_like_secret(value: str) -> bool:
    # A 100% alphabetic word ("constancia", "incorrectos") is almost
    # always a figure of speech ("la clave del éxito es...", "la
    # contraseña son incorrectos"), not a real secret. Every real value
    # seen in the examples (ours and the professor's) has at least one
    # digit or symbol: "Tr0ub4dor&3", "P@ssw0rd!2026", "4821".
    return any(not c.isalpha() for c in value)


# (pattern, whether it must pass _looks_like_secret). Patterns anchored on
# an ambiguous keyword ("clave", "contraseña"...) need the filter; those
# anchored on a rigid format (Bearer, AKIA, JWT, sk-, a URL with an
# embedded credential) already self-validate by their shape and don't.
_PATTERNS = [
    (
        re.compile(
            # The \b after the qualifier is critical: without it,
            # "temporal" (the qualifier) matches inside "temporales" (the
            # adjective), leaving a stray "es" that reads as the
            # connector — confirmed: "Credenciales temporales:
            # password=X" was read whole as a single secret.
            rf"\b(?:{_KEYWORDS})\b(?:\s+(?:{_QUALIFIERS})\b)?{_SUFFIX}{_VALUE_TAIL}",
            re.IGNORECASE,
        ),
        True,
    ),
    (re.compile(rf"\bcódigos?\s+(?:{_CODE_QUALIFIERS})\b{_SUFFIX}{_VALUE_TAIL}", re.IGNORECASE), True),
    (re.compile(rf"\bnúmeros?\s+(?:{_NUMERO_QUALIFIERS})\b{_VALUE_TAIL_SHORT}", re.IGNORECASE), True),
    (
        re.compile(
            rf"\bcvv2?\b(?:\s+(?:de\s+(?:la|su|tu|mi)\s+tarjeta)\b)?{_VALUE_TAIL_SHORT}",
            re.IGNORECASE,
        ),
        True,
    ),
    (re.compile(r"\bBearer\s+(?P<secret>[A-Za-z0-9\-_.]{8,})", re.IGNORECASE), False),
    (re.compile(r"\b(?P<secret>AKIA[0-9A-Z]{16})\b"), False),
    (re.compile(r"\b(?P<secret>eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b"), False),
    # OpenAI/Stripe-style API keys (sk-..., sk-proj-...): a format that's
    # recognizable on its own, without needing a nearby keyword.
    (re.compile(r"\b(?P<secret>sk-[A-Za-z0-9_-]{10,})\b"), False),
    # A credential embedded in a connection string: scheme://user:PASSWORD@host.
    (
        re.compile(
            r"\b(?:https?|ftp|postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://"
            r"[^\s:@/]+:(?P<secret>[^\s@]+)@"
        ),
        False,
    ),
]


class SecretRecognizer(EntityRecognizer):
    """Contextual recognition of passwords, tokens and credentials.

    Presidio has no native recognizer for this: it relies on keywords and
    known credential formats instead of NER, exactly as the assignment
    allows ("NLP/NER or contextual recognition").
    """

    ENTITY = "SECRET"
    SCORE = 0.85

    def __init__(self) -> None:
        super().__init__(supported_entities=[self.ENTITY], supported_language="es", name="SecretRecognizer")

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: List[str], nlp_artifacts: Optional[NlpArtifacts] = None
    ) -> List[RecognizerResult]:
        if self.ENTITY not in entities:
            return []

        results = []
        for pattern, needs_check in _PATTERNS:
            for match in pattern.finditer(text):
                start, end = match.span("secret")
                if needs_check and not _looks_like_secret(match.group("secret")):
                    continue
                results.append(
                    RecognizerResult(
                        entity_type=self.ENTITY,
                        start=start,
                        end=end,
                        score=self.SCORE,
                    )
                )
        return EntityRecognizer.remove_duplicates(results)
