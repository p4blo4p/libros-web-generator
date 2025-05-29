# app/__init__.py
from flask import Flask
# from flask_htmlmin import HTMLMIN  # Mantenlo comentado por ahora

from app.config import Config
from flask_minify import Minify  # Importar
from app.utils.helpers import ensure_https_filter, slugify_ascii  # <--- IMPORTA slugify_ascii AQUÍ
from app.utils.translations import TranslationManager
from app.models.data_loader import load_processed_books, load_processed_bestsellers
from app.utils.context_processors import inject_global_template_variables
import logging

# htmlmin = HTMLMIN()  # Mantenlo comentado


def create_app(config_class=Config):
    app = Flask(
        __name__,
        static_folder=config_class.STATIC_FOLDER,
        template_folder=config_class.TEMPLATE_FOLDER
    )
    app.config.from_object(config_class)

    # Configuración del entorno Jinja2
    app.jinja_env.trim_blocks = True  # Elimina el primer salto de línea después de un bloque
    app.jinja_env.lstrip_blocks = True  # Elimina los espacios en blanco iniciales de una línea hasta el inicio de un bloque

    # Inicializar Flask-Minify
    # Usará el valor de app.config['MINIFY_HTML']
    # También puedes pasar html=True, js=True, cssless=True directamente aquí
    Minify(app=app, html=True, js=True, cssless=True)

    # --- Configuración de Logging Detallado ---
    # (Tu código de logging aquí, como lo teníamos antes)
    if not app.debug or app.config.get('FORCE_DETAILED_LOGGING', False):
        app.logger.handlers.clear()
        app.logger.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        )
        stream_handler.setFormatter(formatter)

        app.logger.addHandler(stream_handler)
        app.logger.propagate = False
        app.logger.info("Detailed logging configured.")
    else:
        app.logger.setLevel(logging.DEBUG)
        app.logger.info("Flask default debug logging active.")
    # --- FIN Configuración de Logging Detallado ---

    # Registrar filtros Jinja2
    app.jinja_env.filters['ensure_https'] = ensure_https_filter
    app.jinja_env.filters['slugify_ascii'] = slugify_ascii  # <--- REGISTRA EL FILTRO AQUÍ

    # Registrar el context processor para variables globales
    app.context_processor(inject_global_template_variables)

    # Cargar datos y gestor de traducciones
    app.books_data = load_processed_books(app.config['BOOKS_DATA_DIR'])
    app.bestsellers_data = load_processed_bestsellers(app.config['BESTSELLERS_JSON_PATH'])
    app.translations_manager = TranslationManager(
        app.config['TRANSLATIONS_JSON_PATH'],
        app.config['DEFAULT_LANGUAGE']
    )

    # Registrar Blueprints
    from app.routes.main_routes import main_bp
    from app.routes.sitemap_routes import sitemap_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(sitemap_bp)

    app.logger.info("BookList Application created and configured.")
    if not app.books_data:
        app.logger.error("CRITICAL ERROR: Book data not loaded (app.books_data is empty).")
    if not app.bestsellers_data:
        app.logger.warning("WARNING: Bestsellers data not loaded (app.bestsellers_data is empty).")

    return app
