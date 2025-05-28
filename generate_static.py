# generate_static.py
import os
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging
from multiprocessing import Pool, cpu_count, current_process
from functools import partial
import argparse # Para parsear argumentos de línea de comando
import json # Para el manifest
import hashlib # Para las firmas
import time # Para timestamps

# --- Configuración del Logger Básico para el Script ---
script_logger = logging.getLogger('generate_static_script')
script_logger.setLevel(logging.INFO) 
script_handler = logging.StreamHandler() 
script_formatter = logging.Formatter('%(asctime)s - %(name)s:%(processName)s - %(levelname)s - %(message)s')
script_handler.setFormatter(script_formatter)
if not script_logger.handlers:
    script_logger.addHandler(script_handler)

# --- Variables Globales para Workers (se establecerán en worker_init) ---
worker_app_instance = None
worker_logger = None 
slugify_to_use_global = None # Se establecerá en worker_init

# --- MANIFEST CONSTANTS ---
MANIFEST_DIR = Path(".cache")
MANIFEST_FILE = MANIFEST_DIR / "generation_manifest.json"

# --- FUNCIONES DE UTILIDAD (slugify, get_translated_url_segment) ---
def slugify_ascii_local(text):
    if text is None: return ""
    text = str(text); text = unidecode(text); text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text); text = re.sub(r'\s+', '-', text)
    text = re.sub(r'--+', '-', text); text = text.strip('-')
    return text if text else "na"

try:
    # Este import se intentará en worker_init para el slugify_to_use_global
    _temp_slugify = slugify_ascii_local 
except ImportError:
    _temp_slugify = slugify_ascii_local
slugify_to_use_global = _temp_slugify # Placeholder, se reasigna en worker_init

def get_translated_url_segment_for_generator(segment_key, lang_code, url_segment_translations, default_app_lang, default_segment_value=None, logger_to_use=None):
    log = logger_to_use if logger_to_use else script_logger 
    if not url_segment_translations or not isinstance(url_segment_translations, dict):
        return default_segment_value if default_segment_value is not None else segment_key
    segments_for_key = url_segment_translations.get(segment_key, {})
    if not isinstance(segments_for_key, dict):
        return default_segment_value if default_segment_value is not None else segment_key
    translated_segment = segments_for_key.get(lang_code)
    if translated_segment: return translated_segment
    if lang_code != default_app_lang:
        translated_segment_default_lang = segments_for_key.get(default_app_lang)
        if translated_segment_default_lang: return translated_segment_default_lang
    if default_segment_value is not None: return default_segment_value
    return segment_key

OUTPUT_DIR = "_site"
ALPHABET = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_CHARS_SITEMAP_KEY = "0"


# --- MANIFEST HELPER FUNCTIONS ---
def load_manifest():
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            script_logger.warning(f"Error al decodificar {MANIFEST_FILE}. Se creará uno nuevo.")
            return {}
    script_logger.info(f"Archivo manifest {MANIFEST_FILE} no encontrado. Se creará uno nuevo.")
    return {}

def save_manifest(manifest_data):
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest_data, f, indent=2)
    script_logger.info(f"Manifest de generación guardado en {MANIFEST_FILE} con {len(manifest_data)} entradas.")

