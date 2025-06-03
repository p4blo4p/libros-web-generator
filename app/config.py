# app/config.py
import os


class Config:
    """Configuraciones base de la aplicación."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-clave-secreta-muy-dificil-de-adivinar'
    MINIFY_HTML = True  # Opcional: si usas alguna extensión para minificar HTML
    SERVER_NAME = 'https://p4blo4p.github.io/libros-web-generator' # Descomentar y ajustar para url_for(_external=True) si es necesario localmente
    # APPLICATION_ROOT = '/'
    # PREFERRED_URL_SCHEME = 'http' # O 'https' si se sirve bajo HTTPS

    # Rutas a archivos de datos  # E302 Corregido: Añadida línea en blanco arriba
    BOOKS_DATA_DIR = 'data/books_collection/'
    BESTSELLERS_JSON_PATH = 'social/amazon_bestsellers_es.json'
    TRANSLATIONS_JSON_PATH = 'data/translations.json'

    # Carpetas de la aplicación Flask
    STATIC_FOLDER = 'static'
    TEMPLATE_FOLDER = 'templates'

    # Configuraciones de idioma
    SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'it', 'de']
    DEFAULT_LANGUAGE = 'en'  # E261 Corregido

    # Traducciones para segmentos de URL (clave canónica -> {'lang': 'traduccion'})  # E261 Corregido
    URL_SEGMENT_TRANSLATIONS = {
        'book': {'en': 'book', 'es': 'libro', 'fr': 'livre', 'it': 'libro', 'de': 'buch'},
        'author': {'en': 'author', 'es': 'autor', 'fr': 'auteur', 'it': 'autore', 'de': 'autor'},
        'versions': {'en': 'versions', 'es': 'versiones', 'fr': 'versions', 'it': 'versioni', 'de': 'versionen'}
        # Añade otros segmentos estructurales si los tienes, ej:  # E261 Corregido
        # 'category': {'en': 'category', 'es': 'categoria', ...}
    }

    # Mapeo de endpoints a los segmentos de URL que deben ser traducidos
    # y el nombre del parámetro de URL que usan en la definición de la ruta.
    # Clave: 'nombre_del_blueprint.nombre_de_la_funcion_vista'
    # Valor: {'segmento_canonico_de_URL_SEGMENT_TRANSLATIONS': 'nombre_del_parametro_en_la_ruta_url'}
    URL_SEGMENTS_TO_TRANSLATE = {
        'main.book_by_identifier': {'book': 'book_url_segment'},
        'main.book_versions': {'versions': 'versions_url_segment'},
        'main.author_books': {'author': 'author_url_segment'},
        # 'main.index': {}, # No necesita segmentos traducibles en la ruta (aparte del lang_code)  # E261 Corregido
        # Si tuvieras una ruta como /<lang_code>/<category_url_segment>/...  # E261 Corregido
        # 'main.category_page': {'category': 'category_url_segment'},
    }
