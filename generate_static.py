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
script_logger.setLevel(logging.INFO)
script_handler = logging.StreamHandler()
script_formatter = logging.Formatter('%(asctime)s - %(name)s:%(processName)s - %(levelname)s - %(message)s')
script_handler.setFormatter(script_formatter)
if not script_logger.handlers:
    script_logger.addHandler(script_handler)

# --- Variables Globales para Workers ---
worker_app_instance = None
worker_logger = None
slugify_to_use_global = None

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
    text = str(text)
    text = unidecode(text)
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'--+', '-', text)
    text = text.strip('-')
    return text if text else "na"

# Determinar qué función slugify usar (app o local)
# Esto se moverá a worker_init para los workers, pero la principal la necesita también.
try:
    from app.utils.helpers import slugify_ascii as slugify_ascii_app_main
    slugify_to_use_global = slugify_ascii_app_main
    script_logger.info("Proceso principal usando slugify_ascii de app.utils.helpers.")
except ImportError:
    slugify_to_use_global = slugify_ascii_local
    script_logger.warning("Proceso principal usando slugify_ascii local.")


def get_sitemap_char_group_for_author_local(author_slug_val):
    """
    Determina a qué grupo de sitemap (letra o especial) pertenece un slug de autor.
    Importante: Usa slugify_to_use_global para consistencia.
    """
    if not author_slug_val:
        return SPECIAL_CHARS_SITEMAP_KEY
    # Es crucial aplicar la misma slugificación que se usará para generar las URLs
    # antes de tomar el primer carácter.
    processed_slug = slugify_to_use_global(author_slug_val)
    if not processed_slug: # Si el slug se vuelve vacío después de procesar
        return SPECIAL_CHARS_SITEMAP_KEY
    first_char = processed_slug[0].lower()
    if first_char in ALPHABET:
        return first_char
    return SPECIAL_CHARS_SITEMAP_KEY


def get_translated_url_segment_for_generator(
    segment_key,
    lang_code,
    url_segment_translations,
    default_app_lang,
    default_segment_value=None
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
        "isbn10": book_data.get("isbn10"),
        "isbn13": book_data.get("isbn13"),
        "asin": book_data.get("asin"),
        "title_slug": book_data.get("title_slug"),
        "author_slug": book_data.get("author_slug"),
        "description": book_data.get("description_short") or book_data.get("description"),
        "cover_image_url": book_data.get("image_url_l") or book_data.get("image_url_m") or book_data.get("image_url_s"),
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
    if not Path(output_path_str).exists():
        logger_to_use.debug(f"REGENERAR (archivo no existe): {output_path_str}")
        return True
    logger_to_use.debug(f"SALTAR (sin cambios): {output_path_str}")
    return False


# --- FUNCIÓN _save_page_local ---
def _save_page_local(client_local, url_path, file_path_obj, logger_to_use):
    try:
        pass  # Evita E/S bloqueado, aunque raro aquí
    except BlockingIOError:
        logger_to_use.warning(f"Intento de E/S bloqueado (raro con logger) para: {url_path}")

    try:
        response = client_local.get(url_path)
        if response.status_code == 200:
            if response.data:
                file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path_obj, 'wb') as f:
                    f.write(response.data)
                logger_to_use.info(f"GENERADO: {url_path} -> {file_path_obj}")
            else:
                logger_to_use.info(f"URL {url_path} devolvió 200 pero sin datos. No se guardó archivo (sitemap vacío?).")
        elif response.status_code in [301, 302, 307, 308]:
            logger_to_use.warning(f"{url_path} devolvió {response.status_code} (redirección). Contenido NO guardado.")
        elif response.status_code == 404:
            logger_to_use.warning(f"404: {url_path} no encontrado. No se guardó el archivo.")
        else:
            logger_to_use.error(f"HTTP {response.status_code} para {url_path}. No se guardó el archivo.")
    except Exception as e:
        logger_to_use.exception(f"EXCEPCIÓN generando y guardando {url_path}: {e}")


# --- FUNCIONES WORKER PARA MULTIPROCESSING ---
def worker_init():
    global worker_app_instance, worker_logger, slugify_to_use_global
    from app import create_app  # Importación tardía para el worker

    proc_name = current_process().name
    worker_app_instance = create_app()
    worker_logger = script_logger  # Usar el logger del script principal

    try:
        from app.utils.helpers import slugify_ascii as slugify_ascii_app_worker
        slugify_to_use_global = slugify_ascii_app_worker
        worker_logger.info(f"Worker {proc_name}: usando slugify_ascii de app.utils.helpers.")
    except ImportError:
        slugify_to_use_global = slugify_ascii_local
        worker_logger.warning(f"Worker {proc_name}: usando slugify_ascii local (fallback).")


