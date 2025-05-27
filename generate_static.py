# generate_static.py
import os
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging

# Intenta importar la fábrica de la aplicación y otras dependencias
try:
    from app import create_app
except ImportError as e:
    # Usar print aquí es aceptable ya que el logger de la app podría no estar disponible aún
    print(f"ERROR CRÍTICO: No se pudo importar 'create_app' desde 'app'. Detalles: {e}")
    print("Asegúrate de que el script se ejecuta desde el directorio raíz del proyecto y que 'app' es un paquete accesible.")
    exit(1)

# --- Configuración de un Logger Básico para el Script ANTES de crear la app ---
script_logger = logging.getLogger('generate_static_script')
script_logger.setLevel(logging.INFO) # Puedes cambiar a logging.DEBUG para más detalle
script_handler = logging.StreamHandler()
script_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
script_handler.setFormatter(script_formatter)
if not script_logger.handlers: # Evitar añadir múltiples handlers si el script se reimporta
    script_logger.addHandler(script_handler)


# --- FUNCIÓN SLUGIFY ---
def slugify_ascii_local(text):
    if text is None: return ""
    text = str(text); text = unidecode(text); text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text); text = re.sub(r'\s+', '-', text)
    text = re.sub(r'--+', '-', text); text = text.strip('-')
    return text if text else "na"

try:
    from app.utils.helpers import slugify_ascii as slugify_ascii_app
    script_logger.info("Usando slugify_ascii importado desde app.utils.helpers.")
    slugify_to_use = slugify_ascii_app
except ImportError:
    script_logger.warning("No se pudo importar slugify_ascii desde app.utils.helpers. Usando la versión local de slugify.")
    slugify_to_use = slugify_ascii_local

# --- FUNCIÓN PARA OBTENER SEGMENTOS URL TRADUCIDOS (ADAPTADA PARA ESTE SCRIPT) ---
def get_translated_url_segment_for_generator(segment_key, lang_code, url_segment_translations, default_app_lang, default_segment_value=None, logger=None):
    log = logger if logger else script_logger 

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

OUTPUT_DIR = "_site"

def save_page(client, url_path, file_path_obj, logger):
    try:
        logger.info(f"Generando: {url_path} -> {file_path_obj}")
    except BlockingIOError:
        logger.warning(f"Intento de E/S bloqueado (raro con logger) para: {url_path}")
    
    try:
        response = client.get(url_path) 
        if response.status_code == 200:
            file_path_obj.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path_obj, 'wb') as f:
                f.write(response.data)
        elif response.status_code in [301, 302, 307, 308]:
            logger.warning(f"{url_path} devolvió {response.status_code} (redirección). El cliente pudo o no haberla seguido. Verifique si se generó el contenido esperado.")
            if response.data:
                 file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                 with open(file_path_obj, 'wb') as f:
                     f.write(response.data)
                 logger.info(f"Datos de redirección para {url_path} guardados.")
            else:
                logger.warning(f"{url_path} redirigió pero no hay datos en la respuesta. No se guardó archivo para esta URL exacta.")
        elif response.status_code == 404:
            logger.warning(f"404: {url_path} no encontrado. No se guardó el archivo.")
        else:
            logger.error(f"HTTP {response.status_code} para {url_path}. No se guardó el archivo.")
    except Exception as e:
        logger.exception(f"EXCEPCIÓN generando y guardando {url_path}: {e}")

