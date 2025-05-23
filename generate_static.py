# generate_static.py
import os
import shutil
from pathlib import Path
import re
from unidecode import unidecode

# Importar la fábrica de la aplicación
# Asegúrate de que el directorio raíz del proyecto esté en PYTHONPATH si es necesario
# o ejecuta este script desde el directorio raíz.
try:
    from app import create_app
except ImportError as e:
    print(f"ERROR: No se pudo importar 'create_app' desde 'app'. Detalles: {e}")
    print("Asegúrate de que el script se ejecuta desde el directorio raíz del proyecto y que 'app' es un paquete accesible.")
    exit(1)


# --- FUNCIÓN SLUGIFY (Debe ser idéntica a la de app/utils/helpers.py) ---
# Idealmente, esta función se importaría para evitar duplicación.
# from app.utils.helpers import slugify_ascii
def slugify_ascii(text):
    if text is None: return ""
    text = str(text); text = unidecode(text); text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text); text = re.sub(r'\s+', '-', text)
    text = re.sub(r'--+', '-', text); text = text.strip('-')
    return text if text else "na"

# Configuración (DEBE SER CONSISTENTE CON main_routes.py y app.config)
OUTPUT_DIR = "_site"
LANGUAGES = ['en', 'es', 'fr', 'it', 'de'] # Lista de idiomas a generar
DEFAULT_LANGUAGE = 'en' # Idioma por defecto para la ruta raíz

def save_page(client, url_path, file_path_obj):
    """Solicita una página y la guarda en un archivo."""
    print(f"Generando: {url_path} -> {file_path_obj}")
    try:
        response = client.get(url_path)
        if response.status_code == 200:
            file_path_obj.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path_obj, 'wb') as f:
                f.write(response.data)
        elif response.status_code == 302 or response.status_code == 301 : # Manejar redirecciones
            print(f"  INFO: {url_path} redirigió (status {response.status_code}). Se sigue la redirección por el cliente.")
            # El test_client de Flask sigue las redirecciones por defecto si no se indica lo contrario.
            # Si la redirección lleva a una página que también generamos, está bien.
            # Si la página raíz '/' redirige a '/en/', el client.get('/') generará el contenido de '/en/'.
        elif response.status_code == 404:
            print(f"  AVISO 404: {url_path} no encontrado. No se guardó el archivo.")
        else:
            print(f"  Error {response.status_code} para {url_path}")
    except Exception as e:
        print(f"  EXCEPCIÓN generando {url_path}: {e}")


def main():
    app_instance = create_app() # Crear instancia de la app
    
    # Obtener datos de libros de la instancia de la app
    books_for_generation = app_instance.books_data 
    if not books_for_generation:
        print("ERROR CRÍTICO: No hay datos de libros (app_instance.books_data está vacío). Saliendo.")
        return

    print("Iniciando generación del sitio estático...")
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    print(f"Directorio de salida creado: {OUTPUT_DIR}")

    # Copiar archivos estáticos
    static_folder_path = Path(app_instance.static_folder) # Ruta absoluta
    if static_folder_path.exists() and static_folder_path.is_dir():
        # El nombre de la carpeta de destino debe ser el mismo que app.static_url_path
        static_output_dir_name = Path(app_instance.static_url_path.strip('/'))
        static_output_dir = Path(OUTPUT_DIR) / static_output_dir_name
        
        if static_output_dir.exists() and static_output_dir.is_dir(): # Compatibilidad < 3.8
            shutil.rmtree(static_output_dir)
        shutil.copytree(static_folder_path, static_output_dir)
        print(f"Carpeta estática '{static_folder_path.name}' copiada a '{static_output_dir}'")
    else:
        print(f"ADVERTENCIA: Carpeta estática no encontrada en {static_folder_path}")

    with app_instance.app_context():
        with app_instance.test_client() as client:
            # 1. Páginas de índice
            print("\nGenerando páginas de índice...")
            # Generar la página raíz (/)
            # El test_client seguirá la redirección a /DEFAULT_LANGUAGE/
            # y guardará el contenido de esa página en _site/index.html
            save_page(client, "/", Path(OUTPUT_DIR) / "index.html")
            save_page(client, "/robots.txt", Path(OUTPUT_DIR) / "robots.txt")

            for lang in LANGUAGES:
                # Generar la página de índice específica del idioma (ej. /en/, /es/)
                flask_url_lang_index = f"/{lang}/"
                output_path_lang_index = Path(OUTPUT_DIR) / lang / "index.html"
                save_page(client, flask_url_lang_index, output_path_lang_index)

            # 2. Páginas de detalles de libros
            print("\nGenerando páginas de detalles de libros...")
            for book_data in books_for_generation:
                author_s = book_data.get('author_slug')
                title_s = book_data.get('title_slug')
                identifier = book_data.get('isbn10') or book_data.get('isbn13') or book_data.get('asin')

                if not (identifier and author_s and title_s): 
                    # print(f"  Aviso: Datos insuficientes para generar URL de libro: {book_data.get('title')}")
                    continue
                
                for lang in LANGUAGES:
                    flask_url = f"/{lang}/book/{author_s}/{title_s}/{identifier}/"
                    dir_author_s = author_s if author_s else "unknown-author"
                    dir_title_s = title_s if title_s else "unknown-title"
                    output_path = Path(OUTPUT_DIR) / lang / "book" / dir_author_s / dir_title_s / identifier / "index.html"
                    save_page(client, flask_url, output_path)
            
            # 3. Páginas de versiones de libros
            print("\nGenerando páginas de versiones de libros...")
            unique_book_bases_slugs = {}
            for book_data in books_for_generation:
                author_s = book_data.get('author_slug')
                base_title_s = book_data.get('base_title_slug')
                if not (author_s and base_title_s): continue
                unique_book_bases_slugs[(author_s, base_title_s)] = True
            
            for author_s, base_title_s in unique_book_bases_slugs.keys():
                for lang in LANGUAGES:
                    flask_url = f"/{lang}/versions/{author_s}/{base_title_s}/"
                    dir_author_s = author_s if author_s else "unknown-author"
                    dir_base_title_s = base_title_s if base_title_s else "unknown-basetitle"
                    output_path = Path(OUTPUT_DIR) / lang / "versions" / dir_author_s / dir_base_title_s / "index.html"
                    save_page(client, flask_url, output_path)

            # 4. Páginas de libros por autor
            print("\nGenerando páginas de libros por autor...")
            unique_author_slugs = set(b.get('author_slug') for b in books_for_generation if b.get('author_slug'))
            for author_s in unique_author_slugs:
                for lang in LANGUAGES:
                    flask_url = f"/{lang}/author/{author_s}/"
                    dir_author_s = author_s if author_s else "unknown-author"
                    output_path = Path(OUTPUT_DIR) / lang / "author" / dir_author_s / "index.html"
                    save_page(client, flask_url, output_path)

            # 5. Sitemap y Test Sitemap
            # Estas rutas en Flask no tienen <lang_code> en su definición, así que se llaman tal cual.
            # El contenido del sitemap.xml SÍ debe generar URLs con <lang_code>.
            print("\nGenerando sitemap.xml y test_sitemap.html...")
            save_page(client, "/sitemap.xml", Path(OUTPUT_DIR) / "sitemap.xml")
            # La ruta /test/ en sitemap_routes.py no tiene <lang_code>
            save_page(client, "/test/", Path(OUTPUT_DIR) / "test_sitemap" / "index.html")

    print(f"\nSitio estático generado con éxito en la carpeta: {OUTPUT_DIR}")

if __name__ == '__main__':
    main()