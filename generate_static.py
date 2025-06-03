# generate_static.py
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging
import os
from multiprocessing import Pool, cpu_count, current_process
# from functools import partial  # No se usa partial con starmap
import argparse
import json
import hashlib
import time

# --- Carga de .env ---
try:
    from dotenv import load_dotenv
    dotenv_path_script_dir = Path(__file__).resolve().parent / '.env'
    dotenv_path_parent_dir = Path(__file__).resolve().parent.parent / '.env'
    dotenv_to_load = None
    if dotenv_path_script_dir.exists():
        dotenv_to_load = dotenv_path_script_dir
    elif dotenv_path_parent_dir.exists():
        dotenv_to_load = dotenv_path_parent_dir

    if dotenv_to_load:
        print(f"[generate_static.py] Loading .env file from: {dotenv_to_load}")
        load_dotenv(dotenv_path=dotenv_to_load, override=True)
    else:
        print("[generate_static.py] .env file not found. Using system environment variables.")
except ImportError:
    print("[generate_static.py] python-dotenv not found, .env file will not be loaded.")

# --- Configuración del Logger ---
script_logger = logging.getLogger('generate_static_script')
if not script_logger.handlers:
    log_level_name_env = os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper()
    log_level_env = getattr(logging, log_level_name_env, logging.INFO)
    script_logger.setLevel(log_level_env)
    script_handler = logging.StreamHandler()
    script_formatter = logging.Formatter(
        '%(asctime)s - %(name)s:%(processName)s - %(levelname)s - '
        '[%(funcName)s:%(lineno)d] - %(message)s'
    )
    script_handler.setFormatter(script_formatter)
    script_logger.addHandler(script_handler)
    script_logger.propagate = False
else:
    log_level_name_env = os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper()
    script_logger.setLevel(getattr(logging, log_level_name_env, logging.INFO))
script_logger.info(f"Logger principal: Nivel {logging.getLevelName(script_logger.level)}")

worker_app_instance, worker_logger, slugify_to_use_global_worker = None, None, None
MANIFEST_DIR, MANIFEST_FILE = Path(".cache"), Path(".cache/generation_manifest.json")
OUTPUT_DIR = Path(os.environ.get('STATIC_SITE_OUTPUT_DIR', '_site'))
ALPHABET, SPECIAL_CHARS_SITEMAP_KEY = "abcdefghijklmnopqrstuvwxyz", "0"


def slugify_ascii_local(text):
    if text is None:
        return ""
    # Aplicar unidecode, convertir a minúsculas, reemplazar no alfanuméricos (excepto espacios y guiones) por nada
    s = re.sub(r'[^\w\s-]', '', unidecode(str(text)).lower())
    # Reemplazar espacios con guiones, luego múltiples guiones con uno solo, y quitar guiones al inicio/final
    return re.sub(r'--+', '-', re.sub(r'\s+', '-', s)).strip('-') or "na"


slugify_to_use_global_main = slugify_ascii_local
try:
    from app.utils.helpers import slugify_ascii as slugify_app
    slugify_to_use_global_main = slugify_app
    script_logger.info("Principal: slugify de app.utils.helpers.")
except ImportError:
    script_logger.warning("Principal: slugify local.")


def get_sitemap_char_group_for_author(name_or_slug, slugifier_func):
    if not name_or_slug:
        return SPECIAL_CHARS_SITEMAP_KEY
    slug = slugifier_func(str(name_or_slug))
    script_logger.debug(f"get_sitemap_char_group: Input='{name_or_slug}', Slug='{slug}' (con {slugifier_func.__name__})")
    if not slug:
        return SPECIAL_CHARS_SITEMAP_KEY
    char = slug[0].lower()
    res = char if char in ALPHABET else SPECIAL_CHARS_SITEMAP_KEY
    script_logger.debug(f"get_sitemap_char_group: PrimerChar='{char}', Grupo='{res}'")
    return res


def get_translated_url_segment_for_generator(key, lang, trans, def_lang, def_val=None):
    default_res = def_val if def_val is not None else key
    if not trans or not isinstance(trans, dict):
        return default_res
    segs = trans.get(key, {})
    if not isinstance(segs, dict):
        return default_res
    val = segs.get(lang)
    if val:
        return val
    if lang != def_lang:
        val_dl = segs.get(def_lang)
        if val_dl:
            return val_dl
    return default_res


