# generate_static.py
import shutil
from pathlib import Path  # Asegúrate de que Path esté importado aquí
import re
from unidecode import unidecode
import logging
# MODIFIED: Añadidas todas las importaciones necesarias para multiprocessing y otras funciones
from multiprocessing import Pool, cpu_count, current_process
from functools import partial
import argparse
import json
import hashlib
import time

# ... (el resto del código como lo tenías, la configuración del logger, etc.) ...
# --- Configuración del Logger Básico para el Script ---
script_logger = logging.getLogger('generate_static_script')  # script_logger se define aquí
script_logger.setLevel(logging.INFO)
script_handler = logging.StreamHandler()
script_formatter = logging.Formatter('%(asctime)s - %(name)s:%(processName)s - %(levelname)s - %(message)s')
script_handler.setFormatter(script_formatter)
if not script_logger.handlers:
    script_logger.addHandler(script_handler)

# --- Variables Globales para Workers (se establecerán en worker_init) ---
worker_app_instance = None
worker_logger = None
slugify_to_use_global = None

# --- MANIFEST CONSTANTS ---
MANIFEST_DIR = Path(".cache")  # Path se usa aquí
MANIFEST_FILE = MANIFEST_DIR / "generation_manifest.json"  # Path se usa aquí


# --- FUNCIONES DE UTILIDAD ---
def slugify_ascii_local(text):  # slugify_ascii_local se define aquí
    # ... (código sin cambios) ...
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


try:
    _temp_slugify = slugify_ascii_local
except ImportError:
    _temp_slugify = slugify_ascii_local
slugify_to_use_global = _temp_slugify


def get_translated_url_segment_for_generator(
    segment_key,
    lang_code,
    url_segment_translations,
    default_app_lang,
    default_segment_value=None
):  # se define aquí
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


OUTPUT_DIR = "_site"  # OUTPUT_DIR se define aquí
ALPHABET = "abcdefghijklmnopqrstuvwxyz"  # ALPHABET se define aquí
SPECIAL_CHARS_SITEMAP_KEY = "0"  # SPECIAL_CHARS_SITEMAP_KEY se define aquí


# --- MANIFEST HELPER FUNCTIONS ---
def load_manifest():  # se define aquí
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            script_logger.warning(f"Error al decodificar {MANIFEST_FILE}. Se creará uno nuevo.")
            return {}
    script_logger.info(f"Archivo manifest {MANIFEST_FILE} no encontrado. Se creará uno nuevo.")
    return {}


def save_manifest(manifest_data):  # se define aquí
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest_data, f, indent=2)
    script_logger.info(f"Manifest de generación guardado en {MANIFEST_FILE} con {len(manifest_data)} entradas.")


def get_book_signature_fields(book_data):  # se define aquí
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