def main():
    script_logger.info("Iniciando script generate_static.py")
    
    app_instance = create_app()
    logger = app_instance.logger 
    logger.info("Instancia de la aplicación Flask creada y su logger está ahora en uso.")
    
    LANGUAGES = app_instance.config.get('SUPPORTED_LANGUAGES', ['en'])
    DEFAULT_LANGUAGE = app_instance.config.get('DEFAULT_LANGUAGE', 'en')
    URL_SEGMENT_TRANSLATIONS_CONFIG = app_instance.config.get('URL_SEGMENT_TRANSLATIONS', {})
    
    books_for_generation = app_instance.books_data 
    if not books_for_generation:
        logger.critical("No hay datos de libros (app_instance.books_data está vacío o no es una lista). Saliendo.")
        return

    logger.info(f"Idiomas soportados: {LANGUAGES}, Idioma por defecto: {DEFAULT_LANGUAGE}")
    logger.info(f"{len(books_for_generation)} libros cargados para generación.")

    logger.info("Iniciando generación del sitio estático...")
    if Path(OUTPUT_DIR).exists():
        logger.info(f"Eliminando directorio de salida existente: {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    logger.info(f"Directorio de salida creado/limpiado: {OUTPUT_DIR}")

    static_folder_path = Path(app_instance.static_folder)
    if static_folder_path.exists() and static_folder_path.is_dir():
        static_output_dir_name = Path(app_instance.static_url_path.strip('/')) 
        static_output_dir = Path(OUTPUT_DIR) / static_output_dir_name
        
        # --- MODIFICACIÓN PARA COMPATIBILIDAD CON PYTHON < 3.8 ---
        if static_output_dir.exists():
             logger.info(f"Destino de estáticos '{static_output_dir}' ya existe. Eliminando antes de copiar.")
             shutil.rmtree(static_output_dir)
        
        shutil.copytree(static_folder_path, static_output_dir)
        # --- FIN DE LA MODIFICACIÓN ---
        
        logger.info(f"Carpeta estática '{static_folder_path.name}' copiada a '{static_output_dir}'")
    else:
        logger.warning(f"Carpeta estática no encontrada en '{static_folder_path}' o no es un directorio.")

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
                    logger.error(f"Error copiando archivo público '{item.name}': {e}")
        if copied_public_files > 0:
             logger.info(f"{copied_public_files} archivos de la carpeta 'public/' copiados a '{public_output_dir}'")
        else:
            logger.info("No se encontraron archivos en la carpeta 'public/' para copiar o hubo errores.")
    else:
        logger.info(f"Carpeta 'public/' no encontrada en '{public_folder_path}'. No se copiaron archivos adicionales.")


    with app_instance.app_context():
        with app_instance.test_client() as client:
            logger.info("Generando páginas principales (índice raíz, sitemap.xml, test)...")
            save_page(client, "/", Path(OUTPUT_DIR) / "index.html", logger) 
            save_page(client, "/sitemap.xml", Path(OUTPUT_DIR) / "sitemap.xml", logger)
            save_page(client, "/test/", Path(OUTPUT_DIR) / "test_sitemap" / "index.html", logger) 

            logger.info("Generando páginas de índice por idioma...")
            for lang in LANGUAGES:
                flask_url_lang_index = f"/{lang}/"
                output_path_lang_index = Path(OUTPUT_DIR) / lang / "index.html"
                save_page(client, flask_url_lang_index, output_path_lang_index, logger)

            logger.info("Generando páginas de detalles de libros...")
            books_processed_count = 0
            for book_data in books_for_generation:
                author_s_original = book_data.get('author_slug')
                title_s_original = book_data.get('title_slug')
                identifier = book_data.get('isbn10') or book_data.get('isbn13') or book_data.get('asin')
                
                if not (identifier and author_s_original and title_s_original): 
                    continue
                
                author_s = slugify_to_use(author_s_original) 
                title_s = slugify_to_use(title_s_original)

                for lang in LANGUAGES:
                    book_segment_translated = get_translated_url_segment_for_generator(
                        'book', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'book', logger=logger
                    )
                    flask_url = f"/{lang}/{book_segment_translated}/{author_s}/{title_s}/{identifier}/"
                    dir_author_s = author_s if author_s else "na-author" 
                    dir_title_s = title_s if title_s else "na-title"     
                    output_path = Path(OUTPUT_DIR) / lang / book_segment_translated / dir_author_s / dir_title_s / identifier / "index.html"
                    save_page(client, flask_url, output_path, logger)
                books_processed_count +=1
            logger.info(f"{books_processed_count} registros de libros procesados para generar páginas de detalle.")
            
            logger.info("Generando páginas de versiones de libros...")
            unique_book_bases_slugs = {} 
            for book_data in books_for_generation:
                author_s_original = book_data.get('author_slug')
                base_title_s_original = book_data.get('base_title_slug')
                if not (author_s_original and base_title_s_original): continue
                unique_book_bases_slugs[(author_s_original, base_title_s_original)] = True
            
            logger.info(f"Número de bases de libros únicas para 'versiones': {len(unique_book_bases_slugs)}")
            versions_pages_count = 0
            for author_s_orig, base_title_s_orig in unique_book_bases_slugs.keys():
                author_s = slugify_to_use(author_s_orig)
                base_title_s = slugify_to_use(base_title_s_orig)
                for lang in LANGUAGES:
                    versions_segment_translated = get_translated_url_segment_for_generator(
                        'versions', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'versions', logger=logger
                    )
                    flask_url = f"/{lang}/{versions_segment_translated}/{author_s}/{base_title_s}/"
                    dir_author_s = author_s if author_s else "na-author"
                    dir_base_title_s = base_title_s if base_title_s else "na-basetitle"
                    output_path = Path(OUTPUT_DIR) / lang / versions_segment_translated / dir_author_s / dir_base_title_s / "index.html"
                    save_page(client, flask_url, output_path, logger)
                versions_pages_count +=1
            logger.info(f"{versions_pages_count} páginas de versiones de libros generadas.")

            logger.info("Generando páginas de libros por autor...")
            unique_author_slugs_orig = set(b.get('author_slug') for b in books_for_generation if b.get('author_slug'))
            logger.info(f"Número de autores únicos para páginas de autor: {len(unique_author_slugs_orig)}")
            author_pages_count = 0
            for author_s_orig in unique_author_slugs_orig:
                author_s = slugify_to_use(author_s_orig)
                for lang in LANGUAGES:
                    author_segment_translated = get_translated_url_segment_for_generator(
                        'author', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'author', logger=logger
                    )
                    flask_url = f"/{lang}/{author_segment_translated}/{author_s}/"
                    dir_author_s = author_s if author_s else "na-author"
                    output_path = Path(OUTPUT_DIR) / lang / author_segment_translated / dir_author_s / "index.html"
                    save_page(client, flask_url, output_path, logger)
                author_pages_count +=1
            logger.info(f"{author_pages_count} páginas de autor generadas.")

    logger.info(f"Sitio estático generado con éxito en la carpeta: {OUTPUT_DIR}")
    logger.info("IMPORTANTE: Revisa las URLs generadas y las rutas de guardado, especialmente para los segmentos traducidos.")

if __name__ == '__main__':
    main()