## Cómo dividir (split) un archivo CSV

Existen varias formas de dividir un archivo CSV grande en archivos más pequeños, tanto online como usando herramientas de línea de comandos o programación.

**Opciones online:**
- Herramientas como Split CSV, Mighty Merge o MaxAI permiten subir tu archivo CSV y dividirlo por número de filas o tamaño de archivo directamente desde el navegador, sin instalar nada[1][4][6].

**Línea de comandos (Linux/Unix):**
- Puedes usar el comando `split` para dividir por líneas:
  ```bash
  split -l 900 archivo.csv parte_
  ```
  Esto crea archivos de 900 líneas cada uno[3][7].
- Para dividir por tamaño:
  ```bash
  split -b 100m archivo.csv parte_
  ```
  Esto crea archivos de 100 MB cada uno[3][5].

