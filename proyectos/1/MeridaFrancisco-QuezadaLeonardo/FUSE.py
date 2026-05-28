#!/usr/bin/env python3
# fuse_fiunamfs.py
# Monta la imagen FiUnamFS en una carpeta usando FUSE.

import os
import sys
import stat
import time

from errno import ENOENT, EEXIST

from fuse import FUSE, Operations, FuseOSError

from imagen_fiunamfs import ImagenFiUnamFS


class MontajeFiUnamFS(Operations):
    def __init__(self, ruta_imagen):
        self.fs = ImagenFiUnamFS(ruta_imagen)

        # Linux puede mandar una escritura por partes.
        # Aquí se guarda temporalmente el contenido hasta cerrar el archivo.
        self.archivos_en_escritura = {}

    def access(self, path, mode):
        # Se acepta el acceso y las validaciones se hacen en read, write, etc.
        return 0

    def _nombre_desde_path(self, path):
        # FiUnamFS no maneja subdirectorios, por eso sólo se toma el nombre.
        return path.lstrip("/")

    def _buscar(self, path):
        nombre = self._nombre_desde_path(path)

        if nombre == "":
            return None

        with self.fs.lock:
            return self.fs.buscar_archivo(nombre)

    def getattr(self, path, fh=None):
        # FUSE usa esto para saber si la ruta es carpeta o archivo.
        if path == "/":
            return {
                "st_mode": stat.S_IFDIR | 0o755,
                "st_nlink": 2,
                "st_size": 0,
                "st_ctime": time.time(),
                "st_mtime": time.time(),
                "st_atime": time.time()
            }

        registro = self._buscar(path)

        if registro is None:
            raise FuseOSError(ENOENT)

        return {
            "st_mode": stat.S_IFREG | 0o644,
            "st_nlink": 1,
            "st_size": registro.tamanio,
            "st_ctime": time.time(),
            "st_mtime": time.time(),
            "st_atime": time.time()
        }

    def readdir(self, path, fh):
        if path != "/":
            raise FuseOSError(ENOENT)

        archivos = self.fs.listar_archivos()
        nombres = [archivo.nombre for archivo in archivos]

        return [".", ".."] + nombres

    def open(self, path, flags):
        if self._buscar(path) is None:
            raise FuseOSError(ENOENT)

        return 0

    def read(self, path, size, offset, fh):
        nombre = self._nombre_desde_path(path)

        if self._buscar(path) is None:
            raise FuseOSError(ENOENT)

        # FUSE puede pedir el archivo por partes, no necesariamente completo.
        return self.fs.leer_archivo(nombre, size, offset)

    def create(self, path, mode, fi=None):
        nombre = self._nombre_desde_path(path)

        if nombre == "":
            raise FuseOSError(ENOENT)

        if self._buscar(path) is not None:
            raise FuseOSError(EEXIST)

        self.archivos_en_escritura[nombre] = bytearray()
        return 0

    def mknod(self, path, mode, dev):
        nombre = self._nombre_desde_path(path)

        if nombre == "":
            raise FuseOSError(ENOENT)

        if self._buscar(path) is not None:
            raise FuseOSError(EEXIST)

        # Algunos comandos usan mknod para crear archivos.
        self.archivos_en_escritura[nombre] = bytearray()
        return 0

    def truncate(self, path, length, fh=None):
        nombre = self._nombre_desde_path(path)

        if nombre not in self.archivos_en_escritura:
            registro = self._buscar(path)

            if registro is None:
                self.archivos_en_escritura[nombre] = bytearray()
            else:
                contenido = self.fs.leer_archivo(nombre)
                self.archivos_en_escritura[nombre] = bytearray(contenido)

        buffer = self.archivos_en_escritura[nombre]

        if length < len(buffer):
            del buffer[length:]
        elif length > len(buffer):
            buffer.extend(b"\x00" * (length - len(buffer)))

        return 0

    def write(self, path, data, offset, fh):
        nombre = self._nombre_desde_path(path)

        if nombre not in self.archivos_en_escritura:
            self.archivos_en_escritura[nombre] = bytearray()

        buffer = self.archivos_en_escritura[nombre]
        fin = offset + len(data)

        # Si se escribe más adelante, se rellenan los bytes intermedios.
        if fin > len(buffer):
            buffer.extend(b"\x00" * (fin - len(buffer)))

        buffer[offset:fin] = data
        return len(data)

    def flush(self, path, fh):
        return 0

    def release(self, path, fh):
        nombre = self._nombre_desde_path(path)

        if nombre in self.archivos_en_escritura:
            contenido = bytes(self.archivos_en_escritura[nombre])

            # Se escribe al cerrar para evitar guardar un archivo incompleto.
            self.fs.reemplazar_archivo(nombre, contenido)

            del self.archivos_en_escritura[nombre]

        return 0

    def unlink(self, path):
        nombre = self._nombre_desde_path(path)

        if self._buscar(path) is None:
            raise FuseOSError(ENOENT)

        self.fs.eliminar_archivo(nombre)
        return 0

    def utimens(self, path, times=None):
        # Algunos comandos intentan actualizar tiempos del archivo.
        # Se acepta para evitar errores innecesarios.
        return 0

    def destroy(self, path):
        self.fs.cerrar()


def main():
    if len(sys.argv) != 3:
        print("Uso:")
        print("  python3 fuse_fiunamfs.py <imagen.img> <carpeta_montaje>")
        sys.exit(1)

    ruta_imagen = sys.argv[1]
    punto_montaje = sys.argv[2]

    if not os.path.exists(ruta_imagen):
        print(f"No existe la imagen: {ruta_imagen}")
        sys.exit(1)

    if not os.path.isdir(punto_montaje):
        print(f"No existe la carpeta de montaje: {punto_montaje}")
        sys.exit(1)

    print("Montando FiUnamFS...")
    print(f"Imagen: {ruta_imagen}")
    print(f"Montaje: {punto_montaje}")
    print(f"Para desmontar: fusermount3 -u {punto_montaje}")

    FUSE(
        MontajeFiUnamFS(ruta_imagen),
        punto_montaje,
        foreground=True
    )


if __name__ == "__main__":
    main()