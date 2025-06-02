# app/models/data_loader.py
import csv
import sys
import os
import logging # <--- AÑADIR ESTA LÍNEA
from flask import current_app # Sigue siendo útil si se corre en contexto de app
from app.utils.helpers import slugify_ascii, load_json_file


def _process_book_row(row_data):
    """Procesa una fila de datos de libro y añade campos slug."""
    author = row_data.get('author', "")
    title = row_data.get('title', "")

    row_data['author_slug'] = slugify_ascii(author)
    row_data['title_slug'] = slugify_ascii(title)

    base_title = title.split('(')[0].strip() if title else ""
    row_data['base_title_slug'] = slugify_ascii(base_title)
    return row_data


def _log_message(message, level_name="INFO"): # Cambiado level a level_name para claridad
    """Helper para loguear o imprimir mensajes."""
    logger_to_use = None
    if current_app: # Priorizar logger de la app si está disponible
        logger_to_use = current_app.logger
    
    if not logger_to_use: # Fallback a logger de módulo si no hay app logger
        module_logger = logging.getLogger(__name__)
        if not module_logger.hasHandlers():
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            module_logger.addHandler(handler)
            # Usar un nivel por defecto para el logger de módulo si no hay SCRIPT_LOG_LEVEL
            module_log_level_name = os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper()
            module_log_level = getattr(logging, module_log_level_name, logging.INFO)
            module_logger.setLevel(module_log_level)
            module_logger.propagate = False # Evitar duplicación
        logger_to_use = module_logger

    log_level_int = getattr(logging, level_name.upper(), logging.INFO) # Convertir nombre a int

    if logger_to_use.isEnabledFor(log_level_int): # Comprobar si el logger está habilitado para este nivel
        if level_name.upper() == "ERROR":
            logger_to_use.error(message)
        elif level_name.upper() == "WARNING":
            logger_to_use.warning(message)
        elif level_name.upper() == "DEBUG":
            logger_to_use.debug(message)
        else: # INFO y otros
            logger_to_use.info(message)
    elif not current_app : # Si no hay logger de app y el nivel no está habilitado, imprimir
         print(f"[{level_name.upper()}] {message}", file=sys.stderr if level_name in ["ERROR", "WARNING"] else sys.stdout)


def load_processed_books(directory_path, filename_filter_key=None):  # Cambiado nombre de parámetro
    """
    Carga libros. Si filename_filter_key se proporciona (ej. '5'),
    solo carga de 'books_FILENAME_FILTER_KEY.csv'.
    Sino, carga de todos los CSVs en el directorio.
    """
    processed_books = []
    directory_path_str = str(directory_path)

    if not os.path.isdir(directory_path_str):
        _log_message(f"Directorio de libros no encontrado '{directory_path_str}'", "ERROR")
        return processed_books

    files_to_process = []
    if filename_filter_key:
        specific_filename = f"books_{filename_filter_key}.csv"
        specific_filepath = os.path.join(directory_path_str, specific_filename)
        if os.path.isfile(specific_filepath):
            files_to_process.append(specific_filename)
            _log_message(f"Objetivo específico: Se procesará solo '{specific_filename}'")
        else:
            _log_message(
                f"Archivo específico '{specific_filename}' no encontrado en '{directory_path_str}'. "
                "No se cargarán libros para esta clave.", "WARNING"
            )
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
                    processed_row = _process_book_row(row)
                    processed_books.append(processed_row)
                    file_book_count += 1
            _log_message(f"Cargados {file_book_count} libros desde '{csv_filepath}'")
        except FileNotFoundError:
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
