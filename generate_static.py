# generate_static.py
import shutil
from pathlib import Path
import re
from unidecode import unidecode
import logging
import os
from multiprocessing import Pool, cpu_count, current_process
from functools import partial
import argparse
import json
import hashlib
import time

# --- Carga de .env ---
try:
    from dotenv import load_dotenv
    dotenv_path_script_dir = Path(__file__).resolve().parent / '.env'
    dotenv_path_parent_dir = Path(__file__).resolve().parent.parent / '.env'
    dotenv_to_load = None
    if dotenv_path_script_dir.exists():
        dotenv_to_load = dotenv_path_script_dir
    elif dotenv_path_parent_dir.exists():
        dotenv_to_load = dotenv_path_parent_dir

    if dotenv_to_load:
        print(f"[generate_static.py] Loading .env file from: {dotenv_to_load}")
        load_dotenv(dotenv_path=dotenv_to_load, override=True)
    else:
        print("[generate_static.py] .env file not found. Using system environment variables.")
except ImportError:
    print("[generate_static.py] python-dotenv not found, .env file will not be loaded.")

# --- Configuración del Logger ---
script_logger = logging.getLogger('generate_static_script')
if not script_logger.handlers:
    log_level_name_env = os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper()
    log_level_env = getattr(logging, log_level_name_env, logging.INFO)
    script_logger.setLevel(log_level_env) # Nivel base del logger
    script_handler = logging.StreamHandler()
    script_formatter = logging.Formatter(
        '%(asctime)s - %(name)s:%(processName)s - %(levelname)s - '
        '[%(funcName)s:%(lineno)d] - %(message)s'
    )
    script_handler.setFormatter(script_formatter)
    script_logger.addHandler(script_handler)
    script_logger.propagate = False
# El nivel se ajustará en main() según el argumento CLI

script_logger.info(
    f"Logger principal (inicial) configurado con nivel: {logging.getLevelName(script_logger.level)}"
)

worker_app_instance, worker_logger, slugify_to_use_global_worker = None, None, None
MANIFEST_DIR, MANIFEST_FILE = Path(".cache"), Path(".cache/generation_manifest.json")
OUTPUT_DIR = Path(os.environ.get('STATIC_SITE_OUTPUT_DIR', '_site'))
ALPHABET, SPECIAL_CHARS_SITEMAP_KEY = "abcdefghijklmnopqrstuvwxyz", "0"

def slugify_ascii_local(text):
    if text is None: return ""
    return re.sub(r'--+', '-', re.sub(r'\s+', '-', re.sub(r'[^\w\s-]', '', unidecode(str(text)).lower()))).strip('-') or "na"

slugify_to_use_global_main = slugify_ascii_local
try:
    from app.utils.helpers import slugify_ascii as slugify_app
    slugify_to_use_global_main = slugify_app
    script_logger.info("Principal: slugify de app.utils.helpers.")
except ImportError: script_logger.warning("Principal: slugify local.")

def get_sitemap_char_group_for_author(name_or_slug, slugifier_func):
    if not name_or_slug: return SPECIAL_CHARS_SITEMAP_KEY
    slug = slugifier_func(str(name_or_slug))
    script_logger.debug(f"get_sitemap_char_group: Input='{name_or_slug}', Slug='{slug}' (con {slugifier_func.__name__})")
    if not slug: return SPECIAL_CHARS_SITEMAP_KEY
    char = slug[0].lower()
    res = char if char in ALPHABET else SPECIAL_CHARS_SITEMAP_KEY
    script_logger.debug(f"get_sitemap_char_group: PrimerChar='{char}', Grupo='{res}'")
    return res

def get_translated_url_segment_for_generator(key, lang, trans, def_lang, def_val=None):
    # ... (sin cambios)
    default_res = def_val if def_val is not None else key
    if not trans or not isinstance(trans,dict): return default_res
    segs = trans.get(key,{})
    if not isinstance(segs,dict): return default_res
    val = segs.get(lang)
    if val: return val
    if lang != def_lang:
        val_dl = segs.get(def_lang)
        if val_dl: return val_dl
    return default_res

