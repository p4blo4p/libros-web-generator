# app/routes/main_routes.py
from flask import Blueprint, render_template, request, abort, current_app, redirect, url_for
from app.utils.helpers import is_valid_isbn, is_valid_asin # Asegúrate que slugify_ascii no se necesite aquí directamente

main_bp = Blueprint('main', __name__)

# Función para obtener el segmento URL traducido
def get_url_segment(segment_key, lang_code, default_segment_value='book'): # default_segment_value es el canonico en ingles
    """
    Obtiene el segmento de URL traducido para una clave y un idioma dados.
    'segment_key' es la clave canónica del segmento (ej: 'book', 'author').
    'lang_code' es el código de idioma para la traducción.
    'default_segment_value' es el valor a usar si no se encuentra traducción ni siquiera en el idioma por defecto.
    Este valor suele ser la versión en inglés del segment_key (ej: 'book' para la clave 'book').
    """
    all_translations = current_app.config.get('URL_SEGMENT_TRANSLATIONS', {})
    segments_for_key = all_translations.get(segment_key, {})
    
    default_app_lang = current_app.config.get('DEFAULT_LANGUAGE', 'en')

    # 1. Intenta obtener la traducción para el lang_code actual
    translated_value = segments_for_key.get(lang_code)
    
    # 2. Si no se encuentra para lang_code Y lang_code no es el idioma por defecto, intenta con el idioma por defecto de la app
    if translated_value is None and lang_code != default_app_lang:
        translated_value = segments_for_key.get(default_app_lang)

    # 3. Si aún no hay valor, usa el default_segment_value proporcionado (que suele ser el segment_key en inglés)
    if translated_value is None:
        translated_value = default_segment_value
            
    # current_app.logger.debug(f"Segment for '{segment_key}' in '{lang_code}': '{translated_value}' (default_app_lang: '{default_app_lang}', default_param_value: '{default_segment_value}')")
    return translated_value

# Funciones de ayuda para obtener datos y la función de traducción
def get_books_data():
    return current_app.books_data

def get_bestsellers_data():
    return current_app.bestsellers_data

def get_t_func(lang_code):
    """Obtiene la función de traducción para el lang_code dado."""
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    default_language = current_app.config.get('DEFAULT_LANGUAGE', 'en')
    if lang_code not in supported_languages:
        lang_code = default_language # Fallback al idioma por defecto si no es soportado
    return current_app.translations_manager.get_translation_func(lang_code)

