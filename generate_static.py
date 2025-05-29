# generate_static.py
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging
from multiprocessing import Pool, cpu_count, current_process
from functools import partial
import argparse
import json
import hashlib
import time

# --- Configuración del Logger Básico para el Script ---
script_logger = logging.getLogger('generate_static_script')
script_logger.setLevel(logging.INFO) # Cambia a DEBUG para ver más detalle
script_handler = logging.StreamHandler()
# Formato más detallado para debug
script_formatter = logging.Formatter('%(asctime)s - %(name)s:%(processName)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s')
script_handler.setFormatter(script_formatter)
if not script_logger.handlers:
    script_logger.addHandler(script_handler)

# --- Variables Globales para Workers ---
worker_app_instance = None
worker_logger = None # Se asignará en worker_init
slugify_to_use_global_worker = None # Específico para el worker

# --- CONSTANTES ---
MANIFEST_DIR = Path(".cache")
MANIFEST_FILE = MANIFEST_DIR / "generation_manifest.json"
OUTPUT_DIR = "_site"
ALPHABET = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_CHARS_SITEMAP_KEY = "0"


# --- FUNCIONES DE UTILIDAD (LOCALES AL SCRIPT) ---
def slugify_ascii_local(text):
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

# Determinar qué función slugify usar para el proceso principal
# Los workers lo harán en worker_init
slugify_to_use_global_main = slugify_ascii_local # Default
try:
    from app.utils.helpers import slugify_ascii as slugify_ascii_app_main
    slugify_to_use_global_main = slugify_ascii_app_main
    script_logger.info("Proceso principal usando slugify_ascii de app.utils.helpers.")
except ImportError:
    script_logger.warning("Proceso principal usando slugify_ascii local (app.utils.helpers no encontrado).")


def get_sitemap_char_group_for_author_local(author_name_or_slug, slugifier_func):
    """
    Determina a qué grupo de sitemap (letra o especial) pertenece un nombre/slug de autor.
    Usa la función slugifier_func proporcionada.
    """
    # script_logger.debug(f"Input: '{author_name_or_slug}'") # Log de entrada si es necesario
    if not author_name_or_slug:
        # script_logger.debug(f"Resultado: '{SPECIAL_CHARS_SITEMAP_KEY}' (input vacío)")
        return SPECIAL_CHARS_SITEMAP_KEY

    # Es crucial aplicar la misma slugificación que se usará para generar las URLs
    processed_slug = slugifier_func(author_name_or_slug)
    # script_logger.debug(f"Slug procesado: '{processed_slug}'")

    if not processed_slug: # Si el slug se vuelve vacío después de procesar
        # script_logger.debug(f"Resultado: '{SPECIAL_CHARS_SITEMAP_KEY}' (slug procesado vacío)")
        return SPECIAL_CHARS_SITEMAP_KEY

    first_char = processed_slug[0].lower()
    # script_logger.debug(f"Primer carácter: '{first_char}'")

    if first_char in ALPHABET:
        # script_logger.debug(f"Resultado: '{first_char}' (alfabético)")
        return first_char
    # script_logger.debug(f"Resultado: '{SPECIAL_CHARS_SITEMAP_KEY}' (no alfabético)")
    return SPECIAL_CHARS_SITEMAP_KEY


def get_translated_url_segment_for_generator(
    segment_key, lang_code, url_segment_translations,
    default_app_lang, default_segment_value=None
):
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
        "cover_image_url": book_data.get("image_url_l") or book_data.get("image_url_m") or book_data.get("image_url_s"),
        "publication_date": book_data.get("publication_date"),
        "publisher": book_data.get("publisher_name"), "language_code": book_data.get("language_code"),
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
    if not Path(output_path_str).exists():
        logger_to_use.debug(f"REGENERAR (archivo no existe): {output_path_str}")
        return True
    logger_to_use.debug(f"SALTAR (sin cambios): {output_path_str}")
    return False


