import os
import requests
from math import ceil, sqrt
import csv
from PIL import Image, ImageOps

#En glitch usar comando refresh para que aparezcan imagenes

def download_images(image_urls, temp_dir="temp_images"):
    """
    Descarga imágenes desde una lista de URLs y las guarda en un directorio temporal.

    Parameters:
    - image_urls: Lista de URLs de imágenes.
    - temp_dir: Directorio temporal donde se guardarán las imágenes descargadas.

    Returns:
    - Lista de rutas locales de las imágenes descargadas.
    """
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    local_paths = []
    for i, url in enumerate(image_urls):
        try:
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                file_path = os.path.join(temp_dir, f"image_{i}.jpg")
                with open(file_path, "wb") as file:
                    for chunk in response.iter_content(1024):
                        file.write(chunk)
                local_paths.append(file_path)
            else:
                print(f"Error al descargar la imagen desde {url}")
        except Exception as e:
            print(f"Excepción al descargar la imagen desde {url}: {e}")
    
    return local_paths


def list_images_in_directory(directory_path, extensions=None):
    """
    Lista todas las imágenes en un directorio específico.

    Parameters:
    - directory_path: Ruta del directorio donde buscar imágenes.
    - extensions: Lista de extensiones de archivos a considerar como imágenes. Ejemplo: ['.jpg', '.png']
                  Si es None, se usará un conjunto de extensiones por defecto.

    Returns:
    - Una lista de rutas de imágenes encontradas en el directorio.
    """
    if extensions is None:
        extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
    
    # Normaliza las extensiones a minúsculas para evitar problemas
    extensions = set(ext.lower() for ext in extensions)
    
    # Lista de imágenes encontradas
    image_files = []

    # Recorre el directorio y filtra los archivos por extensión
    for filename in os.listdir(directory_path):
        if os.path.isfile(os.path.join(directory_path, filename)):
            _, ext = os.path.splitext(filename)
            if ext.lower() in extensions:
                image_files.append(os.path.join(directory_path, filename))
    
    return image_files

def create_mosaic(image_paths, image_size, output_path, margin=10, background_color=(255, 255, 255)):
    """
    Crea un mosaico a partir de una lista de imágenes con mejoras estéticas.
    
    Parameters:
    - image_paths: Lista de rutas de imágenes.
    - image_size: Tupla (ancho, alto) que define el tamaño de cada imagen.
    - output_path: Ruta donde se guardará el mosaico final.
    - margin: Espaciado entre las imágenes (en píxeles).
    - background_color: Color del fondo para el mosaico.
    """
    num_images = len(image_paths)
    cols = ceil(sqrt(num_images))  # Número de columnas
    rows = ceil(num_images / cols)  # Número de filas

    image_width, image_height = image_size
    cell_width = image_width + margin
    cell_height = image_height + margin

    # Crea una nueva imagen en blanco para el mosaico con el color de fondo
    mosaic_width = cols * cell_width - margin
    mosaic_height = rows * cell_height - margin
    mosaic = Image.new('RGB', (mosaic_width, mosaic_height), background_color)

    for i, image_path in enumerate(image_paths):
        image = Image.open(image_path)
        
        # Ajusta las proporciones de la imagen manteniéndolas
        image.thumbnail((image_width, image_height), Image.ANTIALIAS)
        
        # Crea un lienzo con fondo para centrar la imagen
        padded_image = Image.new('RGB', (image_width, image_height), background_color)
        pad_x = (image_width - image.width) // 2
        pad_y = (image_height - image.height) // 2
        padded_image.paste(image, (pad_x, pad_y))


        # Calcula la posición en el mosaico
        x = (i % cols) * cell_width
        y = (i // cols) * cell_height
        
        mosaic.paste(bordered_image, (x, y))
    
    mosaic.save(output_path)
    print(f"Mosaico creado y guardado en {output_path}")
    
def get_image_urls_for_title(file_path, title_prefix):
    """
    Extrae las URLs de imágenes de libros cuyo título comienza con un prefijo específico.

    Parameters:
    - file_path: Ruta al archivo CSV.
    - title_prefix: Prefijo del título a buscar (por ejemplo, "1984").

    Returns:
    - Una lista de URLs de imágenes.
    """
    image_urls = []

    # Abrir el archivo CSV
    with open(file_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        # Iterar por cada línea del archivo
        for row in reader:
            if row['title'].startswith(title_prefix):
                image_urls.append(row['image_url'])

    return image_urls

# Ejemplo de uso
file_path = "../books.csv"  # Cambia esto por la ruta real del archivo
title_prefix = "1984"
image_urls = get_image_urls_for_title(file_path, title_prefix)

print("URLs de imágenes:")
print(image_urls)

# Descargar las imágenes desde las URLs
#image_paths = download_images(image_urls)

image_paths = list_images_in_directory('temp_images')

# Crear el mosaico
image_size = (100, 100)  # Tamaño de cada imagen en el mosaico
output_path = 'mosaic.jpg'

create_mosaic(image_paths, image_size, output_path)

# Nota: Limpieza del directorio temporal si es necesario.
