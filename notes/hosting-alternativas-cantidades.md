## Cómo alojar más de un millón de libros en una web estática con límite de 50,000 archivos y buen SEO

Dado el límite de 50,000 archivos en tu hosting, pero la necesidad de mostrar más de un millón de libros, debes evitar generar un archivo HTML por libro. Aquí tienes estrategias viables para mantener buen SEO y usabilidad:

### Opciones técnicas

**1. Carga dinámica por JavaScript (SPA o AJAX)**
- Puedes tener unas pocas páginas HTML (por ejemplo, una página de índice y una plantilla de detalle) y cargar los datos de los libros dinámicamente desde archivos JSON, una API o una base de datos externa.
- Ventaja: Reduces drásticamente el número de archivos estáticos.
- Desventaja: El SEO se complica, ya que los motores de búsqueda pueden no indexar correctamente el contenido cargado dinámicamente, aunque Google ha mejorado mucho en indexar contenido renderizado por JavaScript. Para maximizar el SEO, deberías implementar técnicas como prerendering o usar frameworks que soporten *server-side rendering* (SSR) o *static site generation* (SSG) incremental[5].

**2. Agrupación de entradas (paginación y listados)**
- En lugar de una página por libro, crea páginas de listado (por ejemplo, 1,000 páginas de 1,000 libros cada una), y una única plantilla de detalle que carga el libro específico por ID usando JavaScript.
- Así, solo necesitas generar un número limitado de archivos HTML (paginados, por ejemplo, /libros/1.html, /libros/2.html, etc.) y el resto se maneja dinámicamente.
- Ventaja: Mejor control del número de archivos y posibilidad de tener URLs amigables para SEO.
- Desventaja: Los detalles de cada libro pueden no estar indexados individualmente si solo existen en el frontend.

**3. Uso de bases de datos externas o APIs**
- Puedes almacenar los datos de los libros en una base de datos (por ejemplo, Firestore, Supabase, Airtable) y servirlos bajo demanda.
- El frontend puede seguir siendo estático, pero la información se consulta en tiempo real.

### Buenas prácticas SEO

- **URLs amigables:** Usa rutas limpias y descriptivas para los libros, aunque sean rutas virtuales gestionadas por JavaScript.
- **Sitemaps:** Genera un sitemap.xml con todas las URLs virtuales que quieras indexar, aunque se resuelvan dinámicamente. Esto ayuda a los buscadores a descubrir el contenido.
- **Prerendering/SSR:** Si usas frameworks como Next.js, puedes prerenderar las páginas más populares o recientes y servir el resto bajo demanda, combinando SSG con generación incremental[5].
- **Metaetiquetas dinámicas:** Asegúrate de que cada libro tenga su propio título y meta descripción, aunque se generen en el frontend.

### Resumen en tabla

| Estrategia                   | Nº de archivos | SEO nativo | SEO avanzado posible | Escalabilidad |
|------------------------------|---------------|------------|---------------------|--------------|
| HTML por libro               | >1,000,000    | Sí         | Sí                  | No           |
| SPA con carga dinámica       | <100          | No*        | Sí (con SSR/Prerender) | Sí           |
| Páginas de listado + detalle | <50,000       | Parcial    | Sí (con sitemap y URLs amigables) | Sí           |
| API externa + frontend estático | <100        | No*        | Sí (con SSR/Prerender) | Sí           |

\*Sin SSR ni prerender, el SEO es limitado porque los bots pueden no indexar bien el contenido cargado dinámicamente.

---

**Conclusión:**  
La mejor opción es combinar páginas de listado estáticas (agrupando libros) con carga dinámica de los detalles por JavaScript, y reforzar el SEO con un sitemap bien construido y metaetiquetas dinámicas. Si el SEO es crítico, considera frameworks que permitan generación estática incremental o SSR para las páginas de detalle más relevantes[5][1].

[1] https://www.reddit.com/r/webdev/comments/1fs1ujr/free_options_for_posting_a_very_large_static/
[2] https://www.webhostingtalk.com/showthread.php?t=602681
[3] https://serverfault.com/questions/137678/web-hosting-any-web-host-that-supports-files-more-than-50-000-in-number
[4] https://tonyteaches.tech/unlimited-shared-web-hosting-limits/
[5] https://vercel.com/docs/limits
[6] https://stackoverflow.com/questions/30191826/static-web-sites-are-never-memory-intensive
[7] https://github.com/Azure/static-web-apps/issues/520
[8] https://learn.microsoft.com/en-us/answers/questions/1086097/what-we-can-do-if-we-will-end-up-having-more-than
