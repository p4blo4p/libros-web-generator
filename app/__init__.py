# app/__init__.py
from flask import Flask
from app.config import Config
from flask_minify import Minify
from app.utils.helpers import ensure_https_filter, slugify_ascii
from app.utils.translations import TranslationManager
from app.models.data_loader import load_processed_books, load_processed_bestsellers
from app.utils.context_processors import inject_global_template_variables
import logging
import os  # Necesario para la configuración de logging


def create_app(config_class=Config):
    app = Flask(
        __name__,
        static_folder=config_class.STATIC_FOLDER,  # Se toma de Config
        template_folder=config_class.TEMPLATE_FOLDER,  # Se toma de Config
        # APPLICATION_ROOT y SERVER_NAME se establecen en la clase Config
        # y Flask los recogerá de app.config
    )
    app.config.from_object(config_class)

    # Flask-Minify (se basa en app.config['MINIFY_HTML'])
    Minify(app=app, html=app.config.get('MINIFY_HTML', True), js=True, cssless=True)

    # --- Configuración de Logging Detallado ---
    # Tu código de logging, asegurándose de que no haya conflicto si se corre desde generate_static.py
    if not app.debug or app.config.get('FORCE_DETAILED_LOGGING', False):
        # Limpiar handlers existentes para evitar duplicados si create_app se llama varias veces
        # (generate_static.py podría crear una instancia para config y luego otra para workers)
        # Esto es más relevante si el logger es el logger raíz o el logger de la app.

        # Solo modificar handlers si es el logger de la app y no tiene ya los específicos.
        # O si es el logger raíz y quieres controlarlo.
        # Para simplificar: si no hay handlers o los que hay son los por defecto de Flask:
        if (
            not app.logger.handlers or
            (
                len(app.logger.handlers) == 1 and
                isinstance(app.logger.handlers[0], logging.StreamHandler) and
                app.logger.handlers[0].formatter._fmt == logging.BASIC_FORMAT
            )
        ):
            app.logger.handlers.clear()  # Limpia los handlers por defecto de Flask si los hay
            app.logger.setLevel(logging.DEBUG)  # O app.config.get('LOG_LEVEL', 'DEBUG').upper()

            log_dir = os.path.join(app.root_path, '..', 'logs')  # Asumiendo que logs está al nivel de la carpeta app
            os.makedirs(log_dir, exist_ok=True)

            # Handler para consola (StreamHandler)
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.DEBUG)  # O el nivel que desees para consola
            formatter_stream = logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(module)s:%(lineno)d]'  # Más conciso para consola
            )
            stream_handler.setFormatter(formatter_stream)
            app.logger.addHandler(stream_handler)

            # Handler para archivo (RotatingFileHandler)
            # Solo añadir si no estamos en un worker de generate_static que podría tener su propio log
            if not os.environ.get('IS_STATIC_GENERATION_WORKER'):  # Variable a definir en worker_init
                file_handler = logging.handlers.RotatingFileHandler(
                    os.path.join(log_dir, 'app.log'), maxBytes=102400, backupCount=5
                )
                file_handler.setLevel(logging.DEBUG)  # O el nivel que desees para archivo
                formatter_file = logging.Formatter(
                    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
                )
                file_handler.setFormatter(formatter_file)
                app.logger.addHandler(file_handler)

            app.logger.propagate = False  # Evitar que los logs suban al logger raíz si lo configuras aparte
            app.logger.info("Detailed logging configured for Flask app.")
    else:
        # Logging por defecto de Flask cuando app.debug = True
        app.logger.setLevel(logging.DEBUG)
        app.logger.info("Flask default debug logging active.")

    # --- FIN Configuración de Logging ---

    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.filters['ensure_https'] = ensure_https_filter
    app.jinja_env.filters['slugify_ascii'] = slugify_ascii
    app.context_processor(inject_global_template_variables)

    # Cargar datos y gestor de traducciones
    # Usar try-except para robustez
    try:
        app.books_data = load_processed_books(app.config['BOOKS_DATA_DIR'])
        app.bestsellers_data = load_processed_bestsellers(app.config['BESTSELLERS_JSON_PATH'])
        app.translations_manager = TranslationManager(
            app.config['TRANSLATIONS_JSON_PATH'],
            app.config['DEFAULT_LANGUAGE']
        )
        if not app.books_data:
            app.logger.error("CRITICAL ERROR: Book data not loaded (app.books_data is empty).")
        else:
            app.logger.info(f"{len(app.books_data)} books loaded.")
        if not app.bestsellers_data:
            app.logger.warning("WARNING: Bestsellers data not loaded (app.bestsellers_data is empty).")
        else:
            app.logger.info(f"{len(app.bestsellers_data)} bestsellers loaded.")
    except Exception as e:
        app.logger.exception(f"Failed to load data or initialize TranslationManager: {e}")
        app.books_data = []  # Asegurar que existan como listas vacías si falla la carga
        app.bestsellers_data = []
        # Podrías necesitar un TranslationManager dummy o manejar la ausencia
        app.translations_manager = None

    from app.routes.main_routes import main_bp
    from app.routes.sitemap_routes import sitemap_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(sitemap_bp)

    app.logger.info("BookList Application instance created and configured.")
    return app
