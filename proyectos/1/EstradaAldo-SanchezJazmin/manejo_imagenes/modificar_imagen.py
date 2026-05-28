#!/usr/bin/env python3
"""
archivo utilizado para corregir la version de la imagen original
anteriormente tenia 24-2, ahora tendra 26-2
"""
from pathlib import Path

ruta = Path("manejo_imagenes/fiunamfs.img")

datos = bytearray(ruta.read_bytes())

# nueva version, para que vaya a corde con lo establecido
datos[14:18] = b"26-2"

ruta.write_bytes(datos)
