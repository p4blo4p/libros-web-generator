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

ALPHABET = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_CHARS_SITEMAP_KEY = "0"


def get_books_data():
    return getattr(current_app, 'books_data', [])


def get_supported_languages():
    return current_app.config.get('SUPPORTED_LANGUAGES', ['en'])


def get_default_language():
    return current_app.config.get('DEFAULT_LANGUAGE', 'en')


def get_sitemap_char_group_for_author(author_slug_val):
    if not author_slug_val:
        return SPECIAL_CHARS_SITEMAP_KEY
    # Asumimos que author_slug_val ya es un slug limpio y en minúsculas
    # Si no, se debería aplicar slugify_ascii aquí también.
    first_char = str(author_slug_val)[0].lower()
    return first_char if first_char in ALPHABET else SPECIAL_CHARS_SITEMAP_KEY


@sitemap_bp.route('/sitemap.xml')
def sitemap_index():
    sitemaps_to_include = []
    supported_langs = get_supported_languages()
    current_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    for lang_code in supported_langs:
        sitemaps_to_include.append({
            'loc': url_for('sitemap.sitemap_language_core', lang_code=lang_code, _external=True),
            'lastmod': current_date_str
        })

    for lang_code in supported_langs:
        for char_key in list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]:
            sitemaps_to_include.append({
                'loc': url_for('sitemap.sitemap_language_char_specific',
                               lang_code=lang_code, char_key=char_key, _external=True),
                'lastmod': current_date_str
            })
    try:
        template = current_app.jinja_env.get_template('sitemap_index_template.xml')
        xml_output = template.render(sitemaps=sitemaps_to_include)
    except Exception as e:
        current_app.logger.error(f"Error renderizando sitemap_index_template.xml: {e}", exc_info=True)
        return "Error generando sitemap index.", 500

    response = make_response(xml_output)
    response.headers["Content-Type"] = "application/xml"
    return response


@sitemap_bp.route('/sitemap_<lang_code>_core.xml')
def sitemap_language_core(lang_code):
    supported_langs = get_supported_languages()
    default_lang = get_default_language()
    if lang_code not in supported_langs:
        abort(404)

    current_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    pages = []
    loc_idx = url_for('main.index', lang_code=lang_code, _external=True)
    alts_idx = [{'lang': alt, 'href': url_for('main.index', lang_code=alt, _external=True)}
                for alt in supported_langs]
    alts_idx.append({'lang': 'x-default',
                     'href': url_for('main.index', lang_code=default_lang, _external=True)})
    pages.append({
        'loc': loc_idx, 'lastmod': current_date_str, 'alternates': alts_idx,
        'changefreq': 'daily', 'priority': '1.0'
    })

    try:
        template = current_app.jinja_env.get_template('sitemap_template.xml')
        xml_output = template.render(pages=pages)
    except Exception as e:
        current_app.logger.error(f"Error renderizando sitemap_template.xml para core '{lang_code}': {e}", exc_info=True)
        return f"Error generando sitemap core para {lang_code}.", 500

    response = make_response(xml_output)
    response.headers["Content-Type"] = "application/xml"
    return response


def _prepare_alternates_for_sitemap_entry(endpoint_name, lang_code_main, default_lang, supported_langs, **kwargs):
    """Prepara la lista de alternates para una entrada del sitemap."""
    loc_main = url_for(endpoint_name, lang_code=lang_code_main, _external=True, **kwargs)
    alternates = []
    for alt_lang_code in supported_langs:
        alternates.append({
            'lang': alt_lang_code,
            'href': url_for(endpoint_name, lang_code=alt_lang_code, _external=True, **kwargs)
        })
    alternates.append({
        'lang': 'x-default',
        'href': url_for(endpoint_name, lang_code=default_lang, _external=True, **kwargs)
    })
    return loc_main, alternates


