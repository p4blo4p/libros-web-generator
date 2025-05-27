import csv
import string

ALPHABET = string.ascii_lowercase + string.digits  # 'abcdefghijklmnopqrstuvwxyz0123456789'
SPECIAL = 'special'  # Nombre para los archivos de caracteres no alfanuméricos

input_file = 'books.csv'
output_files = {}

# Abrir el archivo de entrada
with open(input_file, 'r', newline='', encoding='utf-8') as infile:
    reader = csv.reader(infile)
    header = next(reader)  # Leer cabecera

    # Crear un writer para cada letra/dígito y uno para especiales
    for char in ALPHABET:
        filename = f'books_{char}.csv'
        out = open(filename, 'w', newline='', encoding='utf-8')
        writer = csv.writer(out)
        writer.writerow(header)
        output_files[char] = (out, writer)
    # Archivo para especiales
    special_out = open(f'books_{SPECIAL}.csv', 'w', newline='', encoding='utf-8')
    special_writer = csv.writer(special_out)
    special_writer.writerow(header)
    output_files[SPECIAL] = (special_out, special_writer)

    # Procesar cada fila
    for row in reader:
        if not row:
            continue
        first_char = row[0].strip().lower()[:1]
        if first_char in ALPHABET:
            output_files[first_char][1].writerow(row)
        else:
            output_files[SPECIAL][1].writerow(row)

# Cerrar todos los archivos
for out, _ in output_files.values():
    out.close()

print("¡Listo! Archivos generados por letra inicial.")
