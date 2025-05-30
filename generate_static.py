# generate_static.py
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging
import os # <--- AÑADIDO
from logging.handlers import RotatingFileHandler # <--- AÑADIDO para logging de script más robusto
from multiprocessing import Pool, cpu_count, current_process
from functools import partial
import argparse
import json
import hashlib
import time

# --- Carga de .env para variables de entorno (ej. GITHUB_PAGES_*) ---
# Esto debe hacerse ANTES de importar cualquier cosa de 'app' que pueda usar Config
try:
    from dotenv import load_dotenv
    dotenv_path = Path(__file__).resolve().parent.parent / '.env' # Asume .env en la raíz del proyecto
    if dotenv_path.exists():
        print(f"[generate_static.py] Loading .env file from: {dotenv_path}")
        load_dotenv(dotenv_path)
    else:
        print(f"[generate_static.py] .env file not found at {dotenv_path}, using system environment variables.")
except ImportError:
    print("[generate_static.py] python-dotenv not found, .env file will not be loaded. Using system environment variables.")
# --- FIN Carga de .env ---


# --- Configuración del Logger Básico para el Script ---
# (Mantenemos tu logger de script, pero podría ser bueno hacerlo un poco más configurable)
script_logger = logging.getLogger('generate_static_script')
# Evitar añadir handlers múltiples veces si el script se importa o se re-ejecuta en un mismo proceso
if not script_logger.handlers:
    script_logger.setLevel(os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper())
    script_handler = logging.StreamHandler()
    script_formatter = logging.Formatter(
        '%(asctime)s - %(name)s:%(processName)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
    )
    script_handler.setFormatter(script_formatter)
    script_logger.addHandler(script_handler)
    script_logger.propagate = False # Para que no envíe logs al logger raíz si está configurado


# --- Variables Globales para Workers ---
worker_app_instance = None
worker_logger = None
slugify_to_use_global_worker = None


# --- CONSTANTES ---
MANIFEST_DIR = Path(".cache")
MANIFEST_FILE = MANIFEST_DIR / "generation_manifest.json"
OUTPUT_DIR = Path(os.environ.get('STATIC_SITE_OUTPUT_DIR', '_site')) # Usa variable de entorno o default _site
ALPHABET = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_CHARS_SITEMAP_KEY = "0"


# --- FUNCIONES DE UTILIDAD (LOCALES AL SCRIPT) ---
def slugify_ascii_local(text):
    # Tu función slugify_ascii_local ...
    if text is None:
        return ""
    text_str = str(text)
    text_und = unidecode(text_str)
    text_low = text_und.lower()
    text_re1 = re.sub(r'[^\w\s-]', '', text_low)
    text_re2 = re.sub(r'\s+', '-', text_re1)
    text_re3 = re.sub(r'--+', '-', text_re2)
    text_strip = text_re3.strip('-')
    return text_strip if text_strip else "na"


slugify_to_use_global_main = slugify_ascii_local
try:
    # La importación de app y sus utils debe ser DESPUÉS de load_dotenv
    from app.utils.helpers import slugify_ascii as slugify_ascii_app_main
    slugify_to_use_global_main = slugify_ascii_app_main
    script_logger.info("Proceso principal usando slugify_ascii de app.utils.helpers.")
except ImportError:
    script_logger.warning("Proceso principal usando slugify_ascii local (app.utils.helpers no encontrado).")


def get_sitemap_char_group_for_author_local(author_name_or_slug, slugifier_func):
    # Tu función get_sitemap_char_group_for_author_local ...
    if not author_name_or_slug:
        return SPECIAL_CHARS_SITEMAP_KEY
    processed_slug = slugifier_func(author_name_or_slug)
    if not processed_slug:
        return SPECIAL_CHARS_SITEMAP_KEY
    first_char = processed_slug[0].lower()
    if first_char in ALPHABET:
        return first_char
    return SPECIAL_CHARS_SITEMAP_KEY


def get_translated_url_segment_for_generator(
    segment_key, lang_code, url_segment_translations,
    default_app_lang, default_segment_value=None
):
    # Tu función get_translated_url_segment_for_generator ...
    if not url_segment_translations or not isinstance(url_segment_translations, dict):
        return default_segment_value if default_segment_value is not None else segment_key
    segments_for_key = url_segment_translations.get(segment_key, {})
    if not isinstance(segments_for_key, dict):
        return default_segment_value if default_segment_value is not None else segment_key
    translated_segment = segments_for_key.get(lang_code)
    if translated_segment:
        return translated_segment
    if lang_code != default_app_lang:
        translated_segment_default_lang = segments_for_key.get(default_app_lang)
        if translated_segment_default_lang:
            return translated_segment_default_lang
    if default_segment_value is not None:
        return default_segment_value
    return segment_key


