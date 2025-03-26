git@github.com:p4blo4p/libros-web-generator.git

# libros-web-generator

```csv
book_id, cover_image_uri, book_title, book_details, format, publication_info, authorlink, author, num_pages, genres, num_ratings, num_reviews, average_rating, rating_distribution, 
```

```csv
ISBN10, Brand, format, image_url, item_weight, product_dimensions, rating, reviews_count, title, url, categories
```




Usar un script independiente como el que te proporcioné anteriormente es una forma sencilla y directa de generar archivos HTML estáticos. Sin embargo, si prefieres mantener la funcionalidad dentro de Flask, puedes usar Flask para generar y exportar los archivos HTML estáticos. Aquí te muestro cómo hacerlo.


Este script de Flask tiene una nueva ruta `/exportar` que cuando se visita, genera los archivos HTML estáticos en un directorio `output` y devuelve el archivo `index.html` como una descarga. De esta manera, puedes mantener la funcionalidad dentro de Flask y exportar los archivos HTML estáticos cuando lo necesites.

Para ejecutar la aplicación Flask, abre una terminal, navega al directorio donde se encuentran los archivos y ejecuta el siguiente comando:

```sh
python app.py
```

Luego, abre tu navegador web y ve a http://127.0.0.1:5000/ para ver la lista de libros. Para exportar los archivos HTML estáticos, ve a http://127.0.0.1:5000/exportar y se descargará el archivo `index.html` generado.



# Datasets
## Amazon
* https://www.kaggle.com/datasets/joebeachcapital/amazon-books
## Kindle
* https://www.kaggle.com/datasets/asaniczka/amazon-kindle-books-dataset-2023-130k-books