def get_book_signature_fields(book_data):
    """Define qué campos del libro contribuyen a su firma."""
    # IMPORTANTE: AJUSTA ESTOS CAMPOS SEGÚN TU ESTRUCTURA DE DATOS
    fields_for_signature = {
        "isbn10": book_data.get("isbn10"),
        "isbn13": book_data.get("isbn13"),
        "asin": book_data.get("asin"),
        "title_slug": book_data.get("title_slug"), # Usar slugs si son la base de la URL
        "author_slug": book_data.get("author_slug"),
        "description": book_data.get("description_short") or book_data.get("description"), # Ejemplo
        "cover_image_url": book_data.get("image_url_l") or book_data.get("image_url_m") or book_data.get("image_url_s"),
        "publication_date": book_data.get("publication_date"),
        "publisher": book_data.get("publisher_name"),
        "language_code": book_data.get("language_code"), # Si el mismo libro puede tener diferentes datos por idioma en la fuente
        # "last_modified": book_data.get("last_modified_timestamp") # Si tienes este campo
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
        # No loguear aquí INFO en cada llamada si es muy verboso, dejarlo a la función de tarea
        # logger_to_use.info(f"Intentando generar: {url_path} -> {file_path_obj}") 
        pass
    except BlockingIOError: # Esto es específico de print, el logger maneja la E/S de forma diferente
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
            # Generalmente no guardamos el contenido de una redirección, el cliente debería seguirla
            # Pero si tu `generate_static` espera esto, puedes descomentar:
            # if response.data:
            #      file_path_obj.parent.mkdir(parents=True, exist_ok=True)
            #      with open(file_path_obj, 'wb') as f: f.write(response.data)
            #      logger_to_use.info(f"Datos de redirección para {url_path} guardados.")
            # else:
            #     logger_to_use.warning(f"{url_path} redirigió sin datos.")
        elif response.status_code == 404:
            logger_to_use.warning(f"404: {url_path} no encontrado. No se guardó el archivo.")
        else:
            logger_to_use.error(f"HTTP {response.status_code} para {url_path}. No se guardó el archivo.")
    except Exception as e:
        logger_to_use.exception(f"EXCEPCIÓN generando y guardando {url_path}: {e}")

# --- FUNCIONES WORKER PARA MULTIPROCESSING ---
def worker_init():
    global worker_app_instance, worker_logger, slugify_to_use_global
    from app import create_app # Importar aquí, dentro del worker
    
    # Usar el nombre del proceso para el logger si se necesita distinguir
    proc_name = current_process().name
    # script_logger.info(f"Worker {proc_name}: Inicializando...") # El script_logger ya tiene processName

    worker_app_instance = create_app()
    
    # Configurar un logger específico para este worker o usar el global del script
    # Si se usa el global, el formatter ya incluye %(processName)s
    worker_logger = script_logger 
    # worker_logger = logging.getLogger(f'worker_{proc_name}') # Alternativa
    # if not worker_logger.handlers:
    #     handler = logging.StreamHandler()
    #     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    #     handler.setFormatter(formatter)
    #     worker_logger.addHandler(handler)
    #     worker_logger.setLevel(logging.INFO)

    try:
        from app.utils.helpers import slugify_ascii as slugify_ascii_app
        slugify_to_use_global = slugify_ascii_app
        worker_logger.info(f"Worker {proc_name}: usando slugify_ascii de app.utils.helpers.")
    except ImportError:
        slugify_to_use_global = slugify_ascii_local
        worker_logger.warning(f"Worker {proc_name}: usando slugify_ascii local.")
    # worker_logger.info(f"Worker {proc_name}: Inicializado con instancia de app.")


def generate_book_detail_pages_task(book_data_item, config_params_manifest_tuple):
    global worker_app_instance, worker_logger, slugify_to_use_global
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
                    'book', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'book', logger_to_use=log_target
                )
                flask_url = f"/{lang}/{book_segment_translated}/{author_s}/{title_s}/{identifier}/"
                output_path_obj = Path(OUTPUT_DIR_BASE) / lang / book_segment_translated / author_s / title_s / identifier / "index.html"
                output_path_str = str(output_path_obj)
                
                if FORCE_REGENERATE_ALL or should_regenerate_page(output_path_str, current_book_content_signature, manifest_data_global, log_target):
                    _save_page_local(client, flask_url, output_path_obj, log_target)
                    generated_pages_info.append({
                        "path": output_path_str,
                        "signature": current_book_content_signature,
                        "timestamp": time.time()
                    })
    return generated_pages_info

def generate_author_pages_task(author_slug_original, config_params_manifest_tuple):
    global worker_app_instance, worker_logger, slugify_to_use_global
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
    current_author_page_signature = calculate_signature({"book_ids_author_page": author_page_source_identifiers, "author_slug": author_slug_original})

    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                author_segment_translated = get_translated_url_segment_for_generator('author', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'author', logger_to_use=log_target)
                flask_url = f"/{lang}/{author_segment_translated}/{author_s}/"
                output_path_obj = Path(OUTPUT_DIR_BASE) / lang / author_segment_translated / author_s / "index.html"
                output_path_str = str(output_path_obj)

                if FORCE_REGENERATE_ALL or should_regenerate_page(output_path_str, current_author_page_signature, manifest_data_global, log_target):
                    _save_page_local(client, flask_url, output_path_obj, log_target)
                    generated_pages_info.append({
                        "path": output_path_str,
                        "signature": current_author_page_signature,
                        "timestamp": time.time()
                    })
    return generated_pages_info

