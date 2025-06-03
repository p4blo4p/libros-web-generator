# app/routes/main_routes.py
from flask import (
    Blueprint, render_template, request, abort,
    current_app, redirect, url_for, Response
)
# from jinja2 import Environment, FileSystemLoader  # F401: Unused
from pathlib import Path

# Asumiendo que estas utilidades son accesibles
from app.utils.helpers import is_valid_isbn, is_valid_asin
# Necesitarás una función slugify consistente y la función de grupo de sitemap
from app.utils.helpers import get_sitemap_char_group_for_author, slugify_ascii
# o mover el de generate_static.py
# a un lugar común.

# Para cargar datos de libros específicos para sitemaps de archivos
from app.models.data_loader import load_processed_books as app_load_books


main_bp = Blueprint('main', __name__)

# --- Constantes para sitemaps (podrían estar en config) ---
ALPHABET_SITEMAP = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_CHARS_SITEMAP_KEY_SITEMAP = "0"  # Para evitar confusión con el '0' de generate_static.py


# --- Funciones de Ayuda (existentes, las mantengo por contexto) ---
def get_url_segment(segment_key, lang_code, default_segment_value='book'):
    all_translations = current_app.config.get('URL_SEGMENT_TRANSLATIONS', {})
    segments_for_key = all_translations.get(segment_key, {})
    default_app_lang = current_app.config.get('DEFAULT_LANGUAGE', 'en')
    translated_value = segments_for_key.get(lang_code)
    if translated_value is None and lang_code != default_app_lang:
        translated_value = segments_for_key.get(default_app_lang)
    if translated_value is None:
        translated_value = default_segment_value
    return translated_value


def get_books_data_for_request():
    """
    Obtiene los datos de libros para la solicitud actual.
    Para sitemaps de archivos, esto podría ser sobreescrito por una carga específica.
    """
    return current_app.books_data


def get_bestsellers_data():
    return current_app.bestsellers_data


def get_t_func(lang_code):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    default_app_language_config = current_app.config.get('DEFAULT_LANGUAGE', 'en')
    if lang_code not in supported_languages:
        lang_code = default_app_language_config
    return current_app.translations_manager.get_translation_func(lang_code)


@main_bp.url_defaults
def url_defaults(endpoint, values):  # noqa: C901
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    default_app_language_config = current_app.config.get('DEFAULT_LANGUAGE', 'en')
    lang_code_from_values = values.get('lang_code')
    if lang_code_from_values is None:
        if request and hasattr(request, 'view_args') and 'lang_code' in request.view_args:
            lang_code_from_values = request.view_args['lang_code']
        elif endpoint not in ['main.root_index', 'main.sitemap_index_xml']:  # No añadir lang_code a sitemap.xml
            lang_code_from_values = default_app_language_config

    segments_config_map = current_app.config.get('URL_SEGMENTS_TO_TRANSLATE', {})
    raw_config_for_endpoint = segments_config_map.get(endpoint)
    segments_for_this_endpoint = {}
    if isinstance(raw_config_for_endpoint, dict):
        segments_for_this_endpoint = raw_config_for_endpoint
    elif raw_config_for_endpoint is not None:
        current_app.logger.error(
            f"url_defaults: Misconfiguration for endpoint '{endpoint}'. "
            f"Expected dict, got {type(raw_config_for_endpoint)}. Value: '{raw_config_for_endpoint}'."
        )

    if endpoint not in ['main.root_index', 'main.sitemap_index_xml']:
        values.setdefault('lang_code', lang_code_from_values or default_app_language_config)

    if segments_for_this_endpoint:
        effective_lang_code_for_segments = lang_code_from_values
        if not effective_lang_code_for_segments or effective_lang_code_for_segments not in supported_languages:
            effective_lang_code_for_segments = default_app_language_config

        if endpoint not in ['main.root_index', 'main.sitemap_index_xml']:
            values.setdefault('lang_code', effective_lang_code_for_segments)

        for original_segment_key, target_url_param_name in segments_for_this_endpoint.items():
            translated_segment = get_url_segment(
                original_segment_key,
                effective_lang_code_for_segments,
                default_segment_value=original_segment_key
            )
            values.setdefault(target_url_param_name, translated_segment)


