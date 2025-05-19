# app/utils/translations.py
from app.utils.helpers import load_json_file

class TranslationManager:
    def __init__(self, translations_path, default_lang='en'):
        self.translations = load_json_file(translations_path) or {}
        self.default_lang = default_lang
        if not self.translations:
            print(f"ADVERTENCIA: No se pudieron cargar las traducciones desde '{translations_path}'.")
            # Fallback mínimo si el archivo no se carga
            self.translations = {
                'en': {'title': 'Book List (Default)', 'author': 'Author (Default)'},
                'es': {'title': 'Lista de Libros (Por Defecto)', 'author': 'Autor (Por Defecto)'}
            }


    def get_translation_func(self, lang):
        """Devuelve una función t(key) para el idioma dado."""
        effective_lang = lang if lang in self.translations else self.default_lang
        
        def t(key):
            # Obtener el diccionario del idioma, o el inglés por defecto, o un diccionario vacío
            lang_dict = self.translations.get(effective_lang, self.translations.get(self.default_lang, {}))
            return lang_dict.get(key, key) # Devolver la clave si no se encuentra la traducción
        return t

# Puedes instanciarlo una vez y usarlo, o instanciarlo en app/__init__.py
# Ejemplo de cómo se podría usar directamente:
# translations_manager = TranslationManager('translations.json')
# t_es = translations_manager.get_translation_func('es')
# print(t_es('title'))