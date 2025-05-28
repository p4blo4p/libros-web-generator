# generate_static.py
import os
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging
from multiprocessing import Pool, cpu_count, current_process
from functools import partial
import argparse
import json # NEW: Para el manifest
import hashlib # NEW: Para las firmas
import time # NEW: Para timestamps

# ... (configuración del logger como antes) ...
script_logger = logging.getLogger('generate_static_script')
script_logger.setLevel(logging.INFO) 
script_handler = logging.StreamHandler() 
script_formatter = logging.Formatter('%(asctime)s - %(name)s:%(processName)s - %(levelname)s - %(message)s')
script_handler.setFormatter(script_formatter)
if not script_logger.handlers:
    script_logger.addHandler(script_handler)

worker_app_instance = None
worker_logger = None 
slugify_to_use_global = None # Se establecerá en worker_init

# --- MANIFEST CONSTANTS ---
MANIFEST_DIR = Path(".cache") # NEW
MANIFEST_FILE = MANIFEST_DIR / "generation_manifest.json" # NEW

# --- FUNCIONES DE UTILIDAD (slugify, get_translated_url_segment - sin cambios) ---
def slugify_ascii_local(text):
    if text is None: return ""
    text = str(text); text = unidecode(text); text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text); text = re.sub(r'\s+', '-', text)
    text = re.sub(r'--+', '-', text); text = text.strip('-')
    return text if text else "na"

try:
    _temp_slugify = slugify_ascii_local
except ImportError:
    _temp_slugify = slugify_ascii_local
slugify_to_use_global = _temp_slugify

def get_translated_url_segment_for_generator(segment_key, lang_code, url_segment_translations, default_app_lang, default_segment_value=None, logger_to_use=None):
    # ... (sin cambios) ...
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


# --- MANIFEST HELPER FUNCTIONS --- NEW ---
def load_manifest():
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            script_logger.warning(f"Error al decodificar {MANIFEST_FILE}. Se creará uno nuevo.")
            return {}
    return {}

def save_manifest(manifest_data):
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest_data, f, indent=2)
    script_logger.info(f"Manifest de generación guardado en {MANIFEST_FILE}")

def get_book_signature_fields(book_data):
    """Define qué campos del libro contribuyen a su firma."""
    # IMPORTANTE: Ajusta estos campos según tu estructura de datos
    # y lo que consideres que debe disparar una regeneración.
    # El orden de las claves importa para la consistencia del JSON antes del hash.
    # Por eso usamos un diccionario ordenado (o simplemente ordenamos las claves).
    fields_for_signature = {
        "isbn10": book_data.get("isbn10"),
        "isbn13": book_data.get("isbn13"),
        "asin": book_data.get("asin"),
        "title": book_data.get("title"), # O title_slug si es más estable
        "author": book_data.get("author"), # O author_slug
        "description": book_data.get("description"),
        "cover_image_url": book_data.get("cover_image_url"),
        "publication_date": book_data.get("publication_date"),
        "publisher": book_data.get("publisher"),
        # Añade "last_modified": book_data.get("last_modified_timestamp") si lo tienes
    }
    # Ordenar las claves para una representación JSON consistente
    return dict(sorted(fields_for_signature.items()))


def calculate_signature(data_dict_for_signature):
    """Calcula un hash MD5 de un diccionario (después de serializarlo a JSON)."""
    # Serializar a JSON con claves ordenadas para asegurar consistencia
    json_string = json.dumps(data_dict_for_signature, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(json_string.encode('utf-8')).hexdigest()

def should_regenerate_page(output_path_str, current_signature, manifest_data, logger_to_use):
    """Decide si una página necesita ser regenerada."""
    page_manifest_entry = manifest_data.get(output_path_str)
    if not page_manifest_entry:
        logger_to_use.debug(f"REGENERAR (nuevo): {output_path_str}")
        return True  # No existe en el manifest, generar
    if page_manifest_entry.get('signature') != current_signature:
        logger_to_use.debug(f"REGENERAR (firma cambiada): {output_path_str}")
        return True  # La firma cambió, regenerar
    if not Path(output_path_str).exists():
        logger_to_use.debug(f"REGENERAR (archivo no existe): {output_path_str}")
        return True # El archivo fue borrado manualmente
    # Podrías añadir más chequeos aquí (ej. timestamp de plantillas)
    logger_to_use.debug(f"SALTAR (sin cambios): {output_path_str}")
    return False

# --- FUNCIÓN _save_page_local (sin cambios en su lógica interna, solo en cómo se llama) ---
def _save_page_local(client_local, url_path, file_path_obj, logger_to_use):
    # ... (sin cambios respecto a la versión anterior con multiprocessing) ...
    try:
        logger_to_use.info(f"Generando: {url_path} -> {file_path_obj}")
    except BlockingIOError:
        logger_to_use.warning(f"Intento de E/S bloqueado para: {url_path}")
    
    try:
        response = client_local.get(url_path)
        if response.status_code == 200:
            if response.data: 
                file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path_obj, 'wb') as f:
                    f.write(response.data)
            else:
                logger_to_use.info(f"URL {url_path} devolvió 200 pero sin datos. No se guardó archivo.")
        elif response.status_code in [301, 302, 307, 308]:
            logger_to_use.warning(f"{url_path} devolvió {response.status_code} (redirección).")
            if response.data:
                 file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                 with open(file_path_obj, 'wb') as f: f.write(response.data)
                 logger_to_use.info(f"Datos de redirección para {url_path} guardados.")
            else:
                logger_to_use.warning(f"{url_path} redirigió sin datos.")
        elif response.status_code == 404:
            logger_to_use.warning(f"404: {url_path} no encontrado. No se guardó el archivo.")
        else:
            logger_to_use.error(f"HTTP {response.status_code} para {url_path}. No se guardó el archivo.")
    except Exception as e:
        logger_to_use.exception(f"EXCEPCIÓN generando y guardando {url_path}: {e}")


