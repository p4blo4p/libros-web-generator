# app/models/data_loader.py
import csv
import sys
from app.utils.helpers import slugify_ascii, load_json_file

def load_processed_books(csv_filepath):
    """Carga libros desde CSV y añade campos slug."""
    processed_books = []
    try:
        with open(csv_filepath, encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row in enumerate(reader):
                author = row.get('author')
                title = row.get('title')

                row['author_slug'] = slugify_ascii(author)
                row['title_slug'] = slugify_ascii(title)
                
                base_title = title.split('(')[0].strip() if title else ""
                row['base_title_slug'] = slugify_ascii(base_title)
                
                # Depuración (opcional, puedes quitarla para producción)
                if i < 2:
                    print(f"DEBUG DataLoader - Author: '{author}', Slug: '{row['author_slug']}'")
                    print(f"DEBUG DataLoader - Title: '{title}', Slug: '{row['title_slug']}', BaseSlug: '{row['base_title_slug']}'")
                processed_books.append(row)
    except FileNotFoundError:
        print(f"ERROR: Archivo de libros no encontrado '{csv_filepath}'", file=sys.stderr)
    except Exception as e:
        print(f"ERROR cargando/procesando libros desde '{csv_filepath}': {e}", file=sys.stderr)
    return processed_books

def load_processed_bestsellers(json_filepath):
    """Carga bestsellers desde JSON y añade campos slug."""
    bestsellers_raw = load_json_file(json_filepath)
    processed_bestsellers = []
    if bestsellers_raw:
        for item in bestsellers_raw:
            item_author = item.get('author')
            item_title = item.get('title')
            item['author_slug'] = slugify_ascii(item_author)
            item['title_slug'] = slugify_ascii(item_title)
            # Podrías añadir base_title_slug si es relevante y tienes esa info o lógica
            processed_bestsellers.append(item)
    else:
        print("ADVERTENCIA: No se cargaron datos de bestsellers.")
    return processed_bestsellers

# Carga de datos global para la aplicación (o podrías hacerlo bajo demanda)
# books_data = load_processed_books('books.csv') # La ruta se tomará de la config
# bestsellers_data = load_processed_bestsellers('social/amazon_bestsellers_es.json')