# --- FUNCIÓN _save_page_local ---
def _save_page_local(client_local, url_path, file_path_obj, logger_to_use):
    try:
        response = client_local.get(url_path)
        if response.status_code == 200:
            if response.data:
                file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path_obj, 'wb') as f: f.write(response.data)
                logger_to_use.info(f"GENERADO: {url_path} -> {file_path_obj}")
            else:
                logger_to_use.info(f"URL {url_path} devolvió 200 sin datos. No se guardó (sitemap vacío?).")
        elif response.status_code in [301, 302, 307, 308]:
            logger_to_use.warning(f"{url_path} REDIR {response.status_code}. NO guardado.")
        elif response.status_code == 404:
            logger_to_use.warning(f"404: {url_path} no encontrado. NO guardado.")
        else:
            logger_to_use.error(f"HTTP {response.status_code} para {url_path}. NO guardado.")
    except Exception as e:
        logger_to_use.exception(f"EXCEPCIÓN generando/guardando {url_path}: {e}")


# --- FUNCIONES WORKER PARA MULTIPROCESSING ---
def worker_init():
    global worker_app_instance, worker_logger, slugify_to_use_global_worker
    from app import create_app

    proc_name = current_process().name
    worker_app_instance = create_app()
    # Configurar un logger específico para el worker si se quiere diferenciar del script_logger
    # Por ahora, usamos el mismo logger principal para simplificar
    worker_logger = logging.getLogger(f'generate_static_worker.{proc_name}')
    if not worker_logger.handlers: # Evitar duplicar handlers si el logger ya existe
        worker_handler = logging.StreamHandler()
        worker_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s')
        worker_handler.setFormatter(worker_formatter)
        worker_logger.addHandler(worker_handler)
    worker_logger.setLevel(script_logger.level) # Heredar nivel del logger principal
    worker_logger.propagate = False # Evitar que los logs del worker se propaguen al root logger


    slugify_to_use_global_worker = slugify_ascii_local # Default
    try:
        from app.utils.helpers import slugify_ascii as slugify_ascii_app_worker
        slugify_to_use_global_worker = slugify_ascii_app_worker
        worker_logger.info("Usando slugify_ascii de app.utils.helpers.")
    except ImportError:
        worker_logger.warning("Usando slugify_ascii local (app.utils.helpers no encontrado).")


def generate_book_detail_pages_task(book_data_item, config_params_manifest_tuple):
    config_params, manifest_data_global = config_params_manifest_tuple
    # Acceder a slugify_to_use_global_worker definido en worker_init
    global slugify_to_use_global_worker

    # ... (resto de la lógica de la función como la tenías, usando slugify_to_use_global_worker) ...
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE_STR = config_params['OUTPUT_DIR']
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)

    log_target = worker_logger # Usar el logger del worker
    generated_pages_info = []

    author_s_original = book_data_item.get('author_slug')
    title_s_original = book_data_item.get('title_slug')
    identifier = book_data_item.get('isbn10') or book_data_item.get('isbn13') or book_data_item.get('asin')

    if not (identifier and author_s_original and title_s_original):
        log_target.debug(f"Saltando libro (datos incompletos): ID {identifier}")
        return generated_pages_info

    # Usar la función slugify del worker
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
                flask_url = f"/{lang}/{book_segment_translated}/{author_s}/{title_s}/{identifier}/"
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
                        "path": output_path_str, "signature": current_book_content_signature, "timestamp": time.time()
                    })
    return generated_pages_info


def generate_author_pages_task(author_slug_original, config_params_manifest_tuple):
    config_params, manifest_data_global = config_params_manifest_tuple
    global slugify_to_use_global_worker
    # ... (resto de la lógica, usando slugify_to_use_global_worker) ...
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE_STR = config_params['OUTPUT_DIR']
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS_DATA = config_params['ALL_BOOKS_DATA']

    log_target = worker_logger
    generated_pages_info = []
    author_s = slugify_to_use_global_worker(author_slug_original)

    # Filtrar libros por el slug del autor YA PROCESADO para consistencia
    author_books_data = [b for b in ALL_BOOKS_DATA if slugify_to_use_global_worker(b.get('author_slug')) == author_s]
    if not author_books_data:
        log_target.debug(f"No se encontraron libros para el slug de autor procesado '{author_s}' (original '{author_slug_original}').")
        return generated_pages_info

    author_page_source_identifiers = sorted([
        b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in author_books_data
    ])
    current_author_page_signature = calculate_signature({
        "book_ids_author_page": author_page_source_identifiers,
        "author_slug": author_slug_original
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
                        "path": output_path_str, "signature": current_author_page_signature, "timestamp": time.time()
                    })
    return generated_pages_info