@main_bp.url_defaults
def url_defaults(endpoint, values):
    # current_app.logger.debug(f"--- url_defaults START --- Endpoint: '{endpoint}', Initial values: {values}")
    
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    default_language = current_app.config.get('DEFAULT_LANGUAGE', 'en')

    lang_code_from_values = values.get('lang_code')
    # current_app.logger.debug(f"url_defaults: lang_code from values.get('lang_code'): '{lang_code_from_values}'")

    if lang_code_from_values is None:
        if request and hasattr(request, 'view_args') and 'lang_code' in request.view_args:
            lang_code_from_values = request.view_args['lang_code']
        elif endpoint != 'main.root_index': # root_index no necesita lang_code en values para url_for
             lang_code_from_values = default_language


    segments_config_map = current_app.config.get('URL_SEGMENTS_TO_TRANSLATE', {})
    raw_config_for_endpoint = segments_config_map.get(endpoint)
    segments_for_this_endpoint = {} # Por defecto, un diccionario vacío.
    if isinstance(raw_config_for_endpoint, dict):
        segments_for_this_endpoint = raw_config_for_endpoint
    elif raw_config_for_endpoint is not None: # Configuración existe, pero no es un diccionario.
        current_app.logger.error(
            f"url_defaults: Misconfiguration for endpoint '{endpoint}'. "
            f"URL_SEGMENTS_TO_TRANSLATE entry for this endpoint should be a dictionary, "
            f"but got {type(raw_config_for_endpoint)}. Value: '{raw_config_for_endpoint}'. "
            f"Treating as no segment translation needed for this endpoint."
        )
    
    if segments_for_this_endpoint: # Si hay segmentos definidos para traducir para este endpoint
        effective_lang_code = lang_code_from_values
        if effective_lang_code not in supported_languages: # Asegurar que lang_code sea válido para la traducción
            effective_lang_code = default_language
        
        values.setdefault('lang_code', effective_lang_code) # Asegurar que lang_code esté en values

        for original_segment_key, target_url_param_name in segments_for_this_endpoint.items():
            # original_segment_key (e.g., 'book') is used as default_segment_value
            translated_segment = get_url_segment(original_segment_key, effective_lang_code, default_segment_value=original_segment_key)
            
            # current_app.logger.debug(f"url_defaults: get_url_segment returned: '{translated_segment}' for key='{original_segment_key}', lang='{effective_lang_code}'")
            # current_app.logger.debug(f"url_defaults: Values BEFORE setdefault for '{target_url_param_name}': {values}")
            values.setdefault(target_url_param_name, translated_segment)
            # current_app.logger.debug(f"url_defaults: Values AFTER setdefault for '{target_url_param_name}': {values}")
            # current_app.logger.debug(f"url_defaults: Segment '{target_url_param_name}' is now '{values[target_url_param_name]}'")
    else:
        # current_app.logger.debug(f"url_defaults: No segment translation needed for endpoint '{endpoint}'")
        # Asegurarse de que lang_code esté en values si no se hizo traducción pero se conoce
        if lang_code_from_values and 'lang_code' not in values:
            values['lang_code'] = lang_code_from_values
        elif 'lang_code' not in values and endpoint != 'main.root_index': # root_index no necesita lang_code en values
             # Si no hay lang_code y no es el root_index, usar el default.
             # Esto es importante para que url_for(main.index) funcione correctamente sin pasar lang_code.
            values.setdefault('lang_code', default_language)


    # current_app.logger.debug(f"--- url_defaults END --- Endpoint: '{endpoint}', Final values for url_for: {values}")


@main_bp.route('/')
def root_index():
    """Redirige la raíz del sitio a la versión con el idioma por defecto."""
    default_language = current_app.config.get('DEFAULT_LANGUAGE', 'en')
    return redirect(url_for('main.index', lang_code=default_language))

@main_bp.route('/<lang_code>/')
def index(lang_code):
    """Página de inicio para un idioma específico."""
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    default_language = current_app.config.get('DEFAULT_LANGUAGE', 'en')
    if lang_code not in supported_languages:
        # current_app.logger.info(f"Unsupported lang_code '{lang_code}' in index. Redirecting to default.")
        return redirect(url_for('main.index', lang_code=default_language))
    
    t = get_t_func(lang_code)
    bestsellers = get_bestsellers_data()
    return render_template('index.html', books_data=bestsellers, lang=lang_code, t=t)

@main_bp.route('/<lang_code>/<book_url_segment>/<author_slug>/<book_slug>/<identifier>/')
def book_by_identifier(lang_code, book_url_segment, author_slug, book_slug, identifier):
    """Página de detalle de un libro para un idioma específico."""
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        # current_app.logger.info(f"Unsupported lang_code '{lang_code}' in book_by_identifier. Aborting 404.")
        abort(404)

    # Validar el segmento de URL recibido contra el esperado para el idioma
    expected_segment = get_url_segment('book', lang_code, 'book') # 'book' es la clave canónica
    if book_url_segment != expected_segment:
        current_app.logger.warning(f"Route segment mismatch for book (lang '{lang_code}'): URL segment '{book_url_segment}' != expected '{expected_segment}'. Aborting 404.")
        abort(404)
    
    t = get_t_func(lang_code)
    books = get_books_data()
   
    if not (is_valid_isbn(identifier) or is_valid_asin(identifier)):
        # current_app.logger.info(f"Invalid identifier '{identifier}' in book_by_identifier. Aborting 400.")
        abort(400, description="Invalid ISBN or ASIN")

    # Los slugs ya deberían estar normalizados por generate_static.py y por el uso de slugify_to_use
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


