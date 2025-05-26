# app/routes/main_routes.py
from flask import Blueprint, render_template, request, abort, current_app, redirect, url_for
from app.utils.helpers import is_valid_isbn, is_valid_asin

main_bp = Blueprint('main', __name__)

# Estos deberían idealmente venir de app.config o ser cargados allí.
# Asegúrate de que estos valores sean consistentes con generate_static.py
SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'it', 'de']
DEFAULT_LANGUAGE = 'en'

# Función para obtener el segmento URL traducido
# Esta función se modifica ligeramente para incluir el log que se observa en la traza.
def get_url_segment(segment_key, lang_code, default_segment_value='book'):
    """
    Obtiene el segmento de URL traducido para una clave y un idioma dados.
    'segment_key' es la clave canónica del segmento (ej: 'book', 'author').
    'lang_code' es el código de idioma para la traducción.
    'default_segment_value' es el valor a usar si no se encuentra traducción ni siquiera en el idioma por defecto.
    Este valor suele ser la versión en inglés del segment_key (ej: 'book' para la clave 'book').
    """
    # Accede a URL_SEGMENT_TRANSLATIONS, que debería estar configurado así:
    # current_app.config['URL_SEGMENT_TRANSLATIONS'] = {
    #     'book': {'en': 'book', 'es': 'libro', 'it': 'libro', ...},
    #     'author': {'en': 'author', 'es': 'autor', ...}
    # }
    all_translations = current_app.config.get('URL_SEGMENT_TRANSLATIONS', {})
    segments_for_key = all_translations.get(segment_key, {})
    
    # Determina el valor de fallback:
    # 1. Traducción en el idioma por defecto (DEFAULT_LANGUAGE).
    # 2. O el 'default_segment_value' proporcionado.
    fallback_value = segments_for_key.get(DEFAULT_LANGUAGE, default_segment_value)
    
    # Obtiene la traducción para el lang_code dado, o usa el fallback_value.
    translated_value = segments_for_key.get(lang_code, fallback_value)
    
    # Log correspondiente a la línea observada [main_routes.py:22]
    # El log original es "Segment for 'book' in 'it': 'libro' [in /opt/buildhome/repo/app/routes/main_routes.py:22]"
    current_app.logger.debug(f"Segment for '{segment_key}' in '{lang_code}': '{translated_value}'")
    
    return translated_value

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

# Esta es la función url_defaults inferida de los logs.
# Se registra para ser llamada por url_for() para rellenar/modificar valores.
@main_bp.url_defaults
def url_defaults(endpoint, values):
    # Log correspondiente a [main_routes.py:64]
    current_app.logger.debug(f"--- url_defaults START --- Endpoint: '{endpoint}', Initial values: {values}")

    # Obtener lang_code de los valores pasados a url_for.
    # Si no está, podría intentar obtenerse del contexto de la solicitud actual o usar el predeterminado.
    # Los logs muestran que 'lang_code' está presente en 'Initial values'.
    lang_code_from_values = values.get('lang_code')
    
    # Log correspondiente a [main_routes.py:71]
    current_app.logger.debug(f"url_defaults: lang_code from values.get('lang_code'): '{lang_code_from_values}'")

    # Si no se proporciona lang_code en url_for, se podría intentar obtener del contexto actual.
    # Esto es útil si se llama a url_for sin lang_code desde una vista que ya tiene lang_code.
    if lang_code_from_values is None:
        if request and hasattr(request, 'view_args') and 'lang_code' in request.view_args:
            lang_code_from_values = request.view_args['lang_code']
        # Si aún no hay lang_code, y el endpoint lo requiere (la mayoría lo hacen aquí),
        # se podría establecer uno por defecto o dejar que Flask falle si es un parámetro requerido.
        # Por ahora, asumimos que lang_code será provisto o no es necesario para todos los endpoints.

    # Lógica para traducir segmentos de URL.
    # Esto requiere una configuración como:
    # current_app.config['URL_SEGMENTS_TO_TRANSLATE'] = {
    #     'main.book_by_identifier': {'book': 'book_segment'}, # 'book' es la clave, 'book_segment' es el param en la URL
    #     'main.author_books': {'author': 'author_segment_name_in_url'}, # Ejemplo
    #     'main.index': {} # No necesita traducción de segmento
    # }
    segments_config_map = current_app.config.get('URL_SEGMENTS_TO_TRANSLATE', {})
    
    # Obtener la configuración de segmentos para el endpoint actual.
    # ESTA ES LA PARTE CRÍTICA DONDE PODRÍA OCURRIR EL ERROR SI LA CONFIGURACIÓN NO ES UN DICCIONARIO.
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
        # segments_for_this_endpoint permanece como {}
    
    if segments_for_this_endpoint: # Si hay segmentos definidos para traducir para este endpoint
        # Asegurar que el lang_code sea válido para la traducción, usando el idioma por defecto como fallback.
        # Usar el lang_code de values si está disponible, sino el del contexto de la solicitud o el por defecto.
        effective_lang_code = lang_code_from_values
        if effective_lang_code not in SUPPORTED_LANGUAGES:
            effective_lang_code = DEFAULT_LANGUAGE
        
        # Si lang_code no estaba en values, pero lo hemos deducido, añadirlo.
        values.setdefault('lang_code', effective_lang_code)

        for original_segment_key, target_url_param_name in segments_for_this_endpoint.items():
            # original_segment_key: ej. 'book', 'author' (clave para buscar en URL_SEGMENT_TRANSLATIONS)
            # target_url_param_name: ej. 'book_segment' (nombre del parámetro en la regla de URL y en 'values')
            
            # El default_segment_value para get_url_segment debería ser la versión en inglés del segmento.
            # Asumimos que original_segment_key es la versión en inglés (ej: 'book').
            translated_segment = get_url_segment(original_segment_key, effective_lang_code, default_segment_value=original_segment_key)
            
            # Log correspondiente a [main_routes.py:111]
            current_app.logger.debug(f"url_defaults: get_url_segment returned: '{translated_segment}' for key='{original_segment_key}', lang='{effective_lang_code}'")
            
            # Log correspondiente a [main_routes.py:113]
            current_app.logger.debug(f"url_defaults: Values BEFORE setdefault for '{target_url_param_name}': {values}")
            values.setdefault(target_url_param_name, translated_segment)
            # Log correspondiente a [main_routes.py:115]
            current_app.logger.debug(f"url_defaults: Values AFTER setdefault for '{target_url_param_name}': {values}")
            # Log correspondiente a [main_routes.py:116]
            current_app.logger.debug(f"url_defaults: Segment '{target_url_param_name}' is now '{values[target_url_param_name]}'")
    else:
        # Log correspondiente a [main_routes.py:118]
        current_app.logger.debug(f"url_defaults: No segment translation needed for endpoint '{endpoint}'")
        # Asegurarse de que lang_code esté en values si no se hizo traducción pero se conoce
        if lang_code_from_values and 'lang_code' not in values:
            values['lang_code'] = lang_code_from_values
        elif 'lang_code' not in values and endpoint != 'main.root_index': # root_index no necesita lang_code en values
             # Si no hay lang_code y no es el root_index, usar el default.
             # Esto es importante para que url_for(main.index) funcione correctamente.
            values.setdefault('lang_code', DEFAULT_LANGUAGE)


    # Log correspondiente a [main_routes.py:120]
    current_app.logger.debug(f"--- url_defaults END --- Endpoint: '{endpoint}', Final values for url_for: {values}")


