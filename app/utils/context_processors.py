# app/utils/context_processors.py
from flask import current_app, request


def inject_global_template_variables():
    """
    Hace que variables globales útiles estén disponibles en todas las plantillas.
    Esto incluye información sobre idiomas y la URL actual para el selector de idioma.
    """
    supported_langs = current_app.config.get('SUPPORTED_LANGUAGES', ['en'])
    default_lang = current_app.config.get('DEFAULT_LANGUAGE', 'en')

    # Determinar el idioma actual de la página
    # 'lang' es la variable que pasas a render_template (ej. book_versions.html tiene lang={{ lang }})
    # Si no se pasa explícitamente 'lang', intentamos obtenerlo de los argumentos de la vista (URL)
    current_lang = request.view_args.get('lang_code') if request.view_args else None

    if not current_lang or current_lang not in supported_langs:
        # Si no se encuentra en view_args o no es soportado, usar el default.
        # Esto es un fallback, idealmente 'lang_code' siempre estará en view_args
        # para las rutas internacionalizadas.
        current_lang = default_lang
        # current_app.logger.debug(
        #     f"Context Processor: lang_code not in view_args or unsupported. "
        #     f"Using default: {current_lang}"
        # )

    # Parámetros de la URL actual para reconstruir enlaces en otros idiomas
    # Esto es crucial para el selector de idiomas
    view_args = request.view_args.copy() if request.view_args else {}
    endpoint = request.endpoint or 'main.index'  # Fallback a index si no hay endpoint

    return dict(
        SUPPORTED_LANGUAGES=supported_langs,
        DEFAULT_LANGUAGE=default_lang,
        # 'lang' ya se pasa a render_template, pero 'current_lang_for_selector'
        # puede ser más explícito para el selector si es necesario.
        # Usaremos la variable 'lang' que ya pasas a tus plantillas para determinar
        # el idioma actual. Si 'lang' no está disponible en algún template donde
        # uses el selector, este current_lang puede servir.
        current_lang_from_context=current_lang,

        # Información para el selector de idioma,
        # para construir URLs a la misma página en otro idioma
        current_endpoint_for_selector=endpoint,
        current_view_args_for_selector=view_args
    )
