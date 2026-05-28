"""
Creacion de parser y verificacion de rutas
"""

import argparse # libreria para leer argumentos de terminal

"""
Creacion del parser para leer argumento de la linea de comandos
"""
def crear_parser():
    parser = argparse.ArgumentParser(
        prog="fiunamfs",
        description="Sistema de archivos FiUnamFS"
    )
    
    parser.add_argument(
        "imagen",
        help="Ruta de la imagen del sistema fiunamfs"
    )
    
    parser.add_argument(
        "montaje",
        help="Directorio donde se va a montar el sistema de archivos"
    )
    """
    operaciones me sirve a que el usuario solo ejecute una sola accion de todas las 
    contenidas en el grupo, es decir, no puede listar y eliminar al mismo tiempo
    """
    operaciones = parser.add_mutually_exclusive_group()
    
    operaciones.add_argument(
        "--listar",
        action="store_true",
        help="lista los archivos que hay en FiUnamFS"
    )
    
    operaciones.add_argument(
        "--leer",
        metavar="ARCHIVO",
        help="lee el contenido de un archivo de FiUnamFS."
    )
    
    operaciones.add_argument(
        "--copiar",
        metavar="ARCHIVO",
        help="copia un archivo de FiUnamFS al destino local"
    )
    
    parser.add_argument(
        "--destino",
        default=".",
        help="destino donde se va a guardar el archivo extraido"
    )
    
    operaciones.add_argument(
        "--eliminar",
        metavar="ARCHIVO",
        help="elimina un archivo de FiUnamFS"
    )
    
    operaciones.add_argument(
        "--insertar",
        metavar="ARCHIVO_LOCAL",
        help="copia un archivo del sistema local hacia FiUnamFS"
    )
    
    return parser

"""
Valida si las rutas existen en el sistema
"""
def validar_rutas(ruta_imagen, ruta_montaje):
    if not ruta_imagen.exists():
        print(f"Error: no se encontro la imagen en '{ruta_imagen}'.")
        return False
    
    if not ruta_imagen.is_file():
        print(f"Error: '{ruta_imagen}' no es el archivo esperado.")
        return False
    
    if not ruta_montaje.exists():
        print(f"Error: no existe la ruta de '{ruta_montaje}'.")
        return False
    
    if not ruta_montaje.is_dir():
        print(f"Error: '{ruta_montaje}' no es un directorio.")
        return False
    
    return True