@main_bp.route('/')
def root_index():
    """Redirige la raíz del sitio a la versión con el idioma por defecto."""
    return redirect(url_for('main.index', lang_code=DEFAULT_LANGUAGE))

@main_bp.route('/<lang_code>/')
def index(lang_code):
    """Página de inicio para un idioma específico."""
    if lang_code not in SUPPORTED_LANGUAGES:
        return redirect(url_for('main.index', lang_code=DEFAULT_LANGUAGE))
    
    t = get_t_func(lang_code)
    bestsellers = get_bestsellers_data()
    return render_template('index.html', books_data=bestsellers, lang=lang_code, t=t)

# La ruta para book_by_identifier debe usar el nombre del parámetro que se establece en url_defaults.
# Si URL_SEGMENTS_TO_TRANSLATE es {'main.book_by_identifier': {'book': 'book_segment'}},
# entonces la ruta debe ser /<lang_code>/<book_segment>/...
# Sin embargo, el código original tiene /<lang_code>/book/...
# Esto implica que 'book_segment' es solo para `url_for`, y la ruta real es fija.
# O, que las rutas también son dinámicas (lo cual es más complejo).
# Asumiré que las rutas son fijas como en el código original, y 'book_segment' se usa si la ruta fuera <book_segment>.
# Si la ruta es fija con 'book', entonces la traducción de 'book' no se usa en la definición de la ruta,
# sino en los enlaces generados por url_for si la ruta estuviera parametrizada con <book_segment>.
# Dado el ejemplo de "libro" para "it", es probable que las rutas SÍ sean dinámicas.
# Ejemplo: @main_bp.route('/<lang_code>/<book_segment>/<author_slug>/<book_slug>/<identifier>/')
# Por ahora, mantendré las rutas como en el original, y 'book_segment' en url_defaults sería para
# si se necesitara construir URLs con ese segmento traducido. Si las rutas NO usan <book_segment>,
# entonces la traducción de 'book' no tiene efecto en la formación de la URL.

@main_bp.route('/<lang_code>/book/<author_slug>/<book_slug>/<identifier>/')
def book_by_identifier(lang_code, author_slug, book_slug, identifier): # 'book' es fijo aquí
    """Página de detalle de un libro para un idioma específico."""
    if lang_code not in SUPPORTED_LANGUAGES:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in book_by_identifier. Aborting 404.")
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
        original_title = matched_versions[0].get('title', '')
        display_base_title = original_title.split('(')[0].strip() if original_title else base_book_slug

        return render_template('book_versions.html', 
                               books=matched_versions, lang=lang_code, t=t,
                               page_author_display=display_author,
                               page_base_title_display=display_base_title)
    else:
        current_app.logger.warning(f"Versions not found for lang '{lang_code}': /versions/{author_slug}/{base_book_slug}/")
        abort(404)


@main_bp.route('/<lang_code>/author/<author_slug>/')
def author_books(lang_code, author_slug): # 'author' es fijo aquí
    """Página de libros de un autor para un idioma específico."""
    if lang_code not in SUPPORTED_LANGUAGES:
        current_app.logger.info(f"Unsupported lang_code '{lang_code}' in author_books. Aborting 404.")
        abort(404)
        
    t = get_t_func(lang_code)
    books = get_books_data()

    processed_author_slug = author_slug.lower()
    current_app.logger.info(f"Searching for author_slug (original): '{author_slug}', (processed for search): '{processed_author_slug}'")
    
    matched_books = [b for b in books if b.get('author_slug') == processed_author_slug]
    
    if matched_books:
        display_author = matched_books[0].get('author', author_slug)
        return render_template('author_books.html', 
                               books=matched_books, lang=lang_code, t=t,
                               page_author_display=display_author)
    else:
        current_app.logger.warning(f"Author not found for lang '{lang_code}': /author/{author_slug}/ (searched as '{processed_author_slug}')")
        abort(404)
