# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, url_for, make_response
from datetime import datetime, timezone, timedelta # Importar datetime

from urllib.parse import urljoin

import sys # For printing errors to stderr
import re
import csv
import json

app = Flask(__name__)

# 1. DEFINE LA FUNCIÓN DEL FILTRO
def ensure_https_filter(url_string):
    if not url_string: # Si es None, cadena vacía, etc.
        return ''
    if isinstance(url_string, str) and url_string.startswith('http://'):
        return url_string.replace('http://', 'https://', 1)
    return url_string

# 2. REGISTRA EL FILTRO CON EL ENTORNO JINJA2 DE FLASK
app.jinja_env.filters['ensure_https'] = ensure_https_filter

# Load books data from CSV
def load_books(filename):
    with open(filename) as csvfile:
        reader = csv.DictReader(csvfile)
        books = [row for row in reader]
    return books

# --- Function to Load JSON Data ---
def load_json_data(filepath):
    """Loads JSON data from a specified file path.

    Args:
        filepath (str): The path to the JSON file.

    Returns:
        list or dict or None: The loaded Python object (list/dict) 
                               if successful, otherwise None.
    """
    try:
        # Open the file in read mode ('r') with UTF-8 encoding
        with open(filepath, 'r', encoding='utf-8') as f:
            # Use json.load() to parse the JSON data from the file object
            loaded_data = json.load(f)
            print(f"Successfully loaded data from '{filepath}'")
            return loaded_data
    except FileNotFoundError:
        print(f"Error: The file '{filepath}' was not found.", file=sys.stderr)
        return None # Indicate failure by returning None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from file '{filepath}': {e}", file=sys.stderr)
        return None # Indicate failure
    except IOError as e:
        print(f"Error reading file '{filepath}': {e}", file=sys.stderr)
        return None # Indicate failure
    except Exception as e:
        print(f"An unexpected error occurred during loading: {e}", file=sys.stderr)
        return None # Indicate failure
  
  
books = load_books('books.csv')
# 2. Load the data using the function
bestsellers = load_json_data("social/amazon_bestsellers_es.json") # Store the result in books_data

    
# Language translations
translations = {
    'es': {
        'title': 'Lista de Libros',
        'author': 'Autor',
        'all_versions': 'Versiones de',
        'all_books': 'Libros de',
        'subtitle': 'Subtítulo',
        'language': 'Idioma',
        'categories': 'Categorías',
        'description': 'Descripción',
        'series': 'Serie',
        'edition': 'Edición',
        'firstPublishDate': 'Primera Publicación',
        'published_year': 'Año de Publicación',
        'characters': 'Personajes',
        'format': 'Formato',
        'genres': 'Géneros',
        'isbn10': 'ISBN-10',
        'isbn13': 'ISBN-13',
        'asin': 'ASIN',
        'average_rating': 'Calificación Promedio',
        'awards': 'Premios',
        'ratingsByStars': 'Distribución de Calificaciones',
        'bbeVotes': 'Votos BBE',
        'numRatings': 'Número de Calificaciones',
        'product_dimensions': 'Dimensiones del Producto',
        'publisher': 'Editorial',
        'soldBy': 'Vendido por',
        'weight': 'Peso',
        'top_seller': 'Más vendidos',
        'googlesearch_placeholder': 'Buscar Título, Autor o ISBN',
        'back_to_list': 'Volver a la lista de libros'
    },
    'en': {
        'title': 'Book List',
        'author': 'Author',
        'all_versions': 'Differents versions of',
        'all_books': 'Books of',
        'subtitle': 'Subtitle',
        'language': 'Language',
        'categories': 'Categories',
        'description': 'Description',
        'series': 'Series',
        'edition': 'Edition',
        'firstPublishDate': 'First Publish Date',
        'published_year': 'Published Year',
        'characters': 'Characters',
        'format': 'Format',
        'genres': 'Genres',
        'isbn10': 'ISBN-10',
        'isbn13': 'ISBN-13',
        'asin': 'ASIN',
        'average_rating': 'Average Rating',
        'awards': 'Awards',
        'ratingsByStars': 'Ratings Distribution',
        'bbeVotes': 'BBE Votes',
        'numRatings': 'Number of Ratings',
        'product_dimensions': 'Product Dimensions',
        'publisher': 'Publisher',
        'soldBy': 'Sold By',
        'weight': 'Weight',
      'googlesearch_placeholder': 'Search Title, Author or ISBN',
        'top_seller': 'Top sellers',
        'back_to_list': 'Back to Book List'
    }
}

