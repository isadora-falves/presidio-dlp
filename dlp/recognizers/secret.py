import re
from typing import List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

# Solo se etiqueta el VALOR (grupo "secret"), nunca la palabra clave que lo
# acompaña: en "La contraseña es Tr0ub4dor&3." solo "Tr0ub4dor&3" debe
# sustituirse, dejando intacto "La contraseña es".
# Palabras que, solas, ya identifican un secreto sin ambigüedad. "código" se
# deja fuera a propósito: solo es un secreto cuando va con un calificador
# (código postal, código de barras y código de producto NO lo son).
_KEYWORDS = (
    r"contraseñas?|claves?|passwords?|pwd|passwd|"
    r"tokens?|api[_-]?keys?|secrets?|credenciales?|pines?|pin|"
    r"passphrase|frase\s+de\s+paso"
)

# Calificadores cortos y acotados (no palabras sueltas cualquiera) que
# suelen aparecer entre la palabra clave y el valor: "el token DE ACCESO
# es X", "la clave MAESTRA es Y". Mantenerlo acotado evita falsos positivos
# con frases como "la contraseña antigua ya no es válida".
_QUALIFIERS = (
    r"de\s+acceso|de\s+sesión|de\s+administrador|de\s+red|de\s+seguridad|"
    r"de\s+(?:la|su|tu|mi)\s+tarjeta|maestra|temporal|nueva|actual"
)

# "código" nunca se etiqueta solo: solo cuenta como secreto si va pegado a
# uno de estos calificadores (a diferencia de código postal/de barras/etc.).
_CODE_QUALIFIERS = r"secretos?|de\s+verificaci[oó]n|de\s+acceso|de\s+seguridad|otp|pin"

# "número" tampoco se etiqueta solo (número de teléfono, de pedido, de
# cuenta...): solo cuenta como secreto como sinónimo de CVV ("número de
# seguridad de la tarjeta").
_NUMERO_QUALIFIERS = r"de\s+seguridad(?:\s+de\s+la\s+tarjeta)?"

# Sufijo opcional tras el calificador, p. ej. "código secreto DE RESPALDO es...".
_SUFFIX = r"(?:\s+de\s+respaldo\b)?"


def _value_tail(min_len: int) -> str:
    # El [\"']? inicial cubre el JSON ("password": "valor"): la comilla de
    # cierre de la clave llega antes de los dos puntos.
    return (
        r"[\"']?\s*(?:es|son|:|=)\s*[:=]?\s*"
        rf'[\"\'“]?(?P<secret>[^\s\"\'”.,;]{{{min_len},}})[\"\'”]?'
    )


# El CVV suele tener solo 3 dígitos (4 en Amex): necesita un mínimo de
# longitud propio, más corto que el resto de secretos.
_VALUE_TAIL = _value_tail(4)
_VALUE_TAIL_SHORT = _value_tail(3)

def _looks_like_secret(value: str) -> bool:
    # Una palabra 100% alfabética ("constancia", "incorrectos") casi
    # siempre es una frase hecha ("la clave del éxito es...", "la
    # contraseña son incorrectos"), no un secreto real. Todos los valores
    # reales vistos en los ejemplos (propios y del profesor) tienen al
    # menos un dígito o un símbolo: "Tr0ub4dor&3", "P@ssw0rd!2026", "4821".
    return any(not c.isalpha() for c in value)


# (patrón, si debe pasar _looks_like_secret). Los patrones anclados a una
# palabra clave ambigua ("clave", "contraseña"...) necesitan el filtro;
# los anclados a un formato rígido (Bearer, AKIA, JWT, sk-, URL con
# credencial) ya se autovalidan por su forma y no lo necesitan.
_PATTERNS = [
    (
        re.compile(
            # El \b tras el calificador es crítico: sin él, "temporal" (el
            # calificador) encaja dentro de "temporales" (el adjetivo),
            # dejando "es" suelto como si fuera el conector — probado:
            # "Credenciales temporales: password=X" se leía entero como
            # un solo secreto.
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
    # Claves de API estilo OpenAI/Stripe (sk-..., sk-proj-...): formato
    # reconocible por sí solo, sin depender de una palabra clave cercana.
    (re.compile(r"\b(?P<secret>sk-[A-Za-z0-9_-]{10,})\b"), False),
    # Credencial embebida en una cadena de conexión: esquema://usuario:CLAVE@host.
    (
        re.compile(
            r"\b(?:https?|ftp|postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://"
            r"[^\s:@/]+:(?P<secret>[^\s@]+)@"
        ),
        False,
    ),
]


class SecretRecognizer(EntityRecognizer):
    """Reconocimiento contextual de contraseñas, tokens y credenciales.

    No existe un recognizer nativo de Presidio para esto: se basa en
    palabras clave y formatos de credencial conocidos, en vez de NER,
    tal como permite el enunciado ("NLP/NER o reconocimiento contextual").
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