# --- MANIFEST HELPERS (sin cambios) ---
def load_manifest():
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE,'r',encoding='utf-8') as f: return json.load(f)
        except json.JSONDecodeError: script_logger.warning(f"Error decodificando {MANIFEST_FILE}.")
    else: script_logger.info(f"Manifest {MANIFEST_FILE} no encontrado.")
    return {}

def save_manifest(data):
    MANIFEST_DIR.mkdir(parents=True,exist_ok=True)
    with open(MANIFEST_FILE,'w',encoding='utf-8') as f: json.dump(data,f,indent=2)
    script_logger.info(f"Manifest guardado ({len(data)} entradas).")

def get_book_signature_fields(data):
    # ... (sin cambios)
    return dict(sorted({"isbn10":data.get("isbn10"),"isbn13":data.get("isbn13"),"asin":data.get("asin"),
                        "title_slug":data.get("title_slug"),"author_slug":data.get("author_slug"),
                        "description":data.get("description_short")or data.get("description"),
                        "cover_image_url":(data.get("image_url_l")or data.get("image_url_m")or data.get("image_url_s")),
                        "publication_date":data.get("publication_date"),"publisher":data.get("publisher_name"),
                        "language_code":data.get("language_code")}.items()))

def calculate_signature(data): return hashlib.md5(json.dumps(data,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
def should_regenerate_page(path_str,sig,manifest,log):
    # ... (sin cambios)
    entry=manifest.get(path_str)
    if not entry: log.debug(f"REGEN (nuevo): {path_str}"); return True
    if entry.get('signature')!=sig: log.debug(f"REGEN (firma): {path_str}"); return True
    if not Path(path_str).exists(): log.debug(f"REGEN (no existe): {path_str}"); return True
    log.debug(f"SALTAR: {path_str}"); return False

def _save_page_local(client,url,path_obj,log):
    # ... (sin cambios)
    try:
        resp=client.get(url)
        if resp.status_code==200:
            if resp.data: path_obj.parent.mkdir(parents=True,exist_ok=True); open(path_obj,'wb').write(resp.data); log.info(f"GENERADO: {url} -> {path_obj}")
            else: log.info(f"URL {url} 200 sin datos.")
        elif 300<=resp.status_code<400: log.warning(f"{url} REDIR {resp.status_code} -> {resp.headers.get('Location')}. NO guardado.")
        elif resp.status_code==404: log.warning(f"404: {url}. NO guardado.")
        else: log.error(f"HTTP {resp.status_code} para {url}. NO guardado.")
    except Exception: log.exception(f"EXCEPCIÓN {url}")

def worker_init():
    # ... (sin cambios)
    global worker_app_instance, worker_logger, slugify_to_use_global_worker; from app import create_app
    os.environ['IS_STATIC_GENERATION_WORKER']='1'; proc_name=current_process().name; worker_app_instance=create_app()
    worker_logger=logging.getLogger(f'gsw.{proc_name.split("-")[-1]}')
    if worker_logger.hasHandlers():worker_logger.handlers.clear()
    h=logging.StreamHandler();fmtr=logging.Formatter('%(asctime)s-%(name)s-%(levelname)s-%(message)s')
    h.setFormatter(fmtr);worker_logger.addHandler(h)
    lvl_name=os.environ.get('SCRIPT_LOG_LEVEL','INFO').upper();worker_logger.setLevel(getattr(logging,lvl_name,logging.INFO))
    worker_logger.propagate=False
    slugify_to_use_global_worker=slugify_ascii_local
    try: from app.utils.helpers import slugify_ascii as slugify_app_w; slugify_to_use_global_worker=slugify_app_w; worker_logger.debug("Worker: slugify de app.")
    except ImportError: worker_logger.warning("Worker: slugify local.")
    worker_logger.info(f"Worker inicializado. Slug: {slugify_to_use_global_worker.__name__}. Log: {logging.getLevelName(worker_logger.level)}")

def _generate_task_common(item,cfg_manifest,type): # noqa: C901
    # ... (sin cambios)
    cfg,manifest_g=cfg_manifest;langs,def_lang,url_segs,out_base,force_regen,all_books = \
    cfg['LANGUAGES'],cfg['DEFAULT_LANGUAGE'],cfg['URL_SEGMENT_TRANSLATIONS'],Path(cfg['OUTPUT_DIR']), \
    cfg.get('FORCE_REGENERATE_ALL',False),cfg['ALL_BOOKS_DATA']
    log,slugifier,app_ctx=worker_logger,slugify_to_use_global_worker,worker_app_instance
    gen_info,sig,url_seg_key,dyn_parts=[],"", "",[]
    if type=="book":
        a_o,t_o,id=item.get('author_slug'),item.get('title_slug'),item.get('isbn10')or item.get('isbn13')or item.get('asin')
        if not all([a_o,t_o,id]): log.debug(f"Saltando libro (incompleto): ID '{id}'"); return []
        a_s,t_s=slugifier(a_o),slugifier(t_o); sig=calculate_signature(get_book_signature_fields(item))
        url_seg_key,dyn_parts='book',[a_s,t_s,str(id)]
    elif type=="author":
        a_o=item; a_s=slugifier(a_o)
        books=[b for b in all_books if slugifier(b.get('author_slug'))==a_s]
        if not books: log.debug(f"No hay libros para autor '{a_s}' (orig '{a_o}')."); return []
        ids=sorted([b.get('isbn10')or b.get('isbn13')or b.get('asin')for b in books])
        sig=calculate_signature({"book_ids":ids,"author_slug":a_o}); url_seg_key,dyn_parts='author',[a_s]
    elif type=="versions":
        a_o,b_t_o=item; a_s,b_t_s=slugifier(a_o),slugifier(b_t_o)
        books=[b for b in all_books if slugifier(b.get('author_slug'))==a_s and slugifier(b.get('base_title_slug'))==b_t_s]
        if not books: log.debug(f"No hay versiones para '{a_s}','{b_t_s}'."); return []
        ids=sorted([b.get('isbn10')or b.get('isbn13')or b.get('asin')for b in books])
        sig=calculate_signature({"book_ids":ids,"author_slug":a_o,"base_title_slug":b_t_o})
        url_seg_key,dyn_parts='versions',[a_s,b_t_s]
    else: log.error(f"Tipo de página desconocido: {type}"); return []
    with app_ctx.app_context(),app_ctx.test_client()as client:
        for lang_c in langs:
            seg_trans=get_translated_url_segment_for_generator(url_seg_key,lang_c,url_segs,def_lang,url_seg_key)
            str_dyn_parts=[str(p)for p in dyn_parts]
            url_elems=[f"/{lang_c}",seg_trans]+str_dyn_parts
            url="/"+"/".join(s.strip("/")for s in url_elems if s.strip("/"))+"/"
            path_obj=out_base.joinpath(*([lang_c,seg_trans]+str_dyn_parts+["index.html"]))
            if force_regen or should_regenerate_page(str(path_obj),sig,manifest_g,log):
                _save_page_local(client,url,path_obj,log)
                gen_info.append({"path":str(path_obj),"signature":sig,"timestamp":time.time()})
    return gen_info

def generate_book_detail_pages_task(item,cfg): return _generate_task_common(item,cfg,"book")
def generate_author_pages_task(item,cfg): return _generate_task_common(item,cfg,"author")
def generate_versions_pages_task(item,cfg): return _generate_task_common(item,cfg,"versions")

def _parse_cli_args():
    parser = argparse.ArgumentParser(description="Generador de sitio estático.")
    parser.add_argument("--language", type=str, help="Generar solo para un idioma (ej. 'es').")
    parser.add_argument("--force-regenerate", action="store_true", help="Forzar regeneración.")
    parser.add_argument(
        "--char-key", type=str,
        help="Clave de carácter. Si es dígito (ej. '5'), carga 'books_5.csv' Y filtra autores por '0' (especiales). "
             "Si es letra (ej. 'a') o '0', carga todos los CSVs Y filtra autores por esa letra/'0'. "
             "Requiere --language si es letra/'0' para filtrado de autor."
    )
    parser.add_argument("--log-level", type=str, default=os.environ.get('SCRIPT_LOG_LEVEL', 'INFO').upper(),
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], help="Nivel de log.")
    return parser.parse_args()

def _setup_environment_data(args, logger): # noqa: C901
    from app import create_app
    from app.models.data_loader import load_processed_books as app_load_books
    logger.info(f"Args: {args}")
    if args.force_regenerate: logger.info("FORZANDO REGENERACIÓN.")
    manifest = load_manifest(); logger.info(f"Manifest: {len(manifest)} entradas.")
    if 'IS_STATIC_GENERATION_WORKER' in os.environ: del os.environ['IS_STATIC_GENERATION_WORKER']
    
    # Determinar el filename_key y el char_key para filtro de autor
    filename_key_for_data = None
    actual_char_key_for_author_filter = args.char_key # Por defecto, usar el char_key para filtro de autor

    if args.char_key and args.char_key.isdigit():
        filename_key_for_data = args.char_key
        # Si char_key es un dígito para el archivo, ¿cómo filtramos autores?
        # Opción A: No filtrar autores (actual_char_key_for_author_filter = None)
        # Opción B: Asumir que si el archivo es books_5.csv, los autores son 'especiales' (grupo '0')
        # Opción C: Dejar que el usuario pase OTRO argumento para el filtro de autor.
        # Por ahora, Opción A: si char_key es para archivo, no se usa para filtrar autores por letra.
        actual_char_key_for_author_filter = None # DESACTIVAR filtro de autor si char_key es para archivo
        logger.info(f"char_key '{args.char_key}' es un dígito. Se usará para cargar 'books_{filename_key_for_data}.csv'.")
        logger.info("El filtro de carácter de autor NO se aplicará (se procesarán todos los autores del archivo cargado).")
    elif args.char_key and (args.char_key in ALPHABET or args.char_key == SPECIAL_CHARS_SITEMAP_KEY) and not args.language:
        logger.error(f"--char-key '{args.char_key}' (letra o '0') requiere --language. Saliendo.")
        return None


    # Crear app DESPUÉS de determinar si hay un filtro de archivo, para pasarle el filtro a create_app si es necesario
    # Esto es más complejo si create_app no está diseñado para tomar un filtro.
    # Mantenemos la lógica de recarga por ahora.
    app = create_app()
    logger.info(f"App Flask creada. APP_ROOT:'{app.config.get('APPLICATION_ROOT')}', SERVER_NAME:'{app.config.get('SERVER_NAME')}'")

    if filename_key_for_data: # Si char_key fue para filtrar archivo
        books_dir = app.config.get('BOOKS_DATA_DIR')
        if books_dir:
            logger.info(f"Recargando datos de libros SOLO desde 'books_{filename_key_for_data}.csv'")
            app.books_data = app_load_books(books_dir, filename_filter_key=filename_key_for_data) # Usa la función modificada
            logger.info(f"Libros después de filtro de archivo: {len(app.books_data)}")
            if not app.books_data: logger.warning(f"No se cargaron libros de 'books_{filename_key_for_data}.csv'.")
        else: logger.error("BOOKS_DATA_DIR no configurado.")
    # Si no, app.books_data tiene lo que cargó create_app (todos los archivos)

    all_cfg_langs = app.config.get('SUPPORTED_LANGUAGES',['en'])
    langs_proc = [args.language] if args.language and args.language in all_cfg_langs else all_cfg_langs
    if args.language and args.language not in all_cfg_langs:
        logger.error(f"Idioma '{args.language}' no soportado."); return None
    logger.info(f"Idiomas a procesar: {langs_proc}")

    books_final = app.books_data
    if not books_final and not filename_key_for_data :
        logger.critical("Datos de libros no cargados y no se filtró por archivo."); return None
    logger.info(f"{len(books_final)} libros fuente (después de filtros).")

    return {"app":app, "manifest":manifest, "languages_to_process":langs_proc,
            "default_language":app.config.get('DEFAULT_LANGUAGE','en'),
            "url_segment_translations":app.config.get('URL_SEGMENT_TRANSLATIONS',{}),
            "books_data":books_final, "output_dir_path":OUTPUT_DIR,
            "char_key_for_author_filter": actual_char_key_for_author_filter, # Para _run_parallel_tasks
            "char_key_for_sitemap_gen": args.char_key # El original, para _generate_main_process_pages
            }

def _prepare_output_directory(app,out_dir,lang,cleanup,sitemap_char_key_original,logger): # noqa: C901
    # sitemap_char_key_original es el args.char_key original
    # La limpieza global ahora depende de si hay *algún* filtro
    is_fully_unfiltered_run = not lang and not sitemap_char_key_original

    if not is_fully_unfiltered_run and lang: # Si hay filtro de idioma (con o sin char_key)
        (out_dir/lang).mkdir(parents=True,exist_ok=True)
        logger.info(f"Modo filtro: Asegurando {out_dir/lang}. Sin limpieza global.")
        return

    if cleanup and is_fully_unfiltered_run :
        if out_dir.exists(): logger.info(f"Eliminando {out_dir}"); shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True,exist_ok=True); logger.info(f"{out_dir} creado/limpio.")
        app_static_abs=Path(app.root_path)/app.static_folder
        if app_static_abs.exists()and app_static_abs.is_dir():
            target=out_dir/Path(app.static_url_path.strip('/')).name
            if target.exists():shutil.rmtree(target)
            shutil.copytree(app_static_abs,target,dirs_exist_ok=True); logger.info(f"'{app_static_abs.name}' copiada.")
        else: logger.warning(f"Static dir no encontrado: {app_static_abs}")
        public=Path("public")
        if public.exists()and public.is_dir():
            c=0; [shutil.copy2(i,out_dir/i.name) for i in public.iterdir()if i.is_file()]; c=len(list(public.glob("*"))); logger.info(f"{c} archivos de public/ copiados.") # Error de Flake8 aquí por comprensión en una línea
    else: # Asegurar que el dir base existe si no es limpieza completa
        out_dir.mkdir(parents=True,exist_ok=True)
        if lang: (out_dir/lang).mkdir(parents=True,exist_ok=True)
        logger.info(f"Asegurando {out_dir} y subdirs (sin limpieza completa o filtro activo).")


