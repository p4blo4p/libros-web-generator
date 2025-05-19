# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, url_for, make_response, abort
from flask_htmlmin import HTMLMIN
from datetime import datetime, timezone, timedelta

import sys
import re
import csv
import json

from unidecode import unidecode # Asegúrate de haber hecho: pip install Unidecode

app = Flask(__name__)
app.config['MINIFY_HTML'] = True
# Descomenta y configura si usas url_for con _external=True y necesitas un dominio específico
# app.config['SERVER_NAME'] = 'localhost:5000' # o tu dominio real

htmlmin = HTMLMIN(app)

# --- FUNCIÓN SLUGIFY (ROBUSTA) ---
def slugify_ascii(text):
    if text is None:
        return ""
    text = str(text) # Asegurar que es string
    text = unidecode(text) # Transliterar a ASCII
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)  # Eliminar no alfanuméricos (excepto espacio, guion)
    text = re.sub(r'\s+', '-', text)      # Espacios a guiones
    text = re.sub(r'--+', '-', text)     # Múltiples guiones a uno
    text = text.strip('-')               # Quitar guiones al inicio/final
    if not text: # Si el slug queda vacío después de limpiar
        return "na" # o alguna otra cadena por defecto
    return text

# --- Filtro Jinja2 para HTTPS ---
def ensure_https_filter(url_string):
    if not url_string:
        return ''
    if isinstance(url_string, str) and url_string.startswith('http://'):
        return url_string.replace('http://', 'https://', 1)
    return url_string
app.jinja_env.filters['ensure_https'] = ensure_https_filter