# --- Rutas HTML (existentes) ---
@main_bp.route('/')
def root_index():
    default_lang_config = current_app.config.get('DEFAULT_LANGUAGE', 'en')
    return redirect(url_for('main.index', lang_code=default_lang_config))


@main_bp.route('/<lang_code>/')
def index(lang_code):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        return redirect(url_for('main.index', lang_code=current_app.config.get('DEFAULT_LANGUAGE', 'en')))
    t = get_t_func(lang_code)
    bestsellers = get_bestsellers_data()
    return render_template('index.html', books_data=bestsellers, lang=lang_code, t=t)


@main_bp.route('/<lang_code>/<book_url_segment>/<author_slug>/<book_slug>/<identifier>/')
def book_by_identifier(lang_code, book_url_segment, author_slug, book_slug, identifier):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        abort(404)
    expected_segment = get_url_segment('book', lang_code, 'book')
    if book_url_segment != expected_segment:
        return redirect(
            url_for(
                'main.book_by_identifier', lang_code=lang_code, author_slug=author_slug,
                book_slug=book_slug, identifier=identifier
            ), code=301
        )
    t = get_t_func(lang_code)
    books = get_books_data_for_request()
    if not (is_valid_isbn(identifier) or is_valid_asin(identifier)):
        abort(400)
    found_book = next(
        (b for b in books if b.get('author_slug') == author_slug and
         b.get('title_slug') == book_slug and
         (b.get('isbn10') == identifier or b.get('isbn13') == identifier or b.get('asin') == identifier)),
        None
    )
    if found_book:
        return render_template('book.html', libro=found_book, lang=lang_code, t=t)
    else:
        abort(404)


@main_bp.route('/<lang_code>/<versions_url_segment>/<author_slug>/<base_book_slug>/')
def book_versions(lang_code, versions_url_segment, author_slug, base_book_slug):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        abort(404)
    expected_segment = get_url_segment('versions', lang_code, 'versions')
    if versions_url_segment != expected_segment:
        return redirect(
            url_for(
                'main.book_versions', lang_code=lang_code, author_slug=author_slug,
                base_book_slug=base_book_slug
            ), code=301
        )
    t = get_t_func(lang_code)
    books = get_books_data_for_request()
    matched_versions = [
        b for b in books if b.get('author_slug') == author_slug and
        b.get('base_title_slug') == base_book_slug
    ]
    if matched_versions:
        display_author = matched_versions[0].get('author', author_slug)
        original_title = matched_versions[0].get('title', '')
        display_base_title = original_title.split('(')[0].strip() if original_title else base_book_slug
        if not display_base_title:
            display_base_title = matched_versions[0].get('base_title_slug', base_book_slug)
        return render_template(
            'book_versions.html', books=matched_versions, lang=lang_code, t=t,
            page_author_display=display_author, page_base_title_display=display_base_title
        )
    else:
        abort(404)


@main_bp.route('/<lang_code>/<author_url_segment>/<author_slug>/')
def author_books(lang_code, author_url_segment, author_slug):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        abort(404)
    expected_segment = get_url_segment('author', lang_code, 'author')
    if author_url_segment != expected_segment:
        return redirect(url_for('main.author_books', lang_code=lang_code, author_slug=author_slug), code=301)
    t = get_t_func(lang_code)
    books = get_books_data_for_request()
    matched_books = [b for b in books if b.get('author_slug') == author_slug]
    if matched_books:
        display_author = matched_books[0].get('author', author_slug)
        return render_template(
            'author_books.html', books=matched_books, lang=lang_code, t=t,
            page_author_display=display_author
        )
    else:
        abort(404)


@main_bp.route('/test/')
def test_page():
    return "<h1>Test Page</h1><p>This is a test page for static generation.</p>", 200


# --- Nuevas Rutas para Sitemaps ---

