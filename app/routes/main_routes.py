# app/routes/main_routes.py
from flask import Blueprint, render_template, request, abort, current_app, redirect, url_for
from app.utils.helpers import is_valid_isbn, is_valid_asin

main_bp = Blueprint('main', __name__)

# Función para obtener el segmento URL traducido (ya la tienes y es correcta)
def get_url_segment(segment_key, lang_code, default_segment_value=None):
    """
    Obtiene el segmento de URL traducido para una clave y un idioma dados.
    1. Intenta con el lang_code proporcionado.
    2. Si falla, intenta con el idioma por defecto de la app.
    3. Si eso también falla y se proporciona default_segment_value, lo usa.
    4. Como último recurso, devuelve la segment_key original (o None si se prefiere).
    """
    # Obtener todas las traducciones para la clave, o un diccionario vacío si la clave no existe
    segments_for_key = current_app.config['URL_SEGMENT_TRANSLATIONS'].get(segment_key, {})

    # 1. Intenta con el lang_code específico
    translated_segment = segments_for_key.get(lang_code)
    if translated_segment:
        current_app.logger.debug(f"Segment for '{segment_key}' in '{lang_code}': '{translated_segment}'")
        return translated_segment

    # 2. Si no se encontró para lang_code, intenta con el idioma por defecto de la app
    default_app_lang = current_app.config['DEFAULT_LANGUAGE']
    if lang_code != default_app_lang: # Evitar buscar dos veces si lang_code ya es el default
        translated_segment_default_lang = segments_for_key.get(default_app_lang)
        if translated_segment_default_lang:
            current_app.logger.debug(f"Segment for '{segment_key}' in default lang '{default_app_lang}': '{translated_segment_default_lang}' (used as fallback for '{lang_code}')")
            return translated_segment_default_lang
            
    # 3. Si sigue sin encontrarse y se proporcionó un valor por defecto para ESTA LLAMADA ESPECÍFICA
    if default_segment_value:
        current_app.logger.debug(f"Segment for '{segment_key}' (lang '{lang_code}') not found. Using provided default_segment_value: '{default_segment_value}'")
        return default_segment_value
    
    # 4. Como último recurso, si la clave del segmento ('book', 'author', etc.) existe
    #    pero no hay traducción para el idioma actual o el por defecto,
    #    y no se dio un default_segment_value, podríamos devolver la clave original
    #    o la traducción para el idioma por defecto si existe (aunque ya se cubrió en el paso 2).
    #    Si la 'segment_key' en sí misma no tiene entrada en URL_SEGMENT_TRANSLATIONS,
    #    segments_for_key será {} y todas las búsquedas anteriores fallarán.
    #    En este punto, devolver la 'segment_key' es una opción de fallback razonable.
    current_app.logger.warning(f"URL segment for key '{segment_key}' not found for lang '{lang_code}' or default lang '{default_app_lang}'. Falling back to segment_key itself: '{segment_key}'.")
    return segment_key # Fallback a la clave original (ej. 'book')

# Funciones de ayuda para obtener datos y la función de traducción (sin cambios)
def get_books_data():
    return current_app.books_data

def get_bestsellers_data():
    return current_app.bestsellers_data

def get_t_func(lang_code):
    if lang_code not in current_app.config['SUPPORTED_LANGUAGES']:
        lang_code = current_app.config['DEFAULT_LANGUAGE']
    return current_app.translations_manager.get_translation_func(lang_code)