# --- Cargar datos de libros y añadir slugs ---
def load_books(filename):
    processed_books = []
    try:
        with open(filename, encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row in enumerate(reader): # Contador para depuración
                author = row.get('author')
                title = row.get('title')

                row['author_slug'] = slugify_ascii(author)
                row['title_slug'] = slugify_ascii(title)
                
                base_title = title.split('(')[0].strip() if title else ""
                row['base_title_slug'] = slugify_ascii(base_title)
                
                # Depuración: Imprime slugs de los primeros libros
                if i < 5: # Ajusta este número según necesites
                    print(f"DEBUG load_books - Original Author: '{author}', Author Slug: '{row['author_slug']}'")
                    print(f"DEBUG load_books - Original Title: '{title}', Title Slug: '{row['title_slug']}', Base Title Slug: '{row['base_title_slug']}'")

                processed_books.append(row)
    except FileNotFoundError:
        print(f"ERROR: El archivo de libros '{filename}' no fue encontrado.", file=sys.stderr)
    except Exception as e:
        print(f"ERROR cargando libros desde '{filename}': {e}", file=sys.stderr)
    return processed_books

# --- Cargar datos JSON genérica ---
def load_json_data(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
            print(f"Successfully loaded data from '{filepath}'")
            return loaded_data
    except FileNotFoundError:
        print(f"ERROR: The file '{filepath}' was not found.", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR decoding JSON from file '{filepath}': {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR: An unexpected error occurred loading JSON from '{filepath}': {e}", file=sys.stderr)
        return None

# Carga principal de datos
books = load_books('books.csv')
bestsellers_raw = load_json_data("social/amazon_bestsellers_es.json")

# Procesar bestsellers para añadir slugs
bestsellers = []
if bestsellers_raw:
    for item in bestsellers_raw:
        # Asumimos que los bestsellers podrían no tener todos los campos de 'books.csv'
        # pero al menos 'author' y 'title' para slugificar.
        item_author = item.get('author')
        item_title = item.get('title')
        item['author_slug'] = slugify_ascii(item_author)
        item['title_slug'] = slugify_ascii(item_title)
        # Podrías añadir base_title_slug si es relevante para bestsellers
        bestsellers.append(item)
else:
    print("ADVERTENCIA: No se cargaron datos de bestsellers.")


# --- Traducciones ---
TRANSLATIONS_FILE = 'translations.json'
translations = load_json_data(TRANSLATIONS_FILE)
if translations is None:
    print(f"ADVERTENCIA: No se pudieron cargar las traducciones desde '{TRANSLATIONS_FILE}'. Se usarán valores por defecto.", file=sys.stderr)
    translations = { # Fallback mínimo
        'en': {'title': 'Book List (Default)', 'author': 'Author (Default)'},
        'es': {'title': 'Lista de Libros (Por Defecto)', 'author': 'Autor (Por Defecto)'}
    }

def get_translation(lang, key):
    lang_translations = translations.get(lang, translations.get('en', {}))
    return lang_translations.get(key, key)


# --- Funciones de validación ---
def is_valid_isbn(isbn_str):
    return re.match(r'^\d{10}(\d{3})?$', str(isbn_str or ''))

def is_valid_asin(asin_str):
    return re.match(r'^[A-Z0-9]{10}$', str(asin_str or ''))


# --- RUTAS DE LA APLICACIÓN ---
@app.route('/')
def index():
    #lang = request.args.get('lang', 'en')
    return render_template('index.html', books_data=bestsellers, lang=lang, t=lambda k: get_translation(lang, k))
    
@app.route('/book/<author_slug>/<book_slug>/<identifier>/')
def book_by_identifier(author_slug, book_slug, identifier):
    print(f"DEBUG book_by_identifier - Request for: /book/{author_slug}/{book_slug}/{identifier}/")
    if not (is_valid_isbn(identifier) or is_valid_asin(identifier)):
        print(f"DEBUG book_by_identifier - Invalid identifier: {identifier}")
        abort(400, description="Invalid ISBN or ASIN")
    
    lang = request.args.get('lang', 'en')

    found_book = next((b for b in books if b.get('author_slug') == author_slug and \
                                         b.get('title_slug') == book_slug and \
                                         (b.get('isbn10') == identifier or \
                                          b.get('isbn13') == identifier or \
                                          b.get('asin') == identifier)), None)
    
    if found_book:
        return render_template('book.html', libro=found_book, lang=lang, t=lambda k: get_translation(lang, k))
    else:
        print(f"DEBUG book_by_identifier - Book not found for slugs: author='{author_slug}', book='{book_slug}', id='{identifier}'")
        # Opcional: Imprimir algunos datos para ayudar a depurar la no coincidencia
        # for i, b_item in enumerate(books):
        #     if i < 3:
        #          print(f"  Sample book in data: author_slug='{b_item.get('author_slug')}', title_slug='{b_item.get('title_slug')}', asin='{b_item.get('asin')}'")
        abort(404)

@app.route('/versions/<author_slug>/<base_book_slug>/')
def book_versions(author_slug, base_book_slug):
    print(f"DEBUG book_versions - Request for: /versions/{author_slug}/{base_book_slug}/")
    lang = request.args.get('lang', 'en')
    
    matched_versions = [b for b in books if b.get('author_slug') == author_slug and \
                                           b.get('base_title_slug') == base_book_slug]
    
    if matched_versions:
        display_author = matched_versions[0].get('author', author_slug)
        display_base_title = matched_versions[0].get('title','').split('(')[0].strip() or base_book_slug
        return render_template('book_versions.html', 
                               books=matched_versions, 
                               lang=lang, 
                               t=lambda k: get_translation(lang, k),
                               page_author_display=display_author,
                               page_base_title_display=display_base_title)
    else:
        print(f"DEBUG book_versions - Versions not found for slugs: author='{author_slug}', base_book='{base_book_slug}'")
        abort(404)

@app.route('/author/<author_slug>/')
def author_books(author_slug):
    print(f"DEBUG author_books - Request for: /author/{author_slug}/")
    lang = request.args.get('lang', 'en')
    
    # Depuración adicional para esta ruta específica
    print(f"DEBUG author_books - Searching for author_slug: '{author_slug}'")
    # Imprime algunos author_slugs de la lista 'books' para comparar
    if books and len(books) > 0:
        print("DEBUG author_books - Sample author_slugs from 'books' data (first 5):")
        for i, b_item in enumerate(books):
            if i < 5:
                print(f"  - '{b_item.get('author_slug')}' (Original Author: '{b_item.get('author')}')")
            else:
                break
    else:
        print("DEBUG author_books - 'books' list is empty or not loaded.")

    matched_books = [b for b in books if b.get('author_slug') == author_slug]
    
    if matched_books:
        display_author = matched_books[0].get('author', author_slug)
        return render_template('author_books.html', 
                               books=matched_books, 
                               lang=lang, 
                               t=lambda k: get_translation(lang, k),
                               page_author_display=display_author)
    else:
        print(f"DEBUG author_books - Author not found for slug: '{author_slug}'")
        abort(404)

@app.route('/test/') # Ruta para probar enlaces del sitemap
def test_sitemap():
    sitemap_response = sitemap()
    xml_content = sitemap_response.data.decode('utf-8')
    # Es mejor usar un parser XML real, pero para una prueba rápida:
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_content)
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        links = [loc.text for loc in root.findall('.//ns:loc', namespace)]
    except Exception as e:
        print(f"Error parsing sitemap XML for test: {e}")
        links = ["Error parsing sitemap XML"]
    return render_template('test_sitemap.html', links=links)
      
@app.route('/sitemap.xml')
@htmlmin.exempt # Excluir de la minificación HTML
def sitemap():
    current_formatted_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    sitemap_xml = render_template('sitemap_template.xml', 
                                  all_books_data=books, # 'books' ya tiene los _slug
                                  current_date_for_sitemap=current_formatted_date)
    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"
    return response

if __name__ == '__main__':
    # Para ejecutar: python tu_app_flask.py
    # Accede a http://127.0.0.1:5000/ en tu navegador
    app.run(debug=True)