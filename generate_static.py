# generate_static.py
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging
import os
from multiprocessing import Pool, cpu_count, current_process
from functools import partial
import argparse
import json
import hashlib
import time

# --- Carga de .env ---
try:
    from dotenv import load_dotenv
    dotenv_path_script_dir = Path(__file__).resolve().parent / '.env'
    dotenv_path_parent_dir = Path(__file__).resolve().parent.parent / '.env'
    dotenv_to_load = None
    if dotenv_path_script_dir.exists():
        dotenv_to_load = dotenv_path_script_dir
    elif dotenv_path_parent_dir.exists():
        dotenv_to_load = dotenv_path_parent_dir

    if dotenv_to_load:
        print(f"[generate_static.py] Loading .env file from: {dotenv_to_load}")
        load_dotenv(dotenv_path=dotenv_to_load, override=True)
    else:
        print("[generate_static.py] .env file not found. Using system environment variables.")
except ImportError:
    print("[generate_static.py] python-dotenv not found, .env file will not be loaded.")

# --- Configuración del Logger Básico para el Script ---
script_logger = logging.getLogger('generate_static_script')
if not script_logger.handlers:
    log_level_name = os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    script_logger.setLevel(log_level)
    script_handler = logging.StreamHandler()
    script_formatter = logging.Formatter(
        '%(asctime)s - %(name)s:%(processName)s - %(levelname)s - '
        '[%(funcName)s:%(lineno)d] - %(message)s'
    )
    script_handler.setFormatter(script_formatter)
    script_logger.addHandler(script_handler)
    script_logger.propagate = False
else: # Asegurar que el nivel se actualiza si ya existe el logger
    log_level_name = os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    script_logger.setLevel(log_level)

script_logger.info(
    f"Logger principal configurado con nivel: {logging.getLevelName(script_logger.level)}"
)

# --- Variables Globales (se inicializarán más tarde) ---
worker_app_instance = None
worker_logger = None # Será un logger específico del worker
slugify_to_use_global_worker = None # El slugifier que usará el worker

# --- CONSTANTES ---
MANIFEST_DIR = Path(".cache")
MANIFEST_FILE = MANIFEST_DIR / "generation_manifest.json"
OUTPUT_DIR = Path(os.environ.get('STATIC_SITE_OUTPUT_DIR', '_site'))
ALPHABET = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_CHARS_SITEMAP_KEY = "0"

# --- FUNCIONES DE UTILIDAD ---
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
    script_logger.info("Proceso principal: Usando slugify_ascii de app.utils.helpers.")
except ImportError:
    script_logger.warning("Proceso principal: Usando slugify_ascii local (app.utils.helpers no encontrado).")

def get_sitemap_char_group_for_author(author_name_or_slug, slugifier_func):
    """Determina el grupo de sitemap para un autor usando el slugifier_func provisto."""
    if not author_name_or_slug:
        script_logger.debug(f"get_sitemap_char_group: Input vacío, devolviendo '{SPECIAL_CHARS_SITEMAP_KEY}'")
        return SPECIAL_CHARS_SITEMAP_KEY
    processed_slug = slugifier_func(str(author_name_or_slug))
    script_logger.debug(f"get_sitemap_char_group: Input='{author_name_or_slug}', SlugProcesado='{processed_slug}' con {slugifier_func.__name__}")
    if not processed_slug:
        script_logger.debug(f"get_sitemap_char_group: Slug procesado vacío, devolviendo '{SPECIAL_CHARS_SITEMAP_KEY}'")
        return SPECIAL_CHARS_SITEMAP_KEY
    first_char = processed_slug[0].lower()
    result_char = first_char if first_char in ALPHABET else SPECIAL_CHARS_SITEMAP_KEY
    script_logger.debug(f"get_sitemap_char_group: PrimerChar='{first_char}', ResultadoGrupo='{result_char}'")
    return result_char

def get_translated_url_segment_for_generator(
    segment_key, lang_code, url_segment_translations,
    default_app_lang, default_segment_value=None
):
    default_res = default_segment_value if default_segment_value is not None else segment_key
    if not url_segment_translations or not isinstance(url_segment_translations, dict):
        return default_res
    segments_for_key = url_segment_translations.get(segment_key, {})
    if not isinstance(segments_for_key, dict):
        return default_res
    translated_segment = segments_for_key.get(lang_code)
    if translated_segment:
        return translated_segment
    if lang_code != default_app_lang:
        translated_segment_default_lang = segments_for_key.get(default_app_lang)
        if translated_segment_default_lang:
            return translated_segment_default_lang
    return default_res

