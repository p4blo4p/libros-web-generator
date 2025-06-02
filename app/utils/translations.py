# app/utils/translations.py
from flask import current_app
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
                print(log_message) # Fallback a print si no hay logger
            self.translations = {
                'en': {'title': 'Book List (Default)', 'author': 'Author (Default)'},
                'es': {'title': 'Lista de Libros (Por Defecto)', 'author': 'Autor (Por Defecto)'}
            }

    def _get_translation_string(self, key, lang_dict_effective, lang_dict_default, effective_lang):
        """Helper para obtener la cadena de traducción, probando efectivo y luego default."""
        translation_string = lang_dict_effective.get(key)
        if translation_string is None:
            translation_string = lang_dict_default.get(key)

        if translation_string is None:
            logger = getattr(current_app, 'logger', None)
            # Loguear siempre si falta una clave y hay logger
            if logger: # No necesitamos la condición de debug aquí, loguear siempre si falta
                log_msg = (
                    f"Translation key '{key}' not found for lang '{effective_lang}' "
                    f"or default '{self.default_lang}'."
                )
                logger.warning(log_msg)
            return key # Devolver la clave si no se encuentra traducción
        return translation_string

    def _format_translation(self, key, translation_string, logger, **kwargs):
        """Helper para formatear la cadena de traducción con kwargs."""
        try:
            return translation_string.format(**kwargs)
        except KeyError as e:
            if logger:
                log_msg = (
                    f"Missing key '{e}' in translation arguments for key '{key}', "
                    f"string '{translation_string}', args {kwargs}"
                )
                logger.error(log_msg)
            return translation_string  # Fallback
        except Exception as e:
            if logger:
                log_msg = (
                    f"Error formatting translation for key '{key}', "
                    f"string '{translation_string}', args {kwargs}: {e}"
                )
                logger.error(log_msg)
            return translation_string  # Fallback

    def get_translation_func(self, lang):  # noqa: C901
        """
        Devuelve una función t(key, **kwargs) para el idioma dado que soporta interpolación.
        """
        effective_lang = lang if lang in self.translations else self.default_lang
        lang_dict_effective = self.translations.get(effective_lang, {})
        lang_dict_default = self.translations.get(self.default_lang, {})
        logger = getattr(current_app, 'logger', None)

        def t(key, **kwargs):
            translation_string = self._get_translation_string(
                key, lang_dict_effective, lang_dict_default, effective_lang
            )
            # Si la clave se devolvió porque no se encontró traducción, no intentar formatear
            if translation_string == key and kwargs: # Solo loguear si hay kwargs y no se encontró
                if logger:
                    logger.debug(f"Key '{key}' not found, returning key. Kwargs {kwargs} ignored.")
                return key # Devuelve la clave directamente si no se encontró

            if kwargs:
                return self._format_translation(key, translation_string, logger, **kwargs)
            return translation_string
        return t
