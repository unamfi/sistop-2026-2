#!/usr/bin/python3

#Programa principal, se encarga de implementar FUSE para conectar con todo el resto del sistema
#Autores: Isaac Campos, Alejandro Martinez
#Fecha de realización: 19 Mayo 2026

import fuse
import stat
import errno
import sys
import os
from datetime import datetime
from fiunamfs.disco import Disco
from fuse import Fuse

fuse.fuse_python_api = (0, 2)

#Clase principal del sistema de archivos montado con FUSE.
#Cada método responde a una operación que el sistema operativo puede solicitar:
#listar directorios, obtener atributos, leer, escribir, crear o eliminar archivos.

class FiUnamFs(Fuse):

    ruta_img = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._disco = None

    #Carga el objeto Disco cuando se necesita por primera vez.
    #Esto evita abrir y procesar la imagen antes de que FUSE empiece a usar el sistema.
    @property
    def disco(self):
        if self._disco is None:
            self._disco = Disco(self.ruta_img)
        return self._disco
        
    #Lista el contenido del directorio raíz mostrado por FUSE.
    #Además de los archivos de FiUnamFS, se incluyen las entradas especiales '.' y '..'.
    def readdir(self, path:str, offset:int):
        for r in [ '.', '..' ] + list(self.disco.listarEntradas()):
            yield fuse.Direntry(r)

    #Devuelve los atributos de un archivo o directorio.
    #FUSE usa esta información para saber si la ruta existe, su tamaño y sus permisos.
    def getattr(self, path:str):
        st = fuse.Stat()

        st.st_uid = os.getuid()   
        st.st_gid = os.getgid()   

        if path == '/':
            st.st_mode = stat.S_IFDIR | 0o755
            st.st_nlink = 2
            return st

        else:
            nombre = path.lstrip('/')
            entrada = self.disco.encontrarEntrada(nombre)
            if entrada != None:
                st.st_mode = stat.S_IFREG | 0o755
                st.st_nlink = 1
                st.st_size = entrada.tam_archivo
                cadena_fecha = entrada.hf_creado
                if len(cadena_fecha) == 14 and cadena_fecha.isdigit():
                    fecha_creacion = datetime.strptime(cadena_fecha, '%Y%m%d%H%M%S')
                    marca_tiempo = int(fecha_creacion.timestamp())
                else:
                    marca_tiempo = 0

                st.st_mtime = marca_tiempo
                st.st_ctime = marca_tiempo
                st.st_atime = marca_tiempo
                return st

        return -errno.ENOENT

    #Lee el contenido de un archivo desde FiUnamFS.
    #El parámetro offset permite devolver solo la parte solicitada por el sistema operativo.
    def read(self, path: str, size: int, offset: int) -> bytes:
        contenido = self.disco.leerEntrada(path.lstrip('/'))
        if contenido != None:
            slen = len(contenido)
            if offset < slen:
                if offset + size > slen:
                    size = slen - offset
                buf = contenido[offset:offset+size]
            else:
                # If reading beyond the end of the file, return an empty
                # byte string.
                buf = b''

            return buf
        else:
            return -errno.ENOENT

    #FUSE puede llamar a truncate durante ciertas operaciones de escritura.
    #En este proyecto se acepta la llamada para permitir el flujo normal de escritura.
    def truncate(self, path, length):
        return 0

    #Elimina un archivo del sistema montado.
    #Internamente se marca su entrada como libre dentro del directorio de FiUnamFS.
    def unlink(self, path: str):
        nombre = path.lstrip('/')
        if self.disco.encontrarEntrada(nombre) is not None:
            self.disco.eliminarEntrada(nombre)
            return 0
        else:
            return -errno.ENOENT

    #Crea una nueva entrada vacía cuando el sistema operativo solicita crear un archivo.
    #El contenido se escribirá posteriormente mediante el método write.
    def create(self, path:str, flags, mode):
        nombre = path.lstrip('/')
        if self.disco.encontrarEntrada(nombre):
            return -errno.EEXIST
        self.disco.escribirEntrada(nombre, b'')
        return 0

    #Valida que el archivo exista antes de permitir que sea abierto desde el punto de montaje.
    def open(self, path, flags):
        nombre = path.lstrip('/')
        if self.disco.encontrarEntrada(nombre) is None:
            return -errno.ENOENT
        return 0

    #Escribe datos sobre un archivo existente.
    #Se reconstruye el contenido considerando el offset para respetar la posición de escritura.
    def write(self, path, buf, offset):
        nombre = path.lstrip('/')
        entrada = self.disco.encontrarEntrada(nombre)
        if entrada is None:
            return -errno.ENOENT
        contenido = self.disco.leerEntrada(nombre)
        if contenido is None:
            contenido = b''
        nuevo = bytearray(contenido)
        if offset > len(nuevo):
            nuevo.extend(b'\x00' * (offset - len(nuevo)))
        nuevo[offset:offset+len(buf)] = buf
        self.disco.sobrescribirEntrada(nombre, bytes(nuevo))
        return len(buf)
    
#Configura FUSE, recibe la ruta de la imagen y monta el sistema de archivos.
#La imagen se toma del primer argumento recibido al ejecutar el programa.
def main():
    if len(sys.argv) < 3:
        sys.argv.append('--help')

    title = 'Proyecto - Mini Sistema de Archivos con FUSE'
    descr = ("Lee la imagen de un disco y permite montarlo al igual que realizar operaciones sobre el sistema")

    ruta_img = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    FiUnamFs.ruta_img = ruta_img

    if ruta_img and os.path.exists(ruta_img):
        try:
            from fiunamfs.disco import Disco
            _temp_disco = Disco(ruta_img) 
        except RuntimeError as e:
            print(f"\nError: {e}\n", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"\Error inesperado al leer la imagen: {e}\n", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"\nLa imagen '{ruta_img}' no existe.\n", file=sys.stderr)
        sys.exit(1)

    usage = ("\n\nProyecto: Mini Sistema de Archivos con FUSE\n  %s: %s\n\n%s\n\n%s" %
             (sys.argv[0], title, descr, fuse.Fuse.fusage))

    server = FiUnamFs(version="%prog " + fuse.__version__,
                                 usage=usage,
                                 dash_s_do='setsingle')

    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()
