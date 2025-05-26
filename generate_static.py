# generate_static.py
import os
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import sys # Para verificar la versión de Python

# Intenta importar la fábrica de la aplicación y otras dependencias
try:
    from app import create_app
except ImportError as e:
    print(f"ERROR: No se pudo importar 'create_app' desde 'app'. Detalles: {e}")
    print("Asegúrate de que el script se ejecuta desde el directorio raíz del proyecto y que 'app' es un paquete accesible.")
    exit(1)

# --- FUNCIÓN SLUGIFY ---
try:
    from app.utils.helpers import slugify_ascii
    print("INFO: slugify_ascii importado desde app.utils.helpers.")
except ImportError:
    print("ADVERTENCIA: No se pudo importar slugify_ascii desde app.utils.helpers. Usando la versión local.")
    def slugify_ascii(text):
        if text is None: return ""
        text = str(text); text = unidecode(text); text = text.lower()
        text = re.sub(r'[^\w\s-]', '', text); text = re.sub(r'\s+', '-', text)
        text = re.sub(r'--+', '-', text); text = text.strip('-')
        return text if text else "na"

# --- FUNCIÓN PARA OBTENER SEGMENTOS URL TRADUCIDOS (ADAPTADA PARA ESTE SCRIPT) ---
def get_translated_url_segment_for_generator(segment_key, lang_code, url_segment_translations, default_app_lang, default_segment_value=None):
    segments_for_key = url_segment_translations.get(segment_key, {})
    translated_segment = segments_for_key.get(lang_code)
    if translated_segment:
        return translated_segment
    if lang_code != default_app_lang:
        translated_segment_default_lang = segments_for_key.get(default_app_lang)
        if translated_segment_default_lang:
            return translated_segment_default_lang
    if default_segment_value:
        return default_segment_value
    return segment_key

OUTPUT_DIR = "_site"

def save_page(client, url_path, file_path_obj):
    # En generate_static.py, línea 47
    try:
        print(f"Generando: {url_path} -> {file_path_obj}")
    except BlockingIOError:
        # Puedes simplemente pasar, o registrar de una manera menos propensa a bloquear
        # Por ejemplo, acumulando mensajes y escribiéndolos en lotes, o a un archivo.
        # Pero para un build, a menudo es mejor solo reducir la salida.
        # pass # O un log más simple
        print(f"Intento de E/S bloqueado para: {url_path}")
    try:
        response = client.get(url_path)
        if response.status_code == 200:
            file_path_obj.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path_obj, 'wb') as f:
                f.write(response.data)
        elif response.status_code in [301, 302, 307, 308]:
            print(f"  INFO: {url_path} redirigió (status {response.status_code}). Contenido de la página final guardado.")
        elif response.status_code == 404:
            print(f"  AVISO 404: {url_path} no encontrado. No se guardó el archivo.")
        else:
            print(f"  Error {response.status_code} para {url_path}")
    except Exception as e:
        print(f"  EXCEPCIÓN generando {url_path}: {e}")

