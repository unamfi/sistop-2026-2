import sys
import os
import stat
import errno
import struct
import tempfile
from time import time
from datetime import datetime
from fuse import FUSE, Operations, FuseOSError
from fiunamfs import FiUnamFS
from monitor import Monitor

class FiUnamFuse(Operations):
    def __init__(self, img_path):
        self.img_path = img_path
        self.fs = FiUnamFS(img_path)
        
        # Sincronización multihilos: Inicializamos el monitor
        self.monitor = Monitor(self.fs)
        self.monitor.iniciar()
        
        # Diccionario para gestionar los archivos mientras se están arrastrando/escribiendo
        self.archivos_abiertos = {}

    def destroy(self, path):
        # Detenemos el hilo limpiamente al desmontar
        self.monitor.detener()

    def _parse_time(self, time_str):
        try:
            dt = datetime.strptime(time_str[:14], "%Y%m%d%H%M%S")
            return dt.timestamp()
        except Exception:
            return time()

    # ==========================================
    # LECTURA Y LISTADO (Listar y Extraer)
    # ==========================================

    def getattr(self, path, fh=None):
        if path == '/':
            return {
                'st_mode': (stat.S_IFDIR | 0o755),
                'st_nlink': 2,
                'st_ctime': time(),
                'st_mtime': time(),
                'st_atime': time()
            }
        
        filename = path.lstrip('/')

        # Si el archivo se está copiando en este instante, devolvemos 
        # las propiedades del archivo temporal para que la barra de progreso funcione
        for info in self.archivos_abiertos.values():
            if info['filename'] == filename:
                st = os.stat(info['temp_path'])
                return {
                    'st_mode': (stat.S_IFREG | 0o644),
                    'st_nlink': 1,
                    'st_size': st.st_size, 
                    'st_ctime': time(),
                    'st_mtime': time(),
                    'st_atime': time()
                }
        
        # Si no se está copiando, lo buscamos en el directorio del disco
        archivos = self.fs.listar(imprimir=False)
        for archivo in archivos:
            file_name_bytes = archivo[1:15].decode('ascii', errors='ignore').rstrip('\x00').rstrip()
            
            if file_name_bytes == filename:
                file_size = struct.unpack('<I', archivo[16:20])[0]
                creation_time = archivo[30:44].decode('ascii', errors='ignore').rstrip('\x00')
                mod_time = archivo[50:64].decode('ascii', errors='ignore').rstrip('\x00')
                
                return {
                    'st_mode': (stat.S_IFREG | 0o644),
                    'st_nlink': 1,
                    'st_size': file_size,
                    'st_ctime': self._parse_time(creation_time),
                    'st_mtime': self._parse_time(mod_time),
                    'st_atime': self._parse_time(mod_time)
                }

        raise FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        yield '.'
        yield '..'
        
        archivos = self.fs.listar(imprimir=False)
        for archivo in archivos:
            file_type = chr(archivo[0])
            if file_type == '-':
                file_name = archivo[1:15].decode('ascii', errors='ignore').rstrip('\x00').rstrip()
                yield file_name
                
        # Mostrar también los archivos fantasma que apenas se están recibiendo
        for info in self.archivos_abiertos.values():
            yield info['filename']

    def read(self, path, length, offset, fh):
        filename = path.lstrip('/')
        data = self.fs.extraer_datos(filename)
        
        if data is None:
            raise FuseOSError(errno.ENOENT)
        return data[offset:offset + length]

    def unlink(self, path):
        # Eliminar archivo
        filename = path.lstrip('/')
        exito = self.fs.borrar(filename)
        
        if exito:
            self.monitor.notificar('delete')
        else:
            raise FuseOSError(errno.EIO)

    # ==========================================
    # ESCRITURA (Pegar desde FUSE a FiUnamfs)
    # ==========================================

    def create(self, path, mode, fi=None):
        # Se arrastra un archivo. Creamos un archivo temporal 
        filename = path.lstrip('/')
        fd, temp_path = tempfile.mkstemp() 
        self.archivos_abiertos[fd] = {'filename': filename, 'temp_path': temp_path}
        return fd

    def write(self, path, buf, offset, fh):
        # Se mandan los bytes. Los guardamos en nuestro archivo temporal
        os.lseek(fh, offset, os.SEEK_SET)
        os.write(fh, buf)
        return len(buf)

    def release(self, path, fh):
        # Se terminó de enviar todo
        if fh in self.archivos_abiertos:
            file_info = self.archivos_abiertos[fh]
            filename = file_info['filename']
            temp_path = file_info['temp_path']
            
            os.close(fh) # Liberamos el temporal para que FiUnamFS pueda leerlo
            
            # Mandamos llamar la función original (esto inyecta los datos al superbloque/clusters)
            exito = self.fs.pegar(temp_path, nombre_destino=filename)
            
            if exito:
                self.monitor.notificar('paste')
            
            # Borramos el archivo temporal
            os.remove(temp_path)
            del self.archivos_abiertos[fh]
            
        return 0

def main():
    if len(sys.argv) < 3:
        print("Uso: python/python3 interfazFUSE.py <archivo.img> <punto_de_montaje>")
        sys.exit(1)

    img_path = sys.argv[1]
    mount_point = sys.argv[2]

    print(f"Montando '{img_path}' en '{mount_point}'...")
    
    print("\n===========================================================================================\n")
    print("    Para desmontar presiona Ctrl+C o usa 'umount <punto_de_montaje>' en otra terminal.")
    print("\n===========================================================================================\n")

    FUSE(FiUnamFuse(img_path), mount_point, nothreads=True, foreground=True)
    

if __name__ == '__main__':
    main()