# --- MANIFEST HELPER FUNCTIONS ---
# (Tus funciones de manifest: load_manifest, save_manifest, get_book_signature_fields,
# calculate_signature, should_regenerate_page ... sin cambios necesarios aquí)
def load_manifest():
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            script_logger.warning(f"Error al decodificar {MANIFEST_FILE}. Se creará uno nuevo.")
            return {}
    script_logger.info(f"Archivo manifest {MANIFEST_FILE} no encontrado. Se creará uno nuevo.")
    return {}

def save_manifest(manifest_data):
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2)
    script_logger.info(f"Manifest de generación guardado en {MANIFEST_FILE} con {len(manifest_data)} entradas.")

def get_book_signature_fields(book_data):
    fields_for_signature = {
        "isbn10": book_data.get("isbn10"), "isbn13": book_data.get("isbn13"),
        "asin": book_data.get("asin"), "title_slug": book_data.get("title_slug"),
        "author_slug": book_data.get("author_slug"),
        "description": book_data.get("description_short") or book_data.get("description"),
        "cover_image_url": (
            book_data.get("image_url_l") or
            book_data.get("image_url_m") or
            book_data.get("image_url_s")
        ),
        "publication_date": book_data.get("publication_date"),
        "publisher": book_data.get("publisher_name"),
        "language_code": book_data.get("language_code"),
    }
    return dict(sorted(fields_for_signature.items()))

def calculate_signature(data_dict_for_signature):
    json_string = json.dumps(data_dict_for_signature, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(json_string.encode('utf-8')).hexdigest()

def should_regenerate_page(output_path_str, current_signature, manifest_data, logger_to_use):
    page_manifest_entry = manifest_data.get(output_path_str)
    if not page_manifest_entry:
        logger_to_use.debug(f"REGENERAR (nuevo): {output_path_str}")
        return True
    if page_manifest_entry.get('signature') != current_signature:
        logger_to_use.debug(f"REGENERAR (firma cambiada): {output_path_str}")
        return True
    if not Path(output_path_str).exists(): # Convertir a Path object para .exists()
        logger_to_use.debug(f"REGENERAR (archivo no existe): {output_path_str}")
        return True
    logger_to_use.debug(f"SALTAR (sin cambios): {output_path_str}")
    return False


# --- FUNCIÓN _save_page_local ---
def _save_page_local(client_local, url_path, file_path_obj, logger_to_use):
    # Tu función _save_page_local ...
    # Asegúrate de que url_path considera APPLICATION_ROOT si es necesario para el test_client
    # Normalmente, test_client.get('/') funciona incluso si APPLICATION_ROOT es /repo.
    # Si Flask está bien configurado, url_for dentro de las vistas generará las URLs correctas
    # que el test_client usará.
    try:
        # url_for dentro de la app ya debería tener el prefijo de APPLICATION_ROOT si está configurado
        # y test_client.get() debería manejarlo.
        # Por ejemplo, si app.config['APPLICATION_ROOT'] = '/myrepo', y una ruta es '/page',
        # test_client.get('/myrepo/page') es lo que se probaría.
        # Sin embargo, las URLs que pasas aquí son relativas a la app (sin el APPLICATION_ROOT explícito)
        # ya que el test_client opera dentro del contexto de la app.
        # Ejemplo: app.config['APPLICATION_ROOT'] = '/myrepo'
        # Ruta en blueprint: @bp.route('/contact') -> accesible en /myrepo/contact
        # test_client.get('/contact') -> debería funcionar y testear /myrepo/contact
        # Si esto falla, podrías necesitar prefijar url_path con app.config.get('APPLICATION_ROOT', '')
        # solo para el cliente de prueba si este no lo hace automáticamente.
        # app_prefix = worker_app_instance.config.get('APPLICATION_ROOT', '') if worker_app_instance else ''
        # full_url_path_for_client = f"{app_prefix}{url_path}".replace('//', '/')
        # response = client_local.get(full_url_path_for_client)

        # Vamos a asumir que test_client.get() con la URL de la ruta (sin APPLICATION_ROOT) es correcto.
        # Flask debería mapearlo internamente.
        response = client_local.get(url_path)

        if response.status_code == 200:
            if response.data:
                file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path_obj, 'wb') as f:
                    f.write(response.data)
                logger_to_use.info(f"GENERADO: {url_path} -> {file_path_obj}")
            else:
                logger_to_use.info(f"URL {url_path} devolvió 200 sin datos. No se guardó (sitemap vacío?).")
        elif response.status_code in [301, 302, 307, 308]:
            # Las redirecciones pueden ser válidas si son internas y llevan a una página generada.
            # Podrías querer registrar la ubicación de la redirección.
            location = response.headers.get('Location')
            logger_to_use.warning(f"{url_path} REDIR {response.status_code} -> {location}. NO guardado directamente.")
        elif response.status_code == 404:
            logger_to_use.warning(f"404: {url_path} no encontrado. NO guardado.")
        else:
            logger_to_use.error(f"HTTP {response.status_code} para {url_path}. NO guardado.")
    except Exception as e:
        logger_to_use.exception(f"EXCEPCIÓN generando/guardando {url_path}: {e}")