def _generate_main_process_pages(app, langs, out_dir, lang_arg, force_regen, sitemap_char_key_original, logger): # noqa: C901
    # sitemap_char_key_original es el args.char_key
    logger.info(f"Gen main pages: lang_arg='{lang_arg}', sitemap_char_key='{sitemap_char_key_original}', langs={langs}")
    with app.app_context(), app.test_client() as client:
        is_fully_unfiltered_run = not lang_arg and not sitemap_char_key_original
        
        if is_fully_unfiltered_run: # Índice HTML global solo sin filtros
            if force_regen or not (out_dir/"index.html").exists(): _save_page_local(client,"/",out_dir/"index.html",logger)

        # Índices HTML de idioma: solo si el sitemap_char_key_original no se usó para filtrar por archivo (es decir, no es dígito)
        # Y si sitemap_char_key_original no es una letra/'0' (es decir, queremos todos los sitemaps de ese idioma)
        generate_lang_indexes = not sitemap_char_key_original 
        if generate_lang_indexes:
            for lang_c in langs:
                if force_regen or not(out_dir/lang_c/"index.html").exists(): _save_page_local(client,f"/{lang_c}/",out_dir/lang_c/"index.html",logger)

        for lang_c in langs:
            s_core_url,s_core_path=f"/sitemap_{lang_c}_core.xml",out_dir/f"sitemap_{lang_c}_core.xml"
            
            key_for_sitemap = sitemap_char_key_original
            
            if key_for_sitemap: # Si se pasó un char_key
                if key_for_sitemap.isdigit() and key_for_sitemap != SPECIAL_CHARS_SITEMAP_KEY:
                    # Si es un dígito (y no '0'), implica que se filtró por archivo.
                    # Para sitemaps, solo generamos el _core.xml para este idioma.
                    logger.info(f"char_key '{key_for_sitemap}' es dígito (filtro de archivo): Generando solo {s_core_path}")
                    _save_page_local(client,s_core_url,s_core_path,logger)
                elif key_for_sitemap == "core":
                    _save_page_local(client,s_core_url,s_core_path,logger)
                elif key_for_sitemap in ALPHABET or key_for_sitemap == SPECIAL_CHARS_SITEMAP_KEY:
                    # Si es una letra o '0', generar solo ESE sitemap de carácter. NO el core.
                    s_url,s_path=f"/sitemap_{lang_c}_{key_for_sitemap}.xml",out_dir/f"sitemap_{lang_c}_{key_for_sitemap}.xml"
                    _save_page_local(client,s_url,s_path,logger)
                    logger.info(f"char_key '{key_for_sitemap}' (letra/0): Generando solo {s_path}")
                else:
                    logger.warning(f"char_key '{key_for_sitemap}' no reconocido para sitemap en '{lang_c}'. No se genera sitemap de carácter.")
            else: # Sin filtro de char_key, generar todos para el idioma
                logger.info(f"Generando todos sitemaps para '{lang_c}'.")
                _save_page_local(client,s_core_url,s_core_path,logger)
                for char_k in list(ALPHABET)+[SPECIAL_CHARS_SITEMAP_KEY]:
                    s_url,s_path=f"/sitemap_{lang_c}_{char_k}.xml",out_dir/f"sitemap_{lang_c}_{char_k}.xml"
                    _save_page_local(client,s_url,s_path,logger)
        
        if is_fully_unfiltered_run: # Sitemap index principal solo sin filtros
            _save_page_local(client,"/sitemap.xml",out_dir/"sitemap.xml",logger)