@main_bp.url_defaults
def add_translated_segments_to_url_values(endpoint, values):
    current_app.logger.debug(f"--- url_defaults START --- Endpoint: '{endpoint}', Initial values: {values}")
    
    if not endpoint.startswith(f"{main_bp.name}."):
        current_app.logger.debug(f"--- url_defaults END (not a main_bp endpoint) ---")
        return

    lang_code_for_url = values.get('lang_code')
    current_app.logger.debug(f"url_defaults: lang_code from values.get('lang_code'): '{lang_code_for_url}'")

    if not lang_code_for_url:
        lang_code_for_url = current_app.config['DEFAULT_LANGUAGE']
        # values['lang_code'] = lang_code_for_url # No modificar 'values' aquí todavía si solo es para determinar el segmento
        current_app.logger.debug(f"url_defaults: lang_code_for_url was None, using app default for segment lookup: '{lang_code_for_url}'")

    # Usamos una copia para la validación para no afectar los 'values' originales si no es necesario
    effective_lang_for_segment = lang_code_for_url
    if effective_lang_for_segment not in current_app.config['SUPPORTED_LANGUAGES']:
        original_lc = effective_lang_for_segment
        effective_lang_for_segment = current_app.config['DEFAULT_LANGUAGE']
        current_app.logger.debug(f"url_defaults: lang_code '{original_lc}' not supported for segment lookup, using app default: '{effective_lang_for_segment}'")

    # Asegurarse que 'lang_code' esté en values para la construcción final de la URL, usando el original o el corregido.
    if 'lang_code' not in values or values['lang_code'] not in current_app.config['SUPPORTED_LANGUAGES']:
        values['lang_code'] = current_app.config['DEFAULT_LANGUAGE'] if values.get('lang_code') not in current_app.config['SUPPORTED_LANGUAGES'] else values.get('lang_code', current_app.config['DEFAULT_LANGUAGE'])
        current_app.logger.debug(f"url_defaults: Ensured 'lang_code' in values is now: '{values['lang_code']}'")


    ep_name_only = endpoint.split('.')[-1]
    segment_key_to_translate = None
    segment_value_in_url = None # El placeholder en la ruta, ej <book_segment>
    
    if ep_name_only == 'book_by_identifier':
        segment_key_to_translate = 'book'
        segment_value_in_url = 'book_segment'
        default_fallback_segment = 'book'
    elif ep_name_only == 'book_versions':
        segment_key_to_translate = 'versions'
        segment_value_in_url = 'versions_segment'
        default_fallback_segment = 'versions'
    elif ep_name_only == 'author_books':
        segment_key_to_translate = 'author'
        segment_value_in_url = 'author_segment'
        default_fallback_segment = 'author'
    
    if segment_key_to_translate and segment_value_in_url:
        current_app.logger.debug(f"url_defaults: About to call get_url_segment for key='{segment_key_to_translate}', lang='{effective_lang_for_segment}', fallback='{default_fallback_segment}'")
        translated_segment = get_url_segment(segment_key_to_translate, effective_lang_for_segment, default_fallback_segment)
        current_app.logger.debug(f"url_defaults: get_url_segment returned: '{translated_segment}' for key='{segment_key_to_translate}', lang='{effective_lang_for_segment}'")
        
        current_app.logger.debug(f"url_defaults: Values BEFORE setdefault for '{segment_value_in_url}': {values}")
        values.setdefault(segment_value_in_url, translated_segment)
        current_app.logger.debug(f"url_defaults: Values AFTER setdefault for '{segment_value_in_url}': {values}")
        current_app.logger.debug(f"url_defaults: Segment '{segment_value_in_url}' is now '{values[segment_value_in_url]}'")
    else:
        current_app.logger.debug(f"url_defaults: No segment translation needed for endpoint '{ep_name_only}'")

    current_app.logger.debug(f"--- url_defaults END --- Endpoint: '{endpoint}', Final values for url_for: {values}")

@main_bp.route('/')
def root_index():
    return redirect(url_for('main.index', lang_code=current_app.config['DEFAULT_LANGUAGE']))


@main_bp.route('/<lang_code>/')
def index(lang_code):
    if lang_code not in current_app.config['SUPPORTED_LANGUAGES']:
        return redirect(url_for('main.index', lang_code=current_app.config['DEFAULT_LANGUAGE']))
    
    t = get_t_func(lang_code)
    bestsellers = get_bestsellers_data()
    return render_template('index.html', books_data=bestsellers, lang=lang_code, t=t)


