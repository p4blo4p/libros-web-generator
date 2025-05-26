# app/utils/translations.py
from flask import current_app # Podrías necesitar current_app para logging si lo añades aquí
from app.utils.helpers import load_json_file

class TranslationManager:
    def __init__(self, translations_path, default_lang='en'):
        self.translations = load_json_file(translations_path) or {}
        self.default_lang = default_lang
        if not self.translations:
            # Usar current_app.logger si está disponible y configurado, sino print
            logger = getattr(current_app, 'logger', None)
            log_message = f"ADVERTENCIA: No se pudieron cargar las traducciones desde '{translations_path}'. Usando fallback."
            if logger:
                logger.warning(log_message)
            else:
                print(log_message)
            self.translations = {
                'en': {'title': 'Book List (Default)', 'author': 'Author (Default)'},
                'es': {'title': 'Lista de Libros (Por Defecto)', 'author': 'Autor (Por Defecto)'}
            }

    def get_translation_func(self, lang):
        """Devuelve una función t(key, **kwargs) para el idioma dado que soporta interpolación."""
        effective_lang = lang if lang in self.translations else self.default_lang
        
        # Fallback al diccionario del idioma por defecto si el idioma efectivo no tiene entradas
        # o si el idioma efectivo no se encuentra.
        lang_dict_effective = self.translations.get(effective_lang, {})
        lang_dict_default = self.translations.get(self.default_lang, {})

        def t(key, **kwargs): # <--- AHORA ACEPTA **kwargs
            # 1. Intentar obtener la traducción del idioma efectivo
            translation_string = lang_dict_effective.get(key)

            # 2. Si no se encuentra, intentar con el idioma por defecto de la aplicación
            if translation_string is None:
                translation_string = lang_dict_default.get(key)
            
            # 3. Si sigue sin encontrarse, devolver la clave original
            if translation_string is None:
                # Log de advertencia si no se encuentra la clave y se está en modo debug o con logger
                logger = getattr(current_app, 'logger', None)
                if logger and (getattr(current_app, 'debug', False) or True): # Loguear siempre si falta una clave
                    logger.warning(f"Translation key '{key}' not found for lang '{effective_lang}' or default '{self.default_lang}'.")
                # Si se proporcionaron kwargs, intentar formatear la clave por si acaso es una f-string
                # pero es mejor que la clave no sea formateable.
                # Simplemente devolver la clave es más seguro si no se encuentra.
                return key

            # Si se encontraron kwargs, intentar formatear la cadena
            if kwargs:
                try:
                    return translation_string.format(**kwargs)
                except KeyError as e:
                    # Error si una variable en la cadena de formato no está en kwargs
                    logger = getattr(current_app, 'logger', None)
                    if logger:
                        logger.error(f"Missing key '{e}' in translation arguments for key '{key}', string '{translation_string}', args {kwargs}")
                    return translation_string # Devolver la cadena sin formatear como fallback
                except Exception as e:
                    logger = getattr(current_app, 'logger', None)
                    if logger:
                        logger.error(f"Error formatting translation for key '{key}', string '{translation_string}', args {kwargs}: {e}")
                    return translation_string # Devolver la cadena sin formatear como fallback
            else:
                # Si no hay kwargs, devolver la cadena traducida directamente
                return translation_string
        return t