# --- FUNCIONES WORKER PARA MULTIPROCESSING ---
def worker_init():
    global worker_app_instance, worker_logger, slugify_to_use_global_worker
    # Importar create_app aquí para que cada worker tenga su propia instancia de app
    # y así se cargue la configuración correcta (que puede depender de .env)
    from app import create_app

    # Indicar que este es un worker para que el logging de app/__init__.py se comporte diferente
    os.environ['IS_STATIC_GENERATION_WORKER'] = '1'


    proc_name = current_process().name
    worker_app_instance = create_app() # create_app ahora leerá Config con los ajustes de GH_PAGES
    worker_logger = logging.getLogger(f'generate_static_worker.{proc_name}')

    if not worker_logger.handlers:
        worker_handler = logging.StreamHandler()
        worker_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
        )
        worker_handler.setFormatter(worker_formatter)
        worker_logger.addHandler(worker_handler)

    # Asegurar que el nivel del logger del worker es al menos tan detallado como el del script principal
    # Esto es importante si el script_logger.level se establece en DEBUG dinámicamente.
    # script_logger.level no está disponible aquí directamente, pasarlo o leer de env var.
    worker_log_level_name = os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper()
    worker_logger.setLevel(getattr(logging, worker_log_level_name, logging.INFO))
    worker_logger.propagate = False # Evitar duplicados si el logger de app ya está configurado

    worker_logger.info(f"Worker {proc_name} inicializado. App APPLICATION_ROOT: '{worker_app_instance.config.get('APPLICATION_ROOT')}', SERVER_NAME: '{worker_app_instance.config.get('SERVER_NAME')}'")


    slugify_to_use_global_worker = slugify_ascii_local
    try:
        from app.utils.helpers import slugify_ascii as slugify_ascii_app_worker
        slugify_to_use_global_worker = slugify_ascii_app_worker
        worker_logger.info("Usando slugify_ascii de app.utils.helpers.")
    except ImportError:
        worker_logger.warning("Usando slugify_ascii local (app.utils.helpers no encontrado).")


# --- TAREAS DE GENERACIÓN (generate_book_detail_pages_task, etc.) ---
# (Tus funciones de task ... sin cambios necesarios aquí, ya que usan worker_app_instance
#  y las URLs que construyen para test_client.get() son relativas a la app)
#  Es importante que las URLs para Flask (f"/{lang}/...") NO incluyan el APPLICATION_ROOT
#  ya que el test_client lo maneja internamente.
#  Los Path de salida (Path(OUTPUT_DIR_BASE_STR) / lang / ...) NO deben tener el
#  APPLICATION_ROOT porque son rutas de sistema de archivos.

def generate_book_detail_pages_task(book_data_item, config_params_manifest_tuple):
    # ... tu código existente ...
    # Solo verifica que OUTPUT_DIR_BASE_STR es un Path object si lo necesitas,
    # pero parece que ya lo manejas bien.
    # Y que config_params['OUTPUT_DIR'] es una cadena para Path().
    config_params, manifest_data_global = config_params_manifest_tuple

    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE_STR = str(config_params['OUTPUT_DIR']) # Asegurar que es string para Path()
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)

    log_target = worker_logger # Usar el logger del worker
    generated_pages_info = []

    author_s_original = book_data_item.get('author_slug')
    title_s_original = book_data_item.get('title_slug')
    identifier = book_data_item.get('isbn10') or book_data_item.get('isbn13') or book_data_item.get('asin')

    if not (identifier and author_s_original and title_s_original):
        log_target.debug(f"Saltando libro (datos incompletos): ID {identifier}, Autor '{author_s_original}', Título '{title_s_original}'")
        return generated_pages_info

    author_s = slugify_to_use_global_worker(author_s_original)
    title_s = slugify_to_use_global_worker(title_s_original)

    book_signature_fields = get_book_signature_fields(book_data_item)
    current_book_content_signature = calculate_signature(book_signature_fields)

    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                book_segment_translated = get_translated_url_segment_for_generator(
                    'book', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'book'
                )
                # Estas URLs son para Flask, NO para el sistema de archivos. No deben tener OUTPUT_DIR.
                # Y NO deben tener el APPLICATION_ROOT explícitamente, test_client lo maneja.
                flask_url = f"/{lang}/{book_segment_translated}/{author_s}/{title_s}/{identifier}/"
                
                # Estas rutas son para el SISTEMA DE ARCHIVOS. Deben ser relativas a OUTPUT_DIR.
                # NO deben incluir el APPLICATION_ROOT.
                output_path_obj = (
                    Path(OUTPUT_DIR_BASE_STR) / lang / book_segment_translated /
                    author_s / title_s / identifier / "index.html"
                )
                output_path_str = str(output_path_obj)

                if FORCE_REGENERATE_ALL or should_regenerate_page(
                    output_path_str, current_book_content_signature, manifest_data_global, log_target
                ):
                    _save_page_local(client, flask_url, output_path_obj, log_target)
                    generated_pages_info.append({
                        "path": output_path_str, # Esta es la clave para el manifest
                        "signature": current_book_content_signature,
                        "timestamp": time.time()
                    })
    return generated_pages_info

