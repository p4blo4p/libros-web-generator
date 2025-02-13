import csv
import os
from jinja2 import Environment, FileSystemLoader

# Crear directorios para los archivos HTML generados
os.makedirs('output/libros', exist_ok=True)

# Configurar Jinja2 para cargar plantillas desde el directorio 'templates'
env = Environment(loader=FileSystemLoader('templates'))

# Cargar datos del CSV
def cargar_datos_csv():
    libros = []
    with open('libros.csv', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            libros.append(row)
    return libros

libros = cargar_datos_csv()

# Generar archivo HTML para la lista de libros
index_template = env.get_template('index.html')
index_html = index_template.render(libros=libros)

with open('output/index.html', 'w', encoding='utf-8') as f:
    f.write(index_html)

# Generar archivo HTML para cada libro
libro_template = env.get_template('libro.html')

for libro in libros:
    libro_html = libro_template.render(libro=libro)
    with open(f"output/libros/{libro['book_id']}.html", 'w', encoding='utf-8') as f:
        f.write(libro_html)

print("Exportación completada.")
