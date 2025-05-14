# Objetivos

# Scripts

- app.py test en localhost
- export.py generar web estatica
- social/best_sellerbooks_gemini.py scrap best seller books de amazon codigo IA gemini
- social/yt.py scrap canales de youtube y lo guarda en un JSON

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

- https://www.kaggle.com/datasets/joebeachcapital/amazon-books

## Flags

- https://gist.github.com/jpluimers/9f80a94ba5987acac2ca60f4bf5faac9
- https://alexsobolenko.github.io/flag-icons/

```json
{
  "us": "https://www.amazon.com",
  "uk": "https://www.amazon.co.uk",
  "ca": "https://www.amazon.ca",
  "de": "https://www.amazon.de",
  "es": "https://www.amazon.es",
  "fr": "https://www.amazon.fr",
  "it": "https://www.amazon.it",
  "jp": "https://www.amazon.co.jp",
  "in": "https://www.amazon.in",
  "cn": "https://www.amazon.cn",
  "sg": "https://www.amazon.com.sg",
  "mx": "https://www.amazon.com.mx",
  "ae": "https://www.amazon.ae",
  "br": "https://www.amazon.com.br",
  "nl": "https://www.amazon.nl",
  "au": "https://www.amazon.com.au",
  "tr": "https://www.amazon.com.tr",
  "sa": "https://www.amazon.sa",
  "se": "https://www.amazon.se",
  "pl": "https://www.amazon.pl"
}
```

##

Estados Unidos: www.amazon.com
Canadá: www.amazon.ca
Reino Unido: www.amazon.co.uk
Alemania: www.amazon.de
Francia: www.amazon.fr
Italia: www.amazon.it
España: www.amazon.es
México: www.amazon.com.mx
Brasil: www.amazon.com.br
India: www.amazon.in
Japón: www.amazon.co.jp
Australia: www.amazon.com.au
Países Bajos: www.amazon.nl
Suecia: www.amazon.se
Polonia: www.amazon.pl

Aquí tienes la lista de las tiendas de Amazon en diferentes países, junto con el código Unicode de cada país:

| País           | URL                                            | Código Unicode     |
| -------------- | ---------------------------------------------- | ------------------ |
| Estados Unidos | [www.amazon.com](https://www.amazon.com)       | 🇺🇸 U+1F1FA U+1F1F8 |
| Canadá         | [www.amazon.ca](https://www.amazon.ca)         | 🇨🇦 U+1F1E8 U+1F1E6 |
| Reino Unido    | [www.amazon.co.uk](https://www.amazon.co.uk)   | 🇬🇧 U+1F1EC U+1F1E7 |
| Alemania       | [www.amazon.de](https://www.amazon.de)         | 🇩🇪 U+1F1E9 U+1F1EA |
| Francia        | [www.amazon.fr](https://www.amazon.fr)         | 🇫🇷 U+1F1EB U+1F1F7 |
| Italia         | [www.amazon.it](https://www.amazon.it)         | 🇮🇹 U+1F1EE U+1F1F9 |
| España         | [www.amazon.es](https://www.amazon.es)         | 🇪🇸 U+1F1EA U+1F1F8 |
| México         | [www.amazon.com.mx](https://www.amazon.com.mx) | 🇲🇽 U+1F1F2 U+1F1E6 |
| Brasil         | [www.amazon.com.br](https://www.amazon.com.br) | 🇧🇷 U+1F1E7 U+1F1F7 |
| India          | [www.amazon.in](https://www.amazon.in)         | 🇮🇳 U+1F1EE U+1F1F3 |
| Japón          | [www.amazon.co.jp](https://www.amazon.co.jp)   | 🇯🇵 U+1F1EF U+1F1F5 |
| Australia      | [www.amazon.com.au](https://www.amazon.com.au) | 🇦🇺 U+1F1E6 U+1F1FA |
| Países Bajos   | [www.amazon.nl](https://www.amazon.nl)         | 🇳🇱 U+1F1F3 U+1F1F1 |
| Suecia         | [www.amazon.se](https://www.amazon.se)         | 🇸🇪 U+1F1F8 U+1F1EA |
| Polonia        | [www.amazon.pl](https://www.amazon.pl)         | 🇵🇱 U+1F1F5 U+1F1F1 |

Los códigos Unicode representan las banderas de cada país.

## Kindle

- https://www.kaggle.com/datasets/asaniczka/amazon-kindle-books-dataset-2023-130k-books

Okay, ¡excelente! Hablemos de los **Amazon Bounties (Recompensas)**.

**¿Qué son los Amazon Bounties?**

Son recompensas fijas (una cantidad específica de dinero, no un porcentaje) que Amazon paga a los afiliados cuando un visitante referido a través de su enlace completa una acción específica. Estas acciones suelen ser registros en pruebas gratuitas o suscripciones a servicios de Amazon.

**Programas Comunes que Ofrecen Bounties:**

Aquí tienes una lista de algunos de los programas más populares que suelen tener Bounties, junto con **ejemplos de cómo _podrían_ verse los enlaces de afiliado una vez generados**.

**Importante:**

- **`TUIDAFILIADO-21`** (o `yourtag-20`, etc., dependiendo de tu región) es un **marcador de posición**. Debes reemplazarlo con tu **propio ID de seguimiento** de Amazon Associates.
- Las URLs exactas y la estructura pueden variar ligeramente según tu país y las promociones activas.
- **Estos NO son tus enlaces funcionales.** Son solo ejemplos estructurales. Debes generarlos desde tu cuenta de Afiliados.

---

**Lista de Ejemplos de Enlaces tipo Bounty:**

1.  **Amazon Prime (Prueba Gratuita)**

    - **Acción:** Que un usuario se registre para la prueba gratuita de Amazon Prime.
    - **Página de Destino Típica:** La página principal para suscribirse a Prime.
    - **Ejemplo de Enlace de Afiliado Generado (Estructura):**
      - Formato Largo: `https://www.amazon.es/prime?tag=TUIDAFILIADO-21`
      - O podría dirigir a una página de registro específica: `https://www.amazon.es/gp/prime/pipeline/signup?tag=TUIDAFILIADO-21`
      - Formato Corto (generado por SiteStripe): `https://amzn.to/XYZabc1` (Este enlace corto contendrá tu ID internamente)
    - **Dónde generarlo:** Busca "Prime" en "Programa de Recompensas" en tu panel de Afiliados, o usa SiteStripe en la página de Amazon Prime.

2.  **Audible (Prueba Gratuita / Suscripción)**

    - **Acción:** Que un usuario se registre para la prueba gratuita de Audible (que suele incluir créditos para audiolibros).
    - **Página de Destino Típica:** La página de oferta de la prueba gratuita de Audible.
    - **Ejemplo de Enlace de Afiliado Generado (Estructura):**
      - Formato Largo: `https://www.amazon.es/hz/audible/mlp/membership/premiumplus/monthly?tag=TUIDAFILIADO-21` (La URL exacta de la oferta puede cambiar)
      - Formato Corto: `https://amzn.to/XYZabc2`
    - **Dónde generarlo:** Busca "Audible" en "Programa de Recompensas" o usa SiteStripe en la página de la oferta de Audible en Amazon.

3.  **Kindle Unlimited (Prueba Gratuita)**

    - **Acción:** Que un usuario se registre para la prueba gratuita de Kindle Unlimited (acceso a un catálogo de eBooks y revistas).
    - **Página de Destino Típica:** La página de oferta de Kindle Unlimited.
    - **Ejemplo de Enlace de Afiliado Generado (Estructura):**
      - Formato Largo: `https://www.amazon.es/kindle-dbs/hz/subscribe/ku?tag=TUIDAFILIADO-21`
      - Formato Corto: `https://amzn.to/XYZabc3`
    - **Dónde generarlo:** Busca "Kindle Unlimited" en "Programa de Recompensas" o usa SiteStripe en la página de Kindle Unlimited.

4.  **Amazon Music Unlimited (Prueba Gratuita)**

    - **Acción:** Que un usuario se registre para la prueba gratuita de Amazon Music Unlimited (servicio de streaming de música premium).
    - **Página de Destino Típica:** La página de oferta de Amazon Music Unlimited.
    - **Ejemplo de Enlace de Afiliado Generado (Estructura):**
      - Formato Largo: `https://www.amazon.es/music/unlimited?tag=TUIDAFILIADO-21`
      - Formato Corto: `https://amzn.to/XYZabc4`
    - **Dónde generarlo:** Busca "Music Unlimited" en "Programa de Recompensas" o usa SiteStripe en la página de Amazon Music.

5.  **Amazon Business (Creación de Cuenta Gratuita)**

    - **Acción:** Que un usuario elegible registre una cuenta gratuita de Amazon Business.
    - **Página de Destino Típica:** La página de registro de Amazon Business.
    - **Ejemplo de Enlace de Afiliado Generado (Estructura):**
      - Formato Largo: `https://www.amazon.es/business?tag=TUIDAFILIADO-21`
      - Formato Corto: `https://amzn.to/XYZabc5`
    - **Dónde generarlo:** Busca "Amazon Business" en "Programa de Recompensas" o usa SiteStripe en la página de Amazon Business.

6.  **Listas de Bodas / Nacimiento Amazon (Creación)**
    - **Acción:** Que un usuario cree una Lista de Bodas o Lista de Nacimiento en Amazon.
    - **Página de Destino Típica:** La página principal para crear estas listas.
    - **Ejemplo de Enlace de Afiliado Generado (Estructura):**
      - Lista de Bodas: `https://www.amazon.es/wedding?tag=TUIDAFILIADO-21`
      - Lista de Nacimiento: `https://www.amazon.es/baby-reg?tag=TUIDAFILIADO-21`
      - Formato Corto: `https://amzn.to/XYZabc6` / `https://amzn.to/XYZabc7`
    - **Dónde generarlo:** Busca "Lista de Bodas" o "Lista de Nacimiento" en "Programa de Recompensas" o usa SiteStripe en las páginas correspondientes.

---

**Recuerda:** La mejor forma de obtener los enlaces correctos y actualizados es siempre a través de tu **panel de Amazon Associates** o usando la **barra SiteStripe** mientras navegas por Amazon con tu sesión de afiliado iniciada. ¡Asegúrate de que tu `tag=ID_DE_AFILIADO` esté presente en el enlace final!