def generate_book_detail_pages_task(book_data_item, config_params_manifest_tuple):
    config_params, manifest_data_global = config_params_manifest_tuple
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE_STR = config_params['OUTPUT_DIR'] # Ya es string
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)

    log_target = worker_logger
    generated_pages_info = []

    author_s_original = book_data_item.get('author_slug')
    title_s_original = book_data_item.get('title_slug')
    identifier = book_data_item.get('isbn10') or book_data_item.get('isbn13') or book_data_item.get('asin')

    if not (identifier and author_s_original and title_s_original):
        log_target.debug(f"Saltando libro (datos incompletos): ID {identifier}")
        return generated_pages_info

    author_s = slugify_to_use_global(author_s_original)
    title_s = slugify_to_use_global(title_s_original)

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
                        "path": output_path_str,
                        "signature": current_book_content_signature,
                        "timestamp": time.time()
                    })
    return generated_pages_info


def generate_author_pages_task(author_slug_original, config_params_manifest_tuple):
    config_params, manifest_data_global = config_params_manifest_tuple
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE_STR = config_params['OUTPUT_DIR']
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS_DATA = config_params['ALL_BOOKS_DATA']

    log_target = worker_logger
    generated_pages_info = []
    author_s = slugify_to_use_global(author_slug_original)

    author_books_data = [b for b in ALL_BOOKS_DATA if slugify_to_use_global(b.get('author_slug')) == author_s]
    if not author_books_data: # Podría pasar si el slug original no coincide después de slugify_to_use_global
        return generated_pages_info

    author_page_source_identifiers = sorted([
        b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in author_books_data
    ])
    current_author_page_signature = calculate_signature({
        "book_ids_author_page": author_page_source_identifiers,
        "author_slug": author_slug_original # Usar el original para la firma
    })

    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                author_segment_translated = get_translated_url_segment_for_generator(
                    'author', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'author'
                )
                flask_url = f"/{lang}/{author_segment_translated}/{author_s}/"
                output_path_obj = (
                    Path(OUTPUT_DIR_BASE_STR) / lang / author_segment_translated /
                    author_s / "index.html"
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
    OUTPUT_DIR_BASE_STR = config_params['OUTPUT_DIR']
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS_DATA = config_params['ALL_BOOKS_DATA']

    log_target = worker_logger
    generated_pages_info = []
    author_s_orig, base_title_s_orig = author_base_title_slugs_original
    author_s = slugify_to_use_global(author_s_orig)
    base_title_s = slugify_to_use_global(base_title_s_orig)

    version_books_data = [
        b for b in ALL_BOOKS_DATA
        if slugify_to_use_global(b.get('author_slug')) == author_s and \
           slugify_to_use_global(b.get('base_title_slug')) == base_title_s
    ]
    if not version_books_data:
        return generated_pages_info

    version_page_source_identifiers = sorted([
        b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in version_books_data
    ])
    current_version_page_signature = calculate_signature({
        "book_ids_version_page": version_page_source_identifiers,
        "author_slug": author_s_orig, # Usar original para la firma
        "base_title_slug": base_title_s_orig # Usar original para la firma
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
    parser = argparse.ArgumentParser(description="Generador de sitio estático con cache y paralelización.")
    parser.add_argument(
        "--language", type=str, default=None,
        help=(
            "Generar solo para un idioma específico (ej. 'es'). "
            "Si no se especifica, se generan todos los idiomas configurados."
        )
    )
    parser.add_argument(
        "--force-regenerate", action="store_true",
        help=(
            "Forzar la regeneración de todas las páginas cacheadas (libros, autores, versiones), "
            "ignorando el manifest para ellas."
        )
    )
    parser.add_argument(
        "--char-key", type=str, default=None,
        help="Generar solo para una clave de carácter específica (letra o 0 para especiales). Requiere --language."
    )
    return parser.parse_args()


def _setup_environment_data(args, main_logger):
    main_logger.info(f"Iniciando script generate_static.py con argumentos: {args}")
    if args.force_regenerate:
        main_logger.info(
            "FORZANDO REGENERACIÓN para páginas cacheadas: "
            "El manifest será ignorado para las decisiones de 'should_regenerate'."
        )

    manifest_data = load_manifest()
    main_logger.info(f"Manifest cargado con {len(manifest_data)} entradas desde {MANIFEST_FILE}.")

    from app import create_app # Importación tardía
    app_instance = create_app()
    main_logger.info("Instancia de Flask creada en proceso principal para configuraciones.")

    all_configured_languages = app_instance.config.get('SUPPORTED_LANGUAGES', ['en'])
    if args.language:
        if args.language in all_configured_languages:
            languages_to_process = [args.language]
            main_logger.info(f"Procesando solo para el idioma especificado: {args.language}")
        else:
            main_logger.error(f"Idioma '{args.language}' no está en SUPPORTED_LANGUAGES. Saliendo.")
            return None
    else:
        languages_to_process = all_configured_languages
        main_logger.info(f"Procesando para todos los idiomas configurados: {languages_to_process}")

    books_data_list = app_instance.books_data
    if not books_data_list:
        main_logger.critical("No hay datos de libros (app_instance.books_data está vacío o no es una lista). Saliendo.")
        return None

    main_logger.info(
        f"Idiomas a procesar: {languages_to_process}. "
        f"{len(books_data_list)} libros en total en los datos fuente."
    )

    return {
        "app": app_instance,
        "manifest": manifest_data,
        "languages_to_process": languages_to_process,
        "default_language": app_instance.config.get('DEFAULT_LANGUAGE', 'en'),
        "url_segment_translations": app_instance.config.get('URL_SEGMENT_TRANSLATIONS', {}),
        "books_data": books_data_list,
        "output_dir_path": Path(OUTPUT_DIR),
    }


def _prepare_output_directory(app_static_folder, app_static_url_path, output_dir_path, # noqa: C901
                              current_lang_arg, perform_full_cleanup, char_key_arg, logger): # Añadido char_key_arg
    # Si se especifica un char_key, no hacemos la limpieza global completa ni copiamos assets globales.
    # La idea es que esta ejecución es para una porción muy específica.
    if char_key_arg and current_lang_arg:
        lang_output_dir = output_dir_path / current_lang_arg
        lang_output_dir.mkdir(parents=True, exist_ok=True) # Asegura que el dir del idioma exista
        logger.info(f"Modo char_key: Asegurando que {lang_output_dir} existe. No se realiza limpieza global.")
        # Podrías añadir limpieza específica para el char_key si fuera necesario,
        # por ejemplo, borrar _site/es/autor/z/ o _site/es/libro/z_autor/z_libro/
        # pero esto se complica y podría ser mejor dejarlo para la generación completa.
        return

    if perform_full_cleanup and not current_lang_arg: # Lógica original para limpieza completa
        if output_dir_path.exists():
            logger.info(f"Eliminando {output_dir_path} (generación completa o forzada sin idioma específico)")
            shutil.rmtree(output_dir_path)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"{output_dir_path} creado/limpiado.")

        static_folder_p = Path(app_static_folder)
        if static_folder_p.exists() and static_folder_p.is_dir():
            static_output_dir_name = Path(app_static_url_path.strip('/'))
            static_output_dir = output_dir_path / static_output_dir_name
            if static_output_dir.exists():
                shutil.rmtree(static_output_dir)
            shutil.copytree(static_folder_p, static_output_dir)
            logger.info(f"Carpeta estática '{static_folder_p.name}' copiada a '{static_output_dir}'")

        public_folder_p = Path("public")
        if public_folder_p.exists() and public_folder_p.is_dir():
            copied_public_files = 0
            for item in public_folder_p.iterdir():
                if item.is_file():
                    try:
                        shutil.copy2(item, output_dir_path / item.name)
                        copied_public_files += 1
                    except Exception as e:
                        logger.error(f"Error copiando '{item.name}': {e}")
            logger.info(f"{copied_public_files} archivos de 'public/' copiados a '{output_dir_path}'.")
    else: # No es limpieza completa global, pero asegurar que el dir base y de idioma (si aplica) existan
        output_dir_path.mkdir(parents=True, exist_ok=True)
        if current_lang_arg:
            (output_dir_path / current_lang_arg).mkdir(parents=True, exist_ok=True)
        logger.info(f"Asegurando que {output_dir_path} (y subdirectorios de idioma si aplica) existen.")


def _generate_main_process_pages(app, languages_to_process, output_dir_path,
                                 current_lang_arg, force_regen_arg, char_key_arg, logger):
    logger.info("Generando páginas de índice de idioma y sitemaps (proceso principal)...")
    with app.app_context():
        with app.test_client() as client_main:
            # Generación de index.html global y test_sitemap
            # Solo si NO se está filtrando por idioma específico Y NO por char_key
            if not current_lang_arg and not char_key_arg:
                if force_regen_arg or not (output_dir_path / "index.html").exists(): # Simplificado
                    _save_page_local(client_main, "/", output_dir_path / "index.html", logger)
                if app.url_map.is_endpoint_expecting('main.test_page'):
                    _save_page_local(
                        client_main, "/test/",
                        output_dir_path / "test_sitemap" / "index.html", logger
                    )

            for lang in languages_to_process:
                # Generación de index.html de idioma
                # Solo si NO se está filtrando por char_key (pero SÍ puede ser por idioma)
                if not char_key_arg:
                    if force_regen_arg or not (output_dir_path / lang / "index.html").exists(): # Simplificado
                        _save_page_local(client_main, f"/{lang}/", output_dir_path / lang / "index.html", logger)

                # Generación de Sitemaps
                sitemap_url_core = f"/sitemap_{lang}_core.xml"
                sitemap_path_core = output_dir_path / f"sitemap_{lang}_core.xml"

                if char_key_arg:
                    # Si se especifica un char_key, solo generamos el sitemap para ese char_key.
                    if char_key_arg == "core": # Asumiendo que 'core' es una clave válida para el sitemap core
                        _save_page_local(client_main, sitemap_url_core, sitemap_path_core, logger)
                    else:
                        # Validar que char_key_arg es una letra o SPECIAL_CHARS_SITEMAP_KEY
                        if char_key_arg in ALPHABET or char_key_arg == SPECIAL_CHARS_SITEMAP_KEY:
                            sitemap_url_char = f"/sitemap_{lang}_{char_key_arg}.xml"
                            sitemap_path_char = output_dir_path / f"sitemap_{lang}_{char_key_arg}.xml"
                            _save_page_local(client_main, sitemap_url_char, sitemap_path_char, logger)
                        else:
                            logger.warning(f"char_key '{char_key_arg}' no es válido para generar sitemap. Saltando.")
                else:
                    # Generar sitemap core y todos los de letra/carácter si no se especifica char_key
                    _save_page_local(client_main, sitemap_url_core, sitemap_path_core, logger)
                    letters_and_special = list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]
                    for char_k_iter in letters_and_special:
                        sitemap_url_char = f"/sitemap_{lang}_{char_k_iter}.xml"
                        sitemap_path_char = output_dir_path / f"sitemap_{lang}_{char_k_iter}.xml"
                        _save_page_local(client_main, sitemap_url_char, sitemap_path_char, logger)


def _run_parallel_tasks(env_data, force_regen_arg, char_key_arg, logger):
    num_processes = max(1, cpu_count() - 1 if cpu_count() > 1 else 1)
    logger.info(f"Usando {num_processes} procesos para la generación paralela de páginas cacheadas.")

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
    books_to_process_for_detail = list(all_books_source) # Copia para modificar
    # Usar slugs originales para las claves de los sets, ya que generate_xxx_task los slugifica internamente
    authors_to_process_slugs_orig = {b.get('author_slug') for b in all_books_source if b.get('author_slug')}
    bases_to_process_tuples_orig = {
        (b.get('author_slug'), b.get('base_title_slug'))
        for b in all_books_source
        if b.get('author_slug') and b.get('base_title_slug')
    }

    if char_key_arg and env_data["languages_to_process"]:
        logger.info(f"Filtrando tareas para char_key: '{char_key_arg}' en idioma(s): {env_data['languages_to_process']}")

        books_to_process_for_detail = [
            book for book in all_books_source
            if get_sitemap_char_group_for_author_local(book.get('author_slug')) == char_key_arg
        ]
        logger.info(f"  Libros para detalle después de filtrar: {len(books_to_process_for_detail)}")

        authors_to_process_slugs_orig = {
            author_slug for author_slug in authors_to_process_slugs_orig
            if get_sitemap_char_group_for_author_local(author_slug) == char_key_arg
        }
        logger.info(f"  Autores para páginas después de filtrar: {len(authors_to_process_slugs_orig)}")

        bases_to_process_tuples_orig = {
            (author_slug, base_slug) for author_slug, base_slug in bases_to_process_tuples_orig
            if get_sitemap_char_group_for_author_local(author_slug) == char_key_arg
        }
        logger.info(f"  Bases para versiones después de filtrar: {len(bases_to_process_tuples_orig)}")

        if not books_to_process_for_detail and not authors_to_process_slugs_orig and not bases_to_process_tuples_orig:
            logger.warning(f"No se encontraron elementos para el char_key '{char_key_arg}'. No se ejecutarán tareas paralelas para contenido dinámico.")
            return all_new_manifest_entries

    with Pool(processes=num_processes, initializer=worker_init) as pool:
        if books_to_process_for_detail:
            logger.info(f"Iniciando gen. paralela de páginas de detalle ({len(books_to_process_for_detail)} items)...")
            book_detail_task_with_args = partial(generate_book_detail_pages_task, config_params_manifest_tuple=task_args_tuple)
            results_books = pool.map(book_detail_task_with_args, books_to_process_for_detail)
            for res_list in results_books: all_new_manifest_entries.extend(res_list)
            count_book_detail_generated = sum(len(r) for r in results_books)
            logger.info(f"  Detalle de libros completado. {count_book_detail_generated} páginas (re)generadas.")


        if authors_to_process_slugs_orig:
            logger.info(f"Iniciando gen. paralela de páginas de autor ({len(authors_to_process_slugs_orig)} items)...")
            author_task_with_args = partial(generate_author_pages_task, config_params_manifest_tuple=task_args_tuple)
            results_authors = pool.map(author_task_with_args, list(authors_to_process_slugs_orig))
            for res_list in results_authors: all_new_manifest_entries.extend(res_list)
            count_author_generated = sum(len(r) for r in results_authors)
            logger.info(f"  Páginas de autor completado. {count_author_generated} páginas (re)generadas.")

        if bases_to_process_tuples_orig:
            logger.info(f"Iniciando gen. paralela de páginas de versiones ({len(bases_to_process_tuples_orig)} items)...")
            versions_task_with_args = partial(generate_versions_pages_task, config_params_manifest_tuple=task_args_tuple)
            results_versions = pool.map(versions_task_with_args, list(bases_to_process_tuples_orig))
            for res_list in results_versions: all_new_manifest_entries.extend(res_list)
            count_versions_generated = sum(len(r) for r in results_versions)
            logger.info(f"  Páginas de versiones completado. {count_versions_generated} páginas (re)generadas.")

    return all_new_manifest_entries


def _finalize_generation(manifest_data, new_entries, app, output_dir_path,
                         current_lang_arg, force_regen_arg, char_key_arg, logger):
    if char_key_arg and current_lang_arg:
        logger.info(
            f"Ejecución para idioma '{current_lang_arg}' y char_key '{char_key_arg}'. "
            f"El sitemap_index.xml principal NO se actualizará."
        )
        if new_entries:
            logger.info(f"Actualizando manifest con {len(new_entries)} entradas para {current_lang_arg}/{char_key_arg}...")
            for entry in new_entries:
                manifest_data[entry['path']] = {
                    "signature": entry['signature'],
                    "timestamp": entry['timestamp']
                }
            save_manifest(manifest_data)
        else:
            logger.info(f"No se generaron nuevas entradas de manifest para {current_lang_arg}/{char_key_arg}.")

    elif not current_lang_arg or force_regen_arg: # Lógica original para ejecución completa
        if new_entries:
            logger.info(f"Actualizando manifest global con {len(new_entries)} entradas de workers...")
            for entry in new_entries:
                manifest_data[entry['path']] = {
                    "signature": entry['signature'],
                    "timestamp": entry['timestamp']
                }
        else:
            logger.info("No se (re)generaron páginas cacheadas por los workers (que afectan al manifest).")

        logger.info("Generando sitemap_index.xml principal...")
        with app.app_context():
            with app.test_client() as client_main:
                _save_page_local(client_main, "/sitemap.xml", output_dir_path / "sitemap.xml", logger)
        save_manifest(manifest_data) # Guardar el manifest completo
    else: # Caso: solo idioma, sin char_key
        logger.info(
            f"Ejecución solo para idioma '{current_lang_arg}'. "
            f"{len(new_entries)} páginas del idioma (re)generadas."
        )
        if new_entries:
            logger.info(f"Actualizando manifest con {len(new_entries)} entradas para el idioma {current_lang_arg}...")
            for entry in new_entries:
                manifest_data[entry['path']] = {
                    "signature": entry['signature'],
                    "timestamp": entry['timestamp']
                }
            save_manifest(manifest_data) # Guardar el manifest con actualizaciones del idioma
        else:
            logger.info(f"No se generaron nuevas entradas de manifest para el idioma {current_lang_arg}.")


    logger.info(
        f"Sitio estático (o parte para el idioma '{current_lang_arg if current_lang_arg else 'todos'}'"
        f"{f' y char_key {char_key_arg}' if char_key_arg else ''}) "
        f"generado en: {output_dir_path}"
    )


# --- FUNCIÓN MAIN ---
def main(): # noqa: C901
    main_process_logger = script_logger
    args = _parse_cli_args()

    if args.char_key and not args.language:
        main_process_logger.error("--char-key requiere que se especifique también --language. Saliendo.")
        return

    env_data = _setup_environment_data(args, main_process_logger)
    if env_data is None:
        return

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