# generate_author_pages_task y generate_versions_pages_task seguirían un patrón similar.
# Asegúrate de que OUTPUT_DIR_BASE_STR es un string antes de usarlo con Path()
# y que las flask_url no tienen APPLICATION_ROOT.
def generate_author_pages_task(author_slug_original, config_params_manifest_tuple):
    config_params, manifest_data_global = config_params_manifest_tuple

    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE_STR = str(config_params['OUTPUT_DIR']) # Asegurar string
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS_DATA = config_params['ALL_BOOKS_DATA']

    log_target = worker_logger
    generated_pages_info = []
    author_s = slugify_to_use_global_worker(author_slug_original)

    author_books_data = [
        b for b in ALL_BOOKS_DATA if slugify_to_use_global_worker(b.get('author_slug')) == author_s
    ]
    if not author_books_data:
        log_target.debug(
            f"No se encontraron libros para el slug de autor procesado '{author_s}' (original '{author_slug_original}')."
        )
        return generated_pages_info

    author_page_source_identifiers = sorted([
        b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in author_books_data
    ])
    current_author_page_signature = calculate_signature({
        "book_ids_author_page": author_page_source_identifiers,
        "author_slug": author_slug_original # Usar original para la firma por consistencia
    })

    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                author_segment_translated = get_translated_url_segment_for_generator(
                    'author', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'author'
                )
                flask_url = f"/{lang}/{author_segment_translated}/{author_s}/"
                output_path_obj = (
                    Path(OUTPUT_DIR_BASE_STR) / lang / author_segment_translated / author_s / "index.html"
                )
                output_path_str = str(output_path_obj)

                if FORCE_REGENERATE_ALL or should_regenerate_page(
                    output_path_str, current_author_page_signature, manifest_data_global, log_target
                ):
                    _save_page_local(client, flask_url, output_path_obj, log_target)
                    generated_pages_info.append({
                        "path": output_path_str,
                        "signature": current_author_page_signature,
                        "timestamp": time.time()
                    })
    return generated_pages_info


def generate_versions_pages_task(author_base_title_slugs_original, config_params_manifest_tuple):
    config_params, manifest_data_global = config_params_manifest_tuple

    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE_STR = str(config_params['OUTPUT_DIR']) # Asegurar string
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS_DATA = config_params['ALL_BOOKS_DATA']

    log_target = worker_logger
    generated_pages_info = []
    author_s_orig, base_title_s_orig = author_base_title_slugs_original
    author_s = slugify_to_use_global_worker(author_s_orig)
    base_title_s = slugify_to_use_global_worker(base_title_s_orig)

    version_books_data = [
        b for b in ALL_BOOKS_DATA
        if slugify_to_use_global_worker(b.get('author_slug')) == author_s and
        slugify_to_use_global_worker(b.get('base_title_slug')) == base_title_s
    ]
    if not version_books_data:
        log_target.debug(
            f"No se encontraron libros para versiones de autor '{author_s}' (orig: '{author_s_orig}') y base_title '{base_title_s}' (orig: '{base_title_s_orig}')."
        )
        return generated_pages_info

    version_page_source_identifiers = sorted([
        b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in version_books_data
    ])
    current_version_page_signature = calculate_signature({
        "book_ids_version_page": version_page_source_identifiers,
        "author_slug": author_s_orig, # Usar originales para la firma
        "base_title_slug": base_title_s_orig
    })

    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                versions_segment_translated = get_translated_url_segment_for_generator(
                    'versions', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'versions'
                )
                flask_url = f"/{lang}/{versions_segment_translated}/{author_s}/{base_title_s}/"
                output_path_obj = (
                    Path(OUTPUT_DIR_BASE_STR) / lang / versions_segment_translated /
                    author_s / base_title_s / "index.html"
                )
                output_path_str = str(output_path_obj)

                if FORCE_REGENERATE_ALL or should_regenerate_page(
                    output_path_str, current_version_page_signature, manifest_data_global, log_target
                ):
                    _save_page_local(client, flask_url, output_path_obj, log_target)
                    generated_pages_info.append({
                        "path": output_path_str,
                        "signature": current_version_page_signature,
                        "timestamp": time.time()
                    })
    return generated_pages_info


