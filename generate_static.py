# generate_static.py
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging
import os
from logging.handlers import RotatingFileHandler
from multiprocessing import Pool, cpu_count, current_process
from functools import partial
import argparse
import json
import hashlib
import time

# --- Carga de .env para variables de entorno (ej. GITHUB_PAGES_*) ---
try:
    from dotenv import load_dotenv
    # Asume que .env está en la raíz del proyecto, un nivel arriba de donde suele estar generate_static.py
    # Si generate_static.py está en la raíz, entonces Path(__file__).resolve().parent / '.env'
    dotenv_path = Path(__file__).resolve().parent / '.env' 
    if not dotenv_path.exists(): # Si no está al mismo nivel, buscar un nivel arriba
        dotenv_path = Path(__file__).resolve().parent.parent / '.env'

    if dotenv_path.exists():
        print(f"[generate_static.py] Loading .env file from: {dotenv_path}")
        load_dotenv(dotenv_path)
    else:
        print(f"[generate_static.py] .env file not found at {dotenv_path} or parent, using system environment variables.")
except ImportError:
    print("[generate_static.py] python-dotenv not found, .env file will not be loaded. Using system environment variables.")
# --- FIN Carga de .env ---


# --- Configuración del Logger Básico para el Script ---
script_logger = logging.getLogger('generate_static_script')
if not script_logger.handlers:
    script_logger.setLevel(os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper())
    script_handler = logging.StreamHandler()
    script_formatter = logging.Formatter(
        '%(asctime)s - %(name)s:%(processName)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
    )
    script_handler.setFormatter(script_formatter)
    script_logger.addHandler(script_handler)
    script_logger.propagate = False


# --- Variables Globales para Workers ---
worker_app_instance = None
worker_logger = None
slugify_to_use_global_worker = None


# --- CONSTANTES ---
MANIFEST_DIR = Path(".cache")
MANIFEST_FILE = MANIFEST_DIR / "generation_manifest.json"
OUTPUT_DIR = Path(os.environ.get('STATIC_SITE_OUTPUT_DIR', '_site'))
ALPHABET = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_CHARS_SITEMAP_KEY = "0"


# --- FUNCIONES DE UTILIDAD (LOCALES AL SCRIPT) ---
def slugify_ascii_local(text):
    if text is None: return ""
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
    from app.utils.helpers import slugify_ascii as slugify_ascii_app_main
    slugify_to_use_global_main = slugify_ascii_app_main
    script_logger.info("Proceso principal usando slugify_ascii de app.utils.helpers.")
except ImportError:
    script_logger.warning("Proceso principal usando slugify_ascii local (app.utils.helpers no encontrado).")


def get_sitemap_char_group_for_author_local(author_name_or_slug, slugifier_func):
    if not author_name_or_slug: return SPECIAL_CHARS_SITEMAP_KEY
    processed_slug = slugifier_func(author_name_or_slug)
    if not processed_slug: return SPECIAL_CHARS_SITEMAP_KEY
    first_char = processed_slug[0].lower()
    return first_char if first_char in ALPHABET else SPECIAL_CHARS_SITEMAP_KEY


def get_translated_url_segment_for_generator(
    segment_key, lang_code, url_segment_translations,
    default_app_lang, default_segment_value=None
):
    default_res = default_segment_value if default_segment_value is not None else segment_key
    if not url_segment_translations or not isinstance(url_segment_translations, dict):
        return default_res
    segments_for_key = url_segment_translations.get(segment_key, {})
    if not isinstance(segments_for_key, dict): return default_res
    
    translated_segment = segments_for_key.get(lang_code)
    if translated_segment: return translated_segment
    
    if lang_code != default_app_lang:
        translated_segment_default_lang = segments_for_key.get(default_app_lang)
        if translated_segment_default_lang: return translated_segment_default_lang
            
    return default_res


# --- MANIFEST HELPER FUNCTIONS ---
def load_manifest():
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except json.JSONDecodeError:
            script_logger.warning(f"Error al decodificar {MANIFEST_FILE}. Se creará uno nuevo.")
    else:
        script_logger.info(f"Archivo manifest {MANIFEST_FILE} no encontrado. Se creará uno nuevo.")
    return {}

def save_manifest(manifest_data):
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2)
    script_logger.info(f"Manifest de generación guardado en {MANIFEST_FILE} con {len(manifest_data)} entradas.")