def generate_versions_pages_task(author_base_title_slugs_original, config_params_manifest_tuple):
    config_params, manifest_data_global = config_params_manifest_tuple
    global slugify_to_use_global_worker
    # ... (resto de la lógica, usando slugify_to_use_global_worker) ...
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE_STR = config_params['OUTPUT_DIR']
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS_DATA = config_params['ALL_BOOKS_DATA']

    log_target = worker_logger
    generated_pages_info = []
    author_s_orig, base_title_s_orig = author_base_title_slugs_original
    author_s = slugify_to_use_global_worker(author_s_orig)
    base_title_s = slugify_to_use_global_worker(base_title_s_orig)

    version_books_data = [
        b for b in ALL_BOOKS_DATA
        if slugify_to_use_global_worker(b.get('author_slug')) == author_s and \
           slugify_to_use_global_worker(b.get('base_title_slug')) == base_title_s
    ]
    if not version_books_data:
        log_target.debug(f"No se encontraron libros para versiones de autor '{author_s}' y base_title '{base_title_s}'.")
        return generated_pages_info

    version_page_source_identifiers = sorted([
        b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in version_books_data
    ])
    current_version_page_signature = calculate_signature({
        "book_ids_version_page": version_page_source_identifiers,
        "author_slug": author_s_orig, "base_title_slug": base_title_s_orig
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
                        "path": output_path_str, "signature": current_version_page_signature, "timestamp": time.time()
                    })
    return generated_pages_info


# --- MAIN FUNCTION HELPERS ---
def _parse_cli_args():
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
    # ... (sin cambios significativos, solo asegurar que usa main_logger) ...
    main_logger.info(f"Iniciando script generate_static.py con argumentos: {args}")
    if args.force_regenerate:
        main_logger.info("FORZANDO REGENERACIÓN: El manifest será ignorado para 'should_regenerate'.")

    manifest_data = load_manifest()
    main_logger.info(f"Manifest cargado con {len(manifest_data)} entradas desde {MANIFEST_FILE}.")

    from app import create_app
    app_instance = create_app()
    main_logger.info("Instancia de Flask creada en proceso principal para configuraciones.")

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

    books_data_list = app_instance.books_data
    if not books_data_list:
        main_logger.critical("No hay datos de libros (app.books_data vacío). Saliendo.")
        return None
    main_logger.info(f"Idiomas: {languages_to_process}. {len(books_data_list)} libros fuente.")

    return {
        "app": app_instance, "manifest": manifest_data,
        "languages_to_process": languages_to_process,
        "default_language": app_instance.config.get('DEFAULT_LANGUAGE', 'en'),
        "url_segment_translations": app_instance.config.get('URL_SEGMENT_TRANSLATIONS', {}),
        "books_data": books_data_list, "output_dir_path": Path(OUTPUT_DIR),
    }


def _prepare_output_directory(app_static_folder, app_static_url_path, output_dir_path, # noqa: C901
                              current_lang_arg, perform_full_cleanup, char_key_arg, logger):
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

        static_folder_p = Path(app_static_folder)
        if static_folder_p.exists() and static_folder_p.is_dir():
            static_output_dir = output_dir_path / Path(app_static_url_path.strip('/'))
            if static_output_dir.exists(): shutil.rmtree(static_output_dir)
            shutil.copytree(static_folder_p, static_output_dir)
            logger.info(f"'{static_folder_p.name}' copiada a '{static_output_dir}'")

        public_folder_p = Path("public")
        if public_folder_p.exists() and public_folder_p.is_dir():
            copied = 0
            for item in public_folder_p.iterdir():
                if item.is_file():
                    try:
                        shutil.copy2(item, output_dir_path / item.name); copied +=1
                    except Exception as e: logger.error(f"Error copiando '{item.name}': {e}")
            logger.info(f"{copied} archivos de 'public/' copiados a '{output_dir_path}'.")
    else:
        output_dir_path.mkdir(parents=True, exist_ok=True)
        if current_lang_arg: (output_dir_path / current_lang_arg).mkdir(parents=True, exist_ok=True)
        logger.info(f"Asegurando {output_dir_path} (y subdirs de idioma si aplica).")