# --- MAIN FUNCTION HELPERS ---
def _parse_cli_args():
    # Tu función _parse_cli_args ...
    parser = argparse.ArgumentParser(description="Generador de sitio estático con cache y paralelización.")
    parser.add_argument(
        "--language", type=str, default=None,
        help="Generar solo para un idioma específico (ej. 'es').")
    parser.add_argument(
        "--force-regenerate", action="store_true",
        help="Forzar la regeneración de todas las páginas, ignorando el manifest.")
    parser.add_argument(
        "--char-key", type=str, default=None,
        help="Generar solo para una clave de carácter específica (letra o 0). Requiere --language.")
    return parser.parse_args()


def _setup_environment_data(args, main_logger):
    # Tu función _setup_environment_data ...
    # La importación de app DEBE ser después de que load_dotenv haya tenido oportunidad de ejecutarse.
    from app import create_app

    main_logger.info(f"Iniciando script generate_static.py con argumentos: {args}")
    if args.force_regenerate:
        main_logger.info("FORZANDO REGENERACIÓN: El manifest será ignorado para 'should_regenerate'.")

    manifest_data = load_manifest()
    main_logger.info(f"Manifest cargado con {len(manifest_data)} entradas desde {MANIFEST_FILE}.")

    # Crear instancia de app aquí para obtener configuraciones. create_app() ya usa Config.
    app_instance = create_app()
    main_logger.info(f"Instancia de Flask creada. APP_ROOT: '{app_instance.config.get('APPLICATION_ROOT')}', SERVER_NAME: '{app_instance.config.get('SERVER_NAME')}'")


    all_configured_languages = app_instance.config.get('SUPPORTED_LANGUAGES', ['en'])
    if args.language:
        if args.language in all_configured_languages:
            languages_to_process = [args.language]
            main_logger.info(f"Procesando solo para el idioma: {args.language}")
        else:
            main_logger.error(f"Idioma '{args.language}' no está en SUPPORTED_LANGUAGES. Saliendo.")
            return None
    else:
        languages_to_process = all_configured_languages
        main_logger.info(f"Procesando para todos los idiomas: {languages_to_process}")

    # Acceder a app.books_data que se carga en create_app
    books_data_list = app_instance.books_data
    if not books_data_list: # Comprobar si está vacío
        main_logger.critical("No hay datos de libros (app.books_data vacío después de create_app). Saliendo.")
        return None
    main_logger.info(f"Idiomas: {languages_to_process}. {len(books_data_list)} libros fuente.")

    return {
        "app": app_instance, "manifest": manifest_data,
        "languages_to_process": languages_to_process,
        "default_language": app_instance.config.get('DEFAULT_LANGUAGE', 'en'),
        "url_segment_translations": app_instance.config.get('URL_SEGMENT_TRANSLATIONS', {}),
        "books_data": books_data_list,
        "output_dir_path": OUTPUT_DIR, # Usar la constante global Path object
    }


def _prepare_output_directory(app_instance, output_dir_path,  # Pasamos app_instance
                              current_lang_arg, perform_full_cleanup, char_key_arg, logger):
    # Tu función _prepare_output_directory ...
    # IMPORTANTE: app_static_folder y app_static_url_path ahora vienen de app_instance.config
    app_static_folder = app_instance.static_folder # Esto es una ruta absoluta ya
    app_static_url_path = app_instance.static_url_path # ej. /static o /myrepo/static

    if char_key_arg and current_lang_arg:
        lang_output_dir = output_dir_path / current_lang_arg
        lang_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Modo char_key: Asegurando {lang_output_dir}. Sin limpieza global.")
        return

    if perform_full_cleanup and not current_lang_arg:
        if output_dir_path.exists():
            logger.info(f"Eliminando {output_dir_path} (gen. completa/forzada sin idioma)")
            shutil.rmtree(output_dir_path)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"{output_dir_path} creado/limpiado.")

        # static_folder_p es la ruta absoluta al directorio static de la app
        static_folder_p = Path(app_static_folder)
        if static_folder_p.exists() and static_folder_p.is_dir():
            # El destino de los archivos estáticos debe ser output_dir / (nombre de la carpeta static)
            # app_static_url_path puede ser '/static' o '/repo/static'.
            # Necesitamos solo el último componente 'static'.
            static_dir_name_in_output = Path(app_static_url_path.strip('/')).name
            if GITHUB_PAGES_REPO_NAME and app_static_url_path.startswith(f'/{GITHUB_PAGES_REPO_NAME}'):
                 # si es /repo/static, queremos 'static', no 'repo/static' como nombre de dir
                parts = Path(app_static_url_path.strip('/')).parts
                if len(parts) > 1 and parts[0] == GITHUB_PAGES_REPO_NAME:
                    static_dir_name_in_output = parts[1] # Debería ser 'static'
                else: # si es solo /static o algo inesperado
                    static_dir_name_in_output = Path(app_static_url_path.strip('/')).name
            else: # localmente, será 'static'
                static_dir_name_in_output = Path(app_static_url_path.strip('/')).name


            static_output_dir = output_dir_path / static_dir_name_in_output
            if static_output_dir.exists():
                shutil.rmtree(static_output_dir)
            shutil.copytree(static_folder_p, static_output_dir)
            logger.info(f"'{static_folder_p.name}' copiada a '{static_output_dir}'")
        else:
            logger.warning(f"Directorio static de la app no encontrado en {static_folder_p}")


        public_folder_p = Path("public") # Asume 'public' en la raíz del proyecto
        if public_folder_p.exists() and public_folder_p.is_dir():
            copied = 0
            for item in public_folder_p.iterdir():
                if item.is_file():
                    try:
                        shutil.copy2(item, output_dir_path / item.name)
                        copied += 1
                    except Exception as e:
                        logger.error(f"Error copiando '{item.name}' desde 'public/': {e}")
            logger.info(f"{copied} archivos de 'public/' copiados a '{output_dir_path}'.")
    else:
        output_dir_path.mkdir(parents=True, exist_ok=True)
        if current_lang_arg:
            (output_dir_path / current_lang_arg).mkdir(parents=True, exist_ok=True)
        logger.info(f"Asegurando {output_dir_path} (y subdirs de idioma si aplica).")


