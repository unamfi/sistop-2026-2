"""
Proyecto (Micro) sistema de archivos multihiloss
Autores: 
    - Gonzalez Falcon Luis Adrían
    - Lopez Morales Fernando Samuel
Entrega 2026-05-21
"""

import threading
import time
import struct
import sys, os, stat, errno
import fuse 
from fuse import Fuse

from fiunamfs import FiUnamFS

# Versión de api de python para FUSE
fuse.fuse_python_api = (0, 2)

orden_actual = {"comando": None, "argumentos": []}
sistema_corriendo = True

#mutex para proteger el disco
mutex_fs = threading.Semaphore(1)

#semaforos sincronización
sem_orden_pendiente = threading.Semaphore(0)
sem_orden_terminada = threading.Semaphore(0)


#Hilo secundario que actúa cuando sucede algún evento
def hilo_trabajador(motor_fs):
    global sistema_corriendo, orden_actual
    
    #print("\nHilo TRABAJADOR iniciado y esperando...")
    
    while sistema_corriendo:
        
        #Hilo trabajador se queda en espera hasta que la interfaz suelte el mutex
        sem_orden_pendiente.acquire()
        
        if not sistema_corriendo:
            #print("Hilo TRABAJADOR saliendo")
            break
        
        #print("Hilo TRABAJADOR despierta")
        comando = orden_actual["comando"]
        args = orden_actual["argumentos"]
        
        # Hilo bloquea el disco para realizar una exclusión
        #print("Hilo TRABAJADOR adquiere el mutex del disco para que nadie más lo use")
        mutex_fs.acquire()
        
        try:
            orden_actual["resultado"] = -errno.EIO
            if comando == "listar_fuse":
                orden_actual["resultado"] = motor_fs.listar_directorio()
            elif comando == "eliminar_fuse":
                # Intentamos eliminar, si falla atrapamos el error para FUSE
                try:
                    motor_fs.eliminar_archivo(args[0])
                    orden_actual["resultado"] = 0 # 0 en Unix significa "éxito"
                except FileNotFoundError:
                    orden_actual["resultado"] = -errno.ENOENT
            elif comando == "leer_fuse":
                try:
                    orden_actual["resultado"] = motor_fs.leer_bytes_archivo(args[0], args[1], args[2])
                except FileNotFoundError:
                    orden_actual["resultado"] = -errno.ENOENT
            elif comando == "escribir_fuse":
                try:
                    motor_fs.escribir_desde_buffer(args[0], args[1])
                    orden_actual["resultado"] = 0
                except Exception as e:
                    sys.stderr.write(f"\nError al guardar archivo {e}\n")
                    orden_actual["resultado"] = -errno.ENOSPC
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")
        finally:
            mutex_fs.release()
        
        # liberamos el mutex
        sem_orden_terminada.release()
