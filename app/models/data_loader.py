# app/models/data_loader.py
import csv
import sys
import os
from flask import current_app
from app.utils.helpers import slugify_ascii, load_json_file


def _process_book_row(row_data):
    """Procesa una fila de datos de libro y añade campos slug."""
    author = row_data.get('author', "")  # Usar default si es None
    title = row_data.get('title', "")   # Usar default si es None

    row_data['author_slug'] = slugify_ascii(author)
    row_data['title_slug'] = slugify_ascii(title)

    base_title = title.split('(')[0].strip() if title else ""
    row_data['base_title_slug'] = slugify_ascii(base_title)
    return row_data


def _log_message(message, level="INFO"):
    """Helper para loguear o imprimir mensajes."""
    logger = current_app.logger if current_app else None # Cuidado con current_app fuera de contexto de app
    # Para este script, es mejor pasar el logger o usar un logger de módulo
    # Si se llama desde generate_static.py y current_app no está disponible, logger será None.

    # Solución temporal para data_loader: si no hay logger de app, usar un logger de módulo.
    if not logger:
        module_logger = logging.getLogger(__name__) # Logger específico para este módulo
        if not module_logger.hasHandlers(): # Evitar duplicar handlers
            handler = logging.StreamHandler(sys.stdout) # o sys.stderr para errores
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            module_logger.addHandler(handler)
            module_logger.setLevel(logging.INFO) # o el nivel que desees
        logger_to_use = module_logger
    else:
        logger_to_use = logger


    if hasattr(logger_to_use, level.lower()):
        getattr(logger_to_use, level.lower())(message)
    else:
        logger_to_use.info(f"({level}) {message}")


def load_processed_books(directory_path, target_filename_key=None):  # noqa: C901
    """
    Carga libros. Si target_filename_key se proporciona (ej. '5'),
    solo carga de 'books_TARGET_FILENAME_KEY.csv'.
    Sino, carga de todos los CSVs en el directorio.
    """
    processed_books = []
    directory_path_str = str(directory_path)

    if not os.path.isdir(directory_path_str):
        _log_message(f"Directorio de libros no encontrado '{directory_path_str}'", "ERROR")
        return processed_books

    files_to_process = []
    if target_filename_key:
        specific_filename = f"books_{target_filename_key}.csv"
        specific_filepath = os.path.join(directory_path_str, specific_filename)
        if os.path.isfile(specific_filepath):
            files_to_process.append(specific_filename)
            _log_message(f"Objetivo específico: Se procesará solo '{specific_filename}'")
        else:
            _log_message(
                f"Archivo específico '{specific_filename}' no encontrado en '{directory_path_str}'. "
                "No se cargarán libros para esta clave.", "WARNING"
            )
            # No retornar aquí, para que el log de "Total de libros cargados" sea 0
    else:
        files_to_process = [
            fname for fname in os.listdir(directory_path_str)
            if fname.lower().endswith(".csv")
        ]
        _log_message(f"Se procesarán {len(files_to_process)} archivos CSV del directorio '{directory_path_str}'.")

    for filename in files_to_process:
        csv_filepath = os.path.join(directory_path_str, filename)
        file_book_count = 0
        try:
            with open(csv_filepath, mode='r', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # Validar que author y title no sean None antes de slugify
                    # _process_book_row ya lo maneja con .get('key', "")
                    processed_row = _process_book_row(row)
                    processed_books.append(processed_row)
                    file_book_count += 1
            _log_message(f"Cargados {file_book_count} libros desde '{csv_filepath}'")
        except FileNotFoundError:
            # Esto no debería ocurrir si os.path.isfile fue true, pero por si acaso.
            _log_message(f"Archivo de libros no encontrado (inesperado): '{csv_filepath}'", "ERROR")
        except Exception as e:
            _log_message(f"ERROR cargando/procesando libros desde '{csv_filepath}': {e}", "ERROR")

    _log_message(f"Total de libros cargados para esta llamada: {len(processed_books)}")
    return processed_books


def load_processed_bestsellers(json_filepath):
    """Carga bestsellers desde JSON y añade campos slug."""
    bestsellers_raw = load_json_file(json_filepath)
    processed_bestsellers = []

    if bestsellers_raw and isinstance(bestsellers_raw, list):
        for item in bestsellers_raw:
            if not isinstance(item, dict):
                _log_message(f"Item no es un diccionario en bestsellers: {item}", "WARNING")
                continue

            item_author = item.get('author', "")
            item_title = item.get('title', "")

            item['author_slug'] = slugify_ascii(item_author)
            item['title_slug'] = slugify_ascii(item_title)
            processed_bestsellers.append(item)
        _log_message(f"Cargados {len(processed_bestsellers)} bestsellers desde '{json_filepath}'")
    else:
        warning_msg = (
            f"No se procesaron datos de bestsellers desde '{json_filepath}' "
            "(vacío, error al cargar o no es una lista)."
        )
        _log_message(warning_msg, "WARNING")

    return processed_bestsellers