def load_manifest():
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            script_logger.warning(f"Error decodificando {MANIFEST_FILE}.")
    else:
        script_logger.info(f"Manifest {MANIFEST_FILE} no encontrado.")
    return {}


def save_manifest(data):
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    script_logger.info(f"Manifest guardado ({len(data)} entradas).")


def get_book_signature_fields(data):
    fields = {
        "isbn10": data.get("isbn10"),
        "isbn13": data.get("isbn13"),
        "asin": data.get("asin"),
        "title_slug": data.get("title_slug"),
        "author_slug": data.get("author_slug"),
        "description": data.get("description_short") or data.get("description"),
        "cover_image_url": (data.get("image_url_l") or data.get("image_url_m") or data.get("image_url_s")),
        "publication_date": data.get("publication_date"),
        "publisher": data.get("publisher_name"),
        "language_code": data.get("language_code")
    }
    return dict(sorted(fields.items()))


def calculate_signature(data):
    return hashlib.md5(json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def should_regenerate_page(path_str, sig, manifest, log):
    entry = manifest.get(path_str)
    if not entry:
        log.debug(f"REGEN (nuevo): {path_str}")
        return True
    if entry.get('signature') != sig:
        log.debug(f"REGEN (firma): {path_str}")
        return True
    if not Path(path_str).exists():
        log.debug(f"REGEN (no existe): {path_str}")
        return True
    log.debug(f"SALTAR: {path_str}")
    return False


def _save_page_local(client, url, path_obj, log):
    try:
        resp = client.get(url)
        if resp.status_code == 200:
            if resp.data:
                path_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(path_obj, 'wb') as f:
                    f.write(resp.data)
                log.info(f"GENERADO: {url} -> {path_obj}")
            else:
                log.info(f"URL {url} 200 sin datos.")
        elif 300 <= resp.status_code < 400:
            log.warning(f"{url} REDIR {resp.status_code} -> {resp.headers.get('Location')}. NO guardado.")
        elif resp.status_code == 404:
            log.warning(f"404: {url}. NO guardado.")
        else:
            log.error(f"HTTP {resp.status_code} para {url}. NO guardado.")
    except Exception:
        log.exception(f"EXCEPCIÓN {url}")


def worker_init():
    global worker_app_instance, worker_logger, slugify_to_use_global_worker
    # Asegurarse de que create_app sea importable
    from app import create_app  # Suponiendo que app está en el PYTHONPATH o es un módulo instalable
    os.environ['IS_STATIC_GENERATION_WORKER'] = '1'
    proc_name = current_process().name
    worker_app_instance = create_app()
    worker_logger = logging.getLogger(f'gsw.{proc_name.split("-")[-1]}')
    if worker_logger.hasHandlers():
        worker_logger.handlers.clear()
    h = logging.StreamHandler()
    fmtr = logging.Formatter('%(asctime)s-%(name)s-%(levelname)s-%(message)s')
    h.setFormatter(fmtr)
    worker_logger.addHandler(h)
    lvl_name = os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper()
    worker_logger.setLevel(getattr(logging, lvl_name, logging.INFO))
    worker_logger.propagate = False
    slugify_to_use_global_worker = slugify_ascii_local
    try:
        from app.utils.helpers import slugify_ascii as slugify_app_w
        slugify_to_use_global_worker = slugify_app_w
        worker_logger.debug("Worker: slugify de app.")
    except ImportError:
        worker_logger.warning("Worker: slugify local.")
    worker_logger.info(
        f"Worker inicializado. Slug: {slugify_to_use_global_worker.__name__}. "
        f"Log: {logging.getLevelName(worker_logger.level)}"
    )


def _generate_task_common(item_data, cfg_manifest_tuple, page_type):  # noqa: C901
    config_params, manifest_data_global, *_ = cfg_manifest_tuple
    LANGUAGES = config_params['LANGUAGES']
    DEFAULT_LANGUAGE = config_params['DEFAULT_LANGUAGE']
    URL_SEGMENT_TRANSLATIONS = config_params['URL_SEGMENT_TRANSLATIONS']
    OUTPUT_DIR_BASE = Path(config_params['OUTPUT_DIR'])
    FORCE_REGENERATE = config_params.get('FORCE_REGENERATE_ALL', False)
    ALL_BOOKS = config_params['ALL_BOOKS_DATA']

    log_target = worker_logger
    current_slugifier = slugify_to_use_global_worker
    app_for_context = worker_app_instance

    generated_pages_info = []
    current_page_signature, segment_key_for_url, dynamic_url_parts = "", "", []

    if page_type == "book":
        book = item_data
        author_orig, title_orig = book.get('author_slug'), book.get('title_slug')
        ident = book.get('isbn10') or book.get('isbn13') or book.get('asin')
        if not all([author_orig, title_orig, ident]):
            log_target.debug(f"Saltando libro (datos incompletos): ID '{ident}'")
            return []
        author_s, title_s = current_slugifier(author_orig), current_slugifier(title_orig)
        current_page_signature = calculate_signature(get_book_signature_fields(book))
        segment_key_for_url, dynamic_url_parts = 'book', [author_s, title_s, str(ident)]
    elif page_type == "author":
        author_orig = item_data
        author_s = current_slugifier(author_orig)
        related_books = [b for b in ALL_BOOKS if current_slugifier(b.get('author_slug')) == author_s]
        if not related_books:
            log_target.debug(f"No hay libros para autor '{author_s}' (original '{author_orig}').")
            return []
        ids = sorted([b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in related_books])
        current_page_signature = calculate_signature({"book_ids": ids, "author_slug": author_orig})
        segment_key_for_url, dynamic_url_parts = 'author', [author_s]
    elif page_type == "versions":
        author_orig, base_title_orig = item_data
        author_s, base_title_s = current_slugifier(author_orig), current_slugifier(base_title_orig)
        related_books = [
            b for b in ALL_BOOKS
            if current_slugifier(b.get('author_slug')) == author_s and
            current_slugifier(b.get('base_title_slug')) == base_title_s
        ]
        if not related_books:
            log_target.debug(f"No hay versiones para '{author_s}','{base_title_s}'.")
            return []
        ids = sorted([b.get('isbn10') or b.get('isbn13') or b.get('asin') for b in related_books])
        current_page_signature = calculate_signature({
            "book_ids": ids, "author_slug": author_orig, "base_title_slug": base_title_orig
        })
        segment_key_for_url, dynamic_url_parts = 'versions', [author_s, base_title_s]
    else:
        log_target.error(f"Tipo de página desconocido: {page_type}")
        return []

    with app_for_context.app_context():
        with app_for_context.test_client() as client:
            for lang in LANGUAGES:
                segment_translated = get_translated_url_segment_for_generator(
                    segment_key_for_url, lang, URL_SEGMENT_TRANSLATIONS, DEFAULT_LANGUAGE, segment_key_for_url
                )
                str_dynamic_parts = [str(p) for p in dynamic_url_parts]
                flask_url_path_elements = [f"/{lang}", segment_translated] + str_dynamic_parts
                flask_url = "/" + "/".join(s.strip("/") for s in flask_url_path_elements if s.strip("/")) + "/"

                output_path_parts = [lang, segment_translated] + str_dynamic_parts + ["index.html"]
                output_path_obj = OUTPUT_DIR_BASE.joinpath(*output_path_parts)
                output_path_str = str(output_path_obj)

                if FORCE_REGENERATE or should_regenerate_page(
                    output_path_str, current_page_signature, manifest_data_global, log_target
                ):
                    _save_page_local(client, flask_url, output_path_obj, log_target)
                    generated_pages_info.append({
                        "path": output_path_str, "signature": current_page_signature, "timestamp": time.time()
                    })
    return generated_pages_info


def generate_book_detail_pages_task(item_data, cfg_manifest_tuple):
    return _generate_task_common(item_data, cfg_manifest_tuple, "book")


def generate_author_pages_task(author_slug_original, cfg_manifest_tuple):
    return _generate_task_common(author_slug_original, cfg_manifest_tuple, "author")


def generate_versions_pages_task(author_base_title_slugs_original, cfg_manifest_tuple):
    return _generate_task_common(author_base_title_slugs_original, cfg_manifest_tuple, "versions")


def _parse_cli_args():
    parser = argparse.ArgumentParser(description="Generador de sitio estático.")
    parser.add_argument("--language", type=str, help="Idioma (ej. 'es').")
    parser.add_argument("--force-regenerate", action="store_true", help="Forzar regeneración.")
    parser.add_argument(
        "--char-key", type=str,
        help=(
            "Clave de carácter. "
            "Si es dígito (ej. '5'), carga 'books_5.csv', el filtro de autores se desactiva para tareas paralelas, "
            "y se genera 'sitemap_<lang>_5.xml'. "
            "Si es letra (ej. 'a') o '0', carga todos los CSVs, filtra autores/tareas paralelas por esa clave, "
            "y se genera 'sitemap_<lang>_<letra/0>.xml'. Requiere --language. "
            "Si es 'core', genera solo 'sitemap_<lang>_core.xml' (como índice) y "
            "todos los sitemaps de carácter de ese idioma."
        )
    )
    parser.add_argument(
        "--log-level", type=str, default=os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper(),
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], help="Nivel de log."
    )
    return parser.parse_args()