def _add_book_detail_to_sitemap(book_data, lang_code, default_lang, supported_langs, current_date_str, pages_list):
    author_slug = book_data.get('author_slug')
    book_slug = book_data.get('title_slug')
    identifier = book_data.get('isbn13') or book_data.get('isbn10') or book_data.get('asin')

    if not all([author_slug, book_slug, identifier]):
        return

    loc, alts = _prepare_alternates_for_sitemap_entry(
        'main.book_by_identifier', lang_code, default_lang, supported_langs,
        author_slug=author_slug, book_slug=book_slug, identifier=identifier
    )
    page_entry = {
        'loc': loc,
        'lastmod': book_data.get('last_modified_date', current_date_str),
        'alternates': alts, 'changefreq': 'monthly', 'priority': '0.8'
    }
    if book_data.get('image_url'):
        page_entry['image_url'] = book_data['image_url']
        page_entry['image_title'] = book_data.get('title', '')
    pages_list.append(page_entry)


def _add_book_versions_to_sitemap(book_data, lang_code, default_lang, supported_langs,
                                  current_date_str, pages_list, processed_keys_set):
    author_slug = book_data.get('author_slug')
    base_book_slug = book_data.get('base_title_slug')

    if not (author_slug and base_book_slug):
        return

    version_key = (author_slug, base_book_slug)
    if version_key not in processed_keys_set:
        loc, alts = _prepare_alternates_for_sitemap_entry(
            'main.book_versions', lang_code, default_lang, supported_langs,
            author_slug=author_slug, base_book_slug=base_book_slug
        )
        pages_list.append({
            'loc': loc, 'lastmod': book_data.get('last_modified_date', current_date_str),
            'alternates': alts, 'changefreq': 'monthly', 'priority': '0.7'
        })
        processed_keys_set.add(version_key)


def _add_author_page_to_sitemap(author_slug, lang_code, default_lang, supported_langs,
                                current_date_str, pages_list, processed_slugs_set):
    if author_slug not in processed_slugs_set:
        loc, alts = _prepare_alternates_for_sitemap_entry(
            'main.author_books', lang_code, default_lang, supported_langs,
            author_slug=author_slug
        )
        pages_list.append({
            'loc': loc, 'lastmod': current_date_str,
            'alternates': alts, 'changefreq': 'monthly', 'priority': '0.6'
        })
        processed_slugs_set.add(author_slug)


@sitemap_bp.route('/sitemap_<lang_code>_<char_key>.xml')
def sitemap_language_char_specific(lang_code, char_key):  # noqa: C901
    supported_langs = get_supported_languages()
    default_lang = get_default_language()

    if lang_code not in supported_langs or \
       not (char_key in ALPHABET or char_key == SPECIAL_CHARS_SITEMAP_KEY):
        abort(404)

    current_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    all_books = get_books_data()
    pages = []
    processed_version_keys = set()
    processed_author_page_slugs = set()

    for book in all_books:
        author_slug = book.get('author_slug')
        if get_sitemap_char_group_for_author(author_slug) != char_key:
            continue

        _add_book_detail_to_sitemap(
            book, lang_code, default_lang, supported_langs, current_date_str, pages
        )
        _add_book_versions_to_sitemap(
            book, lang_code, default_lang, supported_langs,
            current_date_str, pages, processed_version_keys
        )
        if author_slug: # Solo añadir página de autor si hay slug de autor
            _add_author_page_to_sitemap(
                author_slug, lang_code, default_lang, supported_langs,
                current_date_str, pages, processed_author_page_slugs
            )

    if not pages:
        current_app.logger.info(
            f"Sitemap para {lang_code} / {char_key} no tiene URLs. Se generará vacío."
        )

    try:
        template = current_app.jinja_env.get_template('sitemap_template.xml')
        xml_output = template.render(pages=pages)
    except Exception as e:
        current_app.logger.error(
            f"Error renderizando sitemap_template.xml para '{lang_code}_{char_key}': {e}", exc_info=True
        )
        return f"Error generando sitemap para {lang_code}_{char_key}.", 500

    response = make_response(xml_output)
    response.headers["Content-Type"] = "application/xml"
    return response
