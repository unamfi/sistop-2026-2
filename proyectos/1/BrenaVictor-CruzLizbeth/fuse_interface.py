"""
Proyecto micro Sistema de Archivos
Autores:
    Brena de León Vícctor JAvier
    Cruz Manríquez Lizbeth

Capa de Abstracción de Llamadas de Interfaz para el Driver de FUSE.

Este módulo implementa el mapeo de llamadas al sistema del estándar POSIX hacia
las operaciones lógicas internas de disco FiUnamFS. Hereda del 
framework 'fuse.Fuse' para traducir las interacciones del kernel.
"""

import stat
import errno
import struct
import fuse
from fuse import Fuse
fuse.fuse_python_api = (0, 2)
class FiUnamFSFuse(Fuse):
    """Comunicación FUSE entre el Kernel de Linux y nuestro micro sistema de archivos.
    
    Cada método implementado aquí intercepta de forma transparente comandos estándar 
    del sistema operativo como ls, touch, cp, rm, cat y df.
    """

    def __init__(self, fiunam, fs_lock, log_operation_callback, *args, **kw):
        """Vincula las instancias operacionales y los candados concurrentes con la superclase FUSE."""
        Fuse.__init__(self, *args, **kw)
        self.fs = fiunam
        self.fs_lock = fs_lock
        self.log_operation = log_operation_callback

    def readdir(self, path, offset):
        """Intercepta la petición de listado de directorios (ej. comando `ls`).
        
        Inyecta las entradas virtuales indispensables '.' y '..' requeridas por POSIX 
        para la navegación relativa, y posteriormente itera sobre el listado de archivos 
        vivos devuelto por el controlador de bajo nivel.
        """
        with self.fs_lock:
            yield fuse.Direntry('.')
            yield fuse.Direntry('..')
            for f in self.fs.read_directory():
                yield fuse.Direntry(f["name"])

    def getattr(self, path):
        """Recupera de forma transparente las estructuras de atributos y metadatos de un nodo (Stat).
        
        Determina si la ruta solicitada corresponde a la raíz virtual (mapeada como un directorio 
        con permisos de lectura y ejecución 0o755) o a un archivo regular activo, reportando su 
        dimensión exacta en bytes al planificador del sistema operativo.
        """
        with self.fs_lock:
            st = fuse.Stat()
            if path == '/':
                st.st_mode = stat.S_IFDIR | 0o755
                st.st_nlink = 2
                return st

            file_entry = self.fs.find_file(path[1:])
            if not file_entry:
                return -errno.ENOENT

            st.st_mode = stat.S_IFREG | 0o644
            st.st_nlink = 1
            st.st_size = file_entry["size"]
            return st

    def read(self, path, size, offset):
        """Procesa la lectura de datos lógicos (ej. comandos `cat` o `cp` externo).
        
        Extrae el búfer de bytes del archivo solicitado y segmenta el rango dinámico 
        delimitado por las variables 'offset' y 'size'. Registra un log asíncrono para evidenciar 
        la copia hacia afuera en el monitor concurrente.
        """
        filename = path[1:]
        with self.fs_lock:
            data = self.fs.read_file(filename)
            if data is None:
                return -errno.ENOENT
            
            self.log_operation(f"READ {filename} ({min(size, len(data) - offset)} bytes en offset {offset})")
            return data[offset:offset + size]

    def unlink(self, path):
        """Captura la llamada de  `rm`."""
        with self.fs_lock:
            if self.fs.delete_file(path[1:]):
                return 0
            return -errno.ENOENT

    def mknod(self, path, mode, dev):
        """Crea un nuevo archivo regular dentro del disco (ej. comando `touch`).
        
        Mapea una nueva estructura binaria de 64 bytes inicializada con el carácter '-' 
        de tipo regular, rellena el nombre con espacios fijos, empaqueta el tamaño inicial (0) 
        en Little-Endian y lo escribe en la primera ranura vacía localizada del directorio.
        """
        filename = path[1:]
        with self.fs_lock:
            if self.fs.find_file(filename):
                return -errno.EEXIST

            entry_pos = self.fs.find_free_directory_entry()
            if entry_pos is None:
                return -errno.ENOSPC

            cluster = self.fs.find_free_cluster(0)
            entry = bytearray(64)
            entry[0:1] = b'-'
            entry[1:16] = filename.encode("ascii").ljust(15, b' ')
            entry[16:20] = struct.pack("<I", 0)
            entry[20:24] = struct.pack("<I", cluster)
            
            date = self.fs.current_date().encode("ascii")
            entry[24:38] = date
            entry[38:52] = date

            self.fs.disk.seek(entry_pos)
            self.fs.disk.write(entry)
            self.fs.disk.flush()
            
            self.log_operation(f"Archivo creado: {filename}")
            return 0

    def create(self, path, mode, dev=0):
        """Redirige las solicitudes de creación hacia mknod conforme al estándar FUSE."""
        return self.mknod(path, mode, dev)

    def write(self, path, buf, offset):
        """Abstrae la inyección y sobreescritura de datos (ej. comando de redirección `>`).
        
        Modifica parcial o totalmente el mapa de bytes del archivo en memoria volátil combinándolo 
        con el contenido del búfer intermedio recibido a partir del offset indicado. Posteriormente, 
        ordena al driver persistir los cambios físicamente dentro de los clústeres del disco duro simulado.
        """
        filename = path[1:]
        with self.fs_lock:
            file_entry = self.fs.find_file(filename)
            if not file_entry:
                return -errno.ENOENT

            old_data = self.fs.read_file(filename) or b''
            new_data = bytearray(old_data)

            if offset > len(new_data):
                new_data.extend(b'\x00' * (offset - len(new_data)))
            
            new_data[offset:offset + len(buf)] = buf

            self.fs.write_file_data(filename, bytes(new_data))
            self.log_operation(f"WRITE {filename} ({len(buf)} bytes en offset {offset})")
            return len(buf)

    def truncate(self, path, length):
        """Captura las llamadas de truncado de flujos binarios."""
        with self.fs_lock:
            if self.fs.truncate_file(path[1:], length):
                return 0
            return -errno.ENOENT

    def utime(self, path, times):
        """Captura las actualizaciones de estampas temporales de acceso para preservar la compatibilidad POSIX."""
        return 0

    def open(self, path, flags):
        """Valida y autoriza el descriptor de apertura transparente exigido por procesos externos."""
        return 0

    def release(self, path, flags):
        """Maneja el cierre del descriptor de archivo liberando los bloqueos del núcleo."""
        return 0

    def statfs(self):
        """Abstrae el reporte de estadísticas generales de almacenamiento del disco (ej. comando `df -h`).
        
        Permite que cualquier herramienta del sistema operativo pueda calcular el espacio disponible, 
        bloques libres y longitudes máximas de nombres del volumen virtual.
        """
        with self.fs_lock:
            st = fuse.Statfs()
            st.f_bsize = 2048
            st.f_blocks = 360  
            st.f_bfree = 200
            st.f_bavail = 200
            st.f_namemax = 15
            return st