def _setup_environment_data(args, logger):  # noqa: C901
    from app import create_app
    from app.models.data_loader import load_processed_books as app_load_books

    logger.info(f"Args: {args}")
    if args.force_regenerate:
        logger.info("FORZANDO REGENERACIÓN.")
    manifest = load_manifest()
    logger.info(f"Manifest: {len(manifest)} entradas.")
    if 'IS_STATIC_GENERATION_WORKER' in os.environ:
        del os.environ['IS_STATIC_GENERATION_WORKER']

    app = create_app()
    logger.info(
        f"App Flask creada. APP_ROOT:'{app.config.get('APPLICATION_ROOT')}', "
        f"SERVER_NAME:'{app.config.get('SERVER_NAME')}'"
    )

    filename_key_for_data = None
    actual_char_key_for_author_filter = args.char_key

    if args.char_key == "core":
        actual_char_key_for_author_filter = None
        logger.info(
            "char_key es 'core'. Se generarán sitemaps de índice y de caracteres. "
            "Sin filtro de archivo ni autor para tareas paralelas."
        )
    elif args.char_key and args.char_key.isdigit():
        filename_key_for_data = args.char_key
        actual_char_key_for_author_filter = None
        logger.info(
            f"char_key ('{args.char_key}') es dígito. Se usará para cargar 'books_{filename_key_for_data}.csv'."
        )
        logger.info("El filtro de carácter de autor para tareas paralelas se desactivará.")
    elif args.char_key and (args.char_key in ALPHABET or args.char_key == SPECIAL_CHARS_SITEMAP_KEY):
        if not args.language:
            logger.error(f"--char-key '{args.char_key}' (letra o '0') requiere --language. Saliendo.")
            return None
        logger.info(f"char_key '{args.char_key}' (letra o '0'). Se usará para filtrar autores en tareas paralelas.")

    if filename_key_for_data:  # Cargar solo un archivo específico
        books_dir = app.config.get('BOOKS_DATA_DIR')
        if books_dir:
            logger.info(f"Recargando datos de libros SOLO desde 'books_{filename_key_for_data}.csv'")
            app.books_data = app_load_books(books_dir, filename_filter_key=filename_key_for_data)
            logger.info(f"Libros después de filtro de archivo: {len(app.books_data)}")
            if not app.books_data:
                logger.warning(f"No se cargaron libros de 'books_{filename_key_for_data}.csv'.")
        else:
            logger.error("BOOKS_DATA_DIR no configurado.")

    all_cfg_langs = app.config.get('SUPPORTED_LANGUAGES', ['en'])
    langs_proc = [args.language] if args.language and args.language in all_cfg_langs else all_cfg_langs
    if args.language and args.language not in all_cfg_langs:
        logger.error(f"Idioma '{args.language}' no soportado.")
        return None
    logger.info(f"Idiomas a procesar: {langs_proc}")

    books_final_for_tasks = app.books_data
    if not books_final_for_tasks:
        logger.critical("Datos de libros no cargados y no se especificó un archivo de datos individual.")
        return None
    logger.info(f"{len(books_final_for_tasks)} libros fuente para tareas paralelas (después de filtro de archivo si aplica).")

    return {
        "app": app,
        "manifest": manifest,
        "languages_to_process": langs_proc,
        "default_language": app.config.get('DEFAULT_LANGUAGE', 'en'),
        "url_segment_translations": app.config.get('URL_SEGMENT_TRANSLATIONS', {}),
        "books_data_for_tasks": books_final_for_tasks,
        "output_dir_path": OUTPUT_DIR,
        "char_key_for_author_filter": actual_char_key_for_author_filter,
        "char_key_for_sitemap_gen_cli": args.char_key
    }