def _generate_main_process_pages(app, languages_to_process, output_dir_path,
                                 current_lang_arg, force_regen_arg, char_key_arg, logger):
    # ... (sin cambios significativos, la lógica de char_key_arg ya estaba bien) ...
    logger.info("Generando páginas de índice de idioma y sitemaps (proceso principal)...")
    with app.app_context():
        with app.test_client() as client_main:
            if not current_lang_arg and not char_key_arg: # Globales solo si no hay filtro lang/char
                if force_regen_arg or not (output_dir_path / "index.html").exists():
                    _save_page_local(client_main, "/", output_dir_path / "index.html", logger)
                if app.url_map.is_endpoint_expecting('main.test_page'): # Ejemplo
                    _save_page_local(client_main, "/test/", output_dir_path / "test_sitemap" / "index.html", logger)

            for lang in languages_to_process:
                if not char_key_arg: # Index de idioma solo si no hay filtro char
                    if force_regen_arg or not (output_dir_path / lang / "index.html").exists():
                        _save_page_local(client_main, f"/{lang}/", output_dir_path / lang / "index.html", logger)

                sitemap_url_core = f"/sitemap_{lang}_core.xml"
                sitemap_path_core = output_dir_path / f"sitemap_{lang}_core.xml"

                if char_key_arg:
                    if char_key_arg == "core":
                         _save_page_local(client_main, sitemap_url_core, sitemap_path_core, logger)
                    elif char_key_arg in ALPHABET or char_key_arg == SPECIAL_CHARS_SITEMAP_KEY:
                        sitemap_url_char = f"/sitemap_{lang}_{char_key_arg}.xml"
                        sitemap_path_char = output_dir_path / f"sitemap_{lang}_{char_key_arg}.xml"
                        _save_page_local(client_main, sitemap_url_char, sitemap_path_char, logger)
                    else:
                        logger.warning(f"char_key '{char_key_arg}' inválido para sitemap. Saltando.")
                else: # Generar todos los sitemaps para el idioma
                    _save_page_local(client_main, sitemap_url_core, sitemap_path_core, logger)
                    for char_k_iter in list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]:
                        sitemap_url_char = f"/sitemap_{lang}_{char_k_iter}.xml"
                        sitemap_path_char = output_dir_path / f"sitemap_{lang}_{char_k_iter}.xml"
                        _save_page_local(client_main, sitemap_url_char, sitemap_path_char, logger)


