import csv
import os
from jinja2 import Environment, FileSystemLoader

def crear_directorios(ruta_directorio):
    """Crear directorios necesarios para los archivos HTML generados."""
    os.makedirs(ruta_directorio, exist_ok=True)

def configurar_entorno_jinja(ruta_plantillas):
    """Configurar Jinja2 para cargar plantillas desde un directorio especificado."""
    return Environment(loader=FileSystemLoader(ruta_plantillas))

def cargar_datos_csv(ruta_csv):
    """Cargar datos de un archivo CSV y devolver una lista de diccionarios."""
    libros = []
    with open(ruta_csv, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            libros.append(row)
    return libros

def generar_html_lista_libros(libros, plantilla, ruta_salida):
    """Generar archivo HTML para la lista de libros."""
    index_html = plantilla.render(libros=libros)
    with open(ruta_salida, 'w', encoding='utf-8') as f:
        f.write(index_html)

def generar_html_libros_individuales(libros, plantilla, ruta_salida):
    """Generar archivo HTML para cada libro individualmente."""
    for libro in libros:
        libro_html = plantilla.render(libro=libro)
        with open(os.path.join(ruta_salida, f"{libro['book_id']}.html"), 'w', encoding='utf-8') as f:
            f.write(libro_html)

def main(ruta_csv, ruta_plantillas, ruta_salida):
    """Función principal para coordinar la exportación de libros a HTML."""
    crear_directorios(os.path.join(ruta_salida, 'libros'))
    env = configurar_entorno_jinja(ruta_plantillas)
    libros = cargar_datos_csv(ruta_csv)
    
    index_template = env.get_template('index.html')
    generar_html_lista_libros(libros, index_template, os.path.join(ruta_salida, 'index.html'))
    
    libro_template = env.get_template('libro.html')
    generar_html_libros_individuales(libros, libro_template, os.path.join(ruta_salida, 'libros'))
    
    print("Exportación completada.")

if __name__ == "__main__":
    ruta_csv = 'libros.csv'
    ruta_plantillas = 'templates'
    ruta_salida = 'output'
    
    main(ruta_csv, ruta_plantillas, ruta_salida)