def _generate_main_process_pages(app, languages_to_process, output_dir_path,
                                 current_lang_arg, force_regen_arg, char_key_arg, logger):
    # Tu función _generate_main_process_pages ...
    # Las URLs para _save_page_local son relativas a la app, ej. "/", "/es/"
    logger.info("Generando páginas de índice de idioma y sitemaps (proceso principal)...")
    with app.app_context():
        with app.test_client() as client_main:
            if not current_lang_arg and not char_key_arg: # Solo en la ejecución completa
                # Página raíz (index.html para el dominio, ej. https://user.github.io/repo/)
                # Flask lo mapeará a la vista correcta (probablemente tu vista para Default Lang o redirección)
                if force_regen_arg or not (output_dir_path / "index.html").exists():
                     _save_page_local(client_main, "/", output_dir_path / "index.html", logger)

                # Si tienes una página de prueba específica
                # if app.url_map.is_endpoint_expecting('main.test_page'): # Revisa si este endpoint existe
                #     _save_page_local(
                #         client_main, "/test/", # Asume que la ruta es /test/
                #         output_dir_path / "test_sitemap" / "index.html", # Ruta de archivo
                #         logger
                #     )

            for lang in languages_to_process:
                if not char_key_arg: # Solo si no estamos en modo char_key
                    # Página de índice para cada idioma (ej. /es/ -> _site/es/index.html)
                    if force_regen_arg or not (output_dir_path / lang / "index.html").exists():
                        _save_page_local(
                            client_main, f"/{lang}/",
                            output_dir_path / lang / "index.html",
                            logger
                        )

                # Sitemaps (rutas de URL como /sitemap_es_core.xml)
                sitemap_url_core = f"/sitemap_{lang}_core.xml"
                sitemap_path_core = output_dir_path / f"sitemap_{lang}_core.xml" # Archivo en la raíz de _site

                if char_key_arg: # Si estamos en modo char_key, solo generar el sitemap relevante
                    if char_key_arg == "core":
                        _save_page_local(client_main, sitemap_url_core, sitemap_path_core, logger)
                    elif char_key_arg in ALPHABET or char_key_arg == SPECIAL_CHARS_SITEMAP_KEY:
                        sitemap_url_char = f"/sitemap_{lang}_{char_key_arg}.xml"
                        sitemap_path_char = output_dir_path / f"sitemap_{lang}_{char_key_arg}.xml"
                        _save_page_local(client_main, sitemap_url_char, sitemap_path_char, logger)
                    else:
                        logger.warning(f"char_key '{char_key_arg}' inválido para sitemap. Saltando.")
                else: # No es modo char_key, generar todos los sitemaps para el idioma
                    _save_page_local(client_main, sitemap_url_core, sitemap_path_core, logger)
                    for char_k_iter in list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]:
                        sitemap_url_ch = f"/sitemap_{lang}_{char_k_iter}.xml"
                        sitemap_path_ch = output_dir_path / f"sitemap_{lang}_{char_k_iter}.xml"
                        _save_page_local(client_main, sitemap_url_ch, sitemap_path_ch, logger)

            # Sitemap Index Principal (sitemap.xml en la raíz de _site)
            # Solo generar si no estamos en modo char_key o modo solo idioma
            if not current_lang_arg and not char_key_arg:
                _save_page_local(client_main, "/sitemap.xml", output_dir_path / "sitemap.xml", logger)


