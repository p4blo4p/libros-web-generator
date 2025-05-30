# app/config.py
import os

# --- NUEVAS VARIABLES DE ENTORNO PARA GITHUB PAGES ---
# Estas serán establecidas por el workflow de GitHub Actions.
# Si ejecutas localmente y quieres simular GH Pages, establece estas en tu .env o entorno.
GITHUB_PAGES_REPO_NAME = os.environ.get('GITHUB_PAGES_REPO_NAME')
GITHUB_PAGES_USERNAME = os.environ.get('GITHUB_PAGES_USERNAME')
# --- FIN NUEVAS VARIABLES ---

class Config:
    """Configuraciones base de la aplicación."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-clave-secreta-muy-dificil-de-adivinar'
    MINIFY_HTML = True

    # --- AJUSTES PARA RUTAS EN FUNCIÓN DEL ENTORNO (LOCAL VS GITHUB PAGES) ---
    if GITHUB_PAGES_REPO_NAME:
        # Estamos en GitHub Pages o simulándolo
        APPLICATION_ROOT = f'/{GITHUB_PAGES_REPO_NAME}'
        if GITHUB_PAGES_USERNAME:
            SERVER_NAME = f'{GITHUB_PAGES_USERNAME}.github.io'
            PREFERRED_URL_SCHEME = 'https'
        else:
            # Solo repo_name, _external=True podría no ser perfecto, pero APPLICATION_ROOT es clave
            SERVER_NAME = None # Dejar que Flask lo infiera o falle si _external=True se usa sin host
            PREFERRED_URL_SCHEME = 'https' # Asumimos https para GH Pages
        print(f"[CONFIG] GitHub Pages Mode: APP_ROOT='{APPLICATION_ROOT}', SERVER_NAME='{SERVER_NAME}'")
    else:
        # Configuración para desarrollo local estándar
        SERVER_NAME = os.environ.get('FLASK_RUN_HOST', '127.0.0.1') + ':' + os.environ.get('FLASK_RUN_PORT', '5000')
        APPLICATION_ROOT = '/'
        PREFERRED_URL_SCHEME = 'http' # O 'https' si sirves localmente bajo HTTPS
        print(f"[CONFIG] Local Mode: APP_ROOT='{APPLICATION_ROOT}', SERVER_NAME='{SERVER_NAME}'")
    # --- FIN AJUSTES DE RUTAS ---

    # Rutas a archivos de datos
    BOOKS_DATA_DIR = 'data/books_collection/'
    BESTSELLERS_JSON_PATH = 'social/amazon_bestsellers_es.json'
    TRANSLATIONS_JSON_PATH = 'data/translations.json'

    # Carpetas de la aplicación Flask
    STATIC_FOLDER = 'static' # Relativo a la raíz de la app
    TEMPLATE_FOLDER = 'templates' # Relativo a la raíz de la app

    # Configuraciones de idioma
    SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'it', 'de']
    DEFAULT_LANGUAGE = 'en'

    # Traducciones para segmentos de URL (clave canónica -> {'lang': 'traduccion'})
    URL_SEGMENT_TRANSLATIONS = {
        'book': {'en': 'book', 'es': 'libro', 'fr': 'livre', 'it': 'libro', 'de': 'buch'},
        'author': {'en': 'author', 'es': 'autor', 'fr': 'auteur', 'it': 'autore', 'de': 'autor'},
        'versions': {'en': 'versions', 'es': 'versiones', 'fr': 'versions', 'it': 'versioni', 'de': 'versionen'}
    }

    # Mapeo de endpoints a los segmentos de URL que deben ser traducidos
    URL_SEGMENTS_TO_TRANSLATE = {
        'main.book_by_identifier': {'book': 'book_url_segment'},
        'main.book_versions': {'versions': 'versions_url_segment'},
        'main.author_books': {'author': 'author_url_segment'},
    }
