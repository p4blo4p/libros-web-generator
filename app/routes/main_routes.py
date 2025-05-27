# app/routes/main_routes.py
from flask import Blueprint, render_template, request, abort, current_app, redirect, url_for
from app.utils.helpers import is_valid_isbn, is_valid_asin

main_bp = Blueprint('main', __name__)

# Estos deberían idealmente venir de app.config o ser cargados allí.
# Asegúrate de que estos valores sean consistentes con generate_static.py
# SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'it', 'de'] # Defined in app config
# DEFAULT_LANGUAGE = 'en' # Defined in app config

# Función para obtener el segmento URL traducido
def get_url_segment(segment_key, lang_code, default_segment_value='book'):
    all_translations = current_app.config.get('URL_SEGMENT_TRANSLATIONS', {})
    segments_for_key = all_translations.get(segment_key, {})
    
    # Get default language from app config
    default_app_lang = current_app.config.get('DEFAULT_LANGUAGE', 'en')

    fallback_value = segments_for_key.get(default_app_lang, default_segment_value)
    translated_value = segments_for_key.get(lang_code, fallback_value)
    
    current_app.logger.debug(f"Segment for '{segment_key}' in '{lang_code}': '{translated_value}'")
    return translated_value

# Funciones de ayuda para obtener datos y la función de traducción
def get_books_data():
    return current_app.books_data

def get_bestsellers_data():
    return current_app.bestsellers_data

def get_t_func(lang_code):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    default_language = current_app.config.get('DEFAULT_LANGUAGE', 'en')
    if lang_code not in supported_languages:
        lang_code = default_language
    return current_app.translations_manager.get_translation_func(lang_code)

@main_bp.url_defaults
def url_defaults(endpoint, values):
    current_app.logger.debug(f"--- url_defaults START --- Endpoint: '{endpoint}', Initial values: {values}")
    
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    default_language = current_app.config.get('DEFAULT_LANGUAGE', 'en')

    lang_code_from_values = values.get('lang_code')
    current_app.logger.debug(f"url_defaults: lang_code from values.get('lang_code'): '{lang_code_from_values}'")

    if lang_code_from_values is None:
        if request and hasattr(request, 'view_args') and 'lang_code' in request.view_args:
            lang_code_from_values = request.view_args['lang_code']
        # Ensure lang_code is always present for relevant endpoints, defaulting if necessary
        elif endpoint != 'main.root_index': # root_index doesn't strictly need lang_code in values for url_for
             lang_code_from_values = default_language


    segments_config_map = current_app.config.get('URL_SEGMENTS_TO_TRANSLATE', {})
    raw_config_for_endpoint = segments_config_map.get(endpoint)
    segments_for_this_endpoint = {}
    if isinstance(raw_config_for_endpoint, dict):
        segments_for_this_endpoint = raw_config_for_endpoint
    elif raw_config_for_endpoint is not None:
        current_app.logger.error(
            f"url_defaults: Misconfiguration for endpoint '{endpoint}'. "
            f"URL_SEGMENTS_TO_TRANSLATE entry for this endpoint should be a dictionary, "
            f"but got {type(raw_config_for_endpoint)}. Value: '{raw_config_for_endpoint}'. "
            f"Treating as no segment translation needed for this endpoint."
        )
    
    if segments_for_this_endpoint:
        effective_lang_code = lang_code_from_values
        if effective_lang_code not in supported_languages:
            effective_lang_code = default_language
        
        values.setdefault('lang_code', effective_lang_code)

        for original_segment_key, target_url_param_name in segments_for_this_endpoint.items():
            translated_segment = get_url_segment(original_segment_key, effective_lang_code, default_segment_value=original_segment_key)
            current_app.logger.debug(f"url_defaults: get_url_segment returned: '{translated_segment}' for key='{original_segment_key}', lang='{effective_lang_code}'")
            current_app.logger.debug(f"url_defaults: Values BEFORE setdefault for '{target_url_param_name}': {values}")
            values.setdefault(target_url_param_name, translated_segment)
            current_app.logger.debug(f"url_defaults: Values AFTER setdefault for '{target_url_param_name}': {values}")
            current_app.logger.debug(f"url_defaults: Segment '{target_url_param_name}' is now '{values[target_url_param_name]}'")
    else:
        current_app.logger.debug(f"url_defaults: No segment translation needed for endpoint '{endpoint}'")
        if lang_code_from_values and 'lang_code' not in values:
             values['lang_code'] = lang_code_from_values
        elif 'lang_code' not in values and endpoint != 'main.root_index':
            values.setdefault('lang_code', default_language)

    current_app.logger.debug(f"--- url_defaults END --- Endpoint: '{endpoint}', Final values for url_for: {values}")