def _run_parallel_tasks(env_data, force_regen_arg, char_key_arg, logger):
    # Tu función _run_parallel_tasks ...
    num_processes = max(1, cpu_count() - 1 if cpu_count() > 1 else 1)
    logger.info(f"Usando {num_processes} procesos para generación paralela.")

    # output_dir_path es un objeto Path, convertir a string para el dict de config
    config_params_for_tasks = {
        'LANGUAGES': env_data["languages_to_process"],
        'DEFAULT_LANGUAGE': env_data["default_language"],
        'URL_SEGMENT_TRANSLATIONS_CONFIG': env_data["url_segment_translations"],
        'OUTPUT_DIR': str(env_data["output_dir_path"]), # Convertir Path a string
        'FORCE_REGENERATE_ALL': force_regen_arg,
        'ALL_BOOKS_DATA': env_data["books_data"] # Ya es una lista
    }
    task_args_tuple = (config_params_for_tasks, env_data["manifest"].copy()) # manifest es un dict
    all_new_manifest_entries = []

    all_books_source = env_data["books_data"]
    current_slugifier_for_filtering = slugify_to_use_global_main

    books_to_process_for_detail_final = list(all_books_source)
    authors_to_process_slugs_orig_final = {
        b.get('author_slug') for b in all_books_source if b.get('author_slug')
    }
    bases_to_process_tuples_orig_final = {
        (b.get('author_slug'), b.get('base_title_slug'))
        for b in all_books_source
        if b.get('author_slug') and b.get('base_title_slug')
    }

    if char_key_arg and env_data["languages_to_process"]:
        logger.info(
            f"Filtrando tareas para char_key: '{char_key_arg}' en idioma(s): {env_data['languages_to_process']}"
        )
        # ... (resto de tu lógica de filtrado, parece correcta)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("--- DEBUG: Verificando grupos de autor para filtrado (primeros 10) ---")
            for i, book_debug in enumerate(all_books_source):
                if i < 10:
                    auth_slug_orig_debug = book_debug.get('author_slug')
                    group_debug = get_sitemap_char_group_for_author_local(
                        auth_slug_orig_debug, current_slugifier_for_filtering
                    )
                    logger.debug(f"  Autor Original: '{auth_slug_orig_debug}', Grupo Calculado: '{group_debug}'")
                else:
                    break
            logger.debug("--- FIN DEBUG ---")

        books_to_process_for_detail_final = [
            book for book in all_books_source
            if get_sitemap_char_group_for_author_local(
                book.get('author_slug'), current_slugifier_for_filtering
            ) == char_key_arg
        ]
        logger.info(f"  Libros para detalle después de filtrar: {len(books_to_process_for_detail_final)}")

        authors_to_process_slugs_orig_final = {
            author_slug for author_slug in authors_to_process_slugs_orig_final
            if get_sitemap_char_group_for_author_local(
                author_slug, current_slugifier_for_filtering
            ) == char_key_arg
        }
        logger.info(f"  Autores para páginas después de filtrar: {len(authors_to_process_slugs_orig_final)}")

        bases_to_process_tuples_orig_final = {
            (author_slug, base_slug) for author_slug, base_slug in bases_to_process_tuples_orig_final
            if get_sitemap_char_group_for_author_local(
                author_slug, current_slugifier_for_filtering
            ) == char_key_arg
        }
        logger.info(f"  Bases para versiones después de filtrar: {len(bases_to_process_tuples_orig_final)}")

        if not books_to_process_for_detail_final and \
           not authors_to_process_slugs_orig_final and \
           not bases_to_process_tuples_orig_final:
            logger.warning(f"No se encontraron elementos para char_key '{char_key_arg}'. Sin tareas paralelas.")
            return all_new_manifest_entries


    # Usa worker_init que ahora establece IS_STATIC_GENERATION_WORKER
    with Pool(processes=num_processes, initializer=worker_init) as pool:
        results_books, results_authors, results_versions = [], [], []

        if books_to_process_for_detail_final:
            logger.info(f"Gen. paralela páginas detalle ({len(books_to_process_for_detail_final)} items)...")
            # Asegurar que task_args_tuple se pasa correctamente.
            # El partial debe definir todos los args excepto el que se mapea.
            task = partial(generate_book_detail_pages_task, config_params_manifest_tuple=task_args_tuple)
            results_books = pool.map(task, books_to_process_for_detail_final)
            for res_list in results_books:
                if res_list:
                    all_new_manifest_entries.extend(res_list)
            logger.info(f"  Detalle libros: {sum(len(r) for r in results_books if r)} (re)generadas.")

        if authors_to_process_slugs_orig_final:
            logger.info(f"Gen. paralela páginas autor ({len(authors_to_process_slugs_orig_final)} items)...")
            task = partial(generate_author_pages_task, config_params_manifest_tuple=task_args_tuple)
            results_authors = pool.map(task, list(authors_to_process_slugs_orig_final))
            for res_list in results_authors:
                if res_list:
                    all_new_manifest_entries.extend(res_list)
            logger.info(f"  Páginas autor: {sum(len(r) for r in results_authors if r)} (re)generadas.")

        if bases_to_process_tuples_orig_final:
            logger.info(f"Gen. paralela páginas versiones ({len(bases_to_process_tuples_orig_final)} items)...")
            task = partial(generate_versions_pages_task, config_params_manifest_tuple=task_args_tuple)
            results_versions = pool.map(task, list(bases_to_process_tuples_orig_final))
            for res_list in results_versions:
                if res_list:
                    all_new_manifest_entries.extend(res_list)
            logger.info(f"  Páginas versiones: {sum(len(r) for r in results_versions if r)} (re)generadas.")

    return all_new_manifest_entries


