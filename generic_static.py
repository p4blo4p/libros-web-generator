import os
import shutil
import urllib.parse
from pathlib import Path

# Asegúrate de que tu_app_flask.py se pueda importar
# Esto podría requerir ajustar sys.path si está en una subcarpeta o es un módulo
# from nombre_de_tu_archivo_flask import app, books, bestsellers
from app import app, books, bestsellers#, slugify # Asumiendo que el archivo es tu_app_flask.py

# Configuración
OUTPUT_DIR = "_site"
LANGUAGES = ['en', 'es']
# Para url_for(_external=True) en el sitemap, si no está en app.config
# app.config['SERVER_NAME'] = 'yourdomain.com' # O localhost:5000
# app.config['APPLICATION_ROOT'] = '/'
# app.config['PREFERRED_URL_SCHEME'] = 'http' # o https


def save_page(client, url_path, file_path):
    """
    Solicita una página y la guarda en un archivo.
    """
    print(f"Generando: {url_path} -> {file_path}")
    try:
        response = client.get(url_path)
        if response.status_code == 200:
            # Asegúrate de que el directorio exista
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'wb') as f: # 'wb' para escribir bytes directamente
                f.write(response.data)
        else:
            print(f"  Error {response.status_code} para {url_path}")
    except Exception as e:
        print(f"  Excepción generando {url_path}: {e}")


# ... (resto del script generate_static.py arriba de esto) ...

def main():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)

    # Copiar archivos estáticos (CSS, JS, imágenes) - MODIFICADO PARA COMPATIBILIDAD
    static_folder_app = Path(app.static_folder) # app.static_folder es la ruta absoluta
    if static_folder_app.exists() and static_folder_app.is_dir():
        # El nombre de la carpeta de destino debe ser el mismo que app.static_url_path
        # Por defecto es /static, así que copiamos a OUTPUT_DIR/static
        static_output_dir = Path(OUTPUT_DIR) / static_folder_app.name

        # Para compatibilidad con Python < 3.8 (sin dirs_exist_ok=True)
        # Primero, si el directorio de destino ya existe, lo eliminamos.
        if static_output_dir.exists():
            shutil.rmtree(static_output_dir)
        
        # Luego, copiamos el árbol de directorios.
        # Si static_output_dir no existía, copytree lo creará.
        # Si existía, lo acabamos de eliminar, así que copytree también lo creará.
        shutil.copytree(static_folder_app, static_output_dir)
        print(f"Carpeta estática copiada a {static_output_dir}")
    else:
        print(f"Advertencia: No se encontró la carpeta estática en {static_folder_app} o no es un directorio.")

    with app.app_context(): # Necesario para url_for si SERVER_NAME está configurado
        with app.test_client() as client:
            # 1. Páginas de índice
            for lang in LANGUAGES:
                url = f"/?lang={lang}"
                output_path = Path(OUTPUT_DIR) / lang / "index.html"
                save_page(client, url, output_path)
                if lang == 'en': # Default language
                    save_page(client, "/", Path(OUTPUT_DIR) / "index.html")


            # 2. Páginas de detalles de libros (por identificador)
            for book_data in books:
                author_slug = slugify(book_data['author'])
                title_slug = slugify(book_data['title']) # El título completo puede tener (Edition)
                
                identifier = book_data.get('isbn10') or book_data.get('isbn13') or book_data.get('asin')
                if not identifier:
                    print(f"Advertencia: El libro '{book_data['title']}' no tiene identificador, omitiendo página de detalle.")
                    continue

                for lang in LANGUAGES:
                    # Usamos los valores originales (no slug) para los parámetros de la URL de Flask
                    # Flask/Werkzeug se encargará de la codificación/decodificación de URL
                    flask_url = f"/{urllib.parse.quote(book_data['author'])}/{urllib.parse.quote(book_data['title'])}/{identifier}/?lang={lang}"
                    
                    # Para la estructura de archivos, usamos slugs para nombres de directorio
                    output_path = Path(OUTPUT_DIR) / lang / author_slug / title_slug / identifier / "index.html"
                    save_page(client, flask_url, output_path)

            # 3. Páginas de versiones de libros
            # Necesitamos encontrar combinaciones únicas de (autor, título base)
            unique_book_bases = {} # (author, base_title) -> True
            for book_data in books:
                base_title = book_data['title'].split('(')[0].strip() # "1984" de "1984 (Spanish Edition)"
                if not base_title: continue
                unique_key = (book_data['author'], base_title)
                unique_book_bases[unique_key] = True
            
            for author, base_title in unique_book_bases.keys():
                author_slug = slugify(author)
                base_title_slug = slugify(base_title)
                for lang in LANGUAGES:
                    flask_url = f"/{urllib.parse.quote(author)}/{urllib.parse.quote(base_title)}/?lang={lang}"
                    output_path = Path(OUTPUT_DIR) / lang / author_slug / base_title_slug / "index.html" # Ojo, aquí el "index.html" representa la página de versiones
                    save_page(client, flask_url, output_path)


            # 4. Páginas de libros por autor
            unique_authors = set(b['author'] for b in books if b.get('author'))
            for author in unique_authors:
                author_slug = slugify(author)
                for lang in LANGUAGES:
                    flask_url = f"/{urllib.parse.quote(author)}/?lang={lang}"
                    output_path = Path(OUTPUT_DIR) / lang / author_slug / "index.html" # Este index.html es para la lista de libros del autor
                    save_page(client, flask_url, output_path)

            # 5. Sitemap.xml
            # La ruta `/sitemap.xml` ya está configurada para usar `SERVER_NAME` si está presente.
            sitemap_url = "/sitemap.xml"
            sitemap_path = Path(OUTPUT_DIR) / "sitemap.xml"
            print(f"Generando: {sitemap_url} -> {sitemap_path}")
            response = client.get(sitemap_url)
            if response.status_code == 200:
                with open(sitemap_path, 'wb') as f:
                    f.write(response.data)
            else:
                print(f"  Error {response.status_code} para {sitemap_url}")

            # 6. (Opcional) test_sitemap.html si lo necesitas estático
            test_sitemap_url = "/test/"
            test_sitemap_path = Path(OUTPUT_DIR) / "test_sitemap" / "index.html" # O simplemente test.html
            save_page(client, test_sitemap_url, test_sitemap_path)


    print(f"Sitio estático generado en la carpeta: {OUTPUT_DIR}")

if __name__ == '__main__':
    main()