Aquí tienes una **tabla comparativa** de los límites y características más relevantes para el despliegue de páginas estáticas en las principales plataformas gratuitas y populares, incluyendo Cloudflare Pages, Netlify, DigitalOcean App Platform y Blogger. Se incluyen límites técnicos, velocidad, precios y capacidad:

| Plataforma                  | Tiempo máx. de build | Builds gratuitos      | Archivos máx./sitio  | Tamaño máx. archivo | Ancho de banda gratis      | Velocidad/Infraestructura         | Precio base      | Otras características destacadas                         |
|-----------------------------|----------------------|----------------------|----------------------|---------------------|----------------------------|-----------------------------------|------------------|----------------------------------------------------------|
| **Cloudflare Pages**        | 20 min/build         | 500/mes              | 20.000               | 25 MiB              | Ilimitado                  | Edge global, muy rápido           | Gratis           | Dominio personalizado, integración Git, SSL, CDN         |
| **Netlify**                 | 15 min/build         | 300/mes (plan free)  | 100.000              | 25 MiB              | 100 GB/mes                 | Edge CDN, rápido                  | Gratis           | Deploy automático, funciones serverless, dominio propio  |
| **DigitalOcean App Platform** | 15 min/build       | 3 sitios estáticos    | 1 GB almacenamiento  | 512 MiB/app         | 1 GB/mes                   | Infraestructura cloud, rápida      | Gratis           | Dominio propio, integración Git, upgrade fácil           |
| **Cloudflare Workers**      | N/A (serverless)     | 100.000 req/día      | N/A                  | 10 MiB/script       | Ilimitado (con límites req)| 250+ ubicaciones edge, muy rápido | Gratis           | Serverless, requiere conocimientos técnicos              |
| **Blogger**                 | N/A                  | Ilimitado            | Ilimitado            | Desconocido         | Ilimitado                  | Infraestructura Google, rápida     | Gratis           | 100% gratis, integración AdSense, dominio propio opcional|

---

### **Notas adicionales**
- **Velocidad:** Todas las plataformas usan CDN o edge computing, por lo que la entrega de páginas estáticas es muy rápida a nivel mundial.
- **Precio:** Todas las opciones de la tabla tienen un plan gratuito. Netlify y DigitalOcean ofrecen planes de pago para más capacidad o funciones avanzadas.
- **Capacidad:** Cloudflare Pages y Netlify destacan por su alto límite de archivos y ancho de banda. DigitalOcean es más limitado en el plan gratuito.
- **Build time:** Cloudflare Pages y Netlify tienen límites estrictos de tiempo de build, importante para proyectos grandes.
- **Dominio personalizado:** Todas permiten usar dominio propio gratis en el plan básico.

---

**Resumen:**  
- **Cloudflare Pages** y **Netlify** son las opciones más equilibradas para proyectos estáticos modernos, con límites generosos y despliegue rápido.
- **DigitalOcean App Platform** es ideal para pequeños proyectos con necesidades básicas.
- **Blogger** es la mejor opción para blogs sencillos sin preocuparse por límites técnicos.

¿Quieres incluir otras plataformas como Vercel, GitHub Pages o Render? ¿O necesitas detalles sobre planes de pago? ¡Dímelo!

Citations:
[1] https://romualdfons.com/mejor-hosting-barato-espana-wordpress-seo/
[2] https://www.opiniones.hosting
[3] https://www.shopify.com/es/blog/mejor-hosting-para-tienda-online
[4] https://miposicionamientoweb.es/cual-es-el-hosting-mas-barato-y-de-calidad/
[5] https://www.comunicarseweb.com.ar/los-mejores-servicios-de-hosting-web-gratuito-en-2025/
[6] https://www.sefici.com/mejor-hosting-web/
[7] https://www.arsys.es/blog/mejores-hosting-para-wordpress-comparativa
[8] https://www.xataka.com/basics/mejores-hosting

---
Respuesta de Perplexity: https://www.perplexity.ai/search/en-cadiz-que-impuestos-se-paga-rSjgcr7oRamYxvoiVMW5Rw?utm_source=copy_output


# JOBS

| Concepto / Límite                  | GitHub-hosted runners            | Self-hosted runners              | Plan Free (Almacenamiento)       | Plan Pro/Team/Enterprise Cloud (Almacenamiento) | Enterprise Server (Almacenamiento)          |
|----------------------------------|---------------------------------|---------------------------------|---------------------------------|-------------------------------------------------|---------------------------------------------|
| **Tiempo máximo por job**         | 6 horas                         | 5 días                          | N/A                             | N/A                                             | N/A                                         |
| **Tiempo máximo por workflow run**| 35 días                        | 35 días                        | N/A                             | N/A                                             | N/A                                         |
| **Número máximo de jobs por matriz** | 256                          | 256                            | N/A                             | N/A                                             | N/A                                         |
| **Número máximo de workflows en cola** | 500 por cada 10 segundos     | 500 por cada 10 segundos       | N/A                             | N/A                                             | N/A                                         |
| **Límite de eventos que disparan workflows** | 1.500 eventos/10s/repositorio| 1.500 eventos/10s/repositorio  | N/A                             | N/A                                             | N/A                                         |
| **Límite API para Actions**       | 1.000 requests/hora/repositorio | 1.000 requests/hora/repositorio | N/A                             | N/A                                             | N/A                                         |
| **Almacenamiento total para artifacts y logs** | N/A                         | N/A                            | 2 GB por repositorio             | 50 GB por repositorio (ampliable pagando)        | Depende de la infraestructura propia        |
| **Tamaño máximo por artifact individual** | N/A                         | N/A                            | 5 GB máximo por artifact         | 5 GB máximo por artifact                         | Depende de la configuración local            |
| **Retención de artifacts y logs** | N/A                           | N/A                            | 90 días (configurable hasta 90) | 90 días (configurable hasta 90)                   | Configurable por el administrador             |
| **Retención de historial de runs** | 400 días                     | 400 días                      | N/A                             | N/A                                             | N/A                                         |
