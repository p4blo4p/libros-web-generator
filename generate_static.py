# generate_static.py
import os
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging

try:
    from app import create_app
except ImportError as e:
    print(f"ERROR CRÍTICO: No se pudo importar 'create_app' desde 'app'. Detalles: {e}")
    exit(1)

script_logger = logging.getLogger('generate_static_script')
script_logger.setLevel(logging.INFO)
script_handler = logging.StreamHandler()
script_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
script_handler.setFormatter(script_formatter)
if not script_logger.handlers:
    script_logger.addHandler(script_handler)

def slugify_ascii_local(text):
    if text is None: return ""
    text = str(text); text = unidecode(text); text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text); text = re.sub(r'\s+', '-', text)
    text = re.sub(r'--+', '-', text); text = text.strip('-')
    return text if text else "na"

try:
    from app.utils.helpers import slugify_ascii as slugify_ascii_app
    slugify_to_use = slugify_ascii_app
except ImportError:
    slugify_to_use = slugify_ascii_local

def get_translated_url_segment_for_generator(segment_key, lang_code, url_segment_translations, default_app_lang, default_segment_value=None, logger=None):
    log = logger if logger else script_logger
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
# Constantes para la generación de sitemaps
ALPHABET = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_CHARS_SITEMAP_KEY = "0" # Usaremos '0' para no alfabéticos (más amigable en URL que '_')

def save_page(client, url_path, file_path_obj, logger):
    try:
        logger.info(f"Generando: {url_path} -> {file_path_obj}")
    except BlockingIOError:
        logger.warning(f"Intento de E/S bloqueado para: {url_path}")
    
    try:
        response = client.get(url_path)
        if response.status_code == 200:
            # Solo guardar si hay contenido, algunos sitemaps pueden estar vacíos (y es válido)
            # pero si la vista devuelve 200 con contenido vacío, se crea archivo vacío.
            # Si la vista devuelve 404 para sitemap vacío, no se guarda nada (manejado abajo).
            if response.data: 
                file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path_obj, 'wb') as f:
                    f.write(response.data)
            else:
                logger.info(f"URL {url_path} devolvió 200 pero sin datos. No se guardó archivo (podría ser un sitemap vacío intencionalmente).")

        elif response.status_code in [301, 302, 307, 308]:
            logger.warning(f"{url_path} devolvió {response.status_code} (redirección).")
            if response.data:
                 file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                 with open(file_path_obj, 'wb') as f: f.write(response.data)
                 logger.info(f"Datos de redirección para {url_path} guardados.")
            else:
                logger.warning(f"{url_path} redirigió sin datos.")
        elif response.status_code == 404:
            logger.warning(f"404: {url_path} no encontrado (puede ser un sitemap de letra/idioma sin contenido). No se guardó el archivo.")
        else:
            logger.error(f"HTTP {response.status_code} para {url_path}. No se guardó el archivo.")
    except Exception as e:
        logger.exception(f"EXCEPCIÓN generando y guardando {url_path}: {e}")

