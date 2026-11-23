import re
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Only the VALUE (the "secret" group) gets tagged, never the keyword next
# to it: in a sentence shaped "keyword + connector + value", only the
# value should be replaced, leaving the keyword and connector untouched.
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


# Environment-variable-style assignment (NAME followed by "=" then a
# value, e.g. a Stripe-style key assigned to a *_SECRET_KEY variable).
# The keyword patterns above all anchor on \b, which never breaks on "_" —
# a keyword glued to another word by an underscore (as in a typical
# SCREAMING_SNAKE_CASE env var name) has no word boundary where these
# patterns need one, so it's invisible to them. Confirmed real gap: a
# config file assigning a Stripe-style value (which uses "_", not the
# "-" our rigid sk- pattern expects) to such a variable passed through
# completely untouched.
# The value is captured in two shapes: quoted (anything but the closing
# quote counts) or bare. The bare branch excludes "(", ")", "[", "]":
# without that, "API_KEY = os.environ[\"RELAYMAIL_API_KEY\"]" let the
# capture run right through "os.environ[" (confirmed) and tag that
# literal code as the secret, since nothing in the character class
# stopped it before the opening quote that follows "[".
_ENV_VAR_CANDIDATE = re.compile(
    r"\b(?P<key>[A-Za-z][A-Za-z0-9_-]*)\s*[:=]\s*"
    r"(?:\"(?P<secret_dq>[^\"]{4,})\"|'(?P<secret_sq>[^']{4,})'|(?P<secret_bare>[^\s\"'#;,()\[\]]{4,}))"
)

# Only the LAST component(s) of the identifier are checked, not any
# substring: "TOKEN_EXPIRY" (a duration, not a secret) must NOT match just
# because "token" appears somewhere in the name. This mirrors how real
# env vars are named (the meaning first, the kind of value last).
_ENV_SUFFIX_WORDS = {
    "secret", "secrets", "token", "tokens", "password", "passwords",
    "passwd", "pwd", "credential", "credentials", "pin", "pins", "passphrase",
}
_ENV_SUFFIX_PAIRS = {("api", "key"), ("api", "keys"), ("secret", "key"), ("secret", "keys"), ("access", "key"), ("access", "keys")}

# A hardcoded fallback passed as the SECOND argument of os.environ.get(...)
# / os.getenv(...) — "it still works even if the env var isn't set yet"
# is a common real antipattern. None of the patterns above look inside a
# function call's arguments at all, so a Stripe-style key hardcoded that
# way, in a realistic integration test file, slipped through completely
# untouched. Scoped to this one Python shape — the same antipattern in
# another language's equivalent call isn't covered.
_GETENV_FALLBACK_CANDIDATE = re.compile(
    r"\bos\.(?:environ\.get|getenv)\(\s*[\"'](?P<key>[A-Za-z][A-Za-z0-9_-]*)[\"']\s*,\s*[\"'](?P<secret>[^\"']{4,})[\"']"
)


def _is_env_secret_key(key: str) -> bool:
    parts = [p for p in re.split(r"[_-]", key.lower()) if p]
    if not parts:
        return False
    if parts[-1] in _ENV_SUFFIX_WORDS:
        return True
    return len(parts) >= 2 and (parts[-2], parts[-1]) in _ENV_SUFFIX_PAIRS


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

        for match in _ENV_VAR_CANDIDATE.finditer(text):
            if not _is_env_secret_key(match.group("key")):
                continue
            if match.group("secret_bare") is not None:
                start, end = match.span("secret_bare")
                value = match.group("secret_bare")
                # A bare (unquoted) value with no digit at all is almost
                # always a code reference, not a literal secret — confirmed:
                # "os.environ" (reading the env var by name, the SAFE way to
                # do it) has no bracket/paren but still has no digit either,
                # unlike every real key/token/password value seen so far.
                if not any(c.isdigit() for c in value):
                    continue
            elif match.group("secret_dq") is not None:
                start, end = match.span("secret_dq")
                value = match.group("secret_dq")
            else:
                start, end = match.span("secret_sq")
                value = match.group("secret_sq")
            if not _looks_like_secret(value):
                continue
            results.append(
                RecognizerResult(
                    entity_type=self.ENTITY,
                    start=start,
                    end=end,
                    score=self.SCORE,
                )
            )

        for match in _GETENV_FALLBACK_CANDIDATE.finditer(text):
            if not _is_env_secret_key(match.group("key")):
                continue
            start, end = match.span("secret")
            if not _looks_like_secret(match.group("secret")):
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