def get_translation(lang, key):
    return translations.get(lang, translations['en']).get(key, key)

def is_valid_isbn(isbn):
    return re.match(r'^\d{10}(\d{3})?$', isbn)


@app.route('/')
def index():
    lang = request.args.get('lang', 'en')
    print(bestsellers)
    return render_template('index.html', books=bestsellers, lang=lang, t=lambda k: get_translation(lang, k))

    
  # /George Orwell/1984/0452284236/
  # template https://github.com/xriley/DevBook-Theme
@app.route('/<author>/<book>/<identifier>/')
def book_by_identifier(author, book, identifier):
    # Validar si el identificador es un ISBN o un ASIN
    if not (is_valid_isbn(identifier) or is_valid_asin(identifier)):
        abort(400, description="Invalid ISBN or ASIN")
    
    lang = request.args.get('lang', 'en')

    # Buscar el libro por ISBN o ASIN
    book = next((b for b in books if b['author'] == author and b['title'] == book and 
                 (b.get('isbn10') == identifier or b.get('isbn13') == identifier or b.get('asin') == identifier)), None)
    
    if book:
        return render_template('book.html', libro=book, lang=lang, t=lambda k: get_translation(lang, k))
    else:
        return "Book not found", 404

def is_valid_asin(asin):
    """
    Validar si un identificador es un ASIN.
    Un ASIN es un alfanumérico de 10 caracteres válido en Amazon.
    """
    return re.match(r'^[A-Z0-9]{10}$', asin)

# esto no incluye titulos como "1984 (Spanish Edition)"
@app.route('/<author>/<book>/')
def book_versions(author, book):
    
    
    lang = request.args.get('lang', 'en')
    book_versions = [b for b in books if b['author'] == author and b['title'].startswith(book)]
    
    if book_versions:
        return render_template('book_versions.html', books=book_versions, lang=lang, t=lambda k: get_translation(lang, k))
    else:
        return "Book versions not found", 404

@app.route('/<author>/')
def author_books(author):
    lang = request.args.get('lang', 'en')
    author_books = [b for b in books if b['author'] == author]
    if author_books:
        return render_template('author_books.html', books=author_books, lang=lang, t=lambda k: get_translation(lang, k))
    else:
        return "Books by author not found", 404

# Nueva ruta para mostrar enlaces del sitemap.xml
@app.route('/test/')
def test_sitemap():
    # Reutilizar la función sitemap para obtener el XML
    sitemap_response = sitemap()
    xml_content = sitemap_response.data.decode('utf-8')

    # Extraer enlaces de las etiquetas <loc>
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_content)
    namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    links = [loc.text for loc in root.findall('.//ns:loc', namespace)]
    
    
    # Renderizar la plantilla HTML con los enlaces
    return render_template('test_sitemap.html', links=links)

      
      
      
@app.route('/sitemap.xml')
def sitemap():
    pages = []
    ten_days_ago = (datetime.now() - timedelta(days=10)).date().isoformat()

    # Static routes
    for rule in app.url_map.iter_rules():
        if "GET" in rule.methods and len(rule.arguments) == 0:
            pages.append(
                ["{}".format(rule.rule), ten_days_ago]#["https://example.com{}".format(rule.rule), ten_days_ago]
            )
            
    base_url = "http://example.com/"
    #relative_path = "users/profile?id=123" # Or "/users/profile?id=123"

    #full_url = urljoin(base_url, relative_path)

    # Dynamic routes
    # Obtener la fecha actual formateada
    current_formatted_date = datetime.now(timezone.utc).strftime('%Y-%m-%d') # Importante usar timezone.utc
    """
    for book in books:
        relative_path = url_for('book_by_identifier', author=book['author'], book=book['title'], identifier=book.get('isbn10') or book.get('isbn13'))
        pages.append([urljoin(base_url, relative_path), ten_days_ago])
    """
    sitemap_xml = render_template('sitemap_template.xml', books=books, current_date_for_sitemap=current_formatted_date)
    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"

    return response


if __name__ == '__main__':
    app.run(debug=True)