def _run_parallel_tasks(env_data, force_regen_arg, char_key_arg, logger): # noqa: C901
    num_processes = max(1, cpu_count() - 1 if cpu_count() > 1 else 1)
    logger.info(f"Usando {num_processes} procesos para generación paralela.")

    config_params_for_tasks = {
        'LANGUAGES': env_data["languages_to_process"],
        'DEFAULT_LANGUAGE': env_data["default_language"],
        'URL_SEGMENT_TRANSLATIONS_CONFIG': env_data["url_segment_translations"],
        'OUTPUT_DIR': str(env_data["output_dir_path"]),
        'FORCE_REGENERATE_ALL': force_regen_arg,
        'ALL_BOOKS_DATA': env_data["books_data"]
    }
    task_args_tuple = (config_params_for_tasks, env_data["manifest"].copy())
    all_new_manifest_entries = []

    all_books_source = env_data["books_data"]
    # Para el filtrado, es importante usar la misma función slugify que usarán los workers
    # Aquí usamos la del proceso principal (slugify_to_use_global_main) para la lógica de filtrado
    # Los workers usarán slugify_to_use_global_worker que debería ser equivalente.
    current_slugifier_for_filtering = slugify_to_use_global_main


    books_to_process_for_detail_final = list(all_books_source)
    authors_to_process_slugs_orig_final = {b.get('author_slug') for b in all_books_source if b.get('author_slug')}
    bases_to_process_tuples_orig_final = {
        (b.get('author_slug'), b.get('base_title_slug'))
        for b in all_books_source
        if b.get('author_slug') and b.get('base_title_slug')
    }

    if char_key_arg and env_data["languages_to_process"]:
        logger.info(f"Filtrando tareas para char_key: '{char_key_arg}' en idioma(s): {env_data['languages_to_process']}")
        # DEBUG: Imprimir algunos slugs de autor y sus grupos calculados
        if logger.isEnabledFor(logging.DEBUG): # Solo si el nivel de log es DEBUG
            logger.debug("--- DEBUG: Verificando grupos de autor para filtrado (primeros 10) ---")
            for i, book_debug in enumerate(all_books_source):
                if i < 10:
                    auth_slug_orig_debug = book_debug.get('author_slug')
                    group_debug = get_sitemap_char_group_for_author_local(auth_slug_orig_debug, current_slugifier_for_filtering)
                    logger.debug(f"  Autor Original: '{auth_slug_orig_debug}', Grupo Calculado: '{group_debug}'")
                else:
                    break
            logger.debug("--- FIN DEBUG ---")


        books_to_process_for_detail_final = [
            book for book in all_books_source
            if get_sitemap_char_group_for_author_local(book.get('author_slug'), current_slugifier_for_filtering) == char_key_arg
        ]
        logger.info(f"  Libros para detalle después de filtrar: {len(books_to_process_for_detail_final)}")

        authors_to_process_slugs_orig_final = {
            author_slug for author_slug in authors_to_process_slugs_orig_final
            if get_sitemap_char_group_for_author_local(author_slug, current_slugifier_for_filtering) == char_key_arg
        }
        logger.info(f"  Autores para páginas después de filtrar: {len(authors_to_process_slugs_orig_final)}")

        bases_to_process_tuples_orig_final = {
            (author_slug, base_slug) for author_slug, base_slug in bases_to_process_tuples_orig_final
            if get_sitemap_char_group_for_author_local(author_slug, current_slugifier_for_filtering) == char_key_arg
        }
        logger.info(f"  Bases para versiones después de filtrar: {len(bases_to_process_tuples_orig_final)}")

        if not books_to_process_for_detail_final and \
           not authors_to_process_slugs_orig_final and \
           not bases_to_process_tuples_orig_final:
            logger.warning(f"No se encontraron elementos para char_key '{char_key_arg}'. Sin tareas paralelas.")
            return all_new_manifest_entries

    with Pool(processes=num_processes, initializer=worker_init) as pool:
        if books_to_process_for_detail_final:
            logger.info(f"Gen. paralela páginas detalle ({len(books_to_process_for_detail_final)} items)...")
            task = partial(generate_book_detail_pages_task, config_params_manifest_tuple=task_args_tuple)
            for res_list in pool.map(task, books_to_process_for_detail_final): all_new_manifest_entries.extend(res_list)
            logger.info(f"  Detalle libros: {sum(len(r) for r in _) if _ else 0} (re)generadas.")

        if authors_to_process_slugs_orig_final:
            logger.info(f"Gen. paralela páginas autor ({len(authors_to_process_slugs_orig_final)} items)...")
            task = partial(generate_author_pages_task, config_params_manifest_tuple=task_args_tuple)
            for res_list in pool.map(task, list(authors_to_process_slugs_orig_final)): all_new_manifest_entries.extend(res_list)
            logger.info(f"  Páginas autor: {sum(len(r) for r in _) if _ else 0} (re)generadas.")

        if bases_to_process_tuples_orig_final:
            logger.info(f"Gen. paralela páginas versiones ({len(bases_to_process_tuples_orig_final)} items)...")
            task = partial(generate_versions_pages_task, config_params_manifest_tuple=task_args_tuple)
            for res_list in pool.map(task, list(bases_to_process_tuples_orig_final)): all_new_manifest_entries.extend(res_list)
            logger.info(f"  Páginas versiones: {sum(len(r) for r in _) if _ else 0} (re)generadas.")
    return all_new_manifest_entries


