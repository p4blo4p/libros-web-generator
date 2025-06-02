# app/models/data_loader.py
import csv
import sys
import os
from flask import current_app
from app.utils.helpers import slugify_ascii, load_json_file


def _process_book_row(row_data):
    """Procesa una fila de datos de libro y añade campos slug."""
    author = row_data.get('author', "") # Usar default si es None
    title = row_data.get('title', "")   # Usar default si es None

    row_data['author_slug'] = slugify_ascii(author)
    row_data['title_slug'] = slugify_ascii(title)

    base_title = title.split('(')[0].strip() if title else ""
    row_data['base_title_slug'] = slugify_ascii(base_title)
    return row_data


def _log_message(message, level="INFO"):
    """Helper para loguear o imprimir mensajes."""
    logger = current_app.logger if current_app else None
    if logger:
        if hasattr(logger, level.lower()):
            getattr(logger, level.lower())(message)
        else:
            logger.info(f"({level}) {message}") # Fallback a info si el nivel no existe
    else:
        print(f"[{level}] {message}", file=sys.stderr if level in ["ERROR", "WARNING"] else sys.stdout)


def load_processed_books(directory_path):  # noqa: C901
    """
    Carga libros desde todos los archivos CSV en el directorio especificado
    y añade campos slug.
    """
    processed_books = []
    directory_path_str = str(directory_path) # Asegurar que es string para os.path

    if not os.path.isdir(directory_path_str):
        _log_message(f"Directorio de libros no encontrado '{directory_path_str}'", "ERROR")
        return processed_books

    for filename in os.listdir(directory_path_str):
        if not filename.lower().endswith(".csv"):
            continue

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
            _log_message(f"Archivo de libros no encontrado '{csv_filepath}'", "ERROR")
        except Exception as e:
            _log_message(f"ERROR cargando/procesando libros desde '{csv_filepath}': {e}", "ERROR")

    _log_message(f"Total de libros cargados de todos los CSVs: {len(processed_books)}")
    return processed_books


def load_processed_bestsellers(json_filepath):
    """Carga bestsellers desde JSON y añade campos slug."""
    bestsellers_raw = load_json_file(json_filepath)
    processed_bestsellers = []

    if bestsellers_raw and isinstance(bestsellers_raw, list): # Verificar que es una lista
        for item in bestsellers_raw:
            if not isinstance(item, dict): # Saltar si el item no es un diccionario
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
