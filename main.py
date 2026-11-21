import argparse
import sys

from dlp.engine import anonymize_text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Anonimiza datos sensibles de un archivo de texto con Presidio."
    )
    parser.add_argument("input_path", help="Ruta del archivo de texto original (UTF-8)")
    parser.add_argument("output_path", help="Ruta donde se escribirá el texto anonimizado")
    args = parser.parse_args()

    try:
        # utf-8-sig strips a leading BOM if present (common when a file is
        # saved from Windows/Notepad) and behaves like plain utf-8 otherwise.
        # Without it, a BOM silently merges into the first word of the
        # document and breaks NER on it (see bitácora ADR-13).
        with open(args.input_path, "r", encoding="utf-8-sig", newline="") as f:
            original_text = f.read()
    except FileNotFoundError:
        print(f"Error: no se encontró el archivo de entrada '{args.input_path}'.", file=sys.stderr)
        return 1
    except UnicodeDecodeError:
        print(f"Error: '{args.input_path}' no es un archivo de texto UTF-8 válido.", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error al leer '{args.input_path}': {exc}", file=sys.stderr)
        return 1

    anonymized_text = anonymize_text(original_text)

    try:
        with open(args.output_path, "w", encoding="utf-8", newline="") as f:
            f.write(anonymized_text)
    except OSError as exc:
        print(f"Error al escribir '{args.output_path}': {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
