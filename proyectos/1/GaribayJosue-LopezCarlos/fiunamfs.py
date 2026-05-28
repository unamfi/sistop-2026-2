import os
import struct
import threading
import queue
import time
from datetime import datetime

# Constantes del sistema de archivos FiUnamFS
TAMANO_CLUSTER = 2048
ENTRADAS_DIRECTORIO = 256
TAMANO_ENTRADA = 64
CLUSTER_DIRECTORIO_INICIO = 1

# Clase para encapsular las peticiones entre hilos
class PeticionFS:
    def __init__(self, accion, *args):
        self.accion = accion
        self.args = args
        self.resultado = None
        self.evento = threading.Event() # Mecanismo de sincronización

# Hilo trabajador que ejecuta las operaciones concurrentes
class FS(threading.Thread):
    def __init__(self, ruta_img, cola_peticiones):
        super().__init__()
        self.ruta_img = ruta_img
        self.cola_peticiones = cola_peticiones
        self.daemon = True  # Se cierra cuando el hilo principal termina
        self.lock_archivo = threading.Lock() 
        
    def run(self):
        while True:
            peticion = self.cola_peticiones.get()
            if peticion.accion == 'SALIR':
                break
            
            # Operaciones sobre el disco
            with self.lock_archivo:
                try:
                    self.validar_version()
                    if peticion.accion == 'LISTAR':
                        peticion.resultado = self.listar_archivos()
                    elif peticion.accion == 'COPIAR_FUERA':
                        peticion.resultado = self.copiar_fuera(peticion.args[0], peticion.args[1])
                    elif peticion.accion == 'COPIAR_DENTRO':
                        peticion.resultado = self.copiar_dentro(peticion.args[0], peticion.args[1])
                    elif peticion.accion == 'ELIMINAR':
                        peticion.resultado = self.eliminar_archivo(peticion.args[0])
                except Exception as e:
                    peticion.resultado = f"Error del sistema: {e}"
            
            peticion.evento.set() 
            self.cola_peticiones.task_done()

    def validar_version(self):
        with open(self.ruta_img, 'rb') as f:
            f.seek(5)
            nombre = f.read(8)
            if nombre != b'FiUnamFS':
                raise ValueError("FiUnamFS no válido.")
            f.seek(14)
            version = f.read(4)
            if b'24-2' not in version and b'26-2' not in version:
                raise ValueError("Versión de FiUnamFS no soportada.")
        
        
    def listar_archivos(self):
        archivos = []
        with open(self.ruta_img, 'rb') as f:
            f.seek(CLUSTER_DIRECTORIO_INICIO * TAMANO_CLUSTER)
            for _ in range(ENTRADAS_DIRECTORIO):
                entrada = f.read(TAMANO_ENTRADA)
                tipo = entrada[0:1]
                nombre = entrada[1:16].decode('ascii', errors='ignore').strip('\x00').strip()
                
                if tipo == b'-' and nombre != '###############':
                    tamano = struct.unpack('<I', entrada[16:20])[0]
                    cluster = struct.unpack('<I', entrada[20:24])[0]
                    fecha_creacion = entrada[30:44].decode('ascii')
                    archivos.append({'nombre': nombre, 'tamano': tamano, 'cluster': cluster, 'creacion': fecha_creacion})
        return archivos
        
    
    def copiar_fuera(self, nombre_fs, ruta_local):
        with open(self.ruta_img, 'rb') as f:
            f.seek(CLUSTER_DIRECTORIO_INICIO * TAMANO_CLUSTER)
            for _ in range(ENTRADAS_DIRECTORIO):
                entrada = f.read(TAMANO_ENTRADA)
                nombre = entrada[1:16].decode('ascii', errors='ignore').strip('\x00').strip()
                
                if nombre == nombre_fs and entrada[0:1] == b'-':
                    tamano = struct.unpack('<I', entrada[16:20])[0]
                    cluster_inicial = struct.unpack('<I', entrada[20:24])[0]
                    
                    f.seek(cluster_inicial * TAMANO_CLUSTER)
                    datos = f.read(tamano)
                    
                    with open(ruta_local, 'wb') as f_local:
                        f_local.write(datos)
                    return f"Completado: '{nombre_fs}' copiado a tu equipo."
  
        return f"Error: Archivo '{nombre_fs}' no encontrado en FiUnamFS."
    
    
    def copiar_dentro(self, ruta_local, nombre_fs):
        if not os.path.exists(ruta_local):
            return "Error: El archivo local no existe."
            
        with open(ruta_local, 'rb') as f_local:
            datos = f_local.read()
            
        tamano = len(datos)
        clusters_requeridos = (tamano + TAMANO_CLUSTER - 1) // TAMANO_CLUSTER
        
        with open(self.ruta_img, 'r+b') as f:
            # Busca una entrada libre y calcula espacio ocupado
            f.seek(CLUSTER_DIRECTORIO_INICIO * TAMANO_CLUSTER)
            offset_libre = -1
            intervalos_ocupados = []
            
            for i in range(ENTRADAS_DIRECTORIO):
                offset_actual = (CLUSTER_DIRECTORIO_INICIO * TAMANO_CLUSTER) + (i * TAMANO_ENTRADA)
                entrada = f.read(TAMANO_ENTRADA)
                nombre = entrada[1:16].decode('ascii', errors='ignore').strip('\x00').strip()
                
                if offset_libre == -1 and (nombre == '###############' or entrada[0:1] == b'/'):
                    offset_libre = offset_actual
                elif entrada[0:1] == b'-' and nombre != '###############':
                    f_tamano = struct.unpack('<I', entrada[16:20])[0]
                    f_cluster = struct.unpack('<I', entrada[20:24])[0]
                    f_req = (f_tamano + TAMANO_CLUSTER - 1) // TAMANO_CLUSTER
                    intervalos_ocupados.append((f_cluster, f_cluster + f_req - 1))
            
            if offset_libre == -1:
                return "Error: Directorio lleno."
                
            # Encontrar espacio contiguo libre
            intervalos_ocupados.sort()
            cluster_actual = 9
            cluster_destino = -1
            
            for inicio, fin in intervalos_ocupados:
                if cluster_actual + clusters_requeridos - 1 < inicio:
                    cluster_destino = cluster_actual
                    break
                cluster_actual = max(cluster_actual, fin + 1)
                
            if cluster_destino == -1:
                if cluster_actual + clusters_requeridos <= 720:
                    cluster_destino = cluster_actual
                else:
                    return "Error: No hay espacio contiguo suficiente."
            
            # Escribir datos
            f.seek(cluster_destino * TAMANO_CLUSTER)
            f.write(datos)
            
            # Escribir entrada de directorio
            ahora = datetime.now().strftime('%Y%m%d%H%M%S').encode('ascii')
            nueva_entrada = bytearray(TAMANO_ENTRADA)
            nueva_entrada[0:1] = b'-'
            nueva_entrada[1:16] = nombre_fs.ljust(15, '\x00').encode('ascii')[:15]
            nueva_entrada[16:20] = struct.pack('<I', tamano)
            nueva_entrada[20:24] = struct.pack('<I', cluster_destino)
            nueva_entrada[30:44] = ahora
            nueva_entrada[50:64] = ahora
            
            f.seek(offset_libre)
            f.write(nueva_entrada)
            
        return f"Éxito: Archivo copiado a FiUnamFS ocupando {clusters_requeridos} clusters."


    def eliminar_archivo(self, nombre_fs):
        with open(self.ruta_img, 'r+b') as f:
            f.seek(CLUSTER_DIRECTORIO_INICIO * TAMANO_CLUSTER)
            for i in range(ENTRADAS_DIRECTORIO):
                offset_actual = (CLUSTER_DIRECTORIO_INICIO * TAMANO_CLUSTER) + (i * TAMANO_ENTRADA)
                entrada = f.read(TAMANO_ENTRADA)
                nombre = entrada[1:16].decode('ascii', errors='ignore').strip('\x00').strip()
                
                if nombre == nombre_fs and entrada[0:1] == b'-':
                    # Marcar como eliminado ('/' en tipo y '#####' en nombre)
                    f.seek(offset_actual)
                    entrada_borrada = bytearray(entrada)
                    entrada_borrada[0:1] = b'/'
                    entrada_borrada[1:16] = b'###############'
                    f.write(entrada_borrada)
                    return f"Éxito: Archivo '{nombre_fs}' eliminado."
                    
        return f"Error: Archivo '{nombre_fs}' no encontrado."
 

