import struct
import threading
from datetime import datetime

CLUSTER_SIZE = 2048
DIRECTORY_START = 2048
ENTRY_SIZE = 64
TOTAL_ENTRIES = 256


class FiUnamFS:
    def __init__(self, ruta):
        self.ruta = ruta
        self.lock = threading.Lock()

    def validar_fs(self):
        try:
            with open(self.ruta, 'rb') as archivo:
                archivo.seek(5)
                nombre = archivo.read(9).decode(
                    'ascii').replace('\x00', '').strip()

                archivo.seek(14)
                version = archivo.read(5).decode(
                    'ascii').replace('\x00', '').strip()

                if nombre != 'FiUnamFS':
                    print('Error: El nombre del sistema de archivos no coincide.')
                    return False

                # Se agrega validación de versión para detectar posibles incompatibilidades,
                # pero se permite continuar si la versión es '24-2' debido a que se
                # usó esa versión para generar la imagen:
                if version == '26-2':
                    print("Sistema de archivos validado correctamente (26-2).")
                elif version == '24-2':
                    print(
                        f"ADVERTENCIA: Se esperaba '26-2', se encontró '{version}'.")
                    print(
                        "Ejecutando debido a que se usó esa versión para generar la imagen...")
                else:
                    print(f"Error: Versión no reconocida: '{version}'.")
                    return False

            return True  # Si el nombre es correcto.

        except Exception as e:
            print(f"Error al abrir la imagen: {e}")
            return False

    def listar_directorio(self):
        """
        Lista los archivos en el directorio raíz de FiUnamFS.
        Devuelve una lista de diccionarios con información de cada archivo.
        """
        archivos_encontrados = []

        with self.lock:

            with open(self.ruta, 'rb') as archivo:

                for i in range(TOTAL_ENTRIES):

                    offset = DIRECTORY_START + (i * ENTRY_SIZE)

                    archivo.seek(offset)
                    entrada = archivo.read(ENTRY_SIZE)

                    tipo = entrada[0:1].decode('ascii')

                    nombre = entrada[1:16].decode('ascii')
                    nombre = nombre.replace('\x00', '').strip()

                    if tipo == '-':

                        tamano = struct.unpack('<I', entrada[16:20])[0]
                        cluster_inicial = struct.unpack(
                            '<I', entrada[20:24])[0]

                        archivos_encontrados.append({
                            'nombre': nombre,
                            'tamano': tamano,
                            'cluster': cluster_inicial
                        })

        return archivos_encontrados

    def mostrar_archivos(self):
        """
        Muestra la información de los archivos encontrados
        en el directorio raíz.
        """
        archivos = self.listar_directorio()

        print('\nContenido de FiUnamFS:\n')

        for archivo in archivos:
            print(f"Nombre: {archivo['nombre']}")
            print(f"Tamano: {archivo['tamano']} bytes")
            print(f"Cluster inicial: {archivo['cluster']}")
            print('--------------------------')

    def copiar_desde_fs(self, nombre_archivo, destino):
        """
        Copia un archivo desde FiUnamFS hacia
        el destino especificado en el sistema host.
        """
        with self.lock:
            with open(self.ruta, 'rb') as archivo:
                for i in range(TOTAL_ENTRIES):
                    offset = DIRECTORY_START + (i * ENTRY_SIZE)
                    archivo.seek(offset)
                    entrada = archivo.read(ENTRY_SIZE)
                    tipo = entrada[0:1].decode('ascii')
                    nombre = entrada[1:16].decode('ascii')
                    nombre = nombre.replace('\x00', '').strip()

                    if tipo == '-' and nombre == nombre_archivo:
                        tamano = struct.unpack('<I', entrada[16:20])[0]
                        cluster = struct.unpack('<I', entrada[20:24])[0]
                        inicio = cluster * CLUSTER_SIZE
                        archivo.seek(inicio)
                        datos = archivo.read(tamano)

                        with open(destino, 'wb') as salida:
                            salida.write(datos)

                        print('Archivo copiado correctamente.')

                        return

        print('Archivo no encontrado.')

    def copiar_hacia_fs(self, ruta_archivo):
        with self.lock:
            indice = self.buscar_entrada_libre()

            if indice == -1:
                print('No hay entradas libres en el directorio.')
                return

            with open(ruta_archivo, 'rb') as archivo_local:
                datos = archivo_local.read()

            tamano = len(datos)
            nombre = ruta_archivo.split('/')[-1]
            nombre = nombre[:15]

            # Calcula el cluster real
            cluster_libre = self.buscar_cluster_libre()

            with open(self.ruta, 'r+b') as archivo:
                inicio_datos = cluster_libre * CLUSTER_SIZE

                archivo.seek(inicio_datos)
                archivo.write(datos)

                offset = DIRECTORY_START + (indice * ENTRY_SIZE)

                archivo.seek(offset)

                archivo.write(b'-')

                nombre_bytes = nombre.encode('ascii')
                nombre_bytes = nombre_bytes.ljust(15, b' ')

                archivo.write(nombre_bytes)

                archivo.write(struct.pack('<I', tamano))
                archivo.write(struct.pack('<I', cluster_libre))

                fecha = datetime.now().strftime('%Y%m%d%H%M%S')
                fecha_bytes = fecha.encode('ascii')

                archivo.seek(offset + 24)
                archivo.write(b'000000')

                archivo.seek(offset + 30)
                archivo.write(fecha_bytes)

                archivo.seek(offset + 50)
                archivo.write(fecha_bytes)

            print('Archivo agregado correctamente.')

    def buscar_entrada_libre(self):
        """
        Busca una entrada en el directorio cuyo nombre sea '###############'.
        Devuelve el índice de la entrada o -1 si no hay espacio.
        """
        with open(self.ruta, 'rb') as archivo:
            for i in range(TOTAL_ENTRIES):
                offset = DIRECTORY_START + (i * ENTRY_SIZE)
                archivo.seek(offset)
                entrada = archivo.read(ENTRY_SIZE)

                # Lee los bytes del nombre (del byte 1 al 15)
                nombre = entrada[1:16].decode('ascii')
                if nombre == '###############':
                    return i
        return -1

    def buscar_cluster_libre(self):
        """
        Escanea el directorio para encontrar el cluster más alto ocupado
        y devuelve el siguiente cluster disponible.
        Los clusters de datos empiezan en el 9.
        """
        siguiente_cluster = 9

        with open(self.ruta, 'rb') as archivo:
            for i in range(TOTAL_ENTRIES):
                offset = DIRECTORY_START + (i * ENTRY_SIZE)
                archivo.seek(offset)
                entrada = archivo.read(ENTRY_SIZE)
                tipo = entrada[0:1].decode('ascii')
                if tipo == '-':
                    tamano = struct.unpack('<I', entrada[16:20])[0]
                    cluster_inicial = struct.unpack('<I', entrada[20:24])[0]

                    # Cuántos clusters ocupa este archivo
                    clusters_ocupados = (
                        tamano + CLUSTER_SIZE - 1) // CLUSTER_SIZE
                    cluster_final_archivo = cluster_inicial + clusters_ocupados

                    if cluster_final_archivo > siguiente_cluster:
                        siguiente_cluster = cluster_final_archivo

        return siguiente_cluster

    def eliminar_archivo(self, nombre_archivo):
        """
        Elimina un archivo del sistema de archivos FiUnamFS
        marcando su entrada como libre.
        """
        with self.lock:
            with open(self.ruta, 'r+b') as archivo:
                for i in range(TOTAL_ENTRIES):

                    offset = DIRECTORY_START + (i * ENTRY_SIZE)

                    archivo.seek(offset)
                    entrada = archivo.read(ENTRY_SIZE)

                    tipo = entrada[0:1].decode('ascii')

                    nombre = entrada[1:16].decode('ascii')
                    nombre = nombre.replace('\x00', '').strip()

                    if tipo == '-' and nombre == nombre_archivo:
                        archivo.seek(offset)
                        archivo.write(b'/')
                        archivo.write(b'###############')

                        print('Archivo eliminado correctamente.')
                        return

        print('Archivo no encontrado.')

    def leer_bytes_archivo(self, nombre_archivo, size, offset):
        """
        Lee una porción de bytes de un archivo específico.
        Ideal para FUSE (read).
        """
        with self.lock:
            with open(self.ruta, 'rb') as archivo:
                # Busca la entrada del archivo
                for i in range(TOTAL_ENTRIES):
                    dir_offset = DIRECTORY_START + (i * ENTRY_SIZE)
                    archivo.seek(dir_offset)
                    entrada = archivo.read(ENTRY_SIZE)

                    nombre = entrada[1:16].decode(
                        'ascii').replace('\x00', '').strip()
                    tipo = entrada[0:1].decode('ascii')

                    if tipo == '-' and nombre == nombre_archivo:
                        tamano = struct.unpack('<I', entrada[16:20])[0]
                        cluster = struct.unpack('<I', entrada[20:24])[0]

                        # Valida offset
                        if offset >= tamano:
                            return b''  # Fin del archivo

                        # Lee la porción solicitada
                        inicio_datos = (cluster * CLUSTER_SIZE) + offset
                        archivo.seek(inicio_datos)

                        # Ajusta tamaño de lectura si excede el final del archivo
                        leer_cantidad = min(size, tamano - offset)
                        return archivo.read(leer_cantidad)
        return b''

    def escribir_bytes_archivo(self, nombre_archivo, data):
        with self.lock:
            indice = self.buscar_entrada_libre()
            if indice == -1:
                raise Exception("No hay espacio en directorio")

            cluster_libre = self.buscar_cluster_libre()

            with open(self.ruta, 'r+b') as archivo:
                inicio_datos = cluster_libre * CLUSTER_SIZE
                archivo.seek(inicio_datos)
                archivo.write(data)

                tamano = len(data)
                offset = DIRECTORY_START + (indice * ENTRY_SIZE)
                archivo.seek(offset)
                archivo.write(b'-')

                nombre_bytes = nombre_archivo.encode(
                    'ascii')[:15].ljust(15, b' ')
                archivo.write(nombre_bytes)

                archivo.write(struct.pack('<I', tamano))
                archivo.write(struct.pack('<I', cluster_libre))

                fecha = datetime.now().strftime('%Y%m%d%H%M%S').encode('ascii')
                archivo.seek(offset + 30)
                archivo.write(fecha)
                archivo.seek(offset + 50)
                archivo.write(fecha)
            print(f'Archivo {nombre_archivo} agregado correctamente.')