def _run_parallel_tasks(env_data, force_regen, author_filter_char_key, logger): # noqa: C901
    # author_filter_char_key ya está determinado (puede ser None si char_key original era para archivo)
    num_procs=max(1,cpu_count()-1 if cpu_count()>1 else 1); logger.info(f"Pool: {num_procs} procesos.")
    cfg_tasks={'LANGUAGES':env_data["languages_to_process"],'DEFAULT_LANGUAGE':env_data["default_language"],
               'URL_SEGMENT_TRANSLATIONS':env_data["url_segment_translations"],'OUTPUT_DIR':str(env_data["output_dir_path"]),
               'FORCE_REGENERATE_ALL':force_regen,'ALL_BOOKS_DATA':env_data["books_data"]}
    task_args=(cfg_tasks,env_data["manifest"].copy()); new_entries=[]
    books_src,slugifier_main=env_data["books_data"],slugify_to_use_global_main # Usar el del main para filtrar aquí

    detail_items,author_items,version_items = list(books_src),{b.get('author_slug')for b in books_src if b.get('author_slug')}, \
                                             {(b.get('author_slug'),b.get('base_title_slug'))for b in books_src if b.get('author_slug')and b.get('base_title_slug')}

    if author_filter_char_key and env_data["languages_to_process"]: # Solo filtrar si hay un char_key válido para AUTOR
        logger.info(f"Filtrando contenido por char_key de autor: '{author_filter_char_key}' en {env_data['languages_to_process']}")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("--- DEBUG: Verificando grupos de autor para filtro de contenido (primeros ~10 distintos) ---")
            # ... (tu bloque de debug como estaba) ...
        detail_items=[b for b in books_src if get_sitemap_char_group_for_author(b.get('author_slug'),slugifier_main)==author_filter_char_key]
        author_items={s for s in author_items if get_sitemap_char_group_for_author(s,slugifier_main)==author_filter_char_key}
        version_items={(a,t)for a,t in version_items if get_sitemap_char_group_for_author(a,slugifier_main)==author_filter_char_key}
        logger.info(f"  Después de filtro autor: Detalle:{len(detail_items)},Autores:{len(author_items)},Versiones:{len(version_items)}")
        if not any([detail_items,author_items,version_items]): logger.warning(f"No hay elementos para char_key autor '{author_filter_char_key}'."); return[]
    
    task_defs=[("Detalle",generate_book_detail_pages_task,detail_items),
               ("Autor",generate_author_pages_task,list(author_items)),
               ("Versiones",generate_versions_pages_task,list(version_items))]
    with Pool(processes=num_procs,initializer=worker_init)as pool:
        for name,func,items in task_defs:
            if items: logger.info(f"Paralelo {name}({len(items)})..."); task_p=partial(func,config_params_manifest_tuple=task_args)
            results=pool.map(task_p,items); count=0
            for res in results:
                if res and isinstance(res,list): new_entries.extend(res); count+=len(res)
            logger.info(f"  {name}: {count} (re)generadas.")
            else: 
                logger.info(f"No items para '{name}'.")
    return new_entries


