"""
interfaz de FUSE para montar FiUnamFS

montaje de lectura con fuse para listar archivos, 
consultar atributos y leer contenido
"""

import errno
import stat
import fuse

from fuse import Fuse
fuse.fuse_python_api = (0,2)

"""
sistema FiUnamFS con fuse
"""
class SistemaFuse(Fuse):
    def __init__(self, fiunamfs, *args, **kwargs):
        Fuse.__init__(self, *args, **kwargs)
        self.fiunamfs = fiunamfs
        self.archivos_temporales = {}
    
    """
    listar el contenido del directorio raiz
    """
    def readdir(self, path, offset):
        if path != "/":
            return -errno.ENOENT
        
        for entrada in [".", ".."]:
            yield fuse.Direntry(entrada)
        
        archivos = self.fiunamfs.listar_archivos()
        
        for archivo in archivos:
            yield fuse.Direntry(archivo.nombre_archivo)
        
        for nombre_archivo in self.archivos_temporales:
            yield fuse.Direntry(nombre_archivo)
    
    """
    obtener atributos de un archivo o directorio
    """
    def getattr(self, path):
        st = fuse.Stat()
        
        if path == "/":
            st.st_mode = stat.S_IFDIR | 0o755
            st.st_nlink = 2
            return st
        
        nombre_archivo = path[1:]
        
        if nombre_archivo in self.archivos_temporales:
            st.st_mode = stat.S_IFREG | 0o644
            st.st_nlink = 1
            st.st_size = len(self.archivos_temporales[nombre_archivo])
            return st
        
        entrada = self.fiunamfs.buscar_archivo(nombre_archivo)
        
        if entrada is None:
            return -errno.ENOENT
        
        st.st_mode = stat.S_IFREG | 0o644
        st.st_nlink = 1
        st.st_size = entrada.tamano
        
        return st
    
    """
    lectura de un archivo de FiUnamFS
    """
    def read(self, path, size, offset):
        nombre_archivo = path[1:]
        
        if nombre_archivo in self.archivos_temporales:
            contenido = self.archivos_temporales[nombre_archivo]
            return bytes(contenido[offset:offset + size])
        
        contenido = self.fiunamfs.leer_archivo(nombre_archivo, size, offset)
        
        if contenido is None:
            return -errno.ENOENT
        
        return contenido
    
    """
    elimina un archivo desde el montaje de FUSE
    """
    def unlink(self, path):
        nombre_archivo = path[1:]
        
        if not self.fiunamfs.eliminar_archivo(nombre_archivo):
            return -errno.ENOENT
        return 0
    
    """
    crea un archivo temporal cuando se copia hacia el montaje
    """
    def crear_archivo_temporal(self, path):
        nombre_archivo = path[1:]
        
        if nombre_archivo in self.archivos_temporales:
            return 0
        
        entrada = self.fiunamfs.buscar_archivo(nombre_archivo)
        
        if entrada is not None:
            contenido = self.fiunamfs.leer_archivo(nombre_archivo)
            
            if contenido is None:
                return -errno.ENOENT
            
            self.archivos_temporales[nombre_archivo] = bytearray(contenido)
            return 0
        
        self.archivos_temporales[nombre_archivo] = bytearray()
        return 0
    
    """
    crea un archivo temporal cuando FUSE usa mknod()
    """
    def mknod(self, path, mode, dev):
        return self.crear_archivo_temporal(path)
    
    """
    crea un archivo temporal cuando FUSE usa create()
    """
    def create(self, path, flags, mode):
        return self.crear_archivo_temporal(path)
    
    """
    escribe los datos recibidos por FUSE en un buffer temporal
    """
    def write(self, path, body, offset):
        nombre_archivo = path[1:]
        
        if nombre_archivo not in self.archivos_temporales:
            if self.fiunamfs.buscar_archivo(nombre_archivo) is not None:
                contenido = self.fiunamfs.leer_archivo(nombre_archivo)
                
                if contenido is None:
                    return -errno.ENOENT
                
                self.archivos_temporales[nombre_archivo] = bytearray(contenido)
                
            else:
                self.archivos_temporales[nombre_archivo] = bytearray()
        
        contenido = self.archivos_temporales[nombre_archivo]
        fin = offset + len(body)
        
        if len(contenido) < offset:
            contenido.extend(b"\x00" * (offset - len(contenido)))
        
        if len(contenido) < fin:
            contenido.extend(b"\x00" * (fin - len(contenido)))
        
        contenido[offset:fin] = body
        
        return len(body)
    
    """
    ajusca el tamano del archivo temporal
    """
    def truncate(self, path, length):
        nombre_archivo = path[1:]
        
        if nombre_archivo not in self.archivos_temporales:
            return 0
        
        contenido = self.archivos_temporales[nombre_archivo]
        
        if len(contenido) < length:
            contenido.extend(b"\x00" * (length - len(contenido)))
        else:
            del contenido[length:]
        
        return 0
    
    """
    guarda el archivo temporal en FiUnamFS cuando FUSE termina de usarlo
    """
    def release(self, path, flags):
        nombre_archivo = path[1:]
        
        if nombre_archivo not in self.archivos_temporales:
            return 0
        
        contenido = bytes(self.archivos_temporales[nombre_archivo])
        
        if self.fiunamfs.buscar_archivo(nombre_archivo) is None:
            if not self.fiunamfs.insertar_archivo_desde_bytes(nombre_archivo, 
                                                              contenido):
                del self.archivos_temporales[nombre_archivo]
                return -errno.EIO
        else:
            if not self.fiunamfs.reemplazar_archivo_desde_bytes(nombre_archivo, 
                                                                contenido):
                del self.archivos_temporales[nombre_archivo]
                return -errno.EIO
        del self.archivos_temporales[nombre_archivo]
        
        return 0
