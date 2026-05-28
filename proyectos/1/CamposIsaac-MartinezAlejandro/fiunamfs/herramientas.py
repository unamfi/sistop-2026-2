#!/usr/bin/python3

#Programa con funciones utilizadas por varias partes del programa
#Autores: Isaac Campos, Alejandro Martinez
#Fecha de realización: 17 Mayo 2026

import struct as s
from datetime import datetime

#Funciones para pasar de binario a numero con little endian
def leerLe(bytes_raw):
    return s.unpack('<I', bytes_raw)[0]

def escribirLe(numero):
    return s.pack('<I', numero)

#Funcion para obtener la fecha y hora en el formato correcto

def obtenerFechaHora():
    return datetime.utcnow().strftime('%Y%m%d%H%M%S')