def _finalize_generation(manifest_data, new_entries, app, output_dir_path,
                         current_lang_arg, force_regen_arg, char_key_arg, logger):
    # Tu función _finalize_generation ...
    # output_dir_path es un objeto Path
    if char_key_arg and current_lang_arg:
        logger.info(
            f"Ejecución para lang '{current_lang_arg}' y char_key '{char_key_arg}'. "
            "Sitemap_index.xml NO actualizado."
        )
        if new_entries:
            logger.info(
                f"Actualizando manifest con {len(new_entries)} entradas para {current_lang_arg}/{char_key_arg}..."
            )
            for entry in new_entries:
                manifest_data[entry['path']] = { # path ya es un string de la task
                    "signature": entry['signature'], "timestamp": entry['timestamp']
                }
            save_manifest(manifest_data)
        else:
            logger.info(f"No se generaron nuevas entradas de manifest para {current_lang_arg}/{char_key_arg}.")

    elif not current_lang_arg or force_regen_arg: # Ejecución completa o forzada
        if new_entries:
            logger.info(f"Actualizando manifest global con {len(new_entries)} entradas de workers...")
            for entry in new_entries:
                manifest_data[entry['path']] = {
                    "signature": entry['signature'], "timestamp": entry['timestamp']
                }
        else:
            logger.info("No se (re)generaron páginas cacheadas por workers (afectando manifest).")
        
        # El sitemap_index.xml ya se genera en _generate_main_process_pages
        # save_manifest() se llama al final de esa función si es una ejecución completa
        save_manifest(manifest_data) # Guardar el manifest con todas las actualizaciones.
    
    else:  # Solo idioma, sin char_key
        logger.info(f"Ejecución solo para idioma '{current_lang_arg}'. {len(new_entries)} págs (re)generadas.")
        if new_entries:
            logger.info(f"Actualizando manifest con {len(new_entries)} entradas para idioma {current_lang_arg}...")
            for entry in new_entries:
                manifest_data[entry['path']] = {
                    "signature": entry['signature'], "timestamp": entry['timestamp']
                }
            save_manifest(manifest_data)
        else:
            logger.info(f"No se generaron nuevas entradas de manifest para idioma {current_lang_arg}.")

    log_msg_final = f"Sitio estático (o parte para idioma '{current_lang_arg or 'todos'}'"
    if char_key_arg:
        log_msg_final += f" y char_key '{char_key_arg}'"
    log_msg_final += f") generado en: {output_dir_path}" # output_dir_path es Path
    logger.info(log_msg_final)


# --- FUNCIÓN MAIN ---
def main():
    main_process_logger = script_logger # Usa el logger global del script
    args = _parse_cli_args()

    if args.char_key and not args.language:
        main_process_logger.error("--char-key requiere que se especifique también --language. Saliendo.")
        return

    env_data = _setup_environment_data(args, main_process_logger)
    if env_data is None:
        return

    app = env_data["app"] # app ya está configurada con APPLICATION_ROOT, etc.
    output_dir = env_data["output_dir_path"] # Ya es un Path object desde _setup_environment_data

    # Determinar si se debe hacer una limpieza completa
    perform_full_cleanup = (not args.language and not args.char_key) or \
                           (args.force_regenerate and not args.language and not args.char_key)

    _prepare_output_directory(
        app, output_dir, # Pasar app completa para acceder a static_folder y static_url_path
        args.language, perform_full_cleanup, args.char_key, main_process_logger
    )
    _generate_main_process_pages(
        app, env_data["languages_to_process"], output_dir,
        args.language, args.force_regenerate, args.char_key, main_process_logger
    )
    new_manifest_entries = _run_parallel_tasks(
        env_data, args.force_regenerate, args.char_key, main_process_logger
    )
    _finalize_generation(
        env_data["manifest"], new_manifest_entries, app, output_dir,
        args.language, args.force_regenerate, args.char_key, main_process_logger
    )


if __name__ == '__main__':
    # Configurar el nivel de log del script principal desde una variable de entorno si se desea
    # script_logger.setLevel(os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper())
    # (ya se hace al definir script_logger)
    main()