def main():
    script_logger.info("Iniciando script generate_static.py")
    app_instance = create_app()
    logger = app_instance.logger
    logger.info("Instancia de Flask creada y su logger en uso.")
    
    LANGUAGES = app_instance.config.get('SUPPORTED_LANGUAGES', ['en'])
    DEFAULT_LANGUAGE = app_instance.config.get('DEFAULT_LANGUAGE', 'en')
    URL_SEGMENT_TRANSLATIONS_CONFIG = app_instance.config.get('URL_SEGMENT_TRANSLATIONS', {})
    
    books_for_generation = app_instance.books_data 
    if not books_for_generation:
        logger.critical("No hay datos de libros. Saliendo.")
        return

    logger.info(f"Idiomas: {LANGUAGES}, Default: {DEFAULT_LANGUAGE}")
    logger.info(f"{len(books_for_generation)} libros cargados.")

    if Path(OUTPUT_DIR).exists():
        logger.info(f"Eliminando {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    logger.info(f"{OUTPUT_DIR} creado/limpiado.")

    static_folder_path = Path(app_instance.static_folder)
    if static_folder_path.exists() and static_folder_path.is_dir():
        static_output_dir_name = Path(app_instance.static_url_path.strip('/'))
        static_output_dir = Path(OUTPUT_DIR) / static_output_dir_name
        if static_output_dir.exists():
             logger.info(f"Eliminando destino de estáticos existente: '{static_output_dir}'")
             shutil.rmtree(static_output_dir)
        shutil.copytree(static_folder_path, static_output_dir)
        logger.info(f"'{static_folder_path.name}' copiado a '{static_output_dir}'")
    else:
        logger.warning(f"Carpeta estática no encontrada: '{static_folder_path}'")

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
                    logger.error(f"Error copiando '{item.name}': {e}")
        logger.info(f"{copied_public_files} archivos de 'public/' copiados a '{public_output_dir}'.")
    else:
        logger.info(f"Carpeta 'public/' no encontrada.")

    # Determinar qué sitemaps de letras se necesitan realmente
    # Esto es para evitar generar un sitemap_index.xml que enlace a sitemaps 404
    # (aunque no es estrictamente necesario, es más limpio)
    # Nota: La ruta Flask para sitemap_index.xml debería idealmente usar esta información
    # o el sitemap_index.xml podría generarse aquí al final.
    # Por simplicidad, aquí generaremos todos y la ruta /sitemap.xml de Flask los listará.
    # Si una ruta de sitemap de letra no tiene contenido, Flask puede devolver 404 o un sitemap vacío.
    
    sitemap_files_to_index = []

    with app_instance.app_context():
        with app_instance.test_client() as client:
            # --- Páginas Principales (no sitemaps) ---
            logger.info("Generando páginas principales...")
            save_page(client, "/", Path(OUTPUT_DIR) / "index.html", logger)
            if app_instance.url_map.is_endpoint_expecting('main.test_page'): # Check if test_page route exists
                save_page(client, "/test/", Path(OUTPUT_DIR) / "test_sitemap" / "index.html", logger)
            else:
                logger.info("Ruta /test/ no encontrada, saltando su generación.")


            for lang in LANGUAGES:
                save_page(client, f"/{lang}/", Path(OUTPUT_DIR) / lang / "index.html", logger)

            logger.info("Generando páginas de detalles de libros...")
            # (Tu lógica existente para generar páginas de libros, autores, versiones)
            # ... (esta parte no cambia mucho, solo usa las variables correctas) ...
            books_processed_count = 0
            for book_data in books_for_generation:
                author_s_original = book_data.get('author_slug')
                title_s_original = book_data.get('title_slug')
                identifier = book_data.get('isbn10') or book_data.get('isbn13') or book_data.get('asin')
                if not (identifier and author_s_original and title_s_original): continue
                author_s = slugify_to_use(author_s_original) 
                title_s = slugify_to_use(title_s_original)
                for lang in LANGUAGES:
                    book_segment_translated = get_translated_url_segment_for_generator('book', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'book', logger)
                    flask_url = f"/{lang}/{book_segment_translated}/{author_s}/{title_s}/{identifier}/"
                    output_path = Path(OUTPUT_DIR) / lang / book_segment_translated / author_s / title_s / identifier / "index.html"
                    save_page(client, flask_url, output_path, logger)
                books_processed_count +=1
            logger.info(f"{books_processed_count} páginas de detalle de libros procesadas.")

            logger.info("Generando páginas de versiones de libros...")
            unique_book_bases_slugs = {(b.get('author_slug'), b.get('base_title_slug')) for b in books_for_generation if b.get('author_slug') and b.get('base_title_slug')}
            versions_pages_count = 0
            for author_s_orig, base_title_s_orig in unique_book_bases_slugs:
                author_s, base_title_s = slugify_to_use(author_s_orig), slugify_to_use(base_title_s_orig)
                for lang in LANGUAGES:
                    versions_segment_translated = get_translated_url_segment_for_generator('versions', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'versions', logger)
                    flask_url = f"/{lang}/{versions_segment_translated}/{author_s}/{base_title_s}/"
                    output_path = Path(OUTPUT_DIR) / lang / versions_segment_translated / author_s / base_title_s / "index.html"
                    save_page(client, flask_url, output_path, logger)
                versions_pages_count +=1
            logger.info(f"{versions_pages_count} páginas de versiones procesadas.")

            logger.info("Generando páginas de autor...")
            unique_author_slugs_orig = {b.get('author_slug') for b in books_for_generation if b.get('author_slug')}
            author_pages_count = 0
            for author_s_orig in unique_author_slugs_orig:
                author_s = slugify_to_use(author_s_orig)
                for lang in LANGUAGES:
                    author_segment_translated = get_translated_url_segment_for_generator('author', lang, URL_SEGMENT_TRANSLATIONS_CONFIG, DEFAULT_LANGUAGE, 'author', logger)
                    flask_url = f"/{lang}/{author_segment_translated}/{author_s}/"
                    output_path = Path(OUTPUT_DIR) / lang / author_segment_translated / author_s / "index.html"
                    save_page(client, flask_url, output_path, logger)
                author_pages_count +=1
            logger.info(f"{author_pages_count} páginas de autor procesadas.")

            # --- Generación de Sitemaps ---
            logger.info("Generando Sitemaps...")
            
            # 1. Sitemap Index (referenciará a los demás)
            # La ruta /sitemap.xml en Flask debe generar este índice.
            # Guardaremos este al final después de saber qué otros sitemaps se generaron,
            # o la ruta Flask /sitemap.xml debe ser inteligente.
            # Por ahora, generamos los sitemaps individuales primero.

            # 2. Sitemaps "core" por idioma
            for lang in LANGUAGES:
                sitemap_url = f"/sitemap_{lang}_core.xml"
                sitemap_path = Path(OUTPUT_DIR) / f"sitemap_{lang}_core.xml"
                save_page(client, sitemap_url, sitemap_path, logger)
                if sitemap_path.exists() and sitemap_path.stat().st_size > 0: # Solo añadir al índice si se creó y no está vacío
                     sitemap_files_to_index.append(sitemap_path.name)


            # 3. Sitemaps por idioma y letra de autor
            letters_and_special = list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]
            for lang in LANGUAGES:
                for char_key in letters_and_special: # 'a', 'b', ..., 'z', '0'
                    sitemap_url = f"/sitemap_{lang}_{char_key}.xml"
                    sitemap_path = Path(OUTPUT_DIR) / f"sitemap_{lang}_{char_key}.xml"
                    save_page(client, sitemap_url, sitemap_path, logger)
                    if sitemap_path.exists() and sitemap_path.stat().st_size > 0:
                        sitemap_files_to_index.append(sitemap_path.name)
            
            # Ahora, generar el sitemap_index.xml principal usando las rutas de Flask
            # que ahora están pobladas con los sitemaps generados.
            # O, si /sitemap.xml en Flask es inteligente, simplemente lo llamamos.
            logger.info("Generando sitemap_index.xml principal...")
            save_page(client, "/sitemap.xml", Path(OUTPUT_DIR) / "sitemap.xml", logger)


    logger.info(f"Sitio estático generado en: {OUTPUT_DIR}")

if __name__ == '__main__':
    main()