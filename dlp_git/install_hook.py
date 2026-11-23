import stat
import subprocess
import sys
from pathlib import Path

HOOK_SOURCE = Path(__file__).resolve().parent / "pre_commit_hook.py"


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Error: ejecuta este script dentro de un repositorio git (usa 'git init' antes).", file=sys.stderr)
        sys.exit(1)
    return Path(result.stdout.strip())


def _venv_python(repo_root: Path) -> Path:
    # Si ya se está ejecutando con el intérprete del .venv, se usa ese mismo
    # (funciona aunque el .venv viva en otra ruta o máquina). Si no, se
    # asume la ubicación estándar del .venv del propio proyecto.
    if ".venv" in sys.executable:
        return Path(sys.executable)
    fallback = repo_root / ".venv" / "bin" / "python3"
    if not fallback.exists():
        print(
            f"Error: no se encontró un Python de .venv. Activa el entorno virtual "
            f"del proyecto antes de instalar el hook, o crea uno en {repo_root / '.venv'}.",
            file=sys.stderr,
        )
        sys.exit(1)
    return fallback


def main() -> None:
    repo_root = _repo_root()
    venv_python = _venv_python(repo_root)

    hook_dest = repo_root / ".git" / "hooks" / "pre-commit"
    body = HOOK_SOURCE.read_text(encoding="utf-8")
    hook_dest.write_text(f"#!{venv_python}\n{body}", encoding="utf-8")
    hook_dest.chmod(hook_dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    print(f"✅ Hook DLP instalado en {hook_dest} (usando {venv_python}).")


if __name__ == "__main__":
    main()
