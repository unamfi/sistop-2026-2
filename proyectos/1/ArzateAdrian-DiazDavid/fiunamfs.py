import os
import stat
import errno
import struct
import time
import math
from fuse import Operations, LoggingMixIn

class FiUnamFS(LoggingMixIn, Operations):
    """
    Capa Productora: Recibe llamadas del sistema operativo vía FUSE 
    y encola tareas al Worker.
    """
    def __init__(self, worker):
        self.worker = worker
        self.metadata = {}
        
        # caché en memoria para agilizar consultas
        self.directory = {}

        # mapa de ocupación de los clusteres
        self.cluster_map = []

        # validación del disco
        self._mount_filesystem()
    
    def _mount_filesystem(self):
        print("Leyendo superbloque...")
        # El superbloque siempre ocupa los primeros 64 bytes (o el Clúster 0 entero)
        sb_data = self.worker.read_bytes(0, 64)
        
        # validación del bloque
        firma = sb_data[5:14].decode('ascii').strip('\x00')
        if firma != 'FiUnamFS':
            raise ValueError(f"Firma del sistema de archivos inválida: '{firma}'")
            
        version = sb_data[14:19].decode('ascii').strip('\x00')
        if version != '24-2': # Cambio provisional para debuggear - Deberia de ser 26-2
            raise ValueError(f"Versión de FiUnamFS no soportada: '{version}'")
            
        label = sb_data[20:36].decode('ascii').strip('\x00')

        # LECTURA DE METADATOS MATEMÁTICOS (<I es Entero 32-bits Little Endian)
        cluster_size = struct.unpack('<I', sb_data[40:44])[0]
        dir_clusters = struct.unpack('<I', sb_data[50:54])[0]
        total_clusters = struct.unpack('<I', sb_data[60:64])[0]
        
        self.metadata = {
            'label': label,
            'cluster_size': cluster_size,
            'dir_clusters': dir_clusters,
            'total_clusters': total_clusters
        }
        
        print(f"Volumen montado: '{label}' | Clusters Totales: {total_clusters} | Tamaño Cluster: {cluster_size} bytes")
        
        # Tras validar leemos los archivos existentes
        self._parse_directory()

        # mapeamos el espacio libre
        self._build_free_space_map()

    def _parse_directory(self):
        print("Parseando clústeres del directorio...")
        self.directory = {}
        
        dir_clusters = self.metadata.get('dir_clusters', 8)
        
        # El directorio vive en los clusters del 1 al dir_clusters
        for cluster_id in range(1, dir_clusters + 1):
            cluster_data = self.worker.read_cluster(cluster_id)
            
            # Dividir los 2048 bytes del cluster en ranuras de 64 bytes
            for offset in range(0, 2048, 64):
                entry = cluster_data[offset:offset+64]
                
                # Extraer Tipo (byte 0)
                file_type = entry[0:1].decode('ascii')
                
                # Extraer Nombre (bytes 1 a 15)
                filename_raw = entry[1:16].decode('ascii')
                filename = filename_raw.rstrip(' \x00') # Remover relleno nulo o espacios
                
                # Validar ranura ocupada vs ranura libre
                if file_type == '/' or filename == '###############':
                    continue
                    
                # Extraer Tamaño (16-20) y Cluster Inicial (20-23)
                file_size = struct.unpack('<I', entry[16:20])[0]
                start_cluster = struct.unpack('<I', entry[20:24])[0]
                
                # Extraer fechas (30-44 y 50-64)
                ctime_raw = entry[30:45].decode('ascii').strip('\x00')
                mtime_raw = entry[50:65].decode('ascii').strip('\x00')
                
                # Función auxiliar para convertir fecha a Timestamp POSIX
                def parse_date(date_str):
                    try:
                        return time.mktime(time.strptime(date_str, '%Y%m%d%H%M%S'))
                    except ValueError:
                        return time.time() # Si falla, devolver fecha actual
                
                ctime = parse_date(ctime_raw)
                mtime = parse_date(mtime_raw)
                
                # Guardar el archivo en la caché para consultas veloces
                self.directory[filename] = {
                    'size': file_size,
                    'start_cluster': start_cluster,
                    'ctime': ctime,
                    'mtime': mtime,
                    # Guardamos su ubicación exacta por si después el usuario decide eliminarlo
                    'meta_cluster_id': cluster_id,
                    'meta_offset': offset
                }

                print(f"    -> Encontrado: {filename} ({file_size} bytes, Clúster Inicial: {start_cluster})")

    def _build_free_space_map(self):
        """
        Genera un mapa en memoria de los clústeres ocupados y libres.
        """
        total_clusters = self.metadata['total_clusters']
        cluster_size = self.metadata['cluster_size']

        self.cluster_map = [False] * total_clusters

        # Los clusters 0 (Superbloque) y 1-8 (Directorio) siempre están ocupados
        for i in range(9):
            self.cluster_map[i] = True

        # Marcar los clusters ocupados por los archivos detectados
        for filename, info in self.directory.items():
            start = info['start_cluster']
            size = info['size']

            if size == 0:
                continue

            # Calcular cuántos clústeres ocupa el archivo
            num_clusters = math.ceil(size / cluster_size)

            for i in range(start, start + num_clusters):
                if i < total_clusters:
                    self.cluster_map[i] = True

        ocupados = sum(self.cluster_map)
        libres = total_clusters - ocupados
        print(f"Mapa de espacio generado: {ocupados} clústeres ocupados, {libres} libres.")

    def find_free_clusters(self, required_clusters):
        """
        Busca una secuencia de 'required_clusters' ininterrumpidos y libres.
        """
        if required_clusters == 0:
            return 0

        total_clusters = self.metadata['total_clusters']
        consecutive = 0
        start_index = -1

        for i in range(9, total_clusters):
            if not self.cluster_map[i]:
                if consecutive == 0:
                    start_index = i
                consecutive += 1

                if consecutive == required_clusters:
                    return start_index
            else:
                consecutive = 0

        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC)) # No hay espacio suficiente en el disco para escribir el archivo

    def getattr(self, path, fh=None):
        # El SO pregunta atributos del archivo o directorio
        if path == '/':
            # Simulamos que la raíz es un directorio válido con todos los permisos
            return {
                'st_mode': (stat.S_IFDIR | 0o755),
                'st_nlink': 2
            }
        
        filename = path.lstrip('/')
        if filename in self.directory:
            f_info = self.directory[filename]
            return {
                'st_mode': (stat.S_IFREG | 0o666), # Indicamos que es un archivo regular
                'st_nlink': 1,
                'st_size': f_info['size'],
                'st_ctime': f_info['ctime'],
                'st_mtime': f_info['mtime'],
                'st_atime': f_info['mtime']
            }
        raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))


    def readdir(self, path, fh):
        # El SO hace un comando 'ls'
        # Siempre debemos devolver el directorio actual y el padre
        dirents = ['.', '..']

        if path == '/':
            # Proyectar las llaves (nombres de archivos) de nuestra caché
            dirents.extend(self.directory.keys())

        for r in dirents:
            yield r
    
    # capa FUSE

    def read(self, path, size, offset, fh):
        """
        El SO pide 'size' bytes del archivo, comenzando en 'offset'.
        Calculamos en qué clústeres caen esos bytes y los extraemos.
        """
        filename = path.lstrip('/')
        if filename not in self.directory:
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT)) # si el archivo no existe, lanzamos error

        f_info = self.directory[filename]
        start_cluster = f_info['start_cluster']
        cluster_size = self.metadata['cluster_size']

        # Calcular la posición absoluta en bytes dentro del disco
        byte_offset = (start_cluster * cluster_size) + offset

        # Pedir al Worker que lea exactamente los bytes requeridos
        data = self.worker.read_bytes(byte_offset, size)

        return data
    
    def create(self, path, mode):
        """
        El SO quiere crear un archivo nuevo. Buscamos una ranura libre
        en el directorio y la inicializamos con tamaño 0.
        """
        filename = path.lstrip('/')

        # Los nombres en FiUnamFS tienen máximo 15 caracteres
        if len(filename) > 15:
            raise OSError(errno.ENAMETOOLONG, os.strerror(errno.ENAMETOOLONG))

        if filename in self.directory:
            raise OSError(errno.EEXIST, os.strerror(errno.EEXIST)) # Si el archivo ya existe, lanzamos error

        # Buscar una ranura libre en el directorio (tipo '/' o nombre '###############')
        slot_cluster, slot_offset = self._find_free_dir_slot()

        now = time.strftime('%Y%m%d%H%M%S')

        # Empaquetar la nueva entrada de 64 bytes
        entry = (
            b'-'                                          # [0]     Tipo: archivo regular
            + filename.encode('ascii').ljust(15, b'\x00') # [1:16]  Nombre (relleno de nulos)
            + struct.pack('<I', 0)                        # [16:20] Tamaño inicial = 0
            + struct.pack('<I', 0)                        # [20:24] Clúster inicial = 0 (aún sin datos)
            + b'\x00' * 6                                 # [24:30] Relleno
            + now.encode('ascii')                         # [30:44] Fecha creación
            + b'\x00' * 6                                 # [44:50] Relleno
            + now.encode('ascii')                         # [50:64] Fecha modificación
        )

        # Escribir la entrada en el clúster correcto del directorio
        cluster_data = bytearray(self.worker.read_cluster(slot_cluster))
        cluster_data[slot_offset:slot_offset + 64] = entry
        self.worker.write_cluster(slot_cluster, bytes(cluster_data))

        # Registrar en la caché en memoria
        self.directory[filename] = {
            'size': 0,
            'start_cluster': 0,
            'ctime': time.time(),
            'mtime': time.time(),
            'meta_cluster_id': slot_cluster,
            'meta_offset': slot_offset
        }

        return 0  # FUSE requiere retornar 0 como file handle en create
    
    def write(self, path, data, offset, fh):
        """
        El SO envía fragmentos del archivo en 'data'. Escribimos los datos
        en clústeres contiguos y actualizamos el directorio.
        """
        filename = path.lstrip('/')
        if filename not in self.directory:
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT)) 

        f_info = self.directory[filename]
        cluster_size = self.metadata['cluster_size']

        new_size = offset + len(data)

        # Calcular cuántos clústeres necesita el archivo tras este write
        required_clusters = math.ceil(new_size / cluster_size)

        # Si el archivo no tiene clústeres asignados, uscamos espacio libre
        if f_info['start_cluster'] == 0:
            start_cluster = self.find_free_clusters(required_clusters)
            f_info['start_cluster'] = start_cluster
            # Marcar los nuevos clústeres como ocupados en el mapa
            for i in range(start_cluster, start_cluster + required_clusters):
                self.cluster_map[i] = True
        else:
            start_cluster = f_info['start_cluster']

        # Calcular la posición absoluta en bytes y escribir
        byte_offset = (start_cluster * cluster_size) + offset
        
        # Escribir los datos bloque a bloque para no desbordar clústeres
        written = 0
        while written < len(data):
            # Determinar en qué clúster caemos
            current_abs_offset = byte_offset + written
            cluster_id = current_abs_offset // cluster_size
            offset_in_cluster = current_abs_offset % cluster_size

            # Cuántos bytes podemos escribir en este clúster sin pasar al siguiente
            space_in_cluster = cluster_size - offset_in_cluster
            chunk = data[written:written + space_in_cluster]

            # Leer el clúster, modificar el fragmento y reescribirlo completo
            cluster_bytes = bytearray(self.worker.read_cluster(cluster_id))
            cluster_bytes[offset_in_cluster:offset_in_cluster + len(chunk)] = chunk
            self.worker.write_cluster(cluster_id, bytes(cluster_bytes))

            written += len(chunk)

        # Actualizar tamaño y metadatos en la caché
        f_info['size'] = new_size
        f_info['mtime'] = time.time()
        self.directory[filename] = f_info

        # Persistir la entrada del directorio en disco
        self._update_dir_entry(filename)

        return len(data)
    
    def unlink(self, path):
        """
        Marca la entrada del directorio como libre (nombre '###############').
        Los clústeres de datos quedan automáticamente disponibles.
        """
        filename = path.lstrip('/')
        if filename not in self.directory:
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))

        f_info = self.directory[filename]
        slot_cluster = f_info['meta_cluster_id']
        slot_offset = f_info['meta_offset']

        # Leer el clúster, sobreescribir la ranura con el marcador de libre
        cluster_bytes = bytearray(self.worker.read_cluster(slot_cluster))
        # Entrada vacía: tipo '/', nombre '###############', resto nulos
        empty_entry = b'/' + b'###############' + b'\x00' * 48
        cluster_bytes[slot_offset:slot_offset + 64] = empty_entry
        self.worker.write_cluster(slot_cluster, bytes(cluster_bytes))

        # Liberar los clústeres de datos en el mapa en memoria
        start = f_info['start_cluster']
        size = f_info['size']
        if start > 0 and size > 0:
            num_clusters = math.ceil(size / self.metadata['cluster_size'])
            for i in range(start, start + num_clusters):
                if i < len(self.cluster_map):
                    self.cluster_map[i] = False

        # Eliminar de la caché
        del self.directory[filename]

    # Funciones de ayuda
    def _find_free_dir_slot(self):
        """
        Busca la primera ranura libre (64 bytes) en los clústeres del directorio.
        """
        dir_clusters = self.metadata['dir_clusters']
        for cluster_id in range(1, dir_clusters + 1):
            cluster_data = self.worker.read_cluster(cluster_id)
            for offset in range(0, 2048, 64):
                entry = cluster_data[offset:offset + 64]
                file_type = entry[0:1].decode('ascii')
                filename_raw = entry[1:16].decode('ascii')
                if file_type == '/' or filename_raw == '###############':
                    return cluster_id, offset
        raise OSError(errno.ENOSPC, "El directorio está lleno, no hay más ranuras disponibles")

    def _update_dir_entry(self, filename):
        """
        Persiste los metadatos de un archivo en su ranura del directorio en disco.
        """
        f_info = self.directory[filename]
        slot_cluster = f_info['meta_cluster_id']
        slot_offset = f_info['meta_offset']
        cluster_size = self.metadata['cluster_size']

        now = time.strftime('%Y%m%d%H%M%S')
        ctime_str = time.strftime('%Y%m%d%H%M%S', time.localtime(f_info['ctime']))

        entry = (
            b'-'
            + filename.encode('ascii').ljust(15, b'\x00')
            + struct.pack('<I', f_info['size'])
            + struct.pack('<I', f_info['start_cluster'])
            + b'\x00' * 6
            + ctime_str.encode('ascii')
            + b'\x00' * 6
            + now.encode('ascii')
        )

        cluster_bytes = bytearray(self.worker.read_cluster(slot_cluster))
        cluster_bytes[slot_offset:slot_offset + 64] = entry
        self.worker.write_cluster(slot_cluster, bytes(cluster_bytes))
