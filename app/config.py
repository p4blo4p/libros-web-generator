# app/config.py
import os

class Config:
    """Configuraciones base de la aplicación."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-clave-secreta-muy-dificil-de-adivinar'
    MINIFY_HTML = True
    #SERVER_NAME = 'localhost:5000' # Descomentar y ajustar para url_for(_external=True) si es necesario
    # APPLICATION_ROOT = '/'
    # PREFERRED_URL_SCHEME = 'http'

    # Rutas a archivos de datos (podrían ser variables de entorno también)
    BOOKS_DATA_DIR = 'data/books_collection/'
    BESTSELLERS_JSON_PATH = 'social/amazon_bestsellers_es.json'
    TRANSLATIONS_JSON_PATH = 'data/translations.json' # O gestionarlo directamente en translations.py

    STATIC_FOLDER = 'static'
    TEMPLATE_FOLDER = 'templates'
    SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'it', 'de']
    DEFAULT_LANGUAGE = 'en'

    # Diccionario de traducciones para los segmentos de URL
    # Clave: 'segmento_canonico' -> {'lang_code': 'traduccion', ...}
    URL_SEGMENT_TRANSLATIONS = {
        'book': {'en': 'book', 'es': 'libro', 'fr': 'livre', 'it': 'libro', 'de': 'buch'},
        'author': {'en': 'author', 'es': 'autor', 'fr': 'auteur', 'it': 'autore', 'de': 'autor'},
        'versions': {'en': 'versions', 'es': 'versiones', 'fr': 'versions', 'it': 'versioni', 'de': 'versionen'}
        # Añade otros segmentos estructurales si los tienes
    }

    # NUEVO: Mapeo de endpoints a los segmentos de URL que deben ser traducidos
    # y el nombre del parámetro de URL que usan.
    # Clave: 'nombre_del_blueprint.nombre_de_la_funcion_vista'
    # Valor: {'segmento_canonico': 'nombre_del_parametro_en_la_ruta_url'}
    URL_SEGMENTS_TO_TRANSLATE = {
        'main.book_by_identifier': {'book': 'book_url_segment'},
        'main.book_versions': {'versions': 'versions_url_segment'},
        'main.author_books': {'author': 'author_url_segment'},
        # 'main.index': {}, # No necesita segmentos traducibles en la ruta (aparte del lang_code)
        # Añade otros endpoints si tienen segmentos de ruta traducibles
    }