# app/__init__.py
from flask import Flask
from flask_htmlmin import HTMLMIN
from app.config import Config
from app.utils.helpers import ensure_https_filter
from app.utils.translations import TranslationManager
from app.models.data_loader import load_processed_books, load_processed_bestsellers

htmlmin = HTMLMIN()

def create_app(config_class=Config):
    app = Flask(__name__,
                static_folder=config_class.STATIC_FOLDER,
                template_folder=config_class.TEMPLATE_FOLDER)
    app.config.from_object(config_class)

    # Inicializar extensiones
    if app.config['MINIFY_HTML']:
        htmlmin.init_app(app)

    # Registrar filtros Jinja2
    app.jinja_env.filters['ensure_https'] = ensure_https_filter

    # Cargar datos y gestor de traducciones y adjuntarlos a la app
    # Esto asegura que se cargan una vez al iniciar la app
    app.books_data = load_processed_books(app.config['BOOKS_CSV_PATH'])
    app.bestsellers_data = load_processed_bestsellers(app.config['BESTSELLERS_JSON_PATH'])
    app.translations_manager = TranslationManager(app.config['TRANSLATIONS_JSON_PATH'])

    # Registrar Blueprints
    from app.routes.main_routes import main_bp
    from app.routes.sitemap_routes import sitemap_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(sitemap_bp)

    # Configurar logging si es necesario
    if not app.debug:
        # ... configuraciones de logging para producción ...
        pass
    
    app.logger.info("Aplicación BookList creada y configurada.")
    if not app.books_data:
        app.logger.error("ERROR CRÍTICO: No se cargaron datos de libros (app.books_data está vacío).")
    if not app.bestsellers_data:
        app.logger.warning("ADVERTENCIA: No se cargaron datos de bestsellers (app.bestsellers_data está vacío).")


    return app