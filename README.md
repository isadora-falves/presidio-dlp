# Presidio DLP

Motor de anonimización de texto en español, basado en **Microsoft Presidio**
(Analyzer + Anonymizer) y **spaCy** (`es_core_news_md`), que lee un archivo
de texto y sustituye los datos sensibles por 6 etiquetas fijas:
`<PERSON>`, `<EMAIL>`, `<PHONE>`, `<DNI_NIE>`, `<IBAN>`, `<SECRET>`.

Funciona completamente offline (modelo de spaCy instalado localmente en
`.venv`); no requiere conexión a Internet ni interfaz gráfica.

El proyecto tiene dos partes: la **Parte 1** es el motor de anonimización
en sí (CLI); la **Parte 2** reutiliza ese mismo motor como un control
preventivo integrado en Git (hook de `pre-commit`).

## Parte 1 — Motor de anonimización (CLI)

### Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Uso

```bash
python main.py texto_original.txt texto_anonimizado.txt
```

El programa lee `texto_original.txt` (UTF-8, con o sin BOM), escribe el
resultado anonimizado en `texto_anonimizado.txt` conservando el resto del
contenido y el formato exacto, y reporta errores (archivo no encontrado,
no-UTF-8, fallo de escritura) por `stderr` con código de salida distinto
de cero.

### Cómo detecta cada etiqueta

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

### Estructura

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

### Autoevaluación (no es el oráculo del profesor)

```bash
python eval.py
```

Compara la salida del motor contra un gabarito manual (`eval_gold.py`)
para los archivos de `examples/`, con la misma lógica de TP/FP/FN que
describe el enunciado. Resultado actual: **P=0.96, R=0.99, F1=0.97**
sobre 79 entidades de gabarito; los únicos fallos son los dos límites ya
documentados en la bitácora (LIM-1, LIM-2).

## Parte 2 — Hook de pre-commit en Git

Reutiliza el mismo motor de la Parte 1 (`dlp.engine.find_entities` /
`anonymize_text`, sin modificarlo) como control preventivo: antes de cada
`git commit`, un hook `pre-commit` analiza únicamente los archivos en el
*staging area* (el contenido exacto que iría al commit, vía `git show
:archivo`, no el del disco) y aplica una política de riesgo escalonada.

### Instalación

```bash
source .venv/bin/activate
python dlp_git/install_hook.py
```

Copia `dlp_git/pre_commit_hook.py` a `.git/hooks/pre-commit` con el
shebang apuntando al Python del `.venv` del proyecto (necesario: el
`#!/usr/bin/env python3` del sistema no tiene presidio/spacy instalados)
y le da permiso de ejecución. Hay que reinstalar el hook si
`pre_commit_hook.py` cambia — no hay sincronización automática entre el
archivo fuente y la copia en `.git/hooks/`.

### Política de riesgo

| Nivel | Etiquetas | Acción |
|-------|-----------|--------|
| Crítico | `SECRET`, `IBAN`, `DNI_NIE` | Bloquea el commit (`exit 1`), genera `archivo.sanitized` con la versión anonimizada |
| Medio | `PERSON`, `EMAIL`, `PHONE` | Permite el commit, imprime un aviso |
| Ninguno | — | Permite el commit en silencio |

Todo archivo bloqueado o con aviso queda registrado en
`logs/dlp_audit.jsonl` (ignorado por git, crece localmente) con el
control ISO 27001 asociado (A.8.12). Nunca se escribe el valor sensible
en el log, solo los tipos de entidad encontrados:

```json
{"timestamp": "2026-11-23T18:00:00+00:00", "control_iso": "A.8.12", "archivo": "config_prod.py", "entidades": ["IBAN", "SECRET"], "accion": "BLOQUEADO"}
```

### Exclusiones (`.dlpignore`)

`examples/` (corpus de prueba de la Parte 1), `demo_git/` (fixture de
demo de esta misma sección, ver abajo), `*.sanitized` y `logs/` quedan
fuera del escaneo del hook — todos con DNI/IBAN/SECRET falsos a
propósito, así que si no se ignoraran, cualquier commit que los tocara
(incluido el que los añade al repo) quedaría bloqueado siempre. Patrones
en `.dlpignore`, uno por línea.

### Demostración

`demo_git/config_prod_fake.py` tiene una clave de AWS y un IBAN
sintéticos (ninguno real), como plantilla para probar el flujo completo.
Vive dentro de `demo_git/`, que está en `.dlpignore` — si no, el propio
commit que lo añade al repo quedaría bloqueado. Para la demo en vivo se
copia fuera de esa carpeta (a una ruta que el hook sí escanea), se
reproduce el bloqueo, y se limpia después:

```bash
cp demo_git/config_prod_fake.py config_prod_demo.py
git add config_prod_demo.py
git commit -m "demo"               # bloqueado, genera config_prod_demo.py.sanitized
mv config_prod_demo.py.sanitized config_prod_demo.py
git add config_prod_demo.py
git commit -m "demo (sanitizado)"  # pasa
rm config_prod_demo.py              # limpieza, no se queda en el repo
```

### Mapeo a ISO/IEC 27001

- **A.5.12** (Clasificación): separación entre datos críticos (`SECRET`,
  `IBAN`, `DNI_NIE`) y PII general (`PERSON`, `EMAIL`, `PHONE`).
- **A.8.11** (Enmascaramiento): generación automática de `archivo.sanitized`.
- **A.8.12** (Prevención de fuga de datos): control técnico preventivo en
  el punto de salida del código (pre-commit), antes de llegar al
  repositorio remoto.

## Decisiones de arquitectura

Registro completo de decisiones, bugs encontrados y limitaciones conocidas,
con ejemplos de entrada/salida para cada una: ver la bitácora
(https://claude.ai/artifact/VJf44XSVP5Zj6CiaNyWdKg).
