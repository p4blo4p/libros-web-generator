# app/utils/helpers.py
import re
from unidecode import unidecode
import json
import sys

def slugify_ascii(text):
    """Genera un slug ASCII limpio."""
    if text is None:
        return ""
    text = str(text)
    text = unidecode(text)
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'--+', '-', text)
    text = text.strip('-')
    return text if text else "na"

def ensure_https_filter(url_string):
    """Filtro Jinja2 para asegurar que una URL es HTTPS."""
    if not url_string:
        return ''
    if isinstance(url_string, str) and url_string.startswith('http://'):
        return url_string.replace('http://', 'https://', 1)
    return url_string

def is_valid_isbn(isbn_str):
    """Valida un formato de ISBN-10 o ISBN-13."""
    return bool(re.match(r'^\d{10}(\d{3})?$', str(isbn_str or '')))

def is_valid_asin(asin_str):
    """Valida un formato de ASIN."""
    return bool(re.match(r'^[A-Z0-9]{10}$', str(asin_str or '')))

def load_json_file(filepath):
    """Carga datos desde un archivo JSON."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Archivo no encontrado '{filepath}'", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"ERROR: Decodificando JSON desde '{filepath}': {e}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: Inesperado cargando JSON desde '{filepath}': {e}", file=sys.stderr)
    return None