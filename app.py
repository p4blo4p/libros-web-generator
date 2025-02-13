from flask import Flask, render_template, send_file
import csv
import os
from jinja2 import Environment, FileSystemLoader

app = Flask(__name__)

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

@app.route('/')
def index():
    return render_template('index.html', libros=libros)

@app.route('/libro/<int:book_id>')
def libro(book_id):
    libro = next((libro for libro in libros if int(libro['book_id']) == book_id), None)
    if libro:
        return render_template('libro.html', libro=libro)
    else:
        return "Libro no encontrado", 404

@app.route('/exportar')
def exportar():
    # Crear directorios para los archivos HTML generados
    os.makedirs('output/libros', exist_ok=True)

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

    return send_file('output/index.html', as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