def _prepare_output_directory(app, out_dir, lang, cleanup, sitemap_char_key_original, logger):  # noqa: C901
    app_static_folder_abs = Path(app.root_path) / app.static_folder
    is_fully_unfiltered_run = not lang and not sitemap_char_key_original

    if not is_fully_unfiltered_run and lang:
        (out_dir / lang).mkdir(parents=True, exist_ok=True)
        logger.info(f"Modo filtro: Asegurando {out_dir / lang}. Sin limpieza global.")
        return

    if cleanup and is_fully_unfiltered_run:
        if out_dir.exists():
            logger.info(f"Eliminando {out_dir}")
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"{out_dir} creado/limpio.")
        if app_static_folder_abs.exists() and app_static_folder_abs.is_dir():
            target = out_dir / Path(app.static_url_path.strip('/')).name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(app_static_folder_abs, target, dirs_exist_ok=True)
            logger.info(f"'{app_static_folder_abs.name}' copiada.")
        else:
            logger.warning(f"Static dir no encontrado: {app_static_folder_abs}")
        public = Path("public")
        if public.exists() and public.is_dir():
            copied_files_count = 0
            for item in public.iterdir():
                if item.is_file():
                    try:
                        shutil.copy2(item, out_dir / item.name)
                        copied_files_count += 1
                    except Exception as e:
                        logger.error(f"Error copiando '{item.name}': {e}")
            logger.info(f"{copied_files_count} archivos de public/ copiados.")
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        if lang:
            (out_dir / lang).mkdir(parents=True, exist_ok=True)
        logger.info(f"Asegurando {out_dir} y subdirs (sin limpieza completa o filtro activo).")


