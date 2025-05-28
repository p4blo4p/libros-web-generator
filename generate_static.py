# generate_static.py
import os
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging
from multiprocessing import Pool, cpu_count, current_process
from functools import partial # Para pasar argumentos fijos a la función del worker

# NO importamos create_app aquí directamente en el scope global
# para evitar problemas con el fork en algunos sistemas.
# Se importará dentro de las funciones que lo necesiten o se pasará como argumento.

# --- Configuración de un Logger Básico para el Script ---
# Este logger se usará en el proceso principal y potencialmente como base
# para los workers si no se reconfigura específicamente para ellos.
script_logger = logging.getLogger('generate_static_script')
script_logger.setLevel(logging.INFO) # O logging.DEBUG para más detalle
script_handler = logging.StreamHandler() # Escribe a la consola
script_formatter = logging.Formatter('%(asctime)s - %(name)s:%(processName)s - %(levelname)s - %(message)s')
script_handler.setFormatter(script_formatter)
if not script_logger.handlers:
    script_logger.addHandler(script_handler)

# --- Variables Globales para Workers (se establecerán en worker_init) ---
# Estas se usarán para evitar pasar la instancia completa de la app a cada tarea
# y para que cada worker tenga su propio cliente.
worker_app_instance = None
worker_client = None
worker_logger = None # Cada worker puede tener su propio logger o usar el script_logger

# --- FUNCIONES DE UTILIDAD (slugify, get_translated_url_segment) ---
# (Estas funciones no cambian, se mantienen como en tu original)
def slugify_ascii_local(text):
    if text is None: return ""
    text = str(text); text = unidecode(text); text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text); text = re.sub(r'\s+', '-', text)
    text = re.sub(r'--+', '-', text); text = text.strip('-')
    return text if text else "na"

# Intentar importar slugify de la app, si no, usar local
try:
    # Este import se hará en el worker_init para que esté en el contexto del worker
    # from app.utils.helpers import slugify_ascii as slugify_ascii_app
    # slugify_to_use = slugify_ascii_app
    # script_logger.info("Usando slugify_ascii importado desde app.utils.helpers (se confirmará en worker).")
    _temp_slugify = slugify_ascii_local # Placeholder
except ImportError:
    _temp_slugify = slugify_ascii_local
    # script_logger.warning("No se pudo importar slugify_ascii desde app.utils.helpers. Usando la versión local de slugify.")

slugify_to_use_global = _temp_slugify # Se reasignará en worker_init si es posible

def get_translated_url_segment_for_generator(segment_key, lang_code, url_segment_translations, default_app_lang, default_segment_value=None, logger_to_use=None):
    log = logger_to_use if logger_to_use else script_logger # Usar el logger pasado o el global del script
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

# --- FUNCIÓN SAVE_PAGE (Modificada para usar el cliente del worker) ---
def save_page_worker(url_path, file_path_obj): # El logger y cliente vienen de variables globales del worker
    global worker_client, worker_logger
    try:
        # worker_logger puede ser None si worker_init falla o no lo establece
        log_target = worker_logger if worker_logger else script_logger
        log_target.info(f"Generando: {url_path} -> {file_path_obj}")
    except BlockingIOError:
        log_target.warning(f"Intento de E/S bloqueado para: {url_path}")
    
    try:
        response = worker_client.get(url_path) # Usa el cliente del worker
        # ... (resto de la lógica de save_page como en tu original) ...
        if response.status_code == 200:
            if response.data: 
                file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path_obj, 'wb') as f:
                    f.write(response.data)
            else:
                log_target.info(f"URL {url_path} devolvió 200 pero sin datos. No se guardó archivo.")
        elif response.status_code in [301, 302, 307, 308]:
            log_target.warning(f"{url_path} devolvió {response.status_code} (redirección).")
            if response.data:
                 file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                 with open(file_path_obj, 'wb') as f: f.write(response.data)
                 log_target.info(f"Datos de redirección para {url_path} guardados.")
            else:
                log_target.warning(f"{url_path} redirigió sin datos.")
        elif response.status_code == 404:
            log_target.warning(f"404: {url_path} no encontrado. No se guardó el archivo.")
        else:
            log_target.error(f"HTTP {response.status_code} para {url_path}. No se guardó el archivo.")

    except Exception as e:
        log_target.exception(f"EXCEPCIÓN generando y guardando {url_path}: {e}")
    return url_path # Devolver algo para seguimiento si es necesario

