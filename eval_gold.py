"""Gabarito manual para los archivos de examples/. Cada entrada es la
sustitución correcta, en el orden en que aparece en el texto. Se resuelve
a offsets con str.find() con cursor, así que el orden importa cuando una
misma subcadena se repite.

Reflejado con honestidad: donde ya sabemos que hay un falso positivo o un
límite no corregido (ver LIM-1, LIM-2 en la bitácora), el gabarito pone lo
que DEBERÍA pasar, no lo que el motor hace hoy — así el eval.py de verdad
mide el costo de esos casos en vez de ocultarlo.
"""

GOLD: dict[str, list[tuple[str, str]]] = {
    "sample_input.txt": [
        ("Ana García", "PERSON"),
        ("ana.garcia@example.com", "EMAIL"),
        ("12345678Z", "DNI_NIE"),
        ("X1234567L", "DNI_NIE"),
        ("612 345 678", "PHONE"),
        ("912 345 678", "PHONE"),
        ("ES91 2100 0418 4502 0005 1332", "IBAN"),
        ("Tr0ub4dor&3", "SECRET"),
        ("a1B2c3D4e5F6g7H8", "SECRET"),
        (
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            "SECRET",
        ),
        ("AKIAABCDEFGHIJKLMNOP", "SECRET"),
        ("X-1234567-L", "DNI_NIE"),
        ("12.345.678-Z", "DNI_NIE"),
        ("4821", "SECRET"),
        ("Azul99", "SECRET"),
        ("384", "SECRET"),
    ],
    "bateria_original.txt": [
        ("Íñigo Etxebarria", "PERSON"),
        ("Montserrat Puig", "PERSON"),
        ("Brais Fernández de la Cruz", "PERSON"),
        ("x 1234567 l", "DNI_NIE"),
        ("(96) 354 12 34", "PHONE"),
        ("V4l3nc!a2026#Secret", "SECRET"),
        ("Sup3rCl4v3!", "SECRET"),
    ],
    "prueba_original.txt": [
        ("Ana García", "PERSON"),
        ("ana@example.com", "EMAIL"),
        ("Carlos Mendoza", "PERSON"),
        ("12345678Z", "DNI_NIE"),
        ("+34 612 345 678", "PHONE"),
        ("ES91 2100 0418 4502 0005 1332", "IBAN"),
        ("S3cr3tP@ss2026", "SECRET"),
        (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            "SECRET",
        ),
        ("Elena Rostova", "PERSON"),
        ("X1234567L", "DNI_NIE"),
        ("914567890", "PHONE"),
    ],
    "stress_original.txt": [
        ("María del Carmen De la Torre-Vázquez", "PERSON"),
        ("12345678-Z", "DNI_NIE"),
        ("JOSE ANTONIO PEREZ", "PERSON"),
        ("+34-600-11-22-33", "PHONE"),
        ("(96) 354 12 34", "PHONE"),
        ("ES9121000418450200051332", "IBAN"),
        ("FR7630006000011234567890189", "IBAN"),
        ("x 1234567 l", "DNI_NIE"),
        ("P@ssw0rd!2026", "SECRET"),
        ("sk-proj-98a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3", "SECRET"),
    ],
    "casos_direcciones.txt": [
        ("Carlos Dalí Ruiz", "PERSON"),
        ("612 345 678", "PHONE"),
    ],
    "casos_mayusculas.txt": [
        ("JOSE ANTONIO PEREZ", "PERSON"),
        ("+34-600-11-22-33", "PHONE"),
        ("MARIA DEL CARMEN GARCIA LOPEZ", "PERSON"),
        ("ANA ISABEL RUIZ MORENO", "PERSON"),
        ("12345678Z", "DNI_NIE"),
    ],
    "casos_nombres_ambiguos.txt": [
        # "Victoria" y "Consuelo" (solas, línea 1 y 3) NO son personas aquí
        # -> sin entrada en el gabarito (LIM-1): lo que el motor marque ahí
        # cuenta como falso positivo, a propósito.
        ("Paz Vega", "PERSON"),
        ("Consuelo Martínez", "PERSON"),
    ],
    "casos_secret_idiomas.txt": [
        ("P@ssw0rd!2026", "SECRET"),
        ("4821", "SECRET"),
        ("384", "SECRET"),
        ("Azul99", "SECRET"),
    ],
    "casos_saltos_linea.txt": [
        ("Ana\nGarcía", "PERSON"),
        ("ES91 2100\n0418 4502 0005 1332", "IBAN"),
        ("12345678Z", "DNI_NIE"),
        ("ana@example.com", "EMAIL"),
        ("Ana García", "PERSON"),
        ("Carlos Dalí Ruiz", "PERSON"),
    ],
    "casos_dni_cif.txt": [
        ("12.345.678-Z", "DNI_NIE"),
        ("X-1234567-L", "DNI_NIE"),
        ("x 1234567 l", "DNI_NIE"),
    ],
    "casos_nombres_formato.txt": [
        ("Isadora Fonseca", "PERSON"),
        ("Isadora Alves", "PERSON"),
        ("Isadora Fonseca", "PERSON"),
        ("Isadora Alves", "PERSON"),
        ("Isadora Fonseca Alves", "PERSON"),
        ("ISADORA fonseca alves", "PERSON"),
        ("ALVES Isadora Fonseca", "PERSON"),
        ("ALVES, Isadora Fonseca", "PERSON"),
        ("ALVES, Isadora FOnseca", "PERSON"),
        # LIM-2: el nombre completo debería ser "Isadora fonseca alves"
        # (100% minúsculas); el motor hoy solo recupera "alves".
        ("Isadora fonseca alves", "PERSON"),
        ("JOSE ANTONIO PEREZ", "PERSON"),
        ("ANA ISABEL RUIZ MORENO", "PERSON"),
        ("12345678Z", "DNI_NIE"),
    ],
}