@main_bp.route('/')
def root_index():
    default_language = current_app.config.get('DEFAULT_LANGUAGE', 'en')
    return redirect(url_for('main.index', lang_code=default_language))

@main_bp.route('/<lang_code>/')
def index(lang_code):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    default_language = current_app.config.get('DEFAULT_LANGUAGE', 'en')
    if lang_code not in supported_languages:
        return redirect(url_for('main.index', lang_code=default_language))
    
    t = get_t_func(lang_code)
    bestsellers = get_bestsellers_data()
    return render_template('index.html', books_data=bestsellers, lang=lang_code, t=t)

# MODIFIED ROUTE: Use <book_url_segment>
@main_bp.route('/<lang_code>/<book_url_segment>/<author_slug>/<book_slug>/<identifier>/')
def book_by_identifier(lang_code, book_url_segment, author_slug, book_slug, identifier):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in book_by_identifier. Aborting 404.")
        abort(404)

    # Validate the received book_url_segment
    expected_segment = get_url_segment('book', lang_code, 'book') # 'book' is the canonical key
    if book_url_segment != expected_segment:
        current_app.logger.info(f"Route segment mismatch for book: URL segment '{book_url_segment}' != expected '{expected_segment}' for lang '{lang_code}'. Aborting 404.")
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
        current_app.logger.warning(f"Book not found for lang '{lang_code}': /{book_url_segment}/{author_slug}/{book_slug}/{identifier}/")
        abort(404)

# MODIFIED ROUTE: Use <versions_url_segment>
@main_bp.route('/<lang_code>/<versions_url_segment>/<author_slug>/<base_book_slug>/')
def book_versions(lang_code, versions_url_segment, author_slug, base_book_slug):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in book_versions. Aborting 404.")
        abort(404)

    # Validate the received versions_url_segment
    expected_segment = get_url_segment('versions', lang_code, 'versions') # 'versions' is the canonical key
    if versions_url_segment != expected_segment:
        current_app.logger.info(f"Route segment mismatch for versions: URL segment '{versions_url_segment}' != expected '{expected_segment}' for lang '{lang_code}'. Aborting 404.")
        abort(404)
        
    t = get_t_func(lang_code)
    books = get_books_data()
    
    matched_versions = [b for b in books if b.get('author_slug') == author_slug and \
                                           b.get('base_title_slug') == base_book_slug]
    if matched_versions:
        display_author = matched_versions[0].get('author', author_slug)
        original_title = matched_versions[0].get('title', '')
        display_base_title = original_title.split('(')[0].strip() if original_title else base_book_slug

        return render_template('book_versions.html', 
                               books=matched_versions, lang=lang_code, t=t,
                               page_author_display=display_author,
                               page_base_title_display=display_base_title)
    else:
        current_app.logger.warning(f"Versions not found for lang '{lang_code}': /{versions_url_segment}/{author_slug}/{base_book_slug}/")
        abort(404)

# MODIFIED ROUTE: Use <author_url_segment>
@main_bp.route('/<lang_code>/<author_url_segment>/<author_slug>/')
def author_books(lang_code, author_url_segment, author_slug):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in author_books. Aborting 404.")
        abort(404)

    # Validate the received author_url_segment
    expected_segment = get_url_segment('author', lang_code, 'author') # 'author' is the canonical key
    if author_url_segment != expected_segment:
        current_app.logger.info(f"Route segment mismatch for author: URL segment '{author_url_segment}' != expected '{expected_segment}' for lang '{lang_code}'. Aborting 404.")
        abort(404)
        
    t = get_t_func(lang_code)
    books = get_books_data()

    processed_author_slug = author_slug.lower() # Slug should already be lowercase, but for safety
    current_app.logger.info(f"Searching for author_slug (original): '{author_slug}', (processed for search): '{processed_author_slug}'")
    
    matched_books = [b for b in books if b.get('author_slug') == processed_author_slug]
    
    if matched_books:
        display_author = matched_books[0].get('author', author_slug)
        return render_template('author_books.html', 
                               books=matched_books, lang=lang_code, t=t,
                               page_author_display=display_author)
    else:
        current_app.logger.warning(f"Author not found for lang '{lang_code}': /{author_url_segment}/{author_slug}/ (searched as '{processed_author_slug}')")
        abort(404)