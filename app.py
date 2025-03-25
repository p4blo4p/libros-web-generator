from flask import Flask, render_template, request, url_for
import csv

app = Flask(__name__)

# Load books data from CSV
def load_books(filename):
    with open(filename, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        books = [row for row in reader]
    return books

books = load_books('books.csv')

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
    return render_template('index.html', books=books, lang=lang, t=lambda k: get_translation(lang, k))

@app.route('/book/<int:book_id>')
def book(book_id):
    lang = request.args.get('lang', 'en')
    book = next((book for book in books if int(book['bookId']) == book_id), None)
    if book:
        return render_template('book.html', libro=book, lang=lang, t=lambda k: get_translation(lang, k))
    else:
        return "Book not found", 404

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

if __name__ == '__main__':
    app.run(debug=True)