def _finalize_generation(manifest,new_entries,out_dir,lang_arg,orig_char_key_cli,logger): # noqa: C901
    # orig_char_key_cli es el args.char_key original del CLI
    updated=False
    if new_entries: logger.info(f"Actualizando manifest: {len(new_entries)} entradas."); updated=True
    for e in new_entries: manifest[e['path']]={"signature":e['signature'],"timestamp":e['timestamp']}
    
    full_run_no_filters = (not lang_arg and not orig_char_key_cli) # Ver si fue ejecución completa sin filtros
    if updated or full_run_no_filters: save_manifest(manifest)
    if not updated and full_run_no_filters: logger.info("Ejecución completa sin nuevas entradas, manifest guardado.")
    elif not updated: logger.info("Manifest no actualizado y no es ejecución completa/parcial con cambios. No se guardó.")

    msg=f"Sitio (o parte para idioma '{lang_arg or 'todos'}'";
    if orig_char_key_cli: msg+=f", char_key (CLI) '{orig_char_key_cli}'"
    msg+=f") generado en: {out_dir}"; logger.info(msg)


def main(): # noqa: C901
    args=_parse_cli_args()
    lvl_name=args.log_level; lvl=getattr(logging,lvl_name,logging.INFO)
    script_logger.setLevel(lvl); script_logger.info(f"Nivel log principal: {lvl_name}")
    os.environ['SCRIPT_LOG_LEVEL']=lvl_name

    # Validar char_key si es letra/0 y no hay idioma
    if args.char_key and (args.char_key in ALPHABET or args.char_key == SPECIAL_CHARS_SITEMAP_KEY) and not args.language:
        script_logger.error(f"--char-key '{args.char_key}' (letra o '0') requiere --language. Saliendo."); return
    
    env_data=_setup_environment_data(args,script_logger);
    if env_data is None: return
    app,out_dir=env_data["app"],env_data["output_dir_path"]
    
    # Obtener las claves de char_key procesadas desde env_data
    author_filter_char_key = env_data["char_key_for_author_filter"]
    sitemap_gen_char_key = env_data["char_key_for_sitemap_gen"]


    cleanup_condition_no_filters = not args.language and not args.char_key # char_key original del CLI
    cleanup_if_forced_and_no_filters = args.force_regenerate and cleanup_condition_no_filters
    perform_cleanup = cleanup_condition_no_filters or cleanup_if_forced_and_no_filters

    _prepare_output_directory(app,out_dir,args.language,perform_cleanup,args.char_key,script_logger) # Pasar args.char_key para la lógica de limpieza
    _generate_main_process_pages(app,env_data["languages_to_process"],out_dir,args.language,
                                 args.force_regenerate,sitemap_gen_char_key,script_logger) # Usa el char_key para sitemap
    new=_run_parallel_tasks(env_data,args.force_regenerate,author_filter_char_key,script_logger) # Usa el char_key para filtro de autor
    _finalize_generation(env_data["manifest"],new,out_dir,args.language,args.char_key,script_logger) # args.char_key para el log

if __name__=='__main__': main()
    main()
