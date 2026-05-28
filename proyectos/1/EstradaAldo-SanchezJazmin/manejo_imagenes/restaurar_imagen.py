#!/usr/bin/env python3
"""
restaura la imagen de pruebas de FiUnamFS

este script copia el contenido de fiunamfs.img sobre fiunamfs_pruebas.img,
dejando la imagen de pruebas en su estado original
"""

from pathlib import Path
import shutil


def main():
    carpeta_actual = Path(__file__).resolve().parent
    
    imagen_original = carpeta_actual / "fiunamfs.img"
    imagen_pruebas = carpeta_actual / "fiunamfs_pruebas.img"
    
    if not imagen_original.exists():
        print(f"Error: no existe la imagen original '{imagen_original}'")
        return 1
    
    if not imagen_original.is_file():
        print(f"Error: '{imagen_original}' no es un archivo valido")
        return 1
    
    shutil.copyfile(imagen_original, imagen_pruebas)
    
    print("Imagen de pruebas restaurada correctamente.")
    print(f"Origen:  {imagen_original}")
    print(f"Destino: {imagen_pruebas}")
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