# --- FUNCIONES WORKER PARA MULTIPROCESSING ---
def worker_init():
    """Inicializador para cada proceso del pool. Crea una instancia de app y cliente."""
    global worker_app_instance, worker_client, worker_logger, slugify_to_use_global
    
    # Importar create_app aquí, dentro del worker
    from app import create_app
    
    script_logger.info(f"Worker {current_process().name}: Inicializando...")
    worker_app_instance = create_app()
    # Es crucial que el cliente se cree y se use DENTRO de un contexto de aplicación
    # Sin embargo, para multiprocessing, a menudo es mejor crear el cliente y luego
    # abrir y cerrar contextos de app para cada grupo de operaciones.
    # Por ahora, crearemos un cliente persistente para el worker.
    # Si da problemas de "working outside of application context", ajustaremos.
    
    # Configurar un logger específico para este worker si se desea
    # Esto ayuda a distinguir logs de diferentes workers.
    # Por simplicidad, los workers pueden seguir usando script_logger, 
    # pero el formatter ya incluye processName.
    worker_logger = logging.getLogger(f'worker_{current_process().name}')
    if not worker_logger.handlers: # Evitar duplicar handlers si worker_init se llama más de una vez (no debería con Pool)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        worker_logger.addHandler(handler)
        worker_logger.setLevel(logging.INFO) # O DEBUG

    try:
        from app.utils.helpers import slugify_ascii as slugify_ascii_app
        slugify_to_use_global = slugify_ascii_app
        worker_logger.info("Worker usando slugify_ascii de app.utils.helpers.")
    except ImportError:
        slugify_to_use_global = slugify_ascii_local
        worker_logger.warning("Worker usando slugify_ascii local.")


    # IMPORTANTE: El cliente se debe usar dentro de un contexto de aplicación.
    # `app_context().push()` aquí y `pop()` al final del worker o por tarea
    # es una forma. Otra es usar `with app.app_context():` en la función de la tarea.
    # Para `test_client`, se recomienda usarlo como un context manager.
    # Por ahora, la función de tarea manejará su propio `with worker_app_instance.test_client() as client:`
    # Así que solo necesitamos `worker_app_instance`.
    # Corrección: Para que `save_page_worker` use un `worker_client` global, debemos crearlo aquí.
    # Y la función de tarea debe asegurarse de que el contexto esté activo.
    
    # Mantener el cliente abierto durante la vida del worker puede ser eficiente
    # pero requiere gestionar el contexto de la aplicación.
    # Alternativa más segura: crear y cerrar cliente por tarea.
    # Probemos con cliente persistente en el worker, y la tarea usa app_context.
    
    # Para que `save_page_worker` acceda a `worker_client`:
    # 1. Establecer `worker_client` aquí.
    # 2. La función de tarea debe operar DENTRO de `with worker_app_instance.app_context():`.
    
    # No crearemos `worker_client` aquí globalmente todavía.
    # La función de tarea creará su propio cliente usando `worker_app_instance.test_client()`.
    # Si eso resulta ineficiente, lo reconsideramos.
    # Corrección: Vamos a crear el cliente aquí para que save_page_worker pueda usarlo
    # y la función de tarea se asegurará de que el app_context esté activo.
    # Esto es un poco complicado. Vamos a optar por que CADA TAREA cree su propio cliente.
    # Esto es más seguro para el aislamiento del contexto.
    # Por lo tanto, `worker_client` no se usará globalmente por ahora. `save_page_worker` necesitará que se le pase el cliente.

    script_logger.info(f"Worker {current_process().name}: Inicializado con instancia de app.")