def generate_versions_pages_task(author_base_title_slugs_original, config_params_manifest_tuple):
    global worker_app_instance, worker_logger, slugify_to_use_global
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

    version_books_data = [b for b in ALL_BOOKS_DATA if b.get('author_slug') == author_s_orig and b.get('base_title_slug') == base_title_s_orig]
    if not version_books_data:
        return generated_pages_info
    
    version_page_source_identifiers = sorted([
        b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in version_books_data
    ])
    current_version_page_signature = calculate_signature({"book_ids_version_page": version_page_source_identifiers, "author_slug": author_s_orig, "base_title_slug": base_title_s_orig})

    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                versions_segment_translated = get_translated_url_segment_for_generator('versions', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'versions', logger_to_use=log_target)
                flask_url = f"/{lang}/{versions_segment_translated}/{author_s}/{base_title_s}/"
                output_path_obj = Path(OUTPUT_DIR_BASE) / lang / versions_segment_translated / author_s / base_title_s / "index.html"
                output_path_str = str(output_path_obj)

                if FORCE_REGENERATE_ALL or should_regenerate_page(output_path_str, current_version_page_signature, manifest_data_global, log_target):
                    _save_page_local(client, flask_url, output_path_obj, log_target)
                    generated_pages_info.append({
                        "path": output_path_str,
                        "signature": current_version_page_signature,
                        "timestamp": time.time()
                    })
    return generated_pages_info

