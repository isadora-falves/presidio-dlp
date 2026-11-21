"""Hand-written gold standard for the files in examples/. Each entry is
the correct substitution, in the order it appears in the text. It gets
resolved to offsets with a cursored str.find(), so order matters whenever
the same substring repeats.

Kept honest on purpose: wherever we already know there's a false positive
or an uncorrected limitation (see LIM-1, LIM-2 in the bitácora), the gold
standard records what SHOULD happen, not what the engine does today — that
way eval.py actually measures the cost of those cases instead of hiding it.
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
        # "Victoria" and "Consuelo" (alone, line 1 and 3) are NOT people
        # here -> no gold entry for them (LIM-1): whatever the engine
        # tags there counts as a false positive, on purpose.
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
        # LIM-2: the full name should be "Isadora fonseca alves" (100%
        # lowercase); the engine today only recovers "alves".
        ("Isadora fonseca alves", "PERSON"),
        ("JOSE ANTONIO PEREZ", "PERSON"),
        ("ANA ISABEL RUIZ MORENO", "PERSON"),
        ("12345678Z", "DNI_NIE"),
    ],
}