def generate_book_detail_pages_task(book_data_item, config_params):
    """Tarea para generar páginas de detalle de un libro en todos los idiomas."""
    global worker_app_instance, worker_logger, slugify_to_use_global
    
    # Extraer parámetros de configuración
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE = config_params['OUTPUT_DIR']

    log_target = worker_logger if worker_logger else script_logger
    count = 0

    author_s_original = book_data_item.get('author_slug')
    title_s_original = book_data_item.get('title_slug')
    identifier = book_data_item.get('isbn10') or book_data_item.get('isbn13') or book_data_item.get('asin')
    
    if not (identifier and author_s_original and title_s_original):
        log_target.debug(f"Saltando libro (datos incompletos): ID {identifier}")
        return 0 # 0 páginas generadas

    author_s = slugify_to_use_global(author_s_original)
    title_s = slugify_to_use_global(title_s_original)

    # Cada tarea opera dentro de su propio contexto de app y con su propio cliente.
    # Esto es más seguro para el aislamiento en multiprocessing.
    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client: # Cliente local para esta tarea
            for lang in LANGUAGES:
                book_segment_translated = get_translated_url_segment_for_generator(
                    'book', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'book', logger_to_use=log_target
                )
                flask_url = f"/{lang}/{book_segment_translated}/{author_s}/{title_s}/{identifier}/"
                # Recrear Path object para asegurar que es seguro entre procesos (aunque strings suelen serlo)
                output_path = Path(OUTPUT_DIR_BASE) / lang / book_segment_translated / author_s / title_s / identifier / "index.html"
                
                # Modificar save_page para que acepte el cliente local
                # Por ahora, llamaré a una versión adaptada aquí mismo o modificaré la global.
                # Modificamos save_page_worker para que use el cliente pasado.
                # Corrección: save_page_worker usará el cliente global del worker.
                # No, es mejor pasar el cliente a save_page.
                _save_page_local(client, flask_url, output_path, log_target) # Llamar a una versión que acepte cliente
                count += 1
    return count

def generate_author_pages_task(author_slug_original, config_params):
    global worker_app_instance, worker_logger, slugify_to_use_global
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE = config_params['OUTPUT_DIR']
    log_target = worker_logger if worker_logger else script_logger
    count = 0

    author_s = slugify_to_use_global(author_slug_original)
    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                author_segment_translated = get_translated_url_segment_for_generator('author', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'author', logger_to_use=log_target)
                flask_url = f"/{lang}/{author_segment_translated}/{author_s}/"
                output_path = Path(OUTPUT_DIR_BASE) / lang / author_segment_translated / author_s / "index.html"
                _save_page_local(client, flask_url, output_path, log_target)
                count += 1
    return count

def generate_versions_pages_task(author_base_title_slugs_original, config_params):
    global worker_app_instance, worker_logger, slugify_to_use_global
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS_CONFIG = config_params['URL_SEGMENT_TRANSLATIONS_CONFIG']
    OUTPUT_DIR_BASE = config_params['OUTPUT_DIR']
    log_target = worker_logger if worker_logger else script_logger
    count = 0

    author_s_orig, base_title_s_orig = author_base_title_slugs_original
    author_s = slugify_to_use_global(author_s_orig)
    base_title_s = slugify_to_use_global(base_title_s_orig)

    with worker_app_instance.app_context():
        with worker_app_instance.test_client() as client:
            for lang in LANGUAGES:
                versions_segment_translated = get_translated_url_segment_for_generator('versions', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'versions', logger_to_use=log_target)
                flask_url = f"/{lang}/{versions_segment_translated}/{author_s}/{base_title_s}/"
                output_path = Path(OUTPUT_DIR_BASE) / lang / versions_segment_translated / author_s / base_title_s / "index.html"
                _save_page_local(client, flask_url, output_path, log_target)
                count += 1
    return count


def _save_page_local(client_local, url_path, file_path_obj, logger_to_use):
    """Versión de save_page que acepta el cliente y el logger."""
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
        elif response.status_code in [301, 302, 307, 308]: # ... (resto igual)
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