def get_all_defined_sitemap_char_keys(app):
    author_filter_keys = list(ALPHABET) + [SPECIAL_CHARS_SITEMAP_KEY]
    data_file_keys = []
    books_data_dir_str = app.config.get('BOOKS_DATA_DIR')
    if books_data_dir_str:
        books_data_dir = Path(books_data_dir_str)
        if books_data_dir.is_dir():
            for i in range(100):  # Asume un máximo de books_0.csv a books_99.csv
                if (books_data_dir / f"books_{i}.csv").exists():
                    if str(i) != SPECIAL_CHARS_SITEMAP_KEY or str(i) not in author_filter_keys:
                        data_file_keys.append(str(i))
                    elif str(i) == SPECIAL_CHARS_SITEMAP_KEY and \
                         (books_data_dir / f"books_{SPECIAL_CHARS_SITEMAP_KEY}.csv").exists():
                        if str(i) not in author_filter_keys:
                            data_file_keys.append(str(i))
                        else:
                            script_logger.debug(
                                f"Archivo books_{str(i)}.csv existe, pero '{str(i)}' "
                                "ya es un char_key de filtro de autor."
                            )

    combined_keys = list(set(author_filter_keys + data_file_keys))
    script_logger.debug(f"Todos los char_keys definidos para sitemaps: {sorted(combined_keys)}")
    return sorted(combined_keys)