class FiUnamFS_FUSE(Fuse):
    def __init__(self, *args, **kw):
        fuse.Fuse.__init__(self, *args, **kw)
        
        #Identificadores del usuario
        self.uid = os.getuid()
        self.gid = os.getgid()

        self.buffers_escritura = {}

    def getattr(self, path: str):
        st = fuse.Stat()
        
        # pertencera al usuario que montó el sistema
        st.st_uid = self.uid
        st.st_gid = self.gid

        if path == '/':
            st.st_mode = stat.S_IFDIR | 0o777
            st.st_nlink = 2
            return st

        nombre_archivo = path[1:]
        

        if nombre_archivo in self.buffers_escritura:
            st.st_mode = stat.S_IFREG | 0o666
            st.st_nlink = 1
            st.st_size = len(self.buffers_escritura[nombre_archivo])
            st.st_ctime = int(time.time())
            st.st_mtime = st.st_ctime
            st.st_atime = st.st_ctime
            return st

        global orden_actual
        orden_actual["comando"] = "listar_fuse"
        sem_orden_pendiente.release()
        sem_orden_terminada.acquire()
        
        archivos = orden_actual["resultado"]

        if nombre_archivo in archivos:
            meta = archivos[nombre_archivo]
            st.st_mode = stat.S_IFREG | 0o666
            st.st_nlink = 1
            st.st_size = meta['tamano']
            st.st_ctime = meta['c_time']
            st.st_mtime = meta['m_time']
            st.st_atime = meta['m_time']
            return st

        return -errno.ENOENT

    def readdir(self, path: str, offset: int):
        if path == '/':
            global orden_actual
            orden_actual["comando"] = "listar_fuse"
            sem_orden_pendiente.release()
            sem_orden_terminada.acquire()
            
            archivos = orden_actual["resultado"]
            
            # COmo en la clase
            for r in ['.', '..'] + list(archivos.keys()):
                yield fuse.Direntry(r)
    def unlink(self, path: str):
        """
        Elimina un archivo. Invocado por el comando 'rm' que detona la llamada unlink()
        """
        nombre_archivo = path[1:]
        
        global orden_actual
        orden_actual["comando"] = "eliminar_fuse"
        orden_actual["argumentos"] = [nombre_archivo]
        
        # Sincronización con el trabajador
        sem_orden_pendiente.release()
        sem_orden_terminada.acquire()
        
        # 0: exitoso || -errno si fallo
        return orden_actual["resultado"]
        
    def read(self, path: str, size: int, offset: int):
        """
        Lee 'size' bytes del archivo indicado, empezando en 'offset'.
        """
        nombre_archivo = path[1:]
        
        global orden_actual
        orden_actual["comando"] = "leer_fuse"
        orden_actual["argumentos"] = [nombre_archivo, size, offset]
        
        # Sincronización con el trabajador
        sem_orden_pendiente.release()
        sem_orden_terminada.acquire()
        
        # El trabajador nos devuelve la cadena de bytes leída, o un error de -errno
        return orden_actual["resultado"]

    def truncate(self, path: str, length: int):
        #Entra cuando se crea un archivo nuevo o se sobreescribe uno.
        
        nombre_archivo = path[1:]
        self.buffers_escritura[nombre_archivo] = b''
        return 0

    def write(self, path: str, buf: bytes, offset: int):
        #Maneja pedazos de archivos
        nombre_archivo = path[1:]
        
        if nombre_archivo not in self.buffers_escritura:
            self.buffers_escritura[nombre_archivo] = b''

        contenido = self.buffers_escritura[nombre_archivo]
        dest = b''
        if offset > 0:
            dest += contenido[0:offset]
        dest += buf
        if len(contenido) > offset + len(buf):
            dest += contenido[(offset+len(buf)):]

        self.buffers_escritura[nombre_archivo] = dest
        return len(buf)

    def release(self, path: str, flags: int):
        #Liberar la memoria con datos
        nombre_archivo = path[1:]
        
        if nombre_archivo in self.buffers_escritura:
            datos_completos = self.buffers_escritura[nombre_archivo]
            
            global orden_actual
            orden_actual["comando"] = "escribir_fuse"
            orden_actual["argumentos"] = [nombre_archivo, datos_completos]
            
            # Mandamos los datos al hilo trabajador
            sem_orden_pendiente.release()
            sem_orden_terminada.acquire()
            
            # Limpiamos la memoria
            del self.buffers_escritura[nombre_archivo]
            
            return orden_actual["resultado"]
        return 0
    def create(self, path: str, *args):
        #Cuando se ejecuta el comando cp o touch para crear u arhi
        nombre_archivo = path[1:]
        self.buffers_escritura[nombre_archivo] = b''
        return 0

    def mknod(self, path: str, *args):
        #Se requiere para realizar cp
        nombre_archivo = path[1:]
        self.buffers_escritura[nombre_archivo] = b''
        return 0

    def open(self, path: str, flags: int):
        #Se invoca antes de leer o escribir, retornar 0 indica que todo está bien
        return 0

    def chmod(self, path: str, mode: int):
        #Evitar copiar los permisos
        return 0

    def chown(self, path: str, uid: int, gid: int):
        #Evitar copiar el owner
        return 0

#Hilo principal que va a contener la funcionalidad de la interfaz
def main():
    global sistema_corriendo, orden_actual
    
    #print("========= INICIANDO PROYECTO 1 =========")
    
    if len(sys.argv) < 2 or sys.argv[1] == '--help':
        #print("Uso: python3 fiunamfs_fuse.py <punto_montaje>")
        sys.exit(1)

    sys.argv.insert(1, '-f')
    #trycatch por si hay un dato que no es válido
    try:
        motor = FiUnamFS("./fiunamfs.img")
        motor.conectar()
        #motor.validar_superbloque()
    except Exception as e:
        #print(f"Error al iniciar: {e}")
        return

    trabajador = threading.Thread(target=hilo_trabajador, args=(motor,))
    trabajador.start()
    time.sleep(0.2)
    
    server = FiUnamFS_FUSE(version="%prog " + fuse.__version__,
                           usage="Montaje FiUnamFS mediante FUSE",
                           dash_s_do='setsingle')
    server.parse(errex=1)
    
    try:
        server.main()
    finally:
        sistema_corriendo = False
        sem_orden_pendiente.release()
        trabajador.join()
        motor.desconectar()

if __name__ == "__main__":
    main()