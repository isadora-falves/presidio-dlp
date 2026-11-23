import fnmatch
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    ).stdout.strip()
)

# Una vez instalado, este archivo vive físicamente en .git/hooks/pre-commit
# (ver dlp_git/install_hook.py), así que __file__ no sirve para ubicar el
# paquete dlp/ — se usa la raíz del repo resuelta arriba.
sys.path.insert(0, str(REPO_ROOT))
from dlp.engine import anonymize_text, find_entities  # noqa: E402
DLPIGNORE_PATH = REPO_ROOT / ".dlpignore"
LOG_PATH = REPO_ROOT / "logs" / "dlp_audit.jsonl"
CONTROL_ISO = "A.8.12"

# Mismas 6 etiquetas finales que produce dlp.engine (ENTITY_LABEL_MAP) — sin
# remapeo propio. SECRET/IBAN/DNI_NIE son datos que, si salen del repo
# local, ya representan una fuga (credencial o documento de identidad);
# PERSON/EMAIL/PHONE son PII que puede justificarse en código de prueba,
# así que solo generan aviso, no bloqueo.
CRITICAL_LABELS = {"SECRET", "IBAN", "DNI_NIE"}
WARNING_LABELS = {"PERSON", "EMAIL", "PHONE"}

_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz",
    ".whl", ".pyc", ".ico", ".woff", ".woff2", ".ttf",
}


def _load_ignore_patterns() -> list:
    if not DLPIGNORE_PATH.exists():
        return []
    patterns = []
    for line in DLPIGNORE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def is_ignored(path: str, patterns: list) -> bool:
    for pattern in patterns:
        if pattern.endswith("/"):
            if path.startswith(pattern) or path == pattern.rstrip("/"):
                return True
        elif fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern):
            return True
    return False


def get_staged_files() -> list:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def read_staged_content(path: str) -> str:
    """El contenido exacto que va al commit, no el que esté en el disco."""
    result = subprocess.run(
        ["git", "show", f":{path}"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore", check=True,
    )
    return result.stdout


def log_audit_event(path: str, labels: set, action: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "control_iso": CONTROL_ISO,
        "archivo": path,
        # Solo los TIPOS de entidad encontrados, nunca el valor sensible en sí.
        "entidades": sorted(labels),
        "accion": action,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def main() -> int:
    patterns = _load_ignore_patterns()
    staged_files = get_staged_files()
    if not staged_files:
        return 0

    print("🔍 [Presidio DLP] Analizando archivos antes del commit...")

    blocked = False
    for path in staged_files:
        if is_ignored(path, patterns) or Path(path).suffix.lower() in _BINARY_EXTENSIONS:
            continue

        content = read_staged_content(path)
        entities = find_entities(content)
        if not entities:
            continue

        labels_found = {label for _, _, label in entities}
        critical = labels_found & CRITICAL_LABELS
        warning = labels_found & WARNING_LABELS

        if critical:
            blocked = True
            log_audit_event(path, labels_found, "BLOQUEADO")
            print(f"\n❌ [BLOQUEO DLP] Datos críticos detectados en '{path}': {', '.join(sorted(critical))}")

            sanitized_path = Path(f"{path}.sanitized")
            sanitized_path.write_text(anonymize_text(content), encoding="utf-8")
            print(f"   💡 Versión anonimizada generada en: {sanitized_path}")
        elif warning:
            log_audit_event(path, labels_found, "ALERTA_PERMITIDO")
            print(f"\n⚠️  [AVISO DLP] PII detectada en '{path}': {', '.join(sorted(warning))} (commit permitido, registrado en auditoría)")

    if blocked:
        print(f"\n🛑 Commit abortado por política DLP (ISO/IEC 27001 {CONTROL_ISO}).")
        print("   Elimina los datos sensibles o usa el archivo .sanitized generado.")
        return 1

    print("✅ [Presidio DLP] Verificación completada. Ningún bloqueo activado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