@main_bp.route('/<lang_code>/<versions_url_segment>/<author_slug>/<base_book_slug>/')
def book_versions(lang_code, versions_url_segment, author_slug, base_book_slug):
    """Página de versiones de un libro para un idioma específico."""
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        # current_app.logger.info(f"Unsupported lang_code '{lang_code}' in book_versions. Aborting 404.")
        abort(404)
        
    # Validar el segmento de URL recibido
    expected_segment = get_url_segment('versions', lang_code, 'versions') # 'versions' es la clave canónica
    if versions_url_segment != expected_segment:
        current_app.logger.warning(f"Route segment mismatch for versions (lang '{lang_code}'): URL segment '{versions_url_segment}' != expected '{expected_segment}'. Aborting 404.")
        abort(404)
        
    t = get_t_func(lang_code)
    books = get_books_data()
    
    # Los slugs ya deberían estar normalizados
    matched_versions = [b for b in books if b.get('author_slug') == author_slug and \
                                           b.get('base_title_slug') == base_book_slug]
    if matched_versions:
        # Para pasar al template, obtener nombres más "humanos" del primer libro encontrado
        display_author = matched_versions[0].get('author', author_slug)
        original_title = matched_versions[0].get('title', '') # Título de una de las versiones
        # Intentar obtener un título base limpio para la página, si no, usar el slug base
        display_base_title = original_title.split('(')[0].strip() if original_title else base_book_slug
        if not display_base_title : # fallback adicional si original_title estaba vacío o no tenía ' ('
             display_base_title = matched_versions[0].get('base_title_slug', base_book_slug)


        return render_template('book_versions.html', 
                               books=matched_versions, lang=lang_code, t=t,
                               page_author_display=display_author,
                               page_base_title_display=display_base_title) # Pasar para el título de la página, etc.
    else:
        current_app.logger.warning(f"Versions not found for lang '{lang_code}': /{versions_url_segment}/{author_slug}/{base_book_slug}/")
        abort(404)


@main_bp.route('/<lang_code>/<author_url_segment>/<author_slug>/')
def author_books(lang_code, author_url_segment, author_slug):
    """Página de libros de un autor para un idioma específico."""
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        # current_app.logger.info(f"Unsupported lang_code '{lang_code}' in author_books. Aborting 404.")
        abort(404)
        
    # Validar el segmento de URL recibido
    expected_segment = get_url_segment('author', lang_code, 'author') # 'author' es la clave canónica
    if author_url_segment != expected_segment:
        current_app.logger.warning(f"Route segment mismatch for author (lang '{lang_code}'): URL segment '{author_url_segment}' != expected '{expected_segment}'. Aborting 404.")
        abort(404)
        
    t = get_t_func(lang_code)
    books = get_books_data()

    # El author_slug de la URL ya debería estar normalizado por generate_static.py
    # current_app.logger.info(f"Searching for author_slug (from URL): '{author_slug}'")
    
    matched_books = [b for b in books if b.get('author_slug') == author_slug]
    
    if matched_books:
        # Para pasar al template, obtener el nombre "humano" del autor del primer libro encontrado
        display_author = matched_books[0].get('author', author_slug)
        return render_template('author_books.html', 
                               books=matched_books, lang=lang_code, t=t,
                               page_author_display=display_author) # Pasar para el título de la página, etc.
    else:
        current_app.logger.warning(f"Author not found for lang '{lang_code}': /{author_url_segment}/{author_slug}/")
        abort(404)

# Ruta de prueba simple si generate_static.py la necesita
@main_bp.route('/test/')
def test_page():
    # current_app.logger.info("Accediendo a la página de test.")
    return "<h1>Test Page</h1><p>This is a test page for static generation.</p>", 200