# --- FUNCIONES WORKER PARA MULTIPROCESSING ---
def worker_init():
    # ... (sin cambios respecto a la versión anterior con multiprocessing) ...
    global worker_app_instance, worker_logger, slugify_to_use_global
    from app import create_app
    script_logger.info(f"Worker {current_process().name}: Inicializando...")
    worker_app_instance = create_app()
    worker_logger = logging.getLogger(f'worker_{current_process().name}')
    if not worker_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        worker_logger.addHandler(handler)
        worker_logger.setLevel(logging.INFO) 
    try:
        from app.utils.helpers import slugify_ascii as slugify_ascii_app
        slugify_to_use_global = slugify_ascii_app
        worker_logger.info("Worker usando slugify_ascii de app.utils.helpers.")
    except ImportError:
        slugify_to_use_global = slugify_ascii_local
        worker_logger.warning("Worker usando slugify_ascii local.")
    script_logger.info(f"Worker {current_process().name}: Inicializado con instancia de app.")


# MODIFIED: Las funciones de tarea ahora devuelven una lista de entradas para el manifest
def generate_book_detail_pages_task(book_data_item, config_params_manifest_tuple):
    """Tarea para generar páginas de detalle de un libro en todos los idiomas."""
    global worker_app_instance, worker_logger, slugify_to_use_global
    
    config_params, manifest_data_global = config_params_manifest_tuple # NEW: Recibir manifest
    
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE = config_params['OUTPUT_DIR']
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False) # NEW

    log_target = worker_logger if worker_logger else script_logger
    generated_pages_info = [] # NEW: Para almacenar info de páginas generadas

    author_s_original = book_data_item.get('author_slug')
    title_s_original = book_data_item.get('title_slug')
    identifier = book_data_item.get('isbn10') or book_data_item.get('isbn13') or book_data_item.get('asin')
    
    if not (identifier and author_s_original and title_s_original):
        log_target.debug(f"Saltando libro (datos incompletos): ID {identifier}")
        return generated_pages_info

    author_s = slugify_to_use_global(author_s_original)
    title_s = slugify_to_use_global(title_s_original)

    # NEW: Calcular firma del libro una vez
    book_signature_fields = get_book_signature_fields(book_data_item)
    current_book_content_signature = calculate_signature(book_signature_fields)

    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                book_segment_translated = get_translated_url_segment_for_generator(
                    'book', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'book', logger_to_use=log_target
                )
                flask_url = f"/{lang}/{book_segment_translated}/{author_s}/{title_s}/{identifier}/"
                output_path_str = str(Path(OUTPUT_DIR_BASE) / lang / book_segment_translated / author_s / title_s / identifier / "index.html")
                
                # NEW: Chequeo del manifest
                if FORCE_REGENERATE_ALL or should_regenerate_page(output_path_str, current_book_content_signature, manifest_data_global, log_target):
                    _save_page_local(client, flask_url, Path(output_path_str), log_target)
                    generated_pages_info.append({
                        "path": output_path_str,
                        "signature": current_book_content_signature, # Firma del contenido del libro
                        "timestamp": time.time()
                    })
                # else: la función should_regenerate ya loguea el SALTADO
    return generated_pages_info