def main():
    app_instance = create_app()
    
    LANGUAGES = app_instance.config.get('SUPPORTED_LANGUAGES', ['en'])
    DEFAULT_LANGUAGE = app_instance.config.get('DEFAULT_LANGUAGE', 'en')
    URL_SEGMENT_TRANSLATIONS = app_instance.config.get('URL_SEGMENT_TRANSLATIONS', {})
    
    books_for_generation = app_instance.books_data 
    if not books_for_generation:
        print("ERROR CRÍTICO: No hay datos de libros (app_instance.books_data está vacío). Saliendo.")
        return

    print("Iniciando generación del sitio estático...")
    if Path(OUTPUT_DIR).exists():
        shutil.rmtree(OUTPUT_DIR)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    print(f"Directorio de salida creado/limpiado: {OUTPUT_DIR}")

    # Copiar archivos estáticos
    static_folder_path = Path(app_instance.static_folder)
    if static_folder_path.exists() and static_folder_path.is_dir():
        static_output_dir_name = Path(app_instance.static_url_path.strip('/'))
        static_output_dir = Path(OUTPUT_DIR) / static_output_dir_name
        
        if static_output_dir.exists(): # Comprobar si el destino existe
            shutil.rmtree(static_output_dir) # Eliminarlo si existe
        shutil.copytree(static_folder_path, static_output_dir) # Copiar sin dirs_exist_ok
        print(f"Carpeta estática '{static_folder_path.name}' copiada a '{static_output_dir}'")
    else:
        print(f"ADVERTENCIA: Carpeta estática no encontrada en {static_folder_path}")

    # Copiar archivos de la carpeta 'public' (si existe)
    public_folder_path = Path("public")
    if public_folder_path.exists() and public_folder_path.is_dir():
        public_output_dir = Path(OUTPUT_DIR)
        for item in public_folder_path.iterdir():
            if item.is_file():
                try:
                    shutil.copy2(item, public_output_dir / item.name)
                except Exception as e:
                    print(f"  ERROR copiando archivo público {item.name}: {e}")
            elif item.is_dir():
                print(f"  AVISO: Subdirectorio '{item.name}' en 'public/' no copiado automáticamente. Copiar manualmente si es necesario o implementar copia recursiva.")
        print(f"Archivos de la carpeta 'public/' copiados a '{public_output_dir}'")

    with app_instance.app_context():
        with app_instance.test_client() as client:
            print("\nGenerando páginas de índice y robots.txt...")
            save_page(client, "/", Path(OUTPUT_DIR) / "index.html")
            save_page(client, "/robots.txt", Path(OUTPUT_DIR) / "robots.txt")

            for lang in LANGUAGES:
                flask_url_lang_index = f"/{lang}/"
                output_path_lang_index = Path(OUTPUT_DIR) / lang / "index.html"
                save_page(client, flask_url_lang_index, output_path_lang_index)

            print("\nGenerando páginas de detalles de libros...")
            for book_data in books_for_generation:
                author_s = book_data.get('author_slug')
                title_s = book_data.get('title_slug')
                identifier = book_data.get('isbn10') or book_data.get('isbn13') or book_data.get('asin')
                if not (identifier and author_s and title_s): continue
                
                for lang in LANGUAGES:
                    book_segment_translated = get_translated_url_segment_for_generator('book', lang, URL_SEGMENT_TRANSLATIONS, DEFAULT_LANGUAGE, 'book')
                    flask_url = f"/{lang}/{book_segment_translated}/{author_s}/{title_s}/{identifier}/"
                    dir_author_s = author_s if author_s else "unknown-author"
                    dir_title_s = title_s if title_s else "unknown-title"
                    output_path = Path(OUTPUT_DIR) / lang / book_segment_translated / dir_author_s / dir_title_s / identifier / "index.html"
                    save_page(client, flask_url, output_path)
            
            print("\nGenerando páginas de versiones de libros...")
            unique_book_bases_slugs = {}
            for book_data in books_for_generation:
                author_s = book_data.get('author_slug')
                base_title_s = book_data.get('base_title_slug')
                if not (author_s and base_title_s): continue
                unique_book_bases_slugs[(author_s, base_title_s)] = True
            
            for author_s, base_title_s in unique_book_bases_slugs.keys():
                for lang in LANGUAGES:
                    versions_segment_translated = get_translated_url_segment_for_generator('versions', lang, URL_SEGMENT_TRANSLATIONS, DEFAULT_LANGUAGE, 'versions')
                    flask_url = f"/{lang}/{versions_segment_translated}/{author_s}/{base_title_s}/"
                    dir_author_s = author_s if author_s else "unknown-author"
                    dir_base_title_s = base_title_s if base_title_s else "unknown-basetitle"
                    output_path = Path(OUTPUT_DIR) / lang / versions_segment_translated / dir_author_s / dir_base_title_s / "index.html"
                    save_page(client, flask_url, output_path)

            print("\nGenerando páginas de libros por autor...")
            unique_author_slugs = set(b.get('author_slug') for b in books_for_generation if b.get('author_slug'))
            for author_s in unique_author_slugs:
                for lang in LANGUAGES:
                    author_segment_translated = get_translated_url_segment_for_generator('author', lang, URL_SEGMENT_TRANSLATIONS, DEFAULT_LANGUAGE, 'author')
                    flask_url = f"/{lang}/{author_segment_translated}/{author_s}/"
                    dir_author_s = author_s if author_s else "unknown-author"
                    output_path = Path(OUTPUT_DIR) / lang / author_segment_translated / dir_author_s / "index.html"
                    save_page(client, flask_url, output_path)

            print("\nGenerando sitemap.xml y test_sitemap.html...")
            save_page(client, "/sitemap.xml", Path(OUTPUT_DIR) / "sitemap.xml")
            save_page(client, "/test/", Path(OUTPUT_DIR) / "test_sitemap" / "index.html")

    print(f"\nSitio estático generado con éxito en la carpeta: {OUTPUT_DIR}")
    print("IMPORTANTE: Revisa las URLs generadas y las rutas de guardado, especialmente para los segmentos traducidos.")

if __name__ == '__main__':
    # Opcional: Comprobar la versión de Python para dar una advertencia más amigable sobre dirs_exist_ok
    # python_version = sys.version_info
    # if python_version < (3, 8):
    #     print(f"ADVERTENCIA: Estás usando Python {python_version.major}.{python_version.minor}. "
    #           "El argumento 'dirs_exist_ok' para shutil.copytree no está disponible. "
    #           "El script usa una alternativa (rmtree + copytree).")
    main()
