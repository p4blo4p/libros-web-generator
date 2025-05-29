# app/utils/translations.py
from flask import current_app  # Podrías necesitar current_app para logging
from app.utils.helpers import load_json_file


class TranslationManager:
    def __init__(self, translations_path, default_lang='en'):
        self.translations = load_json_file(translations_path) or {}
        self.default_lang = default_lang
        if not self.translations:
            logger = getattr(current_app, 'logger', None)
            log_message = (
                f"ADVERTENCIA: No se pudieron cargar las traducciones desde "
                f"'{translations_path}'. Usando fallback."
            )
            if logger:
                logger.warning(log_message)
            else:
                print(log_message)
            self.translations = {
                'en': {'title': 'Book List (Default)', 'author': 'Author (Default)'},
                'es': {'title': 'Lista de Libros (Por Defecto)', 'author': 'Autor (Por Defecto)'}
            }

    def get_translation_func(self, lang):
        """
        Devuelve una función t(key, **kwargs) para el idioma dado que soporta interpolación.
        """
        effective_lang = lang if lang in self.translations else self.default_lang

        lang_dict_effective = self.translations.get(effective_lang, {})
        lang_dict_default = self.translations.get(self.default_lang, {})

        def t(key, **kwargs):  # <--- AHORA ACEPTA **kwargs
            translation_string = lang_dict_effective.get(key)

            if translation_string is None:
                translation_string = lang_dict_default.get(key)

            if translation_string is None:
                logger = getattr(current_app, 'logger', None)
                # Loguear siempre si falta una clave
                if logger and (getattr(current_app, 'debug', False) or True):
                    log_msg_key_not_found = (
                        f"Translation key '{key}' not found for lang '{effective_lang}' "
                        f"or default '{self.default_lang}'."
                    )
                    logger.warning(log_msg_key_not_found)
                return key

            if kwargs:
                try:
                    return translation_string.format(**kwargs)
                except KeyError as e:
                    logger = getattr(current_app, 'logger', None)
                    if logger:
                        log_msg_key_error = (
                            f"Missing key '{e}' in translation arguments for key '{key}', "
                            f"string '{translation_string}', args {kwargs}"
                        )
                        logger.error(log_msg_key_error)
                    return translation_string  # Devolver la cadena sin formatear como fallback
                except Exception as e:
                    logger = getattr(current_app, 'logger', None)
                    if logger:
                        log_msg_format_error = (
                            f"Error formatting translation for key '{key}', "
                            f"string '{translation_string}', args {kwargs}: {e}"
                        )
                        logger.error(log_msg_format_error)
                    return translation_string  # Devolver la cadena sin formatear como fallback
            else:
                return translation_string
        return t
