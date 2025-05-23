#!/bin/bash

# Verificar si se proporcionaron los argumentos necesarios
if [ $# -ne 3 ]; then
    echo "Uso: $0 <archivo_entrada> <lineas_por_archivo> <prefijo_salida>"
    exit 1
fi

# Asignar argumentos a variables
ARCHIVO_ENTRADA=$1
LINEAS_POR_ARCHIVO=$2
PREFIJO_SALIDA=$3

# Verificar si el archivo de entrada existe
if [ ! -f "$ARCHIVO_ENTRADA" ]; then
    echo "El archivo $ARCHIVO_ENTRADA no existe."
    exit 1
fi

# Extraer el encabezado del archivo de entrada
head -n 1 "$ARCHIVO_ENTRADA" > encabezado.csv

# Omitir el encabezado y dividir el archivo
tail -n +2 "$ARCHIVO_ENTRADA" | split -l "$LINEAS_POR_ARCHIVO" - "${PREFIJO_SALIDA}_" --additional-suffix=.csv

# Agregar el encabezado a cada archivo dividido
for file in "${PREFIJO_SALIDA}"_*.csv; do
    cat encabezado.csv "$file" > temp.csv
    mv temp.csv "$file"
done