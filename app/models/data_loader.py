# app/models/data_loader.py
import csv
import sys
import os  # <--- Necesitas importar os
from flask import current_app  # Para logging consistente
from app.utils.helpers import slugify_ascii, load_json_file


def load_processed_books(directory_path):  # Cambiado de csv_filepath a directory_path
    """
    Carga libros desde todos los archivos CSV en el directorio especificado
    y añade campos slug.
    """
    processed_books = []

    # Verificar si el directorio existe
    if not os.path.isdir(directory_path):
        # Usar current_app.logger si está disponible, sino print
        logger = current_app.logger if current_app else None
        error_msg = f"ERROR: Directorio de libros no encontrado '{directory_path}'"
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg, file=sys.stderr)
        return processed_books  # Retorna lista vacía si el directorio no existe

    # Iterar sobre todos los archivos en el directorio
    for filename in os.listdir(directory_path):
        if filename.lower().endswith(".csv"):  # Asegúrate de que solo procesas archivos CSV
            csv_filepath = os.path.join(directory_path, filename)
            try:
                with open(csv_filepath, mode='r', encoding='utf-8-sig') as csvfile:  # utf-8-sig para manejar BOM
                    reader = csv.DictReader(csvfile)
                    file_book_count = 0
                    for i, row in enumerate(reader):
                        author = row.get('author')
                        title = row.get('title')

                        # Validar que author y title no sean None antes de slugify
                        if author is None:
                            author = ""  # o loguear una advertencia y saltar la fila
                        if title is None:
                            title = ""  # o loguear una advertencia y saltar la fila

                        row['author_slug'] = slugify_ascii(author)
                        row['title_slug'] = slugify_ascii(title)

                        base_title = title.split('(')[0].strip() if title else ""
                        row['base_title_slug'] = slugify_ascii(base_title)

                        processed_books.append(row)
                        file_book_count += 1

                # Loguear cuántos libros se cargaron de este archivo
                logger = current_app.logger if current_app else None
                success_msg = f"INFO: Cargados {file_book_count} libros desde '{csv_filepath}'"
                if logger:
                    logger.info(success_msg)
                else:
                    print(success_msg)

            except FileNotFoundError:
                error_msg = f"ERROR: Archivo de libros no encontrado '{csv_filepath}' (debería existir)"
                if logger:
                    logger.error(error_msg)
                else:
                    print(error_msg, file=sys.stderr)
            except Exception as e:
                error_msg = f"ERROR cargando/procesando libros desde '{csv_filepath}': {e}"
                if logger:
                    logger.error(error_msg)
                else:
                    print(error_msg, file=sys.stderr)

    logger = current_app.logger if current_app else None
    total_msg = f"INFO: Total de libros cargados de todos los CSVs: {len(processed_books)}"
    if logger:
        logger.info(total_msg)
    else:
        print(total_msg)

    return processed_books


def load_processed_bestsellers(json_filepath):
    """Carga bestsellers desde JSON y añade campos slug."""
    bestsellers_raw = load_json_file(json_filepath)  # Asume que load_json_file maneja FileNotFoundError
    processed_bestsellers = []
    logger = current_app.logger if current_app else None

    if bestsellers_raw:
        for item in bestsellers_raw:
            item_author = item.get('author') or ""
            item_title = item.get('title') or ""

            item['author_slug'] = slugify_ascii(item_author)
            item['title_slug'] = slugify_ascii(item_title)
            processed_bestsellers.append(item)

        if logger:
            logger.info(
                f"INFO: Cargados {len(processed_bestsellers)} bestsellers desde '{json_filepath}'"
            )
        else:
            print(
                f"INFO: Cargados {len(processed_bestsellers)} bestsellers desde '{json_filepath}'"
            )
    else:
        # load_json_file ya debería imprimir un error si el archivo no se encuentra o está mal formado.
        # Aquí solo indicamos que no se procesaron datos.
        warning_msg = (
            f"ADVERTENCIA: No se procesaron datos de bestsellers desde '{json_filepath}' "
            "(posiblemente vacío o error al cargar)."
        )
        if logger:
            logger.warning(warning_msg)
        else:
            print(warning_msg)

    return processed_bestsellers

# Carga de datos global para la aplicación (comentada para evitar carga duplicada)
# books_data = load_processed_books('books.csv')  # La ruta se tomará de la config
# bestsellers_data = load_processed_bestsellers('social/amazon_bestsellers_es.json')