# --- MANIFEST HELPER FUNCTIONS ---
def load_manifest():
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            script_logger.warning(f"Error decodificando {MANIFEST_FILE}. Se creará nuevo.")
    else:
        script_logger.info(f"Manifest {MANIFEST_FILE} no encontrado. Se creará nuevo.")
    return {}

def save_manifest(manifest_data):
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2)
    script_logger.info(f"Manifest guardado en {MANIFEST_FILE} ({len(manifest_data)} entradas).")

def get_book_signature_fields(book_data):
    return dict(sorted({
        "isbn10": book_data.get("isbn10"), "isbn13": book_data.get("isbn13"),
        "asin": book_data.get("asin"), "title_slug": book_data.get("title_slug"),
        "author_slug": book_data.get("author_slug"),
        "description": book_data.get("description_short") or book_data.get("description"),
        "cover_image_url": (book_data.get("image_url_l") or book_data.get("image_url_m") or book_data.get("image_url_s")),
        "publication_date": book_data.get("publication_date"),
        "publisher": book_data.get("publisher_name"), "language_code": book_data.get("language_code"),
    }.items()))

def calculate_signature(data_dict):
    json_string = json.dumps(data_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(json_string.encode('utf-8')).hexdigest()

def should_regenerate_page(path_str, signature, manifest, logger):
    entry = manifest.get(path_str)
    if not entry:
        logger.debug(f"REGENERAR (nuevo): {path_str}")
        return True
    if entry.get('signature') != signature:
        logger.debug(f"REGENERAR (firma cambiada): {path_str}")
        return True
    if not Path(path_str).exists():
        logger.debug(f"REGENERAR (no existe): {path_str}")
        return True
    logger.debug(f"SALTAR (sin cambios): {path_str}")
    return False

# --- FUNCIÓN _save_page_local ---
def _save_page_local(client, url, path_obj, logger):
    try:
        response = client.get(url)
        if response.status_code == 200:
            if response.data:
                path_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(path_obj, 'wb') as f:
                    f.write(response.data)
                logger.info(f"GENERADO: {url} -> {path_obj}")
            else:
                logger.info(f"URL {url} devolvió 200 sin datos. No se guardó.")
        elif 300 <= response.status_code < 400:
            logger.warning(
                f"{url} REDIR {response.status_code} -> {response.headers.get('Location')}. NO guardado."
            )
        elif response.status_code == 404:
            logger.warning(f"404: {url} no encontrado. NO guardado.")
        else:
            logger.error(f"HTTP {response.status_code} para {url}. NO guardado.")
    except Exception:
        logger.exception(f"EXCEPCIÓN generando/guardando {url}")

# --- FUNCIONES WORKER PARA MULTIPROCESSING ---
def worker_init():
    global worker_app_instance, worker_logger, slugify_to_use_global_worker
    from app import create_app

    os.environ['IS_STATIC_GENERATION_WORKER'] = '1'
    proc_name = current_process().name
    worker_app_instance = create_app()

    # Configurar logger para el worker
    worker_logger = logging.getLogger(f'generate_static_worker.{proc_name}')
    # Limpiar handlers existentes para evitar duplicación si worker_init se llama múltiples veces
    # (aunque no debería en un Pool estándar)
    if worker_logger.hasHandlers():
        worker_logger.handlers.clear()

    worker_handler = logging.StreamHandler()
    worker_formatter = logging.Formatter(
        '%(asctime)s - %(name)s:%(processName)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
    )
    worker_handler.setFormatter(worker_formatter)
    worker_logger.addHandler(worker_handler)

    main_log_level_name = os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper()
    worker_log_level = getattr(logging, main_log_level_name, logging.INFO)
    worker_logger.setLevel(worker_log_level)
    worker_logger.propagate = False # Muy importante para evitar logs duplicados en la consola principal

    # Configurar slugify para el worker
    slugify_to_use_global_worker = slugify_ascii_local # Default
    try:
        from app.utils.helpers import slugify_ascii as slugify_ascii_app_worker
        slugify_to_use_global_worker = slugify_ascii_app_worker
        worker_logger.debug("Worker: Usando slugify_ascii de app.utils.helpers.")
    except ImportError:
        worker_logger.warning("Worker: Usando slugify_ascii local (app.utils.helpers no encontrado).")
    worker_logger.info(f"Worker {proc_name} inicializado. Slugifier: {slugify_to_use_global_worker.__name__}. Nivel de log: {logging.getLevelName(worker_logger.level)}")


# --- TAREAS DE GENERACIÓN REFACTORIZADAS ---
def _generate_task_common(item_data, config_params_manifest_tuple, page_type): # noqa: C901
    config_params, manifest_data_global = config_params_manifest_tuple
    # Estas variables son globales DENTRO DEL CONTEXTO DEL WORKER
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS = config_params['URL_SEGMENT_TRANSLATIONS']
    OUTPUT_DIR_BASE = Path(config_params['OUTPUT_DIR'])
    FORCE_REGENERATE = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS = config_params['ALL_BOOKS_DATA']

    log_target = worker_logger
    current_slugifier = slugify_to_use_global_worker
    app_for_context = worker_app_instance

    generated_pages_info = []
    current_page_signature, segment_key_for_url, dynamic_url_parts = "", "", []

    if page_type == "book":
        book = item_data
        author_orig, title_orig = book.get('author_slug'), book.get('title_slug')
        ident = book.get('isbn10') or book.get('isbn13') or book.get('asin')
        if not all([author_orig, title_orig, ident]):
            log_target.debug(f"Saltando libro (datos incompletos): ID '{ident}'")
            return []
        author_s, title_s = current_slugifier(author_orig), current_slugifier(title_orig)
        current_page_signature = calculate_signature(get_book_signature_fields(book))
        segment_key_for_url, dynamic_url_parts = 'book', [author_s, title_s, str(ident)]
    elif page_type == "author":
        author_orig = item_data
        author_s = current_slugifier(author_orig)
        related_books = [b for b in ALL_BOOKS if current_slugifier(b.get('author_slug')) == author_s]
        if not related_books:
            log_target.debug(f"No hay libros para autor '{author_s}' (original '{author_orig}').")
            return []
        ids = sorted([b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in related_books])
        current_page_signature = calculate_signature({"book_ids": ids, "author_slug": author_orig})
        segment_key_for_url, dynamic_url_parts = 'author', [author_s]
    elif page_type == "versions":
        author_orig, base_title_orig = item_data
        author_s, base_title_s = current_slugifier(author_orig), current_slugifier(base_title_orig)
        related_books = [
            b for b in ALL_BOOKS
            if current_slugifier(b.get('author_slug')) == author_s and
               current_slugifier(b.get('base_title_slug')) == base_title_s
        ]
        if not related_books:
            log_target.debug(f"No hay versiones para '{author_s}', '{base_title_s}'.")
            return []
        ids = sorted([b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in related_books])
        current_page_signature = calculate_signature({
            "book_ids": ids, "author_slug": author_orig, "base_title_slug": base_title_orig
        })
        segment_key_for_url, dynamic_url_parts = 'versions', [author_s, base_title_s]
    else:
        log_target.error(f"Tipo de página desconocido: {page_type}")
        return []

    with app_for_context.app_context():
        with app_for_context.test_client() as client:
            for lang in LANGUAGES:
                segment_translated = get_translated_url_segment_for_generator(
                    segment_key_for_url, lang, URL_SEGMENT_TRANSLATIONS, DEFAULT_LANGUAGE, segment_key_for_url
                )
                str_dynamic_parts = [str(p) for p in dynamic_url_parts]
                flask_url_path_elements = [f"/{lang}", segment_translated] + str_dynamic_parts
                # Construir URL asegurando un solo slash entre partes y al final
                flask_url = "/" + "/".join(s.strip("/") for s in flask_url_path_elements if s.strip("/")) + "/"

                output_path_parts = [lang, segment_translated] + str_dynamic_parts + ["index.html"]
                output_path_obj = OUTPUT_DIR_BASE.joinpath(*output_path_parts)
                output_path_str = str(output_path_obj)

                if FORCE_REGENERATE or should_regenerate_page(
                    output_path_str, current_page_signature, manifest_data_global, log_target
                ):
                    _save_page_local(client, flask_url, output_path_obj, log_target)
                    generated_pages_info.append({
                        "path": output_path_str, "signature": current_page_signature, "timestamp": time.time()
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
    parser.add_argument("--log-level", type=str, default=os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper(),
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help="Nivel de log para el script.")
    return parser.parse_args()

def _setup_environment_data(args, main_logger):
    from app import create_app
    main_logger.info(f"Iniciando con argumentos: {args}")
    if args.force_regenerate: main_logger.info("FORZANDO REGENERACIÓN.")
    manifest_data = load_manifest()
    main_logger.info(f"Manifest cargado: {len(manifest_data)} entradas.")
    if 'IS_STATIC_GENERATION_WORKER' in os.environ:
        del os.environ['IS_STATIC_GENERATION_WORKER']
    app_instance = create_app()
    main_logger.info(
        f"App Flask creada. APP_ROOT: '{app_instance.config.get('APPLICATION_ROOT')}', "
        f"SERVER_NAME: '{app_instance.config.get('SERVER_NAME')}'"
    )
    all_langs = app_instance.config.get('SUPPORTED_LANGUAGES', ['en'])
    langs_to_process = [args.language] if args.language and args.language in all_langs else all_langs
    if args.language and args.language not in all_langs:
        main_logger.error(f"Idioma '{args.language}' no soportado. Saliendo."); return None
    main_logger.info(f"Procesando para idiomas: {langs_to_process}")
    books_list = app_instance.books_data
    if not books_list: main_logger.critical("Datos de libros no cargados. Saliendo."); return None
    main_logger.info(f"{len(books_list)} libros fuente.")
    return {
        "app": app_instance, "manifest": manifest_data,
        "languages_to_process": langs_to_process,
        "default_language": app_instance.config.get('DEFAULT_LANGUAGE', 'en'),
        "url_segment_translations": app_instance.config.get('URL_SEGMENT_TRANSLATIONS', {}),
        "books_data": books_list, "output_dir_path": OUTPUT_DIR,
    }

def _prepare_output_directory(app_instance, output_dir,  # noqa: C901
                              current_lang, perform_cleanup, char_key, logger):
    app_root_path = Path(app_instance.root_path)
    # app.static_folder es el nombre de la carpeta (ej. 'static')
    # app.static_url_path es la ruta URL (ej. '/static')
    app_static_folder_abs = app_root_path / app_instance.static_folder

    if char_key and current_lang:
        (output_dir / current_lang).mkdir(parents=True, exist_ok=True)
        logger.info(f"Modo char_key: Asegurando {output_dir / current_lang}. Sin limpieza global.")
        return

    if perform_cleanup and not current_lang:
        if output_dir.exists():
            logger.info(f"Eliminando {output_dir} (limpieza completa)")
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"{output_dir} creado/limpiado.")

        if app_static_folder_abs.exists() and app_static_folder_abs.is_dir():
            # El nombre del directorio en _site debe ser el nombre base de static_url_path
            static_dir_name_in_output = Path(app_instance.static_url_path.strip('/')).name
            static_target = output_dir / static_dir_name_in_output
            if static_target.exists(): shutil.rmtree(static_target)
            shutil.copytree(app_static_folder_abs, static_target, dirs_exist_ok=True)
            logger.info(f"'{app_static_folder_abs.name}' copiada a '{static_target}'")
        else:
            logger.warning(f"Directorio static de la app no encontrado en {app_static_folder_abs}")

        public_folder = Path("public")
        if public_folder.exists() and public_folder.is_dir():
            copied = 0
            for item in public_folder.iterdir():
                if item.is_file():
                    try:
                        shutil.copy2(item, output_dir / item.name)
                        copied += 1
                    except Exception as e:
                        logger.error(f"Error copiando '{item.name}' de public/: {e}")
            logger.info(f"{copied} archivos de 'public/' copiados a '{output_dir}'.")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        if current_lang:
            (output_dir / current_lang).mkdir(parents=True, exist_ok=True)
        logger.info(f"Asegurando {output_dir} y subdirs (sin limpieza completa).")

def _generate_main_process_pages(app, langs, out_dir, lang_arg, force_regen, char_key, logger): # noqa: C901
    logger.info("Generando páginas de índice y sitemaps (proceso principal)...")
    with app.app_context(), app.test_client() as client:
        if not lang_arg and not char_key:
            if force_regen or not (out_dir / "index.html").exists():
                _save_page_local(client, "/", out_dir / "index.html", logger)

        for lang_code in langs:
            if not char_key:
                if force_regen or not (out_dir / lang_code / "index.html").exists():
                    _save_page_local(client, f"/{lang_code}/", out_dir / lang_code / "index.html", logger)

            sitemap_core_url = f"/sitemap_{lang_code}_core.xml"
            sitemap_core_path = out_dir / f"sitemap_{lang_code}_core.xml"
            if char_key:
                if char_key == "core":
                    _save_page_local(client, sitemap_core_url, sitemap_core_path, logger)
                elif char_key in ALPHABET or char_key == SPECIAL_CHARS_SITEMAP_KEY:
                    s_url = f"/sitemap_{lang_code}_{char_key}.xml"
                    s_path = out_dir / f"sitemap_{lang_code}_{char_key}.xml"
                    _save_page_local(client, s_url, s_path, logger)
            else:
                _save_page_local(client, sitemap_core_url, sitemap_core_path, logger)
                for char_k_iter in list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]:
                    s_url = f"/sitemap_{lang_code}_{char_k_iter}.xml"
                    s_path = out_dir / f"sitemap_{lang_code}_{char_k_iter}.xml"
                    _save_page_local(client, s_url, s_path, logger)

        if not lang_arg and not char_key:
            _save_page_local(client, "/sitemap.xml", out_dir / "sitemap.xml", logger)

def _run_parallel_tasks(env_data, force_regen, char_key, logger): # noqa: C901
    num_procs = max(1, cpu_count() - 1 if cpu_count() > 1 else 1)
    logger.info(f"Usando {num_procs} procesos para generación paralela.")
    config_tasks = {
        'LANGUAGES': env_data["languages_to_process"],
        'DEFAULT_LANGUAGE': env_data["default_language"],
        'URL_SEGMENT_TRANSLATIONS': env_data["url_segment_translations"],
        'OUTPUT_DIR': str(env_data["output_dir_path"]),
        'FORCE_REGENERATE_ALL': force_regen,
        'ALL_BOOKS_DATA': env_data["books_data"]
    }
    task_args = (config_tasks, env_data["manifest"].copy())
    all_new_entries = []
    books_src = env_data["books_data"]
    # IMPORTANTE: Para el filtrado en el proceso principal, usamos el slugifier del proceso principal.
    # Los workers usarán su propio slugifier (que debería ser el mismo si la app se carga igual).
    slugifier_for_main_filtering = slugify_to_use_global_main

    detail_items = list(books_src) # Por defecto, procesar todos
    author_items_orig = {b.get('author_slug') for b in books_src if b.get('author_slug')}
    version_items_orig = {(b.get('author_slug'), b.get('base_title_slug')) for b in books_src
                          if b.get('author_slug') and b.get('base_title_slug')}

    if char_key and env_data["languages_to_process"]:
        logger.info(f"Filtrando tareas para char_key: '{char_key}' en {env_data['languages_to_process']}")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("--- DEBUG: Verificando grupos de autor para filtrado (primeros ~10 distintos) ---")
            checked_authors_debug = set()
            count_debug = 0
            for book_debug in books_src:
                auth_orig = book_debug.get('author_slug')
                if auth_orig and auth_orig not in checked_authors_debug:
                    group = get_sitemap_char_group_for_author(auth_orig, slugifier_for_main_filtering)
                    logger.debug(f"  Autor: '{auth_orig}' (slugificado da {slugifier_for_main_filtering(auth_orig)}) -> Grupo: '{group}'")
                    checked_authors_debug.add(auth_orig)
                    count_debug +=1
                    if count_debug >=10:
                        break
            logger.debug("--- FIN DEBUG ---")

        detail_items = [b for b in books_src if get_sitemap_char_group_for_author(b.get('author_slug'), slugifier_for_main_filtering) == char_key]
        author_items_orig = {s for s in author_items_orig if get_sitemap_char_group_for_author(s, slugifier_for_main_filtering) == char_key}
        version_items_orig = {(a, t) for a, t in version_items_orig if get_sitemap_char_group_for_author(a, slugifier_for_main_filtering) == char_key}

        logger.info(
            f"  Después de filtrar por char_key '{char_key}': "
            f"Detalle: {len(detail_items)}, Autores: {len(author_items_orig)}, Versiones: {len(version_items_orig)}"
        )
        if not any([detail_items, author_items_orig, version_items_orig]):
            logger.warning(f"No se encontraron elementos para char_key '{char_key}'. Sin tareas paralelas."); return []

    task_definitions = [
        ("Detalle libros", generate_book_detail_pages_task, detail_items),
        ("Páginas autor", generate_author_pages_task, list(author_items_orig)),
        ("Páginas versiones", generate_versions_pages_task, list(version_items_orig)),
    ]

    with Pool(processes=num_procs, initializer=worker_init) as pool:
        for name, task_func, items_to_process in task_definitions:
            if items_to_process:
                logger.info(f"Gen. paralela {name} ({len(items_to_process)} items)...")
                current_task_partial = partial(task_func, config_params_manifest_tuple=task_args)
                results_for_task = pool.map(current_task_partial, items_to_process)
                generated_count_for_task = 0
                for res_list in results_for_task:
                    if res_list and isinstance(res_list, list):
                        all_new_entries.extend(res_list)
                        generated_count_for_task += len(res_list)
                logger.info(f"  {name}: {generated_count_for_task} (re)generadas.")
            else:
                logger.info(f"No hay items para '{name}'. Saltando.")
    return all_new_entries

def _finalize_generation(manifest, new_entries, out_dir, lang_arg, char_key, logger): # noqa: C901
    updated_manifest = False
    if new_entries:
        logger.info(f"Actualizando manifest con {len(new_entries)} entradas.")
        for entry in new_entries:
            manifest[entry['path']] = {"signature": entry['signature'], "timestamp": entry['timestamp']}
        updated_manifest = True

    is_full_run_no_filters = (not lang_arg and not char_key)
    # Guardar manifest si se actualizó o si es una ejecución completa
    if updated_manifest or is_full_run_no_filters:
        save_manifest(manifest)
        if not updated_manifest and is_full_run_no_filters:
            logger.info("Ejecución completa sin nuevas entradas, manifest guardado (podría estar vacío si es la primera vez).")
    else:
        logger.info("Manifest no actualizado y no es ejecución completa. No se guardó.")

    log_msg = f"Sitio estático (o parte para idioma '{lang_arg or 'todos'}'"
    if char_key: log_msg += f" y char_key '{char_key}'"
    log_msg += f") generado en: {out_dir}"
    logger.info(log_msg)

# --- FUNCIÓN MAIN ---
def main(): # noqa: C901
    args = _parse_cli_args()
    log_level_name_main = args.log_level # Ya tiene un default de os.environ o INFO
    log_level_main_actual = getattr(logging, log_level_name_main, logging.INFO)
    script_logger.setLevel(log_level_main_actual) # Aplicar el nivel al logger principal
    script_logger.info(f"Nivel de log para script principal establecido a: {log_level_name_main}")
    os.environ['SCRIPT_LOG_LEVEL'] = log_level_name_main # Para que los workers lo hereden

    if args.char_key and not args.language:
        script_logger.error("--char-key requiere --language. Saliendo."); return

    env_data = _setup_environment_data(args, script_logger)
    if env_data is None: return

    app, out_dir = env_data["app"], env_data["output_dir_path"]
    perform_cleanup = (not args.language and not args.char_key) or \
                      (args.force_regenerate and not args.language and not args.char_key)

    _prepare_output_directory(app, out_dir, args.language, perform_cleanup, args.char_key, script_logger)
    _generate_main_process_pages(
        app, env_data["languages_to_process"], out_dir, args.language,
        args.force_regenerate, args.char_key, script_logger
    )
    new_entries = _run_parallel_tasks(env_data, args.force_regenerate, args.char_key, script_logger)
    _finalize_generation(
        env_data["manifest"], new_entries, out_dir, args.language, args.char_key, script_logger
    )

if __name__ == '__main__':
    main()
