from math import ceil, sqrt
from PIL import Image
import csv

def create_mosaic(image_paths, image_size, output_path):
    """
    Crea un mosaico a partir de una lista de imágenes.
    
    Parameters:
    - image_paths: Lista de rutas de imágenes.
    - image_size: Tupla (ancho, alto) que define el tamaño de cada imagen.
    - output_path: Ruta donde se guardará el mosaico final.
    """
    # Calcula el número de imágenes
    num_images = len(image_paths)
    
    # Calcula el número de filas y columnas para un diseño cuadrado o cercano
    cols = ceil(sqrt(num_images))  # Número de columnas
    rows = ceil(num_images / cols)  # Número de filas

    # Tamaño de cada imagen
    image_width, image_height = image_size

    # Crea una nueva imagen en blanco para el mosaico
    mosaic = Image.new('RGB', (cols * image_width, rows * image_height))

    # Itera sobre las imágenes y las coloca en el mosaico
    for i, image_path in enumerate(image_paths):
        # Abrir y redimensionar la imagen
        image = Image.open(image_path).resize((image_width, image_height))
        
        # Calcula la posición (x, y) para colocar la imagen
        x = (i % cols) * image_width
        y = (i // cols) * image_height
        
        # Pega la imagen en el mosaico
        mosaic.paste(image, (x, y))

    # Guarda la imagen final del mosaico
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

# Ejemplo de uso
image_paths = image_urls
image_size = (100, 100)  # Tamaño de cada imagen en el mosaico
output_path = 'mosaic.jpg'

create_mosaic(image_paths, image_size, output_path)