def get_book_signature_fields(book_data):
    return dict(sorted({
        "isbn10": book_data.get("isbn10"), "isbn13": book_data.get("isbn13"),
        "asin": book_data.get("asin"), "title_slug": book_data.get("title_slug"),
        "author_slug": book_data.get("author_slug"),
        "description": book_data.get("description_short") or book_data.get("description"),
        "cover_image_url": book_data.get("image_url_l") or book_data.get("image_url_m") or book_data.get("image_url_s"),
        "publication_date": book_data.get("publication_date"),
        "publisher": book_data.get("publisher_name"),
        "language_code": book_data.get("language_code"),
    }.items()))

def calculate_signature(data_dict_for_signature):
    json_string = json.dumps(data_dict_for_signature, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(json_string.encode('utf-8')).hexdigest()

def should_regenerate_page(output_path_str, current_signature, manifest_data, logger_to_use):
    page_manifest_entry = manifest_data.get(output_path_str)
    if not page_manifest_entry or page_manifest_entry.get('signature') != current_signature or not Path(output_path_str).exists():
        action = "nuevo" if not page_manifest_entry else \
                 ("firma cambiada" if page_manifest_entry.get('signature') != current_signature else "archivo no existe")
        logger_to_use.debug(f"REGENERAR ({action}): {output_path_str}")
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
                logger_to_use.info(f"URL {url_path} devolvió 200 sin datos. No se guardó.")
        elif 300 <= response.status_code < 400 :
            location = response.headers.get('Location')
            logger_to_use.warning(f"{url_path} REDIR {response.status_code} -> {location}. NO guardado.")
        elif response.status_code == 404:
            logger_to_use.warning(f"404: {url_path} no encontrado. NO guardado.")
        else:
            logger_to_use.error(f"HTTP {response.status_code} para {url_path}. NO guardado.")
    except Exception:
        logger_to_use.exception(f"EXCEPCIÓN generando/guardando {url_path}")


# --- FUNCIONES WORKER PARA MULTIPROCESSING ---
def worker_init():
    global worker_app_instance, worker_logger, slugify_to_use_global_worker
    from app import create_app
    os.environ['IS_STATIC_GENERATION_WORKER'] = '1'
    proc_name = current_process().name
    worker_app_instance = create_app()
    worker_logger = logging.getLogger(f'generate_static_worker.{proc_name}')
    if not worker_logger.handlers:
        worker_handler = logging.StreamHandler()
        worker_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s')
        worker_handler.setFormatter(worker_formatter)
        worker_logger.addHandler(worker_handler)
    worker_log_level_name = os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper()
    worker_logger.setLevel(getattr(logging, worker_log_level_name, logging.INFO))
    worker_logger.propagate = False
    worker_logger.info(f"Worker {proc_name} inicializado. App APPLICATION_ROOT: '{worker_app_instance.config.get('APPLICATION_ROOT')}', SERVER_NAME: '{worker_app_instance.config.get('SERVER_NAME')}'")
    slugify_to_use_global_worker = slugify_ascii_local
    try:
        from app.utils.helpers import slugify_ascii as slugify_ascii_app_worker
        slugify_to_use_global_worker = slugify_ascii_app_worker
        worker_logger.info("Usando slugify_ascii de app.utils.helpers.")
    except ImportError:
        worker_logger.warning("Usando slugify_ascii local (app.utils.helpers no encontrado).")


# --- TAREAS DE GENERACIÓN ---
def _generate_task_common(item_data, config_params_manifest_tuple, page_type):
    config_params, manifest_data_global = config_params_manifest_tuple
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE_STR = str(config_params['OUTPUT_DIR'])
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS_DATA = config_params['ALL_BOOKS_DATA'] # Usado para firmas de autor/versiones
    log_target = worker_logger
    generated_pages_info = []

    if page_type == "book":
        book_data_item = item_data
        author_s_original = book_data_item.get('author_slug')
        title_s_original = book_data_item.get('title_slug')
        identifier = book_data_item.get('isbn10') or book_data_item.get('isbn13') or book_data_item.get('asin')
        if not (identifier and author_s_original and title_s_original):
            log_target.debug(f"Saltando libro (datos incompletos): ID {identifier}")
            return generated_pages_info
        author_s = slugify_to_use_global_worker(author_s_original)
        title_s = slugify_to_use_global_worker(title_s_original)
        current_page_signature = calculate_signature(get_book_signature_fields(book_data_item))
        segment_key = 'book'
        url_parts_dynamic = [author_s, title_s, identifier]
    elif page_type == "author":
        author_slug_original = item_data
        author_s = slugify_to_use_global_worker(author_slug_original)
        related_books_data = [b for b in ALL_BOOKS_DATA if slugify_to_use_global_worker(b.get('author_slug')) == author_s]
        if not related_books_data:
            log_target.debug(f"No se encontraron libros para autor '{author_s}'.")
            return generated_pages_info
        source_ids = sorted([b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in related_books_data])
        current_page_signature = calculate_signature({"book_ids_author_page": source_ids, "author_slug": author_slug_original})
        segment_key = 'author'
        url_parts_dynamic = [author_s]
    elif page_type == "versions":
        author_s_orig, base_title_s_orig = item_data
        author_s = slugify_to_use_global_worker(author_s_orig)
        base_title_s = slugify_to_use_global_worker(base_title_s_orig)
        related_books_data = [b for b in ALL_BOOKS_DATA if slugify_to_use_global_worker(b.get('author_slug')) == author_s and slugify_to_use_global_worker(b.get('base_title_slug')) == base_title_s]
        if not related_books_data:
            log_target.debug(f"No se encontraron versiones para autor '{author_s}', base_title '{base_title_s}'.")
            return generated_pages_info
        source_ids = sorted([b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in related_books_data])
        current_page_signature = calculate_signature({"book_ids_version_page": source_ids, "author_slug": author_s_orig, "base_title_slug": base_title_s_orig})
        segment_key = 'versions'
        url_parts_dynamic = [author_s, base_title_s]
    else:
        return generated_pages_info

    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                translated_segment = get_translated_url_segment_for_generator(
                    segment_key, lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, segment_key
                )
                flask_url_parts = [f"/{lang}", translated_segment] + url_parts_dynamic
                flask_url = "/".join(part for part in flask_url_parts if part) + "/"
                
                output_path_parts = [Path(OUTPUT_DIR_BASE_STR), lang, translated_segment] + url_parts_dynamic + ["index.html"]
                output_path_obj = Path(*[part for part in output_path_parts if part])
                output_path_str = str(output_path_obj)

                if FORCE_REGENERATE_ALL or should_regenerate_page(output_path_str, current_page_signature, manifest_data_global, log_target):
                    _save_page_local(client, flask_url, output_path_obj, log_target)
                    generated_pages_info.append({
                        "path": output_path_str,
                        "signature": current_page_signature,
                        "timestamp": time.time()
                    })
    return generated_pages_info

def generate_book_detail_pages_task(book_data_item, config_params_manifest_tuple):
    return _generate_task_common(book_data_item, config_params_manifest_tuple, "book")

def generate_author_pages_task(author_slug_original, config_params_manifest_tuple):
    return _generate_task_common(author_slug_original, config_params_manifest_tuple, "author")

def generate_versions_pages_task(author_base_title_slugs_original, config_params_manifest_tuple):
    return _generate_task_common(author_base_title_slugs_original, config_params_manifest_tuple, "versions")


# --- MAIN FUNCTION HELPERS ---
def _parse_cli_args():
    parser = argparse.ArgumentParser(description="Generador de sitio estático.")
    parser.add_argument("--language", type=str, help="Generar solo para un idioma (ej. 'es').")
    parser.add_argument("--force-regenerate", action="store_true", help="Forzar regeneración.")
    parser.add_argument("--char-key", type=str, help="Generar para clave de carácter. Requiere --language.")
    return parser.parse_args()

def _setup_environment_data(args, main_logger):
    from app import create_app
    main_logger.info(f"Iniciando con argumentos: {args}")
    if args.force_regenerate: main_logger.info("FORZANDO REGENERACIÓN.")
    manifest_data = load_manifest()
    main_logger.info(f"Manifest cargado con {len(manifest_data)} entradas.")
    app_instance = create_app()
    main_logger.info(f"App Flask creada. APP_ROOT: '{app_instance.config.get('APPLICATION_ROOT')}', SERVER_NAME: '{app_instance.config.get('SERVER_NAME')}'")
    
    all_langs = app_instance.config.get('SUPPORTED_LANGUAGES', ['en'])
    langs_to_process = [args.language] if args.language and args.language in all_langs else all_langs
    if args.language and args.language not in all_langs:
        main_logger.error(f"Idioma '{args.language}' no soportado. Saliendo.")
        return None
    main_logger.info(f"Procesando para idiomas: {langs_to_process}")
    
    books_data_list = app_instance.books_data
    if not books_data_list:
        main_logger.critical("Datos de libros no cargados (app.books_data vacío). Saliendo.")
        return None
    main_logger.info(f"{len(books_data_list)} libros fuente.")
    
    return {
        "app": app_instance, "manifest": manifest_data,
        "languages_to_process": langs_to_process,
        "default_language": app_instance.config.get('DEFAULT_LANGUAGE', 'en'),
        "url_segment_translations": app_instance.config.get('URL_SEGMENT_TRANSLATIONS', {}),
        "books_data": books_data_list, "output_dir_path": OUTPUT_DIR,
    }

def _prepare_output_directory(app_instance, output_dir_path,
                              current_lang_arg, perform_full_cleanup, char_key_arg, logger):
    app_static_folder_path = Path(app_instance.static_folder) # Ruta absoluta a app/static
    # app_static_url_path es la URL base para los estáticos, ej: /static o /repo/static
    app_static_url_path_str = app_instance.static_url_path 

    if char_key_arg and current_lang_arg:
        (output_dir_path / current_lang_arg).mkdir(parents=True, exist_ok=True)
        logger.info(f"Modo char_key: Asegurando {output_dir_path / current_lang_arg}. Sin limpieza global.")
        return

    if perform_full_cleanup and not current_lang_arg:
        if output_dir_path.exists():
            logger.info(f"Eliminando {output_dir_path} (limpieza completa)")
            shutil.rmtree(output_dir_path)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"{output_dir_path} creado/limpiado.")

        if app_static_folder_path.exists() and app_static_folder_path.is_dir():
            # Determinar el nombre del directorio para 'static' dentro de output_dir_path
            # Si app_static_url_path_str es '/repo/static', queremos 'static'
            # Si es '/static', queremos 'static'
            # Usamos Path().name para obtener el último componente.
            # Si app_config.APPLICATION_ROOT está configurado, static_url_path ya lo incluye.
            # Necesitamos el nombre base de la carpeta de estáticos.
            
            # Obtener el nombre de la variable GITHUB_PAGES_REPO_NAME del entorno o de la config de la app
            # Esto es crucial porque app_config.py ya ha procesado esto.
            github_repo_name_from_env = os.environ.get('GITHUB_PAGES_REPO_NAME') # Desde .env o Actions
            
            # El nombre del directorio 'static' dentro de _site
            # Debería ser solo 'static', independientemente de APPLICATION_ROOT.
            # Las URLs HTML apuntarán a /APPLICATION_ROOT/static/...
            # pero la carpeta en _site debe ser _site/static/...
            static_dir_name_in_output = "static" # Nombre estándar
            
            static_output_target_dir = output_dir_path / static_dir_name_in_output
            if static_output_target_dir.exists():
                shutil.rmtree(static_output_target_dir)
            shutil.copytree(app_static_folder_path, static_output_target_dir)
            logger.info(f"'{app_static_folder_path.name}' copiada a '{static_output_target_dir}'")
        else:
            logger.warning(f"Directorio static de la app no encontrado en {app_static_folder_path}")

        public_folder_p = Path("public")
        if public_folder_p.exists() and public_folder_p.is_dir():
            copied_count = 0
            for item in public_folder_p.iterdir():
                if item.is_file():
                    try:
                        shutil.copy2(item, output_dir_path / item.name)
                        copied_count +=1
                    except Exception as e:
                        logger.error(f"Error copiando '{item.name}' de public/: {e}")
            logger.info(f"{copied_count} archivos de 'public/' copiados a '{output_dir_path}'.")
    else: # Limpieza no completa o modo específico de idioma/char_key
        output_dir_path.mkdir(parents=True, exist_ok=True)
        if current_lang_arg:
            (output_dir_path / current_lang_arg).mkdir(parents=True, exist_ok=True)
        logger.info(f"Asegurando {output_dir_path} y subdirs de idioma si aplican (sin limpieza completa).")