# Rutas con segmentos traducidos
@main_bp.route('/<lang_code>/<book_segment>/<author_slug>/<book_slug>/<identifier>/', endpoint='book_by_identifier')
def book_by_identifier(lang_code, book_segment, author_slug, book_slug, identifier):
    """Página de detalle de un libro para un idioma específico."""
    if lang_code not in current_app.config['SUPPORTED_LANGUAGES']:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in book_by_identifier. Aborting 404.")
        abort(404)

    # Validación opcional del segmento (defensa en profundidad)
    expected_segment = get_url_segment('book', lang_code, 'book')
    if book_segment != expected_segment:
        current_app.logger.warning(f"Mismatched URL segment for book. URL: {request.path}. Expected '{expected_segment}', got '{book_segment}'. Redirecting or aborting.")
        # Podrías redirigir a la URL canónica correcta o simplemente abortar
        # canonical_url = url_for('main.book_by_identifier', lang_code=lang_code, author_slug=author_slug, book_slug=book_slug, identifier=identifier, _external=True)
        # return redirect(canonical_url, code=301)
        abort(404) 
    
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
        current_app.logger.warning(f"Book not found for lang '{lang_code}': /{book_segment}/{author_slug}/{book_slug}/{identifier}/")
        abort(404)


@main_bp.route('/<lang_code>/<versions_segment>/<author_slug>/<base_book_slug>/', endpoint='book_versions')
def book_versions(lang_code, versions_segment, author_slug, base_book_slug):
    """Página de versiones de un libro para un idioma específico."""
    if lang_code not in current_app.config['SUPPORTED_LANGUAGES']:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in book_versions. Aborting 404.")
        abort(404)

    expected_segment = get_url_segment('versions', lang_code, 'versions')
    if versions_segment != expected_segment:
        current_app.logger.warning(f"Mismatched URL segment for versions. URL: {request.path}. Expected '{expected_segment}', got '{versions_segment}'.")
        abort(404)
        
    t = get_t_func(lang_code)
    books = get_books_data()
    
    processed_author_slug = author_slug.lower()
    processed_base_book_slug = base_book_slug.lower()

    matched_versions = [b for b in books if b.get('author_slug') == processed_author_slug and \
                                           b.get('base_title_slug') == processed_base_book_slug]
    if matched_versions:
        display_author = matched_versions[0].get('author', author_slug)
        original_title = matched_versions[0].get('title', '')
        display_base_title = original_title.split('(')[0].strip() if original_title else base_book_slug

        return render_template('book_versions.html', 
                               books=matched_versions, lang=lang_code, t=t,
                               page_author_display=display_author,
                               page_base_title_display=display_base_title)
    else:
        current_app.logger.warning(f"Versions not found for lang '{lang_code}': /{versions_segment}/{author_slug}/{base_book_slug}/ (searched as '{processed_author_slug}'/'{processed_base_book_slug}')")
        abort(404)


@main_bp.route('/<lang_code>/<author_segment>/<author_slug>/', endpoint='author_books')
def author_books(lang_code, author_segment, author_slug):
    """Página de libros de un autor para un idioma específico."""
    if lang_code not in current_app.config['SUPPORTED_LANGUAGES']:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in author_books. Aborting 404.")
        abort(404)

    expected_segment = get_url_segment('author', lang_code, 'author')
    if author_segment != expected_segment:
        current_app.logger.warning(f"Mismatched URL segment for author. URL: {request.path}. Expected '{expected_segment}', got '{author_segment}'.")
        abort(404)
        
    t = get_t_func(lang_code)
    books = get_books_data()

    processed_author_slug = author_slug.lower()
    
    matched_books = [b for b in books if b.get('author_slug') == processed_author_slug]
    
    if matched_books:
        display_author = matched_books[0].get('author', author_slug)
        return render_template('author_books.html', 
                               books=matched_books, lang=lang_code, t=t,
                               page_author_display=display_author)
    else:
        current_app.logger.warning(f"Author not found for lang '{lang_code}': /{author_segment}/{author_slug}/ (searched as '{processed_author_slug}')")
        abort(404)