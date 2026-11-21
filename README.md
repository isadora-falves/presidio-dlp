# Presidio DLP — Parte 1: Benchmark de anonimización

Motor de anonimización de texto en español, basado en **Microsoft Presidio**
(Analyzer + Anonymizer) y **spaCy** (`es_core_news_md`), que lee un archivo
de texto y sustituye los datos sensibles por 6 etiquetas fijas:
`<PERSON>`, `<EMAIL>`, `<PHONE>`, `<DNI_NIE>`, `<IBAN>`, `<SECRET>`.

Funciona completamente offline (modelo de spaCy instalado localmente en
`.venv`); no requiere conexión a Internet ni interfaz gráfica.

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
python main.py texto_original.txt texto_anonimizado.txt
```

El programa lee `texto_original.txt` (UTF-8, con o sin BOM), escribe el
resultado anonimizado en `texto_anonimizado.txt` conservando el resto del
contenido y el formato exacto, y reporta errores (archivo no encontrado,
no-UTF-8, fallo de escritura) por `stderr` con código de salida distinto
de cero.

## Cómo detecta cada etiqueta

| Etiqueta   | Recognizer                                                     | Técnica |
|------------|-----------------------------------------------------------------|---------|
| `PERSON`   | `SpacyRecognizer` (nativo) + `CasePersonRecognizer` (propio)   | NER (spaCy `es_core_news_md`); el propio cubre mayúsculas sostenidas, mayúsculas mezcladas, apellido primero y el formato "APELLIDO, Nombre" |
| `EMAIL`    | `EmailRecognizer` (nativo)                                     | Regex |
| `PHONE`    | `PhoneRecognizer` (nativo, reconfigurado a toda Europa)         | `phonenumbers` + contexto en español |
| `DNI_NIE`  | `DniNieRecognizer` (propio, `dlp/recognizers/dni_nie.py`)       | Regex tolerante a separadores + dígito de control (checksum módulo 23) |
| `IBAN`     | `IbanRecognizer` (nativo, los 76 países de su registro) + `IbanLineBreakRecognizer` (propio) | Regex + checksum mod-97; el propio cubre un IBAN partido por un salto de línea |
| `SECRET`   | `SecretRecognizer` (propio, `dlp/recognizers/secret.py`)        | Reconocimiento contextual: palabras clave en español + formatos de credencial (Bearer, AWS, JWT, `sk-...`, URL con credencial embebida) |

El análisis se restringe explícitamente a estas 6 entidades
(`dlp/engine.py`, `ENTITY_LABEL_MAP`) para no generar falsos positivos con
otras categorías que Presidio reconoce por defecto (tarjetas de crédito,
fechas, URLs, ubicaciones, etc.).

**PHONE** cubre 46 países europeos (lista en `dlp/engine.py`,
`_EUROPE_REGIONS`); se probó cada región contra una batería de "esto no
es un teléfono" y se excluyeron 4 por falsos positivos reales:
Luxemburgo, Dinamarca, Noruega e Islas Feroe (detalle y ejemplos en la
bitácora, ADR correspondiente).

**PERSON** además pasa por tres guardias de precisión en `dlp/filters.py`:
se descarta cualquier resultado que aparezca justo después de un
indicador de vía española (Calle, Avenida, Gran Vía...), que contenga un
dígito, y se recorta un honorífico inicial (Sra., Dr., D....) del span.
**PHONE** también descarta un resultado que caiga entero dentro de un
`IBAN` ya detectado (un IBAN partido por salto de línea puede coincidir
con el formato de teléfono de algún país).

El archivo de entrada se lee con `encoding="utf-8-sig"` para que un BOM
inicial no arruine la detección de la primera palabra del documento, y el
texto se analiza párrafo por párrafo (no de una sola vez) para que el
contenido de un párrafo lejano no cambie la predicción sobre un nombre en
otro punto del documento.

## Estructura

```
main.py                             # CLI
dlp/engine.py                        # construcción del analyzer/anonymizer, división en párrafos, mapeo de entidades
dlp/filters.py                       # guardias de precisión para PERSON y PHONE
dlp/recognizers/dni_nie.py            # DniNieRecognizer propio (DNI/NIE con separadores)
dlp/recognizers/secret.py             # SecretRecognizer propio
dlp/recognizers/case_person.py        # PERSON con mayúsculas irregulares/apellido primero (verificado con una segunda consulta a spaCy)
dlp/recognizers/iban_linebreak.py     # IBAN partido por un salto de línea
eval.py, eval_gold.py                 # autoevaluación propia (ver más abajo)
examples/sample_input.txt             # texto de prueba con las 6 categorías y casos límite
examples/bateria_original.txt         # pruebas de estrés adicionales (ver bitácora)
examples/prueba_original.txt
examples/stress_original.txt
examples/casos_*.txt                  # archivos de prueba por escenario (direcciones, mayúsculas, formato de nombres, etc.)
examples/documento_oficial.txt        # documento sintético de ~800 líneas (ver bitácora) para probar a escala
examples/*_output.txt                 # salida aprobada de cada archivo de examples/, para detectar regresiones a simple vista
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

Registro completo de decisiones, bugs encontrados y limitaciones conocidas,
con ejemplos de entrada/salida para cada una: ver la bitácora
(https://claude.ai/artifact/VJf44XSVP5Zj6CiaNyWdKg).
