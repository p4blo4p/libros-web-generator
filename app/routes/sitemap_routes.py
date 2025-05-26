# app/routes/sitemap_routes.py
from flask import (
    Blueprint,
    render_template,  # Usado si renderizas directamente a una plantilla con contexto completo
    render_template_string, # <--- IMPORTACIÓN AÑADIDA
    make_response,
    current_app,
    url_for
)
from datetime import datetime, timezone, timedelta #timedelta podría ser útil para lastmod

sitemap_bp = Blueprint('sitemap', __name__)

# Helper para obtener datos de libros, consistente con main_routes
def get_books_data():
    """Obtiene los datos de los libros desde current_app."""
    return current_app.books_data if hasattr(current_app, 'books_data') else []

# Helper para obtener los idiomas soportados y el idioma por defecto
def get_supported_languages():
    return current_app.config.get('SUPPORTED_LANGUAGES', ['en'])

def get_default_language():
    return current_app.config.get('DEFAULT_LANGUAGE', 'en')


def _generate_sitemap_pages(books_data_subset=None):
    """
    Función interna para generar la lista de páginas para el sitemap.
    Si books_data_subset es None, usa todos los libros.
    Sino, usa el subconjunto proporcionado (para pruebas).
    """
    current_formatted_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Si no se proporciona un subconjunto, obtener todos los libros
    all_books = books_data_subset if books_data_subset is not None else get_books_data()

    supported_langs = get_supported_languages()
    default_lang = get_default_language()

    pages = [] # Lista final de entradas para el sitemap

    # 1. URLs de las páginas de índice
    for lang_code in supported_langs:
        loc = url_for('main.index', lang_code=lang_code, _external=True)
        alternates = []
        for alt_lang in supported_langs:
            alternates.append({
                'lang': alt_lang,
                'href': url_for('main.index', lang_code=alt_lang, _external=True)
            })
        alternates.append({
            'lang': 'x-default',
            'href': url_for('main.index', lang_code=default_lang, _external=True)
        })
        pages.append({
            'loc': loc,
            'lastmod': current_formatted_date,
            'alternates': alternates,
            'changefreq': 'weekly',
            'priority': '1.0'
        })

    # 2. URLs de los libros (book_by_identifier)
    processed_book_keys = set()
    for book in all_books: # Iterar sobre el subconjunto (o todos los libros)
        author_slug = book.get('author_slug')
        book_slug = book.get('title_slug')
        identifier = book.get('isbn13') or book.get('isbn10') or book.get('asin')

        if not (author_slug and book_slug and identifier):
            current_app.logger.debug(f"Sitemap Gen: Skipping book due to missing slugs/identifier: {book.get('title')}")
            continue
        
        book_key = (author_slug, book_slug, identifier)
        if book_key in processed_book_keys:
            continue
        processed_book_keys.add(book_key)

        alternates = []
        primary_loc_for_entry = None
        for lang_code in supported_langs:
            try:
                loc = url_for('main.book_by_identifier',
                              lang_code=lang_code,
                              author_slug=author_slug,
                              book_slug=book_slug,
                              identifier=identifier,
                              _external=True)
                alternates.append({'lang': lang_code, 'href': loc})
                if lang_code == default_lang or not primary_loc_for_entry:
                    primary_loc_for_entry = loc
            except Exception as e:
                current_app.logger.error(f"Sitemap Gen: Error generating URL for book: {e} for book {book.get('title')}")
        
        if primary_loc_for_entry:
            page_data = {
                'loc': primary_loc_for_entry,
                'lastmod': book.get('last_modified_date', current_formatted_date),
                'alternates': alternates,
                'changefreq': 'monthly',
                'priority': '0.8'
            }
            # Añadir x-default a las alternativas
            page_data['alternates'].append({
                'lang': 'x-default',
                'href': url_for('main.book_by_identifier',
                                lang_code=default_lang,
                                author_slug=author_slug,
                                book_slug=book_slug,
                                identifier=identifier,
                                _external=True)
            })
            if book.get('image_url'):
                page_data['image_url'] = book['image_url']
                page_data['image_title'] = book.get('title', '')
            pages.append(page_data)

    # 3. URLs de Páginas de Versiones (book_versions) - OPCIONAL, si las quieres en sitemap
    # processed_version_keys = set()
    # for book in all_books:
    #     author_slug = book.get('author_slug')
    #     base_book_slug = book.get('base_title_slug')
    #     if not (author_slug and base_book_slug): continue
    #     version_key = (author_slug, base_book_slug)
    #     if version_key in processed_version_keys: continue
    #     processed_version_keys.add(version_key)
    #     # ... Lógica similar para generar 'loc' y 'alternates' para páginas de versiones ...
    #     # pages.append({ ... 'changefreq': 'monthly', 'priority': '0.7' ... })

    # 4. URLs de Páginas de Autor (author_books) - OPCIONAL, si las quieres en sitemap
    # processed_author_keys = set()
    # for book in all_books:
    #     author_slug = book.get('author_slug')
    #     if not author_slug: continue
    #     if author_slug in processed_author_keys: continue
    #     processed_author_keys.add(author_slug)
    #     # ... Lógica similar para generar 'loc' y 'alternates' para páginas de autor ...
    #     # pages.append({ ... 'changefreq': 'monthly', 'priority': '0.6' ... })
            
    return pages


@sitemap_bp.route('/sitemap.xml')
def sitemap_xml_full():
    """Genera el sitemap XML completo para todos los libros y páginas."""
    if not current_app.config.get('SERVER_NAME'):
        current_app.logger.warning("SERVER_NAME no está configurado. Las URLs del sitemap podrían ser relativas.")

    pages_data = _generate_sitemap_pages() # Llama al helper con todos los libros

    # Renderizar usando la plantilla que espera la lista 'pages'
    # Asegúrate que 'sitemap_template.xml' está en tu carpeta de plantillas
    try:
        template = current_app.jinja_env.get_template('sitemap_template.xml')
        sitemap_xml_output = template.render(pages=pages_data)
    except Exception as e:
        current_app.logger.error(f"Error al renderizar sitemap_template.xml: {e}")
        return "Error al generar el sitemap.", 500

    response = make_response(sitemap_xml_output)
    response.headers["Content-Type"] = "application/xml"
    return response


@sitemap_bp.route('/sitemap_test.xml')
def sitemap_test_xml():
    """Genera un sitemap XML de prueba solo con los primeros N libros."""
    if not current_app.config.get('SERVER_NAME'):
        current_app.logger.warning("SERVER_NAME no está configurado. Las URLs del sitemap (test) podrían ser relativas.")

    num_test_books = 5
    test_books_subset = get_books_data()[:num_test_books] # Tomar solo N libros

    pages_data = _generate_sitemap_pages(books_data_subset=test_books_subset) # Llama al helper con el subconjunto

    try:
        template = current_app.jinja_env.get_template('sitemap_template.xml')
        sitemap_xml_output = template.render(pages=pages_data)
    except Exception as e:
        current_app.logger.error(f"Error al renderizar sitemap_template.xml para prueba: {e}")
        return "Error al generar el sitemap de prueba.", 500
    
    response = make_response(sitemap_xml_output)
    response.headers["Content-Type"] = "application/xml"
    return response