def _generate_main_process_pages(app, languages_to_process, output_dir_path,
                                 current_lang_arg, force_regen_arg, char_key_arg, logger):
    logger.info("Generando páginas de índice de idioma y sitemaps (proceso principal)...")
    with app.app_context(), app.test_client() as client_main:
        if not current_lang_arg and not char_key_arg:
            if force_regen_arg or not (output_dir_path / "index.html").exists():
                _save_page_local(client_main, "/", output_dir_path / "index.html", logger)

        for lang in languages_to_process:
            if not char_key_arg:
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
                _save_page_local(client_main, sitemap_url_core, sitemap_path_core, logger)
                for char_k_iter in list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]:
                    sitemap_url_ch = f"/sitemap_{lang}_{char_k_iter}.xml"
                    sitemap_path_ch = output_dir_path / f"sitemap_{lang}_{char_k_iter}.xml"
                    _save_page_local(client_main, sitemap_url_ch, sitemap_path_ch, logger)
        
        if not current_lang_arg and not char_key_arg: # Sitemap Index principal
            _save_page_local(client_main, "/sitemap.xml", output_dir_path / "sitemap.xml", logger)


def _run_parallel_tasks(env_data, force_regen_arg, char_key_arg, logger):
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
    
    books_src = env_data["books_data"]
    slugifier = slugify_to_use_global_main
    
    # Filtrado de tareas
    detail_tasks = list(books_src)
    author_tasks = {b.get('author_slug') for b in books_src if b.get('author_slug')}
    version_tasks = {(b.get('author_slug'), b.get('base_title_slug')) for b in books_src if b.get('author_slug') and b.get('base_title_slug')}

    if char_key_arg and env_data["languages_to_process"]:
        logger.info(f"Filtrando tareas para char_key: '{char_key_arg}' en {env_data['languages_to_process']}")
        detail_tasks = [b for b in books_src if get_sitemap_char_group_for_author_local(b.get('author_slug'), slugifier) == char_key_arg]
        author_tasks = {s for s in author_tasks if get_sitemap_char_group_for_author_local(s, slugifier) == char_key_arg}
        version_tasks = {(a, t) for a, t in version_tasks if get_sitemap_char_group_for_author_local(a, slugifier) == char_key_arg}
        if not any([detail_tasks, author_tasks, version_tasks]):
            logger.warning(f"No se encontraron elementos para char_key '{char_key_arg}'. Sin tareas paralelas.")
            return all_new_manifest_entries
    
    with Pool(processes=num_processes, initializer=worker_init) as pool:
        task_map = {
            "Detalle libros": (generate_book_detail_pages_task, detail_tasks),
            "Páginas autor": (generate_author_pages_task, list(author_tasks)),
            "Páginas versiones": (generate_versions_pages_task, list(version_tasks)),
        }
        for name, (task_func, items) in task_map.items():
            if items:
                logger.info(f"Gen. paralela {name} ({len(items)} items)...")
                # Crear un nuevo 'partial' para cada tipo de tarea
                current_task_partial = partial(task_func, config_params_manifest_tuple=task_args_tuple)
                results = pool.map(current_task_partial, items)
                generated_count = 0
                for res_list in results:
                    if res_list: 
                        all_new_manifest_entries.extend(res_list)
                        generated_count += len(res_list)
                logger.info(f"  {name}: {generated_count} (re)generadas.")
    return all_new_manifest_entries


