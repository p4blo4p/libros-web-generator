# app/config.py
import os

class Config:
    """Configuraciones base de la aplicación."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-clave-secreta-muy-dificil-de-adivinar'
    MINIFY_HTML = True
    # SERVER_NAME = 'localhost:5000' # Descomentar y ajustar para url_for(_external=True) si es necesario
    # APPLICATION_ROOT = '/'
    # PREFERRED_URL_SCHEME = 'http'

    # Rutas a archivos de datos (podrían ser variables de entorno también)
    BOOKS_CSV_PATH = 'books.csv'
    BESTSELLERS_JSON_PATH = 'social/amazon_bestsellers_es.json'
    TRANSLATIONS_JSON_PATH = 'translations.json' # O gestionarlo directamente en translations.py

    STATIC_FOLDER = 'static'
    TEMPLATE_FOLDER = 'templates'
    SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'it', 'de']
    DEFAULT_LANGUAGE = 'en'
    URL_SEGMENT_TRANSLATIONS = {
        'book': {'en': 'book', 'es': 'libro', 'fr': 'livre', 'it': 'libro', 'de': 'buch'},
        'author': {'en': 'author', 'es': 'autor', 'fr': 'auteur', 'it': 'autore', 'de': 'autor'},
        'versions': {'en': 'versions', 'es': 'versiones', 'fr': 'versions', 'it': 'versioni', 'de': 'versionen'}
        # Añade otros segmentos estructurales si los tienes
    }