def generate_author_pages_task(author_slug_original, config_params_manifest_tuple):
    global worker_app_instance, worker_logger, slugify_to_use_global
    config_params, manifest_data_global = config_params_manifest_tuple
    # ... (extraer config_params como antes) ...
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE = config_params['OUTPUT_DIR']
    FORCE_REGENERATE_ALL = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS_DATA = config_params['ALL_BOOKS_DATA'] # Necesitamos todos los libros para la firma del autor

    log_target = worker_logger if worker_logger else script_logger
    generated_pages_info = []
    author_s = slugify_to_use_global(author_slug_original)

    # NEW: Calcular firma para la página de autor.
    # Esto es más complejo. Podría ser un hash de las firmas de todos sus libros,
    # o un hash de la lista de ISBNs/ASINs de sus libros.
    # Por ahora, una simplificación: si algún libro del autor cambió, regeneramos.
    # O, para ser más precisos, la firma de la página de autor depende de los datos de todos sus libros.
    author_books_data = [b for b in ALL_BOOKS_DATA if b.get('author_slug') == author_slug_original]
    if not author_books_data:
        return generated_pages_info

    # Crear una firma combinada para los libros del autor
    # Podríamos hacer un hash de una lista de firmas de libros, o un hash de los datos relevantes.
    # Para ser más robusto, si cualquier libro del autor cambia, la firma de la página del autor debería cambiar.
    # Una forma es hashear una lista ordenada de los identificadores de los libros del autor.
    author_page_source_identifiers = sorted([
        b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in author_books_data
    ])
    current_author_page_signature = calculate_signature({"book_ids": author_page_source_identifiers})


    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                author_segment_translated = get_translated_url_segment_for_generator('author', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'author', logger_to_use=log_target)
                flask_url = f"/{lang}/{author_segment_translated}/{author_s}/"
                output_path_str = str(Path(OUTPUT_DIR_BASE) / lang / author_segment_translated / author_s / "index.html")

                if FORCE_REGENERATE_ALL or should_regenerate_page(output_path_str, current_author_page_signature, manifest_data_global, log_target):
                    _save_page_local(client, flask_url, Path(output_path_str), log_target)
                    generated_pages_info.append({
                        "path": output_path_str,
                        "signature": current_author_page_signature,
                        "timestamp": time.time()
                    })
    return generated_pages_info


def generate_versions_pages_task(author_base_title_slugs_original, config_params_manifest_tuple):
    global worker_app_instance, worker_logger, slugify_to_use_global
    config_params, manifest_data_global = config_params_manifest_tuple
    # ... (extraer config_params) ...
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

    # NEW: Calcular firma para la página de versiones
    version_books_data = [b for b in ALL_BOOKS_DATA if b.get('author_slug') == author_s_orig and b.get('base_title_slug') == base_title_s_orig]
    if not version_books_data:
        return generated_pages_info
    
    version_page_source_identifiers = sorted([
        b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in version_books_data
    ])
    current_version_page_signature = calculate_signature({"book_ids_versions": version_page_source_identifiers})

    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                versions_segment_translated = get_translated_url_segment_for_generator('versions', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'versions', logger_to_use=log_target)
                flask_url = f"/{lang}/{versions_segment_translated}/{author_s}/{base_title_s}/"
                output_path_str = str(Path(OUTPUT_DIR_BASE) / lang / versions_segment_translated / author_s / base_title_s / "index.html")

                if FORCE_REGENERATE_ALL or should_regenerate_page(output_path_str, current_version_page_signature, manifest_data_global, log_target):
                    _save_page_local(client, flask_url, Path(output_path_str), log_target)
                    generated_pages_info.append({
                        "path": output_path_str,
                        "signature": current_version_page_signature,
                        "timestamp": time.time()
                    })
    return generated_pages_info