def get_sitemap_char_keys_for_language(app, lang_code):
    """
    Determina los char_keys válidos para los que se pueden generar sitemaps individuales
    para un idioma específico. Esto podría involucrar verificar la existencia de contenido.
    Por ahora, usa la configuración global y la exploración de archivos.
    """
    author_filter_config_key = 'VALID_SITEMAP_CHAR_GROUPS_AUTHOR_FILTER'
    default_author_keys = list(ALPHABET_SITEMAP) + [SPECIAL_CHARS_SITEMAP_KEY_SITEMAP]
    author_filter_keys = list(app.config.get(author_filter_config_key, default_author_keys))

    data_file_keys = []
    books_data_dir_str = app.config.get('BOOKS_DATA_DIR')
    if books_data_dir_str:
        books_data_dir = Path(books_data_dir_str)
        if books_data_dir.is_dir():
            for i in range(100):  # Un límite práctico
                if (books_data_dir / f"books_{i}.csv").exists():
                    data_file_keys.append(str(i))

    all_keys = list(set(author_filter_keys + data_file_keys))
    return sorted(all_keys)


@main_bp.route('/sitemap.xml')
def sitemap_index_xml():
    """
    Genera el sitemap índice principal (sitemap.xml) que apunta a los
    sitemaps de índice de cada idioma (sitemap_<lang>_core.xml).
    """
    langs = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    sitemap_entries = []
    for lang_code in langs:
        loc = url_for('main.sitemap_char_group_xml', lang_code=lang_code, char_group='core', _external=True)
        sitemap_entries.append({'loc': loc})

    xml_template_path = Path(current_app.template_folder) / 'sitemap_index.xml'
    if not xml_template_path.exists():
        xml_content = ('<?xml version="1.0" encoding="UTF-8"?>'
                       '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        for entry in sitemap_entries:
            xml_content += f"<sitemap><loc>{entry['loc']}</loc></sitemap>"
        xml_content += '</sitemapindex>'
        return Response(xml_content, mimetype='application/xml')

    return render_template('sitemap_index.xml', sitemaps=sitemap_entries)


@main_bp.route('/sitemap_<lang_code>_<char_group>.xml')  # noqa: C901
def sitemap_char_group_xml(lang_code, char_group):
    supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    if lang_code not in supported_languages:
        abort(404, description=f"Idioma '{lang_code}' no soportado para sitemap.")

    all_individual_sitemap_keys_for_lang = get_sitemap_char_keys_for_language(current_app, lang_code)

    if char_group == 'core':
        sitemap_entries = []
        for key in all_individual_sitemap_keys_for_lang:
            loc = url_for('main.sitemap_char_group_xml', lang_code=lang_code, char_group=key, _external=True)
            sitemap_entries.append({'loc': loc})

        xml_template_path = Path(current_app.template_folder) / 'sitemap_index.xml'
        if not xml_template_path.exists():
            xml_content = ('<?xml version="1.0" encoding="UTF-8"?>'
                           '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
            for entry in sitemap_entries:
                xml_content += f"<sitemap><loc>{entry['loc']}</loc></sitemap>"
            xml_content += '</sitemapindex>'
            return Response(xml_content, mimetype='application/xml')
        return render_template('sitemap_index.xml', sitemaps=sitemap_entries)

    else:
        urls = []
        books_for_sitemap = []
        is_author_filter_key = char_group in list(ALPHABET_SITEMAP) + [SPECIAL_CHARS_SITEMAP_KEY_SITEMAP]
        is_data_file_key = char_group.isdigit()

        if is_data_file_key:
            current_app.logger.debug(f"Sitemap: char_group '{char_group}' es data_file_key. Cargando books_{char_group}.csv.")
            books_data_dir = current_app.config.get('BOOKS_DATA_DIR')
            if books_data_dir:
                try:
                    books_for_sitemap = app_load_books(books_data_dir, filename_filter_key=char_group)
                    current_app.logger.info(
                        f"Cargados {len(books_for_sitemap)} libros desde books_{char_group}.csv para sitemap."
                    )
                except Exception as e:
                    current_app.logger.error(f"Error cargando books_{char_group}.csv para sitemap: {e}")
                    books_for_sitemap = []
            else:
                current_app.logger.warning(
                    f"BOOKS_DATA_DIR no configurado, no se pueden cargar datos para sitemap de archivo '{char_group}'."
                )
                books_for_sitemap = []

            if not books_for_sitemap and char_group not in all_individual_sitemap_keys_for_lang:
                current_app.logger.warning(
                    f"No se encontraron datos ni definición para sitemap char_group '{char_group}', lang '{lang_code}'."
                )
                abort(404)

        elif is_author_filter_key:
            all_books_in_context = get_books_data_for_request()
            current_app.logger.debug(
                f"Sitemap: char_group '{char_group}' es author_filter_key. "
                f"Usando {len(all_books_in_context)} libros en contexto."
            )
            for book in all_books_in_context:
                author_sitemap_group = get_sitemap_char_group_for_author(book.get('author_slug'), slugify_ascii)
                if author_sitemap_group == char_group:
                    books_for_sitemap.append(book)
            current_app.logger.info(
                f"Encontrados {len(books_for_sitemap)} libros para filtro de autor '{char_group}' en sitemap."
            )

        else:
            current_app.logger.warning(
                f"Sitemap: char_group '{char_group}' no reconocido como filtro de autor ni de archivo de datos."
            )
            if char_group not in all_individual_sitemap_keys_for_lang:
                abort(404, description=f"Sitemap char_group '{char_group}' no válido para idioma '{lang_code}'.")

        processed_authors = set()
        processed_versions = set()

        for book in books_for_sitemap:
            try:
                book_url = url_for(
                    'main.book_by_identifier',
                    lang_code=lang_code,
                    author_slug=book.get('author_slug'),
                    book_slug=book.get('title_slug'),
                    identifier=(book.get('isbn10') or book.get('isbn13') or book.get('asin')),
                    _external=True
                )
                urls.append({'loc': book_url, 'lastmod': book.get('last_modified_sitemap_date')})
            except Exception as e:
                current_app.logger.error(f"Error generando URL de libro para sitemap: {book.get('title')} - {e}")

            author_s = book.get('author_slug')
            if author_s and author_s not in processed_authors:
                try:
                    author_url = url_for('main.author_books', lang_code=lang_code, author_slug=author_s, _external=True)
                    urls.append({'loc': author_url, 'lastmod': book.get('last_modified_sitemap_date')})
                    processed_authors.add(author_s)
                except Exception as e:
                    current_app.logger.error(f"Error generando URL de autor para sitemap: {author_s} - {e}")

            base_title_s = book.get('base_title_slug')
            if author_s and base_title_s and (author_s, base_title_s) not in processed_versions:
                try:
                    versions_url = url_for(
                        'main.book_versions', lang_code=lang_code, author_slug=author_s,
                        base_book_slug=base_title_s, _external=True
                    )
                    urls.append({'loc': versions_url, 'lastmod': book.get('last_modified_sitemap_date')})
                    processed_versions.add((author_s, base_title_s))
                except Exception as e:
                    current_app.logger.error(
                        f"Error generando URL de versiones para sitemap: {author_s}/{base_title_s} - {e}"
                    )

        xml_template_path = Path(current_app.template_folder) / 'sitemap_content.xml'
        if not xml_template_path.exists():
            xml_content = ('<?xml version="1.0" encoding="UTF-8"?>'
                           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
            for url_entry in urls:
                xml_content += f"<url><loc>{url_entry['loc']}</loc>"
                if url_entry.get('lastmod'):
                    xml_content += f"<lastmod>{url_entry['lastmod']}</lastmod>"
                xml_content += "</url>"
            xml_content += '</urlset>'
            return Response(xml_content, mimetype='application/xml')

        return render_template('sitemap_content.xml', urls=urls)

# --- FIN Nuevas Rutas para Sitemaps ---