def main():
    ruta_img = 'fiunamfs.img'
     
    if not os.path.exists(ruta_img):
        print(f"No se encontró el archivo '{ruta_img}'.")
        return

    # Inicialización de hilos y sincronización
    cola_peticiones = queue.Queue()
    hilo_fs = FS(ruta_img, cola_peticiones)
    hilo_fs.start()
    
    print("---FiUnamFS---")
    
    while True:
        print("\nElija una opción:")
        print("1.- Listar")
        print("2.- Copiar a mi PC")
        print("3.- Copiar a FS ")
        print("4.- Eliminar")
        print("5.- Salir")
        opcion = input("Selecciona una operación: ").strip()
         
        peticion = None
        if opcion == '1':
            peticion = PeticionFS('LISTAR')
        elif opcion == '2':
            nombre = input("Nombre del archivo en FiUnamFS: ")
            ruta = input("Nombre que tendra el archivo en PC: ")
            peticion = PeticionFS('COPIAR_FUERA', nombre, ruta)
        elif opcion == '3':
            ruta = input("Nombre del archivo en PC: ")
            nombre = input("Nombre que tendra el archivo en FiUnamFS: ")
            peticion = PeticionFS('COPIAR_DENTRO', ruta, nombre)
        elif opcion == '4':
            nombre = input("Nombre del archivo a eliminar en FiUnamFS: ")
            peticion = PeticionFS('ELIMINAR', nombre)
        elif opcion == '5':
            cola_peticiones.put(PeticionFS('SALIR'))
            print("Vuelva pronto!")
            break
        else:
            print("Opción inválida.")
            continue
            
        #   Se envía a la cola y espera a que el evento se active (sincronización)
        cola_peticiones.put(peticion)
        peticion.evento.wait() 
        
        # Procesa los resultados devueltos por el hilo
        if opcion == '1':
            archivos = peticion.resultado
            if isinstance(archivos, list):
                print(f"\n{'Nombre':<16} | {'Tamaño':<10} | {'Cluster':<7} | {'Fecha Creación'}")
                print("-" * 60)
                for arch in archivos:
                    print(f"{arch['nombre']:<16} | {arch['tamano']:<10} | {arch['cluster']:<7} | {arch['creacion']}")
            else:
                print(archivos)
        else:
            print(peticion.resultado)

if __name__ == '__main__':
    main()