# --- FUNCIÓN MAIN (Modificada para manifest y argumentos) ---
def main():
    parser = argparse.ArgumentParser(description="Generador de sitio estático con cache.")
    parser.add_argument(
        "--language", type=str, default=None,
        help="Generar solo para un idioma específico (ej. 'es')."
    )
    parser.add_argument(
        "--force-regenerate", action="store_true",
        help="Forzar la regeneración de todas las páginas, ignorando el manifest."
    )
    args = parser.parse_args()

    main_process_logger = script_logger
    main_process_logger.info(f"Iniciando script con argumentos: {args}")

    if args.force_regenerate:
        main_process_logger.info("FORZANDO REGENERACIÓN: El manifest será ignorado para las decisiones de 'should_regenerate'.")

    # NEW: Cargar manifest
    manifest_data = load_manifest()
    initial_manifest_size = len(manifest_data)
    main_process_logger.info(f"Manifest cargado con {initial_manifest_size} entradas.")

    from app import create_app
    app_instance_main = create_app()
    main_process_logger.info("Instancia de Flask creada en proceso principal.")
    
    ALL_CONFIGURED_LANGUAGES = app_instance_main.config.get('SUPPORTED_LANGUAGES', ['en'])
    LANGUAGES_TO_PROCESS = [args.language] if args.language and args.language in ALL_CONFIGURED_LANGUAGES else ALL_CONFIGURED_LANGUAGES
    # ... (resto de la carga de config y books_for_generation como antes) ...
    DEFAULT_LANGUAGE = app_instance_main.config.get('DEFAULT_LANGUAGE', 'en')
    URL_SEGMENT_TRANSLATIONS_CONFIG = app_instance_main.config.get('URL_SEGMENT_TRANSLATIONS', {})
    books_for_generation_full_list = app_instance_main.books_data # Guardar referencia a la lista completa
    if not books_for_generation_full_list:
        main_process_logger.critical("No hay datos de libros. Saliendo.")
        return
    main_process_logger.info(f"Idiomas a procesar: {LANGUAGES_TO_PROCESS}. {len(books_for_generation_full_list)} libros en total.")


    # --- Preparación de Directorios y Estáticos ---
    # MODIFIED: La limpieza de OUTPUT_DIR solo si no es por idioma específico O si se fuerza regeneración completa.
    # Si es por idioma, asumimos que la estructura base ya existe o se crea.
    # Si es --force-regenerate, siempre se limpia.
    perform_full_cleanup = not args.language or args.force_regenerate

    if perform_full_cleanup:
        if Path(OUTPUT_DIR).exists():
            main_process_logger.info(f"Eliminando {OUTPUT_DIR} (generación completa o forzada)")
            shutil.rmtree(OUTPUT_DIR)
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        main_process_logger.info(f"{OUTPUT_DIR} creado/limpiado.")
        # Copiar estáticos y public solo en limpieza completa
        # ... (código de copia de static y public como antes) ...
        static_folder_path = Path(app_instance_main.static_folder)
        if static_folder_path.exists() and static_folder_path.is_dir():
            static_output_dir_name = Path(app_instance_main.static_url_path.strip('/'))
            static_output_dir = Path(OUTPUT_DIR) / static_output_dir_name
            if static_output_dir.exists(): shutil.rmtree(static_output_dir)
            shutil.copytree(static_folder_path, static_output_dir)
            main_process_logger.info(f"'{static_folder_path.name}' copiado a '{static_output_dir}'")

        public_folder_path = Path("public")
        if public_folder_path.exists() and public_folder_path.is_dir():
            public_output_dir = Path(OUTPUT_DIR)
            copied_public_files = 0
            for item in public_folder_path.iterdir():
                if item.is_file():
                    try: shutil.copy2(item, public_output_dir / item.name); copied_public_files +=1
                    except Exception as e: main_process_logger.error(f"Error copiando '{item.name}': {e}")
            main_process_logger.info(f"{copied_public_files} archivos de 'public/' copiados.")

    else: # Generación parcial por idioma, asegurar que exista el directorio base y de idioma
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        for lang_code in LANGUAGES_TO_PROCESS:
             Path(OUTPUT_DIR) / lang_code.mkdir(parents=True, exist_ok=True)
        main_process_logger.info(f"Asegurando que los directorios de idioma en {OUTPUT_DIR} existen para la generación parcial.")


    # --- Generación de Páginas No Paralelizadas (índices, sitemaps base) ---
    # MODIFIED: Estas se regeneran siempre por simplicidad o si args.force_regenerate
    # El cache se enfoca en las páginas de detalle, autor, versiones.
    main_process_logger.info("Generando páginas principales y sitemaps base (siempre o forzado)...")
    with app_instance_main.app_context():
        with app_instance_main.test_client() as client_main:
            if not args.language or args.force_regenerate: # Generar raíz solo si no es por idioma o forzado
                _save_page_local(client_main, "/", Path(OUTPUT_DIR) / "index.html", main_process_logger)
                if app_instance_main.url_map.is_endpoint_expecting('main.test_page'):
                    _save_page_local(client_main, "/test/", Path(OUTPUT_DIR) / "test_sitemap" / "index.html", main_process_logger)
            
            for lang in LANGUAGES_TO_PROCESS:
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
    num_processes = max(1, cpu_count() - 1)
    main_process_logger.info(f"Usando {num_processes} procesos para la generación paralela.")

    config_params_for_tasks = {
        'LANGUAGES': LANGUAGES_TO_PROCESS,
        'DEFAULT_LANGUAGE': DEFAULT_LANGUAGE,
        'URL_SEGMENT_TRANSLATIONS_CONFIG': URL_SEGMENT_TRANSLATIONS_CONFIG,
        'OUTPUT_DIR': OUTPUT_DIR,
        'FORCE_REGENERATE_ALL': args.force_regenerate, # NEW
        'ALL_BOOKS_DATA': books_for_generation_full_list # NEW: para firmas de autor/versiones
    }
    
    # NEW: Crear tupla para pasar config y manifest
    # El manifest_data se pasa como copia para que cada worker tenga su "vista" inicial,
    # luego el proceso principal actualiza el manifest global con los resultados.
    # Esto es más seguro que intentar que los workers modifiquen un manifest compartido directamente.
    task_args_tuple = (config_params_for_tasks, manifest_data.copy())

    new_manifest_entries = [] # NEW: Para recolectar actualizaciones al manifest

    with Pool(processes=num_processes, initializer=worker_init) as pool:
        
        main_process_logger.info("Generando páginas de detalle de libros (paralelo)...")
        book_detail_task_with_args = partial(generate_book_detail_pages_task, config_params_manifest_tuple=task_args_tuple)
        results_books_list_of_lists = pool.map(book_detail_task_with_args, books_for_generation_full_list)
        for res_list in results_books_list_of_lists: new_manifest_entries.extend(res_list) # NEW
        main_process_logger.info(f"Detalle de libros: {len(new_manifest_entries)} páginas marcadas para/como generadas.")

        main_process_logger.info("Generando páginas de autor (paralelo)...")
        unique_author_slugs_orig = {b.get('author_slug') for b in books_for_generation_full_list if b.get('author_slug')}
        author_task_with_args = partial(generate_author_pages_task, config_params_manifest_tuple=task_args_tuple)
        results_authors_list_of_lists = pool.map(author_task_with_args, list(unique_author_slugs_orig))
        for res_list in results_authors_list_of_lists: new_manifest_entries.extend(res_list) # NEW
        main_process_logger.info(f"Páginas de autor: {len([e for e in new_manifest_entries if 'autor' in e['path']])} adicionales marcadas para/como generadas.")
        # El conteo de arriba es un ejemplo, necesitarías una mejor forma de contar por tipo

        main_process_logger.info("Generando páginas de versiones (paralelo)...")
        unique_book_bases_slugs = {(b.get('author_slug'), b.get('base_title_slug')) for b in books_for_generation_full_list if b.get('author_slug') and b.get('base_title_slug')}
        versions_task_with_args = partial(generate_versions_pages_task, config_params_manifest_tuple=task_args_tuple)
        results_versions_list_of_lists = pool.map(versions_task_with_args, list(unique_book_bases_slugs))
        for res_list in results_versions_list_of_lists: new_manifest_entries.extend(res_list) # NEW
        main_process_logger.info(f"Páginas de versiones: {len([e for e in new_manifest_entries if 'version' in e['path']])} adicionales marcadas para/como generadas.")


    # NEW: Actualizar el manifest principal con los resultados de los workers
    if new_manifest_entries:
        main_process_logger.info(f"Actualizando manifest con {len(new_manifest_entries)} entradas generadas/actualizadas...")
        for entry in new_manifest_entries:
            manifest_data[entry['path']] = {
                "signature": entry['signature'],
                "timestamp": entry['timestamp']
            }
    else:
        main_process_logger.info("No se generaron/actualizaron nuevas páginas cacheadas en esta ejecución.")

    # Eliminar entradas del manifest para archivos que ya no existen (limpieza)
    # Esto es importante si los archivos pueden ser eliminados por otras razones
    # o si la estructura de URL cambia y los archivos antiguos deben ser purgados del manifest.
    # Por ahora, lo omitimos para mantenerlo más simple, pero es una consideración.
    # active_paths_in_manifest = {entry_path for entry_path in manifest_data if Path(entry_path).exists()}
    # manifest_data = {path: data for path, data in manifest_data.items() if path in active_paths_in_manifest}


    # --- Generación de Sitemap Index (solo si no se especifica un idioma O si se fuerza) ---
    if not args.language or args.force_regenerate:
        main_process_logger.info("Generando sitemap_index.xml principal...")
        with app_instance_main.app_context():
            with app_instance_main.test_client() as client_main:
                _save_page_local(client_main, "/sitemap.xml", Path(OUTPUT_DIR) / "sitemap.xml", main_process_logger)

    # NEW: Guardar el manifest actualizado
    save_manifest(manifest_data)
    main_process_logger.info(f"Sitio estático (o parte) generado en: {OUTPUT_DIR}")

if __name__ == '__main__':
    main()
