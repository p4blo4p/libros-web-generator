# app/routes/sitemap_routes.py
from flask import Blueprint, render_template, make_response, current_app, url_for
from datetime import datetime, timezone
import xml.etree.ElementTree as ET # Para test_sitemap

sitemap_bp = Blueprint('sitemap', __name__)

# books_data_store y get_t_func se accederían de manera similar a main_routes
# o se pasarían/inyectarían.

def get_books_data(): # Duplicado temporalmente, idealmente desde un lugar central
    return current_app.books_data

@sitemap_bp.route('/test/')
def test_sitemap():
    # Para generar el sitemap XML para la prueba
    # Esto es un poco circular, pero para probar los enlaces generados está bien
    sitemap_response = sitemap() # Llama a la función sitemap de este mismo blueprint
    xml_content = sitemap_response.data.decode('utf-8')
    try:
        root = ET.fromstring(xml_content)
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        links = [loc.text for loc in root.findall('.//ns:loc', namespace)]
    except Exception as e:
        current_app.logger.error(f"Error parsing sitemap XML for test: {e}")
        links = ["Error parsing sitemap XML for test route"]
    return render_template('test_sitemap.html', links=links)
      
@sitemap_bp.route('/sitemap.xml')
def sitemap():
    # @htmlmin.exempt # Esto se configuraría en el decorador de la app si Flask-HTMLMin se usa globalmente
    current_formatted_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    all_books = get_books_data()

    sitemap_xml = render_template('sitemap_template.xml', 
                                  all_books_data=all_books,
                                  current_date_for_sitemap=current_formatted_date)
    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"
    return response