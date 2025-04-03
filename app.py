# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, url_for, make_response
import datetime
from urllib.parse import urljoin

import sys # For printing errors to stderr
import csv
import json

app = Flask(__name__)

# Load books data from CSV
def load_books(filename):
    with open(filename) as csvfile:
        reader = csv.DictReader(csvfile)
        books = [row for row in reader]
    return books

books = load_books('books.csv')
try:
    # Open the file in read mode ('r') with UTF-8 encoding (recommended for JSON)
    with open(file_path, 'r', encoding='utf-8') as f:
        # Use json.load() to parse the JSON data from the file object
        # Note: It's load() not loads() when reading from a file object
        bestsellers = json.load(f)

    # --- Now 'data' is a Python list containing dictionaries ---
    print(f"Successfully loaded data from '{file_path}'")
except FileNotFoundError:
    print(f"Error: The file '{file_path}' was not found.", file=sys.stderr)
    print("Please ensure the file exists in the correct directory.", file=sys.stderr)
except json.JSONDecodeError as e:
    # This error occurs if the file content is not valid JSON
    print(f"Error decoding JSON from file '{file_path}': {e}", file=sys.stderr)
    print("Please check that the file contains well-formed JSON.", file=sys.stderr)
except IOError as e:
    # Catch other potential file reading errors (e.g., permissions)
    print(f"Error reading file '{file_path}': {e}", file=sys.stderr)
except Exception as e:
    # Catch any other unexpected errors
    print(f"An unexpected error occurred: {e}", file=sys.stderr)
    
# Language translations
translations = {
    'es': {
        'title': 'Lista de Libros',
        'author': 'Autor',
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
        'back_to_list': 'Volver a la lista de libros'
    },
    'en': {
        'title': 'Book List',
        'author': 'Author',
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
        'back_to_list': 'Back to Book List'
    }
}

def get_translation(lang, key):
    return translations.get(lang, translations['en']).get(key, key)

@app.route('/')
def index():
    lang = request.args.get('lang', 'en')
    print(bestsellers)
    return render_template('index.html', books=bestsellers, lang=lang, t=lambda k: get_translation(lang, k))

  # /George Orwell/1984/0452284236/
  # template https://github.com/xriley/DevBook-Theme
@app.route('/<author>/<book>/<isbn>/')
def book_by_isbn(author, book, isbn):
    lang = request.args.get('lang', 'en')
    book = next((b for b in books if b['author'] == author and b['title'] == book and (b.get('isbn10') == isbn or b.get('isbn13') == isbn)), None)
    
    if book:
        return render_template('book.html', libro=book, lang=lang, t=lambda k: get_translation(lang, k))
    else:
        return "Book not found", 404

# esto no incluye titulos como "1984 (Spanish Edition)"
@app.route('/<author>/<book>/')
def book_versions(author, book):
    lang = request.args.get('lang', 'en')
    book_versions = [b for b in books if b['author'] == author and b['title'] == book]
    
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

@app.route('/sitemap.xml')
def sitemap():
    pages = []
    ten_days_ago = (datetime.datetime.now() - datetime.timedelta(days=10)).date().isoformat()

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
    for book in books:
        relative_path = url_for('book_by_isbn', author=book['author'], book=book['title'], isbn=book.get('isbn10') or book.get('isbn13'))
        pages.append([urljoin(base_url, relative_path), ten_days_ago])

    sitemap_xml = render_template('sitemap_template.xml', pages=pages)
    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"

    return response


if __name__ == '__main__':
    app.run(debug=True)
