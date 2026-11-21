# Presidio DLP — Parte 1: Benchmark de anonimización

Motor de anonimización de texto en español, basado en **Microsoft Presidio**
(Analyzer + Anonymizer) y **spaCy** (`es_core_news_md`), que sustituye datos
sensibles por 6 etiquetas fijas: `<PERSON>`, `<EMAIL>`, `<PHONE>`,
`<DNI_NIE>`, `<IBAN>`, `<SECRET>`.

## Uso

```bash
source .venv/bin/activate
python main.py texto_original.txt texto_anonimizado.txt
```

Funciona completamente offline (modelo de spaCy instalado localmente en
`.venv`); no requiere conexión a Internet ni interfaz gráfica.

## Cómo detecta cada etiqueta

| Etiqueta   | Recognizer                                   | Técnica |
|------------|-----------------------------------------------|---------|
| `PERSON`   | `SpacyRecognizer` (nativo) + `CasePersonRecognizer` (propio) | NER (spaCy `es_core_news_md`); el propio cubre mayúsculas mezcladas, apellido primero y "APELLIDO, Nombre" |
| `EMAIL`    | `EmailRecognizer` (nativo)                   | Regex |
| `PHONE`    | `PhoneRecognizer` (nativo, reconfigurado a `supported_regions=("ES",)`) | `phonenumbers` + contexto |
| `DNI_NIE`  | `DniNieRecognizer` (propio, `dlp/recognizers/dni_nie.py`) | Regex tolerante a separadores + dígito de control (checksum) |
| `IBAN`     | `IbanRecognizer` (nativo) + `IbanLineBreakRecognizer` (propio) | Regex + checksum mod-97; el propio cubre IBAN partido por un salto de línea |
| `SECRET`   | `SecretRecognizer` (propio, `dlp/recognizers/secret.py`) | Reconocimiento contextual: palabras clave en español + formatos de credencial (Bearer, AWS, JWT, `sk-...`, URL con credencial embebida) |

El análisis se restringe explícitamente a estas 6 entidades
(`dlp/engine.py`, `ENTITY_LABEL_MAP`) para no generar falsos positivos con
otras categorías que Presidio reconoce por defecto (tarjetas de crédito,
fechas, URLs, ubicaciones, etc.). `dlp/filters.py` además descarta cualquier
`PERSON` que aparezca justo después de un indicador de vía española (Calle,
Avenida, Gran Vía...) o que contenga un dígito, y recorta un honorífico
inicial (Sra., Dr., D....) del span de `PERSON`. El archivo de entrada se
lee con `encoding="utf-8-sig"` para que un BOM inicial no arruine la
detección de la primera palabra del documento.

## Estructura

```
main.py                             # CLI
dlp/engine.py                        # construcción del analyzer/anonymizer, mapeo de entidades
dlp/filters.py                       # guardias de contexto (direcciones, dígitos, honoríficos) para PERSON
dlp/recognizers/dni_nie.py            # DniNieRecognizer propio (DNI/NIE con separadores)
dlp/recognizers/secret.py             # SecretRecognizer propio
dlp/recognizers/case_person.py        # PERSON con mayúsculas irregulares/apellido primero (verificado con una segunda consulta a spaCy)
dlp/recognizers/iban_linebreak.py     # IBAN partido por un salto de línea
examples/sample_input.txt             # texto de prueba con las 6 categorías y casos límite
examples/bateria_original.txt         # pruebas de estrés adicionales (ver bitácora)
examples/prueba_original.txt
examples/stress_original.txt
examples/casos_*.txt                  # archivos de prueba por escenario (direcciones, mayúsculas, formato de nombres, etc.)
```

## Autoevaluación (no es el oráculo del profesor)

```bash
python eval.py
```

Compara la salida del motor contra un gabarito manual (`eval_gold.py`)
para los archivos de `examples/`, con la misma lógica de TP/FP/FN que
describe el enunciado. Resultado actual: **P=0.96, R=0.99, F1=0.97**
sobre 79 entidades de gabarito; los únicos fallos son los dos límites ya
documentados en la bitácora (LIM-1, LIM-2).

## Decisiones de arquitectura

Ver la bitácora: https://claude.ai/artifact/VJf44XSVP5Zj6CiaNyWdKg
