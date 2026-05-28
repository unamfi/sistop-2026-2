from fuse import FUSE, FuseOSError, Operations
from filesystem import FiUnamFS
import stat
import errno
import os


class FiUnamFuse(Operations):
    def __init__(self, ruta_img):
        self.fs = FiUnamFS(ruta_img)
        if not self.fs.validar_fs():
            raise RuntimeError("Imagen de disco inválida")
        # Buffer simple para escritura en memoria
        self.write_buffer = {}

    def getattr(self, path, fh=None):
        if path == '/':
            return dict(st_mode=(stat.S_IFDIR | 0o755), st_nlink=2)

        nombre = path[1:]
        archivos = self.fs.listar_directorio()
        for arch in archivos:
            if arch['nombre'] == nombre:
                return dict(st_mode=(stat.S_IFREG | 0o644), st_nlink=1, st_size=arch['tamano'])
        raise FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        if path != '/':
            return []
        archivos = self.fs.listar_directorio()
        return ['.', '..'] + [arch['nombre'] for arch in archivos]

    def read(self, path, size, offset, fh):
        return self.fs.leer_bytes_archivo(path[1:], size, offset)

    def unlink(self, path):
        self.fs.eliminar_archivo(path[1:])

    def create(self, path, mode, fi=None):
        self.write_buffer[path] = b''  # Inicializar buffer
        return 0

    def write(self, path, data, offset, fh):
        self.write_buffer[path] += data  # Acumular en memoria
        return len(data)

    def release(self, path, fh):
        # Cuando se cierra el archivo, guardamos todo el buffer
        if path in self.write_buffer:
            self.fs.escribir_bytes_archivo(path[1:], self.write_buffer[path])
            del self.write_buffer[path]
        return 0


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print("Uso: python3 fuse_main.py <ruta_imagen> <punto_montaje>")
        sys.exit(1)

    FUSE(FiUnamFuse(sys.argv[1]), sys.argv[2], foreground=True, nonempty=True)