def _finalize_generation(manifest_data, new_entries, app, output_dir_path,
                         current_lang_arg, force_regen_arg, char_key_arg, logger):
    # Simplificado: siempre actualiza el manifest si hay nuevas entradas
    if new_entries:
        logger.info(f"Actualizando manifest con {len(new_entries)} entradas.")
        for entry in new_entries:
            manifest_data[entry['path']] = {"signature": entry['signature'], "timestamp": entry['timestamp']}
    
    # Guardar el manifest si es una ejecución completa, o si hubo cambios en modos parciales
    if (not current_lang_arg and not char_key_arg) or new_entries:
        save_manifest(manifest_data)
    else:
        logger.info("No se generaron nuevas entradas de manifest y no es ejecución completa. Manifest no guardado.")

    # El sitemap_index.xml ya se genera en _generate_main_process_pages si es una ejecución completa.
    log_msg_final = f"Sitio estático (o parte para idioma '{current_lang_arg or 'todos'}'"
    if char_key_arg: log_msg_final += f" y char_key '{char_key_arg}'"
    log_msg_final += f") generado en: {output_dir_path}"
    logger.info(log_msg_final)


# --- FUNCIÓN MAIN ---
def main():
    main_logger = script_logger
    args = _parse_cli_args()
    if args.char_key and not args.language:
        main_logger.error("--char-key requiere --language. Saliendo.")
        return

    env_data = _setup_environment_data(args, main_logger)
    if env_data is None: return

    app, output_dir = env_data["app"], env_data["output_dir_path"]
    perform_full_cleanup = (not args.language and not args.char_key) or \
                           (args.force_regenerate and not args.language and not args.char_key)

    _prepare_output_directory(app, output_dir, args.language, perform_full_cleanup, args.char_key, main_logger)
    _generate_main_process_pages(app, env_data["languages_to_process"], output_dir, args.language, args.force_regenerate, args.char_key, main_logger)
    new_manifest_entries = _run_parallel_tasks(env_data, args.force_regenerate, args.char_key, main_logger)
    _finalize_generation(env_data["manifest"], new_manifest_entries, app, output_dir, args.language, args.force_regenerate, args.char_key, main_logger)

if __name__ == '__main__':
    main()
