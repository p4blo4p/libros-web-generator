# app/utils/helpers.py
import re
from unidecode import unidecode
import json
import sys
import logging # Para la función de sitemap

# Constantes para get_sitemap_char_group_for_author
# Es mejor tenerlas aquí o en un archivo de config/constantes de la app
# que duplicarlas o pasarlas constantemente.
ALPHABET_SITEMAP_HELPER = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_CHARS_SITEMAP_KEY_HELPER = "0"

logger_helpers = logging.getLogger(__name__) # Para mensajes de depuración si es necesario

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


def get_sitemap_char_group_for_author(name_or_slug, slugifier_func=slugify_ascii):
    """
    Determina el grupo de caracteres del sitemap para un nombre o slug de autor.
    :param name_or_slug: El nombre o slug del autor.
    :param slugifier_func: La función a usar para slugificar (por defecto slugify_ascii de este módulo).
    :return: El carácter del grupo del sitemap ('a'-'z', o '0' para especiales/nulos).
    """
    # Usa las constantes definidas en este módulo
    alphabet_to_use = ALPHABET_SITEMAP_HELPER
    special_key_to_use = SPECIAL_CHARS_SITEMAP_KEY_HELPER

    if not name_or_slug:
        return special_key_to_use
    
    # Asegurarse de que el slugifier se aplique
    # Si name_or_slug ya es un slug, aplicarlo de nuevo no debería dañarlo si el slugifier es idempotente para slugs.
    # O, si se pasa un nombre, se slugifica.
    slug = slugifier_func(str(name_or_slug)) # Aplicar siempre el slugifier esperado

    logger_helpers.debug(f"get_sitemap_char_group (helper): Input='{name_or_slug}', Slug='{slug}' (con {slugifier_func.__name__})")
    
    if not slug:
        return special_key_to_use
    
    char = slug[0].lower()
    res = char if char in alphabet_to_use else special_key_to_use
    logger_helpers.debug(f"get_sitemap_char_group (helper): PrimerChar='{char}', Grupo='{res}'")
    return res


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
