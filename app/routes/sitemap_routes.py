# app/routes/sitemap_routes.py
from flask import (
    Blueprint,
    make_response,
    current_app,
    url_for,
    abort
)
from datetime import datetime, timezone

sitemap_bp = Blueprint('sitemap', __name__)

# Constantes deben coincidir con generate_static.py
ALPHABET = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_CHARS_SITEMAP_KEY = "0"  # Para no alfabéticos (ej. slugs que empiezan con número o símbolo)


def get_books_data():
    return current_app.books_data if hasattr(current_app, 'books_data') else []


def get_supported_languages():
    return current_app.config.get('SUPPORTED_LANGUAGES', ['en'])


def get_default_language():
    return current_app.config.get('DEFAULT_LANGUAGE', 'en')


def get_sitemap_char_group_for_author(author_slug_val):
    """Determina a qué grupo de sitemap (letra o especial) pertenece un slug de autor."""
    if not author_slug_val:
        return SPECIAL_CHARS_SITEMAP_KEY  # O None si prefieres no agrupar autores sin slug
    first_char = author_slug_val[0].lower()
    if first_char in ALPHABET:
        return first_char
    return SPECIAL_CHARS_SITEMAP_KEY


@sitemap_bp.route('/sitemap.xml')
def sitemap_index():
    """Genera el sitemap_index.xml que enlaza a todos los sitemaps individuales."""
    sitemaps_to_include = []
    supported_langs = get_supported_languages()
    current_formatted_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    # 1. Sitemaps "core" por idioma
    for lang_code in supported_langs:
        sitemaps_to_include.append({
            'loc': url_for('sitemap.sitemap_language_core', lang_code=lang_code, _external=True),
            'lastmod': current_formatted_date  # Opcional: podrías intentar obtener un lastmod más específico
        })

    chars_for_sitemaps = list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]
    for lang_code in supported_langs:
        for char_key in chars_for_sitemaps:
            sitemaps_to_include.append({
                'loc': url_for(
                    'sitemap.sitemap_language_char_specific',
                    lang_code=lang_code,
                    char_key=char_key,
                    _external=True
                ),
                'lastmod': current_formatted_date  # Opcional
            })

    try:
        template = current_app.jinja_env.get_template('sitemap_index_template.xml')
        sitemap_xml_output = template.render(sitemaps=sitemaps_to_include)
    except Exception as e:
        current_app.logger.error(f"Error al renderizar sitemap_index_template.xml: {e}", exc_info=True)
        return "Error al generar el sitemap index.", 500

    response = make_response(sitemap_xml_output)
    response.headers["Content-Type"] = "application/xml"
    return response


@sitemap_bp.route('/sitemap_<lang_code>_core.xml')
def sitemap_language_core(lang_code):
    """Genera el sitemap para las páginas 'core' de un idioma específico."""
    supported_langs = get_supported_languages()
    default_lang = get_default_language()
    if lang_code not in supported_langs:
        abort(404)

    current_formatted_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    pages = []

    # 1. Página de inicio del idioma
    loc_index = url_for('main.index', lang_code=lang_code, _external=True)
    alternates_index = [
        {'lang': alt_lang, 'href': url_for('main.index', lang_code=alt_lang, _external=True)}
        for alt_lang in supported_langs
    ]
    alternates_index.append({
        'lang': 'x-default',
        'href': url_for('main.index', lang_code=default_lang, _external=True)
    })
    pages.append({
        'loc': loc_index, 'lastmod': current_formatted_date, 'alternates': alternates_index,
        'changefreq': 'daily', 'priority': '1.0'
    })

    if not pages:
        pass  # Dejar que renderice un sitemap vacío si es el caso

    try:
        template = current_app.jinja_env.get_template('sitemap_template.xml')  # Usa la misma plantilla de página
        sitemap_xml_output = template.render(pages=pages)
    except Exception as e:
        current_app.logger.error(f"Error al renderizar sitemap_template.xml para core '{lang_code}': {e}", exc_info=True)
        return f"Error al generar sitemap core para {lang_code}.", 500

    response = make_response(sitemap_xml_output)
    response.headers["Content-Type"] = "application/xml"
    return response


@sitemap_bp.route('/sitemap_<lang_code>_<char_key>.xml')
def sitemap_language_char_specific(lang_code, char_key):  # C901
    """
    Genera el sitemap para un idioma y una clave de carácter específicos (letra o SPECIAL_CHARS_SITEMAP_KEY).
    Incluye libros, versiones y páginas de autor.
    """
    supported_langs = get_supported_languages()
    default_lang = get_default_language()

    if lang_code not in supported_langs:
        abort(404)

    if not (char_key in ALPHABET or char_key == SPECIAL_CHARS_SITEMAP_KEY):
        abort(404)

    current_formatted_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    all_books = get_books_data()
    pages = []

    processed_version_keys = set()  # (author_slug, base_title_slug)
    processed_author_page_slugs = set()  # author_slug

    for book in all_books:
        author_slug = book.get('author_slug')
        book_sitemap_group = get_sitemap_char_group_for_author(author_slug)

        if book_sitemap_group != char_key:
            continue  # Este libro no pertenece a este sitemap de letra/carácter

        book_slug = book.get('title_slug')
        identifier = book.get('isbn13') or book.get('isbn10') or book.get('asin')

        if not (author_slug and book_slug and identifier):
            continue

        # --- 1. Página de Detalle del Libro (book_by_identifier) ---
        loc_book_detail = url_for(
            'main.book_by_identifier',
            lang_code=lang_code,
            author_slug=author_slug,
            book_slug=book_slug,
            identifier=identifier,
            _external=True
        )
        alternates_book_detail = []
        for alt_lang in supported_langs:
            href_val = url_for(
                'main.book_by_identifier', lang_code=alt_lang, author_slug=author_slug,
                book_slug=book_slug, identifier=identifier, _external=True
            )
            alternates_book_detail.append({'lang': alt_lang, 'href': href_val})
        default_href_val = url_for(
            'main.book_by_identifier', lang_code=default_lang, author_slug=author_slug,
            book_slug=book_slug, identifier=identifier, _external=True
        )
        alternates_book_detail.append({'lang': 'x-default', 'href': default_href_val})

        page_entry_book = {
            'loc': loc_book_detail,
            'lastmod': book.get('last_modified_date', current_formatted_date),  # Asume que tienes esta fecha o usa la actual
            'alternates': alternates_book_detail,
            'changefreq': 'monthly',  # O 'yearly' si no cambian mucho
            'priority': '0.8'
        }
        if book.get('image_url'):
            page_entry_book['image_url'] = book['image_url']
            page_entry_book['image_title'] = book.get('title', '')
        pages.append(page_entry_book)

        # --- 2. Página de Versiones del Libro (book_versions) ---
        base_book_slug = book.get('base_title_slug')
        if base_book_slug:  # Solo si tiene un base_title_slug
            version_key = (author_slug, base_book_slug)
            if version_key not in processed_version_keys:
                loc_versions = url_for(
                    'main.book_versions',
                    lang_code=lang_code,
                    author_slug=author_slug,
                    base_book_slug=base_book_slug,
                    _external=True
                )
                alternates_versions = []
                for alt_lang in supported_langs:
                    href_val_versions = url_for(
                        'main.book_versions', lang_code=alt_lang, author_slug=author_slug,
                        base_book_slug=base_book_slug, _external=True
                    )
                    alternates_versions.append({'lang': alt_lang, 'href': href_val_versions})
                default_href_val_versions = url_for(
                    'main.book_versions', lang_code=default_lang, author_slug=author_slug,
                    base_book_slug=base_book_slug, _external=True
                )
                alternates_versions.append({'lang': 'x-default', 'href': default_href_val_versions})

                pages.append({
                    'loc': loc_versions,
                    'lastmod': book.get('last_modified_date', current_formatted_date),  # O una fecha agregada de las versiones
                    'alternates': alternates_versions,
                    'changefreq': 'monthly',
                    'priority': '0.7'
                })
                processed_version_keys.add(version_key)

        # --- 3. Página de Autor (author_books) ---
        if author_slug not in processed_author_page_slugs:
            loc_author = url_for(
                'main.author_books',
                lang_code=lang_code,
                author_slug=author_slug,
                _external=True
            )
            alternates_author = []
            for alt_lang in supported_langs:
                href_val_author = url_for(
                    'main.author_books', lang_code=alt_lang,
                    author_slug=author_slug, _external=True
                )
                alternates_author.append({'lang': alt_lang, 'href': href_val_author})
            default_href_val_author = url_for(
                'main.author_books', lang_code=default_lang,
                author_slug=author_slug, _external=True
            )
            alternates_author.append({'lang': 'x-default', 'href': default_href_val_author})

            pages.append({
                'loc': loc_author,
                'lastmod': current_formatted_date,  # O una fecha basada en la última actualización de un libro del autor
                'alternates': alternates_author,
                'changefreq': 'monthly',
                'priority': '0.6'
            })
            processed_author_page_slugs.add(author_slug)

    if not pages:
        log_message = (
            f"Sitemap para {lang_code} / {char_key} no tiene URLs. "
            "Se generará vacío o no se guardará si hay 404."
        )
        current_app.logger.info(log_message)

    try:
        template = current_app.jinja_env.get_template('sitemap_template.xml')
        sitemap_xml_output = template.render(pages=pages)
    except Exception as e:
        current_app.logger.error(f"Error al renderizar sitemap_template.xml para '{lang_code}_{char_key}': {e}", exc_info=True)
        return f"Error al generar sitemap para {lang_code}_{char_key}.", 500

    response = make_response(sitemap_xml_output)
    response.headers["Content-Type"] = "application/xml"
    return response