def _generate_main_process_pages(app, langs_to_process, out_dir,  # noqa: C901
                                 lang_arg_cli, force_regen, sitemap_char_key_cli, logger):
    logger.info(
        f"Gen main pages: lang_arg_cli='{lang_arg_cli}', sitemap_char_key_cli='{sitemap_char_key_cli}', "
        f"langs_to_process={langs_to_process}"
    )

    with app.app_context(), app.test_client() as client:
        is_fully_unfiltered_run = not lang_arg_cli and not sitemap_char_key_cli

        if is_fully_unfiltered_run:
            if force_regen or not (out_dir / "index.html").exists():
                _save_page_local(client, "/", out_dir / "index.html", logger)

        generate_lang_indexes = not sitemap_char_key_cli or sitemap_char_key_cli == "core"
        if generate_lang_indexes:
            for lang_c in langs_to_process:
                if force_regen or not (out_dir / lang_c / "index.html").exists():
                    _save_page_local(client, f"/{lang_c}/", out_dir / lang_c / "index.html", logger)

        for lang_c in langs_to_process:
            sitemap_lang_core_url = f"/sitemap_{lang_c}_core.xml"
            sitemap_lang_core_path = out_dir / f"sitemap_{lang_c}_core.xml"
            all_individual_sitemap_keys = get_all_defined_sitemap_char_keys(app)

            if sitemap_char_key_cli:
                if sitemap_char_key_cli == "core":
                    logger.info(f"Modo --char-key core: Generando sitemap índice y todos los de carácter para '{lang_c}'.")
                    _save_page_local(client, sitemap_lang_core_url, sitemap_lang_core_path, logger)
                    for char_k in all_individual_sitemap_keys:
                        s_char_url = f"/sitemap_{lang_c}_{char_k}.xml"
                        s_char_path = out_dir / f"sitemap_{lang_c}_{char_k}.xml"
                        _save_page_local(client, s_char_url, s_char_path, logger)
                else:
                    if sitemap_char_key_cli not in all_individual_sitemap_keys:
                        logger.warning(
                            f"El char_key '{sitemap_char_key_cli}' no está en la lista de sitemaps de "
                            f"carácter definidos ({all_individual_sitemap_keys}). "
                            "Se intentará generar de todas formas."
                        )
                    s_char_url = f"/sitemap_{lang_c}_{sitemap_char_key_cli}.xml"
                    s_char_path = out_dir / f"sitemap_{lang_c}_{sitemap_char_key_cli}.xml"
                    logger.info(f"Modo --char-key '{sitemap_char_key_cli}': "
                                f"Generando solo sitemap de carácter específico: {s_char_path}")
                    _save_page_local(client, s_char_url, s_char_path, logger)
            else:
                logger.info(f"Modo ejecución completa para idioma '{lang_c}': "
                            "Generando sitemap índice y todos los de carácter.")
                _save_page_local(client, sitemap_lang_core_url, sitemap_lang_core_path, logger)
                for char_k in all_individual_sitemap_keys:
                    s_char_url = f"/sitemap_{lang_c}_{char_k}.xml"
                    s_char_path = out_dir / f"sitemap_{lang_c}_{char_k}.xml"
                    _save_page_local(client, s_char_url, s_char_path, logger)

        if is_fully_unfiltered_run:
            sitemap_main_url = "/sitemap.xml"  # Flask debe generar un índice de sitemap_<lang>_core.xml
            sitemap_main_path = out_dir / "sitemap.xml"
            logger.info(f"Generando sitemap ÍNDICE principal: {sitemap_main_path}")
            _save_page_local(client, sitemap_main_url, sitemap_main_path, logger)