# --- FUNCIÓN MAIN ---
def main():
    parser = argparse.ArgumentParser(description="Generador de sitio estático con cache y paralelización.")
    parser.add_argument(
        "--language", type=str, default=None,
        help="Generar solo para un idioma específico (ej. 'es'). Si no se especifica, se generan todos los idiomas configurados."
    )
    parser.add_argument(
        "--force-regenerate", action="store_true",
        help="Forzar la regeneración de todas las páginas cacheadas (libros, autores, versiones), ignorando el manifest para ellas."
    )
    args = parser.parse_args()

    main_process_logger = script_logger 
    main_process_logger.info(f"Iniciando script generate_static.py con argumentos: {args}")

    if args.force_regenerate:
        main_process_logger.info("FORZANDO REGENERACIÓN para páginas cacheadas: El manifest será ignorado para las decisiones de 'should_regenerate'.")

    manifest_data = load_manifest()
    initial_manifest_size = len(manifest_data)
    main_process_logger.info(f"Manifest cargado con {initial_manifest_size} entradas desde {MANIFEST_FILE}.")

    from app import create_app
    app_instance_main = create_app()
    main_process_logger.info("Instancia de Flask creada en proceso principal para configuraciones.")
    
    ALL_CONFIGURED_LANGUAGES = app_instance_main.config.get('SUPPORTED_LANGUAGES', ['en'])
    if args.language:
        if args.language in ALL_CONFIGURED_LANGUAGES:
            LANGUAGES_TO_PROCESS = [args.language]
            main_process_logger.info(f"Procesando solo para el idioma especificado: {args.language}")
        else:
            main_process_logger.error(f"Idioma '{args.language}' no está en SUPPORTED_LANGUAGES. Saliendo.")
            return
    else:
        LANGUAGES_TO_PROCESS = ALL_CONFIGURED_LANGUAGES
        main_process_logger.info(f"Procesando para todos los idiomas configurados: {LANGUAGES_TO_PROCESS}")

    DEFAULT_LANGUAGE = app_instance_main.config.get('DEFAULT_LANGUAGE', 'en')
    URL_SEGMENT_TRANSLATIONS_CONFIG = app_instance_main.config.get('URL_SEGMENT_TRANSLATIONS', {})
    
    books_for_generation_full_list = app_instance_main.books_data 
    if not books_for_generation_full_list:
        main_process_logger.critical("No hay datos de libros (app_instance.books_data está vacío o no es una lista). Saliendo.")
        return

    main_process_logger.info(f"Idiomas a procesar: {LANGUAGES_TO_PROCESS}. {len(books_for_generation_full_list)} libros en total en los datos fuente.")

    # --- Preparación de Directorios y Estáticos ---
    perform_full_cleanup = (not args.language) or args.force_regenerate # Limpiar todo si es general o forzado

    if perform_full_cleanup and not args.language : # Solo limpiar todo si es una ejecución completa (sin --language)
        if Path(OUTPUT_DIR).exists():
            main_process_logger.info(f"Eliminando {OUTPUT_DIR} (generación completa o forzada sin idioma específico)")
            shutil.rmtree(OUTPUT_DIR)
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        main_process_logger.info(f"{OUTPUT_DIR} creado/limpiado.")
        
        static_folder_path = Path(app_instance_main.static_folder)
        if static_folder_path.exists() and static_folder_path.is_dir():
            static_output_dir_name = Path(app_instance_main.static_url_path.strip('/'))
            static_output_dir = Path(OUTPUT_DIR) / static_output_dir_name
            if static_output_dir.exists(): shutil.rmtree(static_output_dir)
            shutil.copytree(static_folder_path, static_output_dir)
            main_process_logger.info(f"Carpeta estática '{static_folder_path.name}' copiada a '{static_output_dir}'")

        public_folder_path = Path("public")
        if public_folder_path.exists() and public_folder_path.is_dir():
            public_output_dir = Path(OUTPUT_DIR)
            copied_public_files = 0
            for item in public_folder_path.iterdir():
                if item.is_file():
                    try: shutil.copy2(item, public_output_dir / item.name); copied_public_files +=1
                    except Exception as e: main_process_logger.error(f"Error copiando '{item.name}': {e}")
            main_process_logger.info(f"{copied_public_files} archivos de 'public/' copiados a '{public_output_dir}'.")
    else: 
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        if args.language: # Si es por idioma, asegurar que el subdirectorio del idioma exista
            (Path(OUTPUT_DIR) / args.language).mkdir(parents=True, exist_ok=True)
        main_process_logger.info(f"Asegurando que {OUTPUT_DIR} (y subdirectorios de idioma si aplica) existen.")


    # --- Generación de Páginas No Paralelizadas (índices, sitemaps base) ---
    # Estas se regeneran siempre por simplicidad.
    main_process_logger.info("Generando páginas de índice de idioma y sitemaps por letra/core (proceso principal)...")
    with app_instance_main.app_context():
        with app_instance_main.test_client() as client_main:
            # Generar página raíz solo si no es ejecución por idioma O si se fuerza
            if not args.language or args.force_regenerate:
                _save_page_local(client_main, "/", Path(OUTPUT_DIR) / "index.html", main_process_logger)
                if app_instance_main.url_map.is_endpoint_expecting('main.test_page'):
                    _save_page_local(client_main, "/test/", Path(OUTPUT_DIR) / "test_sitemap" / "index.html", main_process_logger)
            
            for lang in LANGUAGES_TO_PROCESS: # Iterar sobre los idiomas a procesar
                _save_page_local(client_main, f"/{lang}/", Path(OUTPUT_DIR) / lang / "index.html", main_process_logger)
                
                sitemap_url_core = f"/sitemap_{lang}_core.xml"
                sitemap_path_core = Path(OUTPUT_DIR) / f"sitemap_{lang}_core.xml"
                _save_page_local(client_main, sitemap_url_core, sitemap_path_core, main_process_logger)

                letters_and_special = list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]
                for char_key in letters_and_special:
                    sitemap_url_char = f"/sitemap_{lang}_{char_key}.xml"
                    sitemap_path_char = Path(OUTPUT_DIR) / f"sitemap_{lang}_{char_key}.xml"
                    _save_page_local(client_main, sitemap_url_char, sitemap_path_char, main_process_logger)

    # --- Preparación para Paralelización ---
    num_processes = max(1, cpu_count() - 1 if cpu_count() > 1 else 1)
    main_process_logger.info(f"Usando {num_processes} procesos para la generación paralela de páginas cacheadas.")

    config_params_for_tasks = {
        'LANGUAGES': LANGUAGES_TO_PROCESS,
        'DEFAULT_LANGUAGE': DEFAULT_LANGUAGE,
        'URL_SEGMENT_TRANSLATIONS_CONFIG': URL_SEGMENT_TRANSLATIONS_CONFIG,
        'OUTPUT_DIR': OUTPUT_DIR,
        'FORCE_REGENERATE_ALL': args.force_regenerate,
        'ALL_BOOKS_DATA': books_for_generation_full_list 
    }
    
    task_args_tuple = (config_params_for_tasks, manifest_data.copy()) # Pasar copia del manifest
    new_manifest_entries_from_workers = []

    with Pool(processes=num_processes, initializer=worker_init) as pool:
        
        main_process_logger.info("Iniciando generación paralela de páginas de detalle de libros...")
        book_detail_task_with_args = partial(generate_book_detail_pages_task, config_params_manifest_tuple=task_args_tuple)
        # Filtrar libros si es necesario para chunks (no implementado aquí, pero se podría añadir)
        results_books_list_of_lists = pool.map(book_detail_task_with_args, books_for_generation_full_list)
        for res_list in results_books_list_of_lists: new_manifest_entries_from_workers.extend(res_list)
        main_process_logger.info(f"Proceso de detalle de libros completado. {len(new_manifest_entries_from_workers)} páginas cacheadas (re)generadas o marcadas.")

        current_generated_count = len(new_manifest_entries_from_workers)
        main_process_logger.info("Iniciando generación paralela de páginas de autor...")
        unique_author_slugs_orig = {b.get('author_slug') for b in books_for_generation_full_list if b.get('author_slug')}
        author_task_with_args = partial(generate_author_pages_task, config_params_manifest_tuple=task_args_tuple)
        results_authors_list_of_lists = pool.map(author_task_with_args, list(unique_author_slugs_orig))
        for res_list in results_authors_list_of_lists: new_manifest_entries_from_workers.extend(res_list)
        main_process_logger.info(f"Proceso de páginas de autor completado. {len(new_manifest_entries_from_workers) - current_generated_count} páginas de autor cacheadas (re)generadas o marcadas.")

        current_generated_count = len(new_manifest_entries_from_workers)
        main_process_logger.info("Iniciando generación paralela de páginas de versiones...")
        unique_book_bases_slugs = {(b.get('author_slug'), b.get('base_title_slug')) for b in books_for_generation_full_list if b.get('author_slug') and b.get('base_title_slug')}
        versions_task_with_args = partial(generate_versions_pages_task, config_params_manifest_tuple=task_args_tuple)
        results_versions_list_of_lists = pool.map(versions_task_with_args, list(unique_book_bases_slugs))
        for res_list in results_versions_list_of_lists: new_manifest_entries_from_workers.extend(res_list)
        main_process_logger.info(f"Proceso de páginas de versiones completado. {len(new_manifest_entries_from_workers) - current_generated_count} páginas de versiones cacheadas (re)generadas o marcadas.")


    # --- Actualización del Manifest y Sitemap Index Final ---
    # Solo si NO se está ejecutando para un idioma específico (es decir, es una ejecución "global" o "finalizadora")
    # O si se forzó la regeneración (en cuyo caso el manifest se actualiza con todo lo nuevo)
    if not args.language or args.force_regenerate:
        if new_manifest_entries_from_workers:
            main_process_logger.info(f"Actualizando manifest global con {len(new_manifest_entries_from_workers)} entradas de workers...")
            for entry in new_manifest_entries_from_workers:
                manifest_data[entry['path']] = { # Esto sobreescribirá si ya existe, lo cual es correcto
                    "signature": entry['signature'],
                    "timestamp": entry['timestamp']
                }
        else:
            main_process_logger.info("No se (re)generaron páginas cacheadas por los workers en esta ejecución.")
        
        # Aquí es donde también regenerarías el sitemap.xml principal,
        # ya que ahora tienes la información más actualizada (o todo regenerado).
        main_process_logger.info("Generando sitemap_index.xml principal...")
        with app_instance_main.app_context():
            with app_instance_main.test_client() as client_main:
                _save_page_local(client_main, "/sitemap.xml", Path(OUTPUT_DIR) / "sitemap.xml", main_process_logger)
        
        save_manifest(manifest_data) # Guardar el manifest global actualizado
    else:
        main_process_logger.info(f"Ejecución para idioma '{args.language}'. El manifest global no se guardó desde este script. {len(new_manifest_entries_from_workers)} páginas del idioma (re)generadas.")


    main_process_logger.info(f"Sitio estático (o parte para el idioma '{args.language if args.language else 'todos'}') generado en: {OUTPUT_DIR}")

if __name__ == '__main__':
    # from multiprocessing import freeze_support
    # freeze_support() # Descomentar si es necesario para Windows/macOS empaquetado
    main()