def calculate_signature(data_dict_for_signature):  # se define aquí
    json_string = json.dumps(data_dict_for_signature, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(json_string.encode('utf-8')).hexdigest()


def should_regenerate_page(output_path_str, current_signature, manifest_data, logger_to_use):  # se define aquí
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
def _save_page_local(client_local, url_path, file_path_obj, logger_to_use):  # se define aquí
    try:
        pass
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
    from app import create_app

    proc_name = current_process().name

    worker_app_instance = create_app()

    worker_logger = script_logger

    try:
        from app.utils.helpers import slugify_ascii as slugify_ascii_app
        slugify_to_use_global = slugify_ascii_app
        worker_logger.info(f"Worker {proc_name}: usando slugify_ascii de app.utils.helpers.")
    except ImportError:
        slugify_to_use_global = slugify_ascii_local
        worker_logger.warning(f"Worker {proc_name}: usando slugify_ascii local.")


def generate_book_detail_pages_task(book_data_item, config_params_manifest_tuple):
    config_params, manifest_data_global = config_params_manifest_tuple

    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE = config_params['OUTPUT_DIR']
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)

    log_target = worker_logger if worker_logger else script_logger
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
                    Path(OUTPUT_DIR_BASE) / lang / book_segment_translated /
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
    OUTPUT_DIR_BASE = config_params['OUTPUT_DIR']
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS_DATA = config_params['ALL_BOOKS_DATA']

    log_target = worker_logger if worker_logger else script_logger
    generated_pages_info = []
    author_s = slugify_to_use_global(author_slug_original)

    author_books_data = [b for b in ALL_BOOKS_DATA if b.get('author_slug') == author_slug_original]
    if not author_books_data:
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
                    Path(OUTPUT_DIR_BASE) / lang / author_segment_translated /
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
    OUTPUT_DIR_BASE = config_params['OUTPUT_DIR']
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS_DATA = config_params['ALL_BOOKS_DATA']

    log_target = worker_logger if worker_logger else script_logger
    generated_pages_info = []
    author_s_orig, base_title_s_orig = author_base_title_slugs_original
    author_s = slugify_to_use_global(author_s_orig)
    base_title_s = slugify_to_use_global(base_title_s_orig)

    version_books_data = [
        b for b in ALL_BOOKS_DATA
        if b.get('author_slug') == author_s_orig and b.get('base_title_slug') == base_title_s_orig
    ]
    if not version_books_data:
        return generated_pages_info

    version_page_source_identifiers = sorted([
        b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in version_books_data
    ])
    current_version_page_signature = calculate_signature({
        "book_ids_version_page": version_page_source_identifiers,
        "author_slug": author_s_orig,
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
                    Path(OUTPUT_DIR_BASE) / lang / versions_segment_translated /
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

    from app import create_app
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


def _prepare_output_directory(app_static_folder, app_static_url_path, output_dir_path,
                              current_lang_arg, perform_full_cleanup, logger):
    if perform_full_cleanup and not current_lang_arg:
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
    else:
        output_dir_path.mkdir(parents=True, exist_ok=True)
        if current_lang_arg:
            (output_dir_path / current_lang_arg).mkdir(parents=True, exist_ok=True)
        logger.info(f"Asegurando que {output_dir_path} (y subdirectorios de idioma si aplica) existen.")


def _generate_main_process_pages(app, languages_to_process, output_dir_path,
                                 current_lang_arg, force_regen_arg, logger):
    logger.info("Generando páginas de índice de idioma y sitemaps por letra/core (proceso principal)...")
    with app.app_context():
        with app.test_client() as client_main:
            if not current_lang_arg or force_regen_arg:
                _save_page_local(client_main, "/", output_dir_path / "index.html", logger)
                if app.url_map.is_endpoint_expecting('main.test_page'):
                    _save_page_local(
                        client_main, "/test/",
                        output_dir_path / "test_sitemap" / "index.html", logger
                    )

            for lang in languages_to_process:
                _save_page_local(client_main, f"/{lang}/", output_dir_path / lang / "index.html", logger)

                sitemap_url_core = f"/sitemap_{lang}_core.xml"
                sitemap_path_core = output_dir_path / f"sitemap_{lang}_core.xml"
                _save_page_local(client_main, sitemap_url_core, sitemap_path_core, logger)

                letters_and_special = list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]
                for char_key in letters_and_special:
                    sitemap_url_char = f"/sitemap_{lang}_{char_key}.xml"
                    sitemap_path_char = output_dir_path / f"sitemap_{lang}_{char_key}.xml"
                    _save_page_local(client_main, sitemap_url_char, sitemap_path_char, logger)


def _run_parallel_tasks(env_data, force_regen_arg, logger):
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

    with Pool(processes=num_processes, initializer=worker_init) as pool:
        logger.info("Iniciando generación paralela de páginas de detalle de libros...")
        book_detail_task_with_args = partial(generate_book_detail_pages_task, config_params_manifest_tuple=task_args_tuple)
        results_books = pool.map(book_detail_task_with_args, env_data["books_data"])
        for res_list in results_books:
            all_new_manifest_entries.extend(res_list)
        count_book_detail = sum(len(r) for r in results_books) # Count from results of this batch
        log_msg_book_detail = (
            f"Proceso de detalle de libros completado. {count_book_detail} "
            "páginas cacheadas (re)generadas o marcadas."
        )
        logger.info(log_msg_book_detail)

        current_total_entries = len(all_new_manifest_entries)
        logger.info("Iniciando generación paralela de páginas de autor...")
        unique_author_slugs = {b.get('author_slug') for b in env_data["books_data"] if b.get('author_slug')}
        author_task_with_args = partial(generate_author_pages_task, config_params_manifest_tuple=task_args_tuple)
        results_authors = pool.map(author_task_with_args, list(unique_author_slugs))
        for res_list in results_authors:
            all_new_manifest_entries.extend(res_list)
        count_author_pages = len(all_new_manifest_entries) - current_total_entries
        log_msg_author = (
            f"Proceso de páginas de autor completado. {count_author_pages} "
            "páginas de autor cacheadas (re)generadas o marcadas."
        )
        logger.info(log_msg_author)

        current_total_entries = len(all_new_manifest_entries)
        logger.info("Iniciando generación paralela de páginas de versiones...")
        unique_bases = {
            (b.get('author_slug'), b.get('base_title_slug'))
            for b in env_data["books_data"]
            if b.get('author_slug') and b.get('base_title_slug')
        }
        versions_task_with_args = partial(generate_versions_pages_task, config_params_manifest_tuple=task_args_tuple)
        results_versions = pool.map(versions_task_with_args, list(unique_bases))
        for res_list in results_versions:
            all_new_manifest_entries.extend(res_list)
        count_version_pages = len(all_new_manifest_entries) - current_total_entries
        log_msg_versions = (
            f"Proceso de páginas de versiones completado. {count_version_pages} "
            "páginas de versiones cacheadas (re)generadas o marcadas."
        )
        logger.info(log_msg_versions)
    return all_new_manifest_entries


def _finalize_generation(manifest_data, new_entries, app, output_dir_path,
                         current_lang_arg, force_regen_arg, logger):
    if not current_lang_arg or force_regen_arg:
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
        save_manifest(manifest_data)
    else:
        logger.info(
            f"Ejecución para idioma '{current_lang_arg}'. El manifest global no se guardó. "
            f"{len(new_entries)} páginas del idioma (re)generadas."
        )

    logger.info(
        f"Sitio estático (o parte para el idioma '{current_lang_arg if current_lang_arg else 'todos'}') "
        f"generado en: {output_dir_path}"
    )


# --- FUNCIÓN MAIN ---
def main():
    main_process_logger = script_logger
    args = _parse_cli_args()

    env_data = _setup_environment_data(args, main_process_logger)
    if env_data is None:
        return  # Setup failed, error already logged

    app = env_data["app"]
    perform_full_cleanup = (not args.language) or args.force_regenerate
    _prepare_output_directory(
        app.static_folder, app.static_url_path, env_data["output_dir_path"],
        args.language, perform_full_cleanup, main_process_logger
    )

    _generate_main_process_pages(
        app, env_data["languages_to_process"], env_data["output_dir_path"],
        args.language, args.force_regenerate, main_process_logger
    )

    new_manifest_entries = _run_parallel_tasks(
        env_data, args.force_regenerate, main_process_logger
    )

    _finalize_generation(
        env_data["manifest"], new_manifest_entries, app, env_data["output_dir_path"],
        args.language, args.force_regenerate, main_process_logger
    )


if __name__ == '__main__':
    main()