def _run_parallel_tasks(env_data, force_regen, author_filter_char_key_for_tasks, logger):  # noqa: C901
    num_procs = max(1, cpu_count() - 1 if cpu_count() > 1 else 1)
    logger.info(f"Pool: {num_procs} procesos.")

    books_src = env_data["books_data_for_tasks"]

    cfg_tasks = {
        'LANGUAGES': env_data["languages_to_process"],
        'DEFAULT_LANGUAGE': env_data["default_language"],
        'URL_SEGMENT_TRANSLATIONS': env_data["url_segment_translations"],
        'OUTPUT_DIR': str(env_data["output_dir_path"]),
        'FORCE_REGENERATE_ALL': force_regen,
        'ALL_BOOKS_DATA': books_src
    }
    task_args = (cfg_tasks, env_data["manifest"].copy())
    new_entries = []
    slugifier_main = slugify_to_use_global_main

    detail_items = list(books_src)
    author_items_source = {b.get('author_slug') for b in books_src if b.get('author_slug')}
    version_items_source = {
        (b.get('author_slug'), b.get('base_title_slug'))
        for b in books_src if b.get('author_slug') and b.get('base_title_slug')
    }

    if author_filter_char_key_for_tasks and env_data["languages_to_process"]:
        logger.info(f"Filtrando contenido de tareas paralelas por char_key de autor: '{author_filter_char_key_for_tasks}'")
        detail_items = [
            b for b in detail_items
            if get_sitemap_char_group_for_author(b.get('author_slug'), slugifier_main) == author_filter_char_key_for_tasks
        ]
        author_items_source = {
            s for s in author_items_source
            if get_sitemap_char_group_for_author(s, slugifier_main) == author_filter_char_key_for_tasks
        }
        version_items_source = {
            (a, t) for a, t in version_items_source
            if get_sitemap_char_group_for_author(a, slugifier_main) == author_filter_char_key_for_tasks
        }
        logger.info(
            f"  Después de filtro de autor para tareas: Detalle:{len(detail_items)}, "
            f"Autores:{len(author_items_source)}, Versiones:{len(version_items_source)}"
        )
        if not any([detail_items, author_items_source, version_items_source]):
            logger.warning(f"No hay elementos para tareas paralelas con char_key de autor '{author_filter_char_key_for_tasks}'.")
            return []

    task_defs = [
        ("Detalle", generate_book_detail_pages_task, detail_items),
        ("Autor", generate_author_pages_task, list(author_items_source)),
        ("Versiones", generate_versions_pages_task, list(version_items_source))
    ]

    with Pool(processes=num_procs, initializer=worker_init) as pool:
        for name, func, items in task_defs:
            if items:
                logger.info(f"Paralelo {name}({len(items)})...")
                starmap_iterable = [(item, task_args) for item in items]
                results = pool.starmap(func, starmap_iterable)
                count = 0
                for res_list in results:
                    if res_list and isinstance(res_list, list):
                        new_entries.extend(res_list)
                        count += len(res_list)
                logger.info(f"  {name}: {count} entradas de manifest actualizadas/añadidas desde workers.")
            else:
                logger.info(f"No items para tareas paralelas '{name}'.")
    return new_entries


def _finalize_generation(manifest, new_entries, out_dir, lang_arg, orig_char_key_cli, logger):  # noqa: C901
    updated = False
    if new_entries:
        logger.info(f"Actualizando manifest: {len(new_entries)} entradas.")
        updated = True
        for e in new_entries:
            manifest[e['path']] = {"signature": e['signature'], "timestamp": e['timestamp']}

    full_run_no_filters = (not lang_arg and not orig_char_key_cli)
    if updated or full_run_no_filters:
        save_manifest(manifest)
        if not updated and full_run_no_filters:
            logger.info(
                "Ejecución completa sin nuevas entradas de tareas paralelas, manifest guardado "
                "(puede haber cambios de sitemaps)."
            )
    elif not updated:
        logger.info("Manifest no actualizado (sin cambios de tareas paralelas) y no es ejecución completa. No se guardó.")

    msg = f"Sitio (o parte para idioma '{lang_arg or 'todos'}'"
    if orig_char_key_cli:
        msg += f", char_key (CLI) '{orig_char_key_cli}'"
    msg += f") generado en: {out_dir}"
    logger.info(msg)


def main():  # noqa: C901
    args = _parse_cli_args()
    lvl_name = args.log_level
    lvl = getattr(logging, lvl_name, logging.INFO)
    script_logger.setLevel(lvl)
    script_logger.info(f"Nivel log principal: {lvl_name}")
    os.environ['SCRIPT_LOG_LEVEL'] = lvl_name

    env_data = _setup_environment_data(args, script_logger)
    if env_data is None:
        return

    app = env_data["app"]
    out_dir = env_data["output_dir_path"]
    author_filter_char_key_for_tasks = env_data["char_key_for_author_filter"]
    sitemap_char_key_from_cli = env_data["char_key_for_sitemap_gen_cli"]

    is_fully_unfiltered_cli_run = not args.language and not args.char_key
    perform_cleanup = is_fully_unfiltered_cli_run or (args.force_regenerate and is_fully_unfiltered_cli_run)

    _prepare_output_directory(app, out_dir, args.language, perform_cleanup, sitemap_char_key_from_cli, script_logger)

    _generate_main_process_pages(
        app, env_data["languages_to_process"], out_dir, args.language,
        args.force_regenerate, sitemap_char_key_from_cli, script_logger
    )

    new_manifest_entries = _run_parallel_tasks(
        env_data, args.force_regenerate, author_filter_char_key_for_tasks, script_logger
    )

    _finalize_generation(
        env_data["manifest"], new_manifest_entries, out_dir, args.language, args.char_key, script_logger
    )


if __name__ == '__main__':
    main()