def _finalize_generation(manifest_data, new_entries, app, output_dir_path,
                         current_lang_arg, force_regen_arg, char_key_arg, logger):
    # ... (sin cambios significativos, la lógica de char_key_arg ya estaba bien) ...
    if char_key_arg and current_lang_arg:
        logger.info(f"Ejecución para lang '{current_lang_arg}' y char_key '{char_key_arg}'. Sitemap_index.xml NO actualizado.")
        if new_entries:
            logger.info(f"Actualizando manifest con {len(new_entries)} entradas para {current_lang_arg}/{char_key_arg}...")
            for entry in new_entries: manifest_data[entry['path']] = {"signature": entry['signature'], "timestamp": entry['timestamp']}
            save_manifest(manifest_data)
        else: logger.info(f"No se generaron nuevas entradas de manifest para {current_lang_arg}/{char_key_arg}.")

    elif not current_lang_arg or force_regen_arg:
        if new_entries:
            logger.info(f"Actualizando manifest global con {len(new_entries)} entradas de workers...")
            for entry in new_entries: manifest_data[entry['path']] = {"signature": entry['signature'], "timestamp": entry['timestamp']}
        else: logger.info("No se (re)generaron páginas cacheadas por workers (afectando manifest).")
        logger.info("Generando sitemap_index.xml principal...")
        with app.app_context():
            with app.test_client() as client_main:
                _save_page_local(client_main, "/sitemap.xml", output_dir_path / "sitemap.xml", logger)
        save_manifest(manifest_data)
    else: # Solo idioma
        logger.info(f"Ejecución solo para idioma '{current_lang_arg}'. {len(new_entries)} págs (re)generadas.")
        if new_entries:
            logger.info(f"Actualizando manifest con {len(new_entries)} entradas para idioma {current_lang_arg}...")
            for entry in new_entries: manifest_data[entry['path']] = {"signature": entry['signature'], "timestamp": entry['timestamp']}
            save_manifest(manifest_data)
        else: logger.info(f"No se generaron nuevas entradas de manifest para idioma {current_lang_arg}.")

    log_msg_final = f"Sitio estático (o parte para idioma '{current_lang_arg or 'todos'}'"
    if char_key_arg: log_msg_final += f" y char_key '{char_key_arg}'"
    log_msg_final += f") generado en: {output_dir_path}"
    logger.info(log_msg_final)


# --- FUNCIÓN MAIN ---
def main(): # noqa: C901
    main_process_logger = script_logger
    args = _parse_cli_args()

    if args.char_key and not args.language:
        main_process_logger.error("--char-key requiere que se especifique también --language. Saliendo.")
        return

    env_data = _setup_environment_data(args, main_process_logger)
    if env_data is None: return

    app = env_data["app"]
    perform_full_cleanup = (not args.language and not args.char_key) or \
                           (args.force_regenerate and not args.language and not args.char_key)

    _prepare_output_directory(
        app.static_folder, app.static_url_path, env_data["output_dir_path"],
        args.language, perform_full_cleanup, args.char_key, main_process_logger
    )
    _generate_main_process_pages(
        app, env_data["languages_to_process"], env_data["output_dir_path"],
        args.language, args.force_regenerate, args.char_key, main_process_logger
    )
    new_manifest_entries = _run_parallel_tasks(
        env_data, args.force_regenerate, args.char_key, main_process_logger
    )
    _finalize_generation(
        env_data["manifest"], new_manifest_entries, app, env_data["output_dir_path"],
        args.language, args.force_regenerate, args.char_key, main_process_logger
    )


if __name__ == '__main__':
    main()