# --- FUNCIÓN MAIN (Modificada para usar Multiprocessing) ---
def main():
    # Usar el logger del script para el proceso principal
    main_process_logger = script_logger 
    main_process_logger.info("Iniciando script generate_static.py en proceso principal...")

    # Crear la instancia de la app UNA VEZ en el proceso principal para obtener configuraciones
    # y para generar páginas que no se paralelizan.
    from app import create_app # Importar aquí para el main
    app_instance_main = create_app()
    # El logger de la app_instance_main se puede usar para logs generales de la app desde el main.
    # Pero para el script en sí, seguiremos usando `main_process_logger`.
    main_process_logger.info("Instancia de Flask creada en proceso principal para configuraciones.")
    
    LANGUAGES = app_instance_main.config.get('SUPPORTED_LANGUAGES', ['en'])
    DEFAULT_LANGUAGE = app_instance_main.config.get('DEFAULT_LANGUAGE', 'en')
    URL_SEGMENT_TRANSLATIONS_CONFIG = app_instance_main.config.get('URL_SEGMENT_TRANSLATIONS', {})
    
    books_for_generation = app_instance_main.books_data
    if not books_for_generation:
        main_process_logger.critical("No hay datos de libros. Saliendo.")
        return

    main_process_logger.info(f"Idiomas: {LANGUAGES}, Default: {DEFAULT_LANGUAGE}")
    main_process_logger.info(f"{len(books_for_generation)} libros cargados para procesar.")

    # --- Preparación de Directorios y Estáticos (en proceso principal) ---
    if Path(OUTPUT_DIR).exists():
        main_process_logger.info(f"Eliminando {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    main_process_logger.info(f"{OUTPUT_DIR} creado/limpiado.")

    static_folder_path = Path(app_instance_main.static_folder)
    if static_folder_path.exists() and static_folder_path.is_dir():
        static_output_dir_name = Path(app_instance_main.static_url_path.strip('/'))
        static_output_dir = Path(OUTPUT_DIR) / static_output_dir_name
        if static_output_dir.exists():
             main_process_logger.info(f"Eliminando destino de estáticos existente: '{static_output_dir}'")
             shutil.rmtree(static_output_dir)
        shutil.copytree(static_folder_path, static_output_dir)
        main_process_logger.info(f"'{static_folder_path.name}' copiado a '{static_output_dir}'")
    else:
        main_process_logger.warning(f"Carpeta estática no encontrada: '{static_folder_path}'")

    public_folder_path = Path("public")
    if public_folder_path.exists() and public_folder_path.is_dir():
        public_output_dir = Path(OUTPUT_DIR)
        copied_public_files = 0
        for item in public_folder_path.iterdir():
            if item.is_file():
                try:
                    shutil.copy2(item, public_output_dir / item.name)
                    copied_public_files +=1
                except Exception as e:
                    main_process_logger.error(f"Error copiando '{item.name}': {e}")
        main_process_logger.info(f"{copied_public_files} archivos de 'public/' copiados a '{public_output_dir}'.")
    else:
        main_process_logger.info(f"Carpeta 'public/' no encontrada.")

    # --- Generación de Páginas No Paralelizadas (índices, sitemaps base) ---
    sitemap_files_to_index = [] # Para el sitemap_index.xml
    main_process_logger.info("Generando páginas principales y sitemaps base (proceso principal)...")
    with app_instance_main.app_context():
        with app_instance_main.test_client() as client_main:
            _save_page_local(client_main, "/", Path(OUTPUT_DIR) / "index.html", main_process_logger)
            if app_instance_main.url_map.is_endpoint_expecting('main.test_page'):
                _save_page_local(client_main, "/test/", Path(OUTPUT_DIR) / "test_sitemap" / "index.html", main_process_logger)
            
            for lang in LANGUAGES:
                _save_page_local(client_main, f"/{lang}/", Path(OUTPUT_DIR) / lang / "index.html", main_process_logger)
                
                # Sitemaps "core" por idioma
                sitemap_url = f"/sitemap_{lang}_core.xml"
                sitemap_path = Path(OUTPUT_DIR) / f"sitemap_{lang}_core.xml"
                _save_page_local(client_main, sitemap_url, sitemap_path, main_process_logger)
                if sitemap_path.exists() and sitemap_path.stat().st_size > 0:
                     sitemap_files_to_index.append(sitemap_path.name)

            # Sitemaps por idioma y letra (generados por Flask, no por libro individual)
            letters_and_special = list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]
            for lang in LANGUAGES:
                for char_key in letters_and_special:
                    sitemap_url = f"/sitemap_{lang}_{char_key}.xml"
                    sitemap_path = Path(OUTPUT_DIR) / f"sitemap_{lang}_{char_key}.xml"
                    _save_page_local(client_main, sitemap_url, sitemap_path, main_process_logger)
                    if sitemap_path.exists() and sitemap_path.stat().st_size > 0:
                        sitemap_files_to_index.append(sitemap_path.name)


    # --- Preparación para Paralelización ---
    num_processes = max(1, cpu_count() - 1) # Dejar un core libre o usar todos
    main_process_logger.info(f"Usando {num_processes} procesos para la generación paralela.")

    # Parámetros de configuración que se pasarán a cada tarea
    config_params_for_tasks = {
        'LANGUAGES': LANGUAGES,
        'DEFAULT_LANGUAGE': DEFAULT_LANGUAGE,
        'URL_SEGMENT_TRANSLATIONS_CONFIG': URL_SEGMENT_TRANSLATIONS_CONFIG,
        'OUTPUT_DIR': OUTPUT_DIR, # Pasar como string, Path objects pueden no ser picklables fácilmente
    }

    # Crear un Pool de workers. `initializer` se llama una vez por proceso worker.
    # `initargs` son los argumentos para `initializer`.
    # No pasamos `initargs` porque `worker_init` no los toma, accede a globales para configurar.
    # Esto es para que los workers tengan su propia instancia de app.
    with Pool(processes=num_processes, initializer=worker_init) as pool:
        
        # 1. Tareas para páginas de detalle de libros
        main_process_logger.info("Iniciando generación paralela de páginas de detalle de libros...")
        # Usar partial para fijar el argumento config_params_for_tasks
        # tasks_book_details = [(book_data, config_params_for_tasks) for book_data in books_for_generation]
        # results_books = pool.starmap(generate_book_detail_pages_task, tasks_book_details)
        # Alternativa con pool.map y partial:
        book_detail_task_with_config = partial(generate_book_detail_pages_task, config_params=config_params_for_tasks)
        results_books = pool.map(book_detail_task_with_config, books_for_generation)
        total_book_pages_generated = sum(results_books)
        main_process_logger.info(f"{total_book_pages_generated} páginas de detalle de libros generadas en paralelo.")

        # 2. Tareas para páginas de autor
        main_process_logger.info("Iniciando generación paralela de páginas de autor...")
        unique_author_slugs_orig = {b.get('author_slug') for b in books_for_generation if b.get('author_slug')}
        author_task_with_config = partial(generate_author_pages_task, config_params=config_params_for_tasks)
        results_authors = pool.map(author_task_with_config, list(unique_author_slugs_orig))
        total_author_pages_generated = sum(results_authors)
        main_process_logger.info(f"{total_author_pages_generated} páginas de autor generadas en paralelo.")


        # 3. Tareas para páginas de versiones
        main_process_logger.info("Iniciando generación paralela de páginas de versiones...")
        unique_book_bases_slugs = {(b.get('author_slug'), b.get('base_title_slug')) for b in books_for_generation if b.get('author_slug') and b.get('base_title_slug')}
        versions_task_with_config = partial(generate_versions_pages_task, config_params=config_params_for_tasks)
        results_versions = pool.map(versions_task_with_config, list(unique_book_bases_slugs))
        total_versions_pages_generated = sum(results_versions)
        main_process_logger.info(f"{total_versions_pages_generated} páginas de versiones generadas en paralelo.")


    # --- Generación de Sitemap Index (después de que todo lo demás se haya generado) ---
    main_process_logger.info("Generando sitemap_index.xml principal (proceso principal)...")
    with app_instance_main.app_context():
        with app_instance_main.test_client() as client_main:
            # La ruta /sitemap.xml en Flask debería ser capaz de encontrar los sitemaps generados
            # en el sistema de archivos si es necesario, o generar su contenido dinámicamente
            # basado en las reglas de la aplicación.
            _save_page_local(client_main, "/sitemap.xml", Path(OUTPUT_DIR) / "sitemap.xml", main_process_logger)

    main_process_logger.info(f"Sitio estático generado en: {OUTPUT_DIR}")

if __name__ == '__main__':
    # Esto es importante para multiprocessing en Windows y a veces en otros OS.
    # Debe estar bajo `if __name__ == '__main__':`
    # from multiprocessing import freeze_support
    # freeze_support() # Descomentar si tienes problemas, especialmente en Windows

    main()
