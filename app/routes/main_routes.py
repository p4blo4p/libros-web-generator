# app/routes/main_routes.py
from flask import Blueprint, render_template, request, abort, current_app, redirect, url_for
from app.utils.helpers import is_valid_isbn, is_valid_asin

main_bp = Blueprint('main', __name__)

# Estos deberían idealmente venir de app.config
# Asegúrate de que estos valores sean consistentes con generate_static.py
SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'it', 'de']
DEFAULT_LANGUAGE = 'en'

# Función para obtener el segmento URL traducido
def get_url_segment(segment_key, lang_code, default_segment='book'):
    segments = current_app.config['URL_SEGMENT_TRANSLATIONS'].get(segment_key, {})
    return segments.get(lang_code, segments.get(DEFAULT_LANGUAGE, default_segment))

# Funciones de ayuda para obtener datos y la función de traducción
def get_books_data():
    return current_app.books_data

def get_bestsellers_data():
    return current_app.bestsellers_data

def get_t_func(lang_code):
    """Obtiene la función de traducción para el lang_code dado."""
    if lang_code not in SUPPORTED_LANGUAGES:
        lang_code = DEFAULT_LANGUAGE # Fallback al idioma por defecto si no es soportado
    return current_app.translations_manager.get_translation_func(lang_code)


@main_bp.route('/')
def root_index():
    """Redirige la raíz del sitio a la versión con el idioma por defecto."""
    # Podrías añadir lógica de detección de idioma del navegador aquí si lo deseas
    # y redirigir a ese idioma si está soportado.
    return redirect(url_for('main.index', lang_code=DEFAULT_LANGUAGE))

@main_bp.route('/<lang_code>/')
def index(lang_code):
    """Página de inicio para un idioma específico."""
    if lang_code not in SUPPORTED_LANGUAGES:
        # Redirige al idioma por defecto si el lang_code no es soportado
        # o podrías mostrar un 404 específico.
        return redirect(url_for('main.index', lang_code=DEFAULT_LANGUAGE))
    
    t = get_t_func(lang_code)
    bestsellers = get_bestsellers_data()
    # Pasa 'lang_code' como 'lang' a la plantilla para consistencia
    return render_template('index.html', books_data=bestsellers, lang=lang_code, t=t)


@main_bp.route('/<lang_code>/book/<author_slug>/<book_slug>/<identifier>/')
def book_by_identifier(lang_code, author_slug, book_slug, identifier):
    """Página de detalle de un libro para un idioma específico."""
    if lang_code not in SUPPORTED_LANGUAGES:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in book_by_identifier. Aborting 404.")
        abort(404) # O redirigir al idioma por defecto
    
    t = get_t_func(lang_code)
    books = get_books_data()

   
    if not (is_valid_isbn(identifier) or is_valid_asin(identifier)):
        current_app.logger.info(f"Invalid identifier '{identifier}' in book_by_identifier. Aborting 400.")
        abort(400, description="Invalid ISBN or ASIN")

    found_book = next((b for b in books if b.get('author_slug') == author_slug and \
                                         b.get('title_slug') == book_slug and \
                                         (b.get('isbn10') == identifier or \
                                          b.get('isbn13') == identifier or \
                                          b.get('asin') == identifier)), None)
    if found_book:
        return render_template('book.html', libro=found_book, lang=lang_code, t=t)
    else:
        current_app.logger.warning(f"Book not found for lang '{lang_code}': /book/{author_slug}/{book_slug}/{identifier}/")
        abort(404)


@main_bp.route('/<lang_code>/versions/<author_slug>/<base_book_slug>/')
def book_versions(lang_code, author_slug, base_book_slug):
    """Página de versiones de un libro para un idioma específico."""
    if lang_code not in SUPPORTED_LANGUAGES:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in book_versions. Aborting 404.")
        abort(404)
        
    t = get_t_func(lang_code)
    books = get_books_data()
    
    matched_versions = [b for b in books if b.get('author_slug') == author_slug and \
                                           b.get('base_title_slug') == base_book_slug]
    if matched_versions:
        display_author = matched_versions[0].get('author', author_slug)
        # Asegúrate de que 'title' existe antes de hacer split
        original_title = matched_versions[0].get('title', '')
        display_base_title = original_title.split('(')[0].strip() if original_title else base_book_slug

        return render_template('book_versions.html', 
                               books=matched_versions, lang=lang_code, t=t,
                               page_author_display=display_author,
                               page_base_title_display=display_base_title)
    else:
        current_app.logger.warning(f"Versions not found for lang '{lang_code}': /versions/{author_slug}/{base_book_slug}/")
        abort(404)


# app/routes/main_routes.py

# ... (otras importaciones y código) ...

@main_bp.route('/<lang_code>/author/<author_slug>/')
def author_books(lang_code, author_slug):
    """Página de libros de un autor para un idioma específico."""
    if lang_code not in SUPPORTED_LANGUAGES:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in author_books. Aborting 404.")
        abort(404)
        
    t = get_t_func(lang_code)
    books = get_books_data()

    # Convertir el author_slug de la URL a minúsculas para la comparación
    processed_author_slug = author_slug.lower()
    current_app.logger.info(f"Searching for author_slug (original): '{author_slug}', (processed for search): '{processed_author_slug}'")
    
    # Los author_slug en books_data ya están en minúsculas gracias a slugify_ascii
    matched_books = [b for b in books if b.get('author_slug') == processed_author_slug]
    
    if matched_books:
        display_author = matched_books[0].get('author', author_slug) # Puedes usar el author_slug original para mostrar si quieres
        return render_template('author_books.html', 
                               books=matched_books, lang=lang_code, t=t,
                               page_author_display=display_author)
    else:
        current_app.logger.warning(f"Author not found for lang '{lang_code}': /author/{author_slug}/ (searched as '{processed_author_slug}')")
        abort(404)