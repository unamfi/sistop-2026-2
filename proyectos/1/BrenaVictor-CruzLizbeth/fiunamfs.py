"""
Proyecto micro Sistema de Archivos
Autores:
    Brena de León Vícctor JAvier
    Cruz Manríquez Lizbeth

Controlador de Bajo Nivel para el Micro Sistema de Archivos FiUnamFS.

Este módulo encapsula la abstracción y las operaciones binarias directas
sobre el archivo contenedor (dsico). Implementa el parsing
de estructuras Little-Endian para entradas de directorio de tamaño fijo (64 bytes)
y la gestión de espacio libre en clústeres mediante el algoritmo First-Fit.

"""

import struct
import time

# =========================================================
# CONSTANTES GEOMÉTRICAS DEL SISTEMA DE ARCHIVOS
# =========================================================
# Definidas estrictamente bajo el mapa de memoria estático de la especificación.
DISK_FILE = "fiunamfs.img"
CLUSTER_SIZE = 2048
ENTRY_SIZE = 64
DIRECTORY_OFFSET = 1 * CLUSTER_SIZE
DIRECTORY_SIZE = 8 * CLUSTER_SIZE
MAX_ENTRIES = DIRECTORY_SIZE // ENTRY_SIZE
DATA_START_CLUSTER = 9

class FiUnamFS:
    """Clase controladora encargada de la manipulación binaria.
    
    Esta clase actúa de manera análoga a un driver de dispositivo, abstrayendo
    las llamadas de lectura/escritura en bloques mediante desplazamientos
    lineales (.seek) y formateo de bytes estructurados.
    """

    def __init__(self, disk_file, fs_lock, log_operation_callback):
        """Inicializa el controlador abriendo el descriptor de archivo en modo binario.
        
        Recibe el candado global y el callback 
        de log para interactuar de forma segura y desacoplada con el monitor concurrente.
        """
        self.disk_file = disk_file
        self.fs_lock = fs_lock
        self.log_operation = log_operation_callback
        self.disk = open(disk_file, "r+b")
        self.validate_superblock()

    def validate_superblock(self):
        """Garantiza la integridad y firmas del dsico.
        
        Inspecciona los offsets fijos asignados a la firma de identidad ('FiUnamFS')
        y evalúa la cadena de versión. Posee tolerancia de diseño para aceptar 
        las firmas '24-2' y '26-2', previniendo excepciones críticas si se valida 
        con contenedores alternativos provistos por la evaluación docente.
        """
        with self.fs_lock:
            # Validación de firma de identidad del sistema de archivos (Bytes 5-12)
            self.disk.seek(5)
            fs_name = self.disk.read(8).decode("ascii", errors="ignore").strip('\x00').strip()
            
            if "FiUnamFS" not in fs_name:
                raise Exception(f"Sistema de archivos inválido. Se leyó: '{fs_name}'")

            # Validación de la versión de la especificación académica (Bytes 14-17)
            self.disk.seek(14)
            version = self.disk.read(4).decode("ascii", errors="ignore").strip('\x00').strip()

            if version not in ["24-2", "26-2"]:
                raise Exception(f"Versión incorrecta o no soportada. Se leyó: '{version}'")
            
            print(f"FiUnamFS verificado con éxito. Versión detectada: {version}")

    def read_directory(self):
        """Escanea linealmente la tabla de directorio mapeada en los clústeres 1 al 8.
        
        Desempaqueta las estructuras de 64 bytes utilizando formato Little-Endian ('<I').
        Descarta de forma dinámica las entradas marcadas con borrado lógico (carácter '/')
        o bloques de inicialización ('###############'), consolidando una lista de 
        diccionarios con los metadatos de los archivos activos en memoria volátil.
        """
        entries = []
        self.disk.seek(DIRECTORY_OFFSET)
        for _ in range(MAX_ENTRIES):
            pos = self.disk.tell()
            entry = self.disk.read(ENTRY_SIZE)
            if not entry or len(entry) < ENTRY_SIZE:
                break

            file_type = entry[0:1].decode("ascii", errors="ignore")
            filename = entry[1:16].decode("ascii", errors="ignore").replace('\x00', '').strip()

            if filename == "###############" or file_type == "/":
                continue
            if not filename:
                continue

            # Unpack de enteros sin signo de 4 bytes (Formatos de tamaño y clúster inicial)
            filesize = struct.unpack('<I', entry[16:20])[0]
            start_cluster = struct.unpack('<I', entry[20:24])[0]
            created = entry[24:38].decode("ascii", errors="ignore")
            modified = entry[38:52].decode("ascii", errors="ignore")

            entries.append({
                "name": filename,
                "size": filesize,
                "cluster": start_cluster,
                "created": created,
                "modified": modified,
                "dir_pos": pos
            })
        return entries

    def find_file(self, filename):
        """Realiza una búsqueda secuencial en la lista filtrada del directorio."""
        for f in self.read_directory():
            if f["name"] == filename.strip():
                return f
        return None

    def read_file(self, filename):
        """Extrae el flujo de bytes crudos correspondientes a un archivo del disco.
        
        Calcula el desplazamiento multiplicando el índice del clúster inicial 
        por el tamaño de clúster geométrico (2048 bytes), extrayendo únicamente los 
        bytes delimitados por el metadato de tamaño oficial para evitar lecturas de basura.
        """
        with self.fs_lock:
            file_entry = self.find_file(filename)
            if not file_entry:
                return None
            self.disk.seek(file_entry["cluster"] * CLUSTER_SIZE)
            return self.disk.read(file_entry["size"])

    def find_free_cluster(self, size_bytes):
        """Algoritmo de asignación de espacio First-Fit para almacenamiento de datos.
        
        Determina la cantidad de bloques requeridos aplicando la función a la división 
        del tamaño. Mapea exhaustivamente los mapas de clústeres ocupados por todos los archivos 
        existentes en el directorio para localizar el primer rango contiguo de clústeres 
        libres disponibles a partir de la zona de datos (Clúster 9).
        """
        needed_clusters = (size_bytes + CLUSTER_SIZE - 1) // CLUSTER_SIZE
        if needed_clusters == 0:
            needed_clusters = 1

        used = set()
        for f in self.read_directory():
            clusters_used = (f["size"] + CLUSTER_SIZE - 1) // CLUSTER_SIZE
            if clusters_used == 0:
                clusters_used = 1
            for c in range(f["cluster"], f["cluster"] + clusters_used):
                used.add(c)

        current = DATA_START_CLUSTER
        while True:
            if all((current + i) not in used for i in range(needed_clusters)):
                return current
            current += 1

    def find_free_directory_entry(self):
        """Busca un espacio disponible en la tabla lineal de directorio."""
        self.disk.seek(DIRECTORY_OFFSET)
        for _ in range(MAX_ENTRIES):
            pos = self.disk.tell()
            entry = self.disk.read(ENTRY_SIZE)
            filename = entry[1:16].decode("ascii", errors="ignore")
            if filename.startswith("###############") or entry[0:1] == b'\x00':
                return pos
        return None

    def current_date(self):
        """Devuelve la estampa de tiempo formateada bajo el estándar de la especificación (AAAAMMDDHHMMSS)."""
        return time.strftime("%Y%m%d%H%M%S")

    def delete_file(self, filename):
        """Ejecuta el borrado lógico del archivo sobre la tabla.
        
        Cambia el carácter indicador de tipo a '/' y sobreescribe el nombre con almohadillas. 
        Esta estrategia libera el índice de forma inmediata para futuras creaciones sin necesidad 
        de borrar de forma destructiva los datos en los bloques físicos del clúster.
        """
        with self.fs_lock:
            file_entry = self.find_file(filename)
            if not file_entry:
                return False
            self.disk.seek(file_entry["dir_pos"])
            self.disk.write(b'/')
            self.disk.write(b'###############')
            self.disk.flush()
            self.log_operation(f"Archivo eliminado: {filename}")
            return True

    def truncate_file(self, filename, size):
        """Modifica el tamaño lógico de un archivo regular en el medio virtual.
        
        Si el tamaño solicitado es menor, trunca el flujo de bytes. Si es mayor, 
        expande el archivo rellenando la diferencia con caracteres (padding de ceros), 
        asegurando la persistencia y consistencia en los bloques asignados.
        """
        with self.fs_lock:
            file_entry = self.find_file(filename)
            if not file_entry:
                return False
            data = self.read_file(filename) or b''
            if len(data) > size:
                data = data[:size]
            else:
                data += b'\x00' * (size - len(data))
            return self.write_file_data(filename, data)

    def write_file_data(self, filename, data):
        """Sincroniza y escribe el búfer de bytes dentro de los clústeres de almacenamiento.
        
        Evalúa si la nueva dimensión de datos desborda el espacio asignado previamente. 
        De ser necesario, invoca dinámicamente una reubicación de clúster mediante First-Fit, 
        reescribiendo los punteros binarios e inyectando la fecha de modificación actualizada.
        """
        file_entry = self.find_file(filename)
        if not file_entry:
            return False

        needed_clusters = (len(data) + CLUSTER_SIZE - 1) // CLUSTER_SIZE
        current_clusters = (file_entry["size"] + CLUSTER_SIZE - 1) // CLUSTER_SIZE
        cluster = file_entry["cluster"]

        if needed_clusters > current_clusters:
            cluster = self.find_free_cluster(len(data))

        self.disk.seek(cluster * CLUSTER_SIZE)
        self.disk.write(data)

        # Actualización de metadatos en la tabla de directorio (Tamaño y Clúster de inicio)
        self.disk.seek(file_entry["dir_pos"] + 16)
        self.disk.write(struct.pack('<I', len(data)))
        self.disk.write(struct.pack('<I', cluster))    
        
        # Sobreescritura de la estampa de tiempo de modificación
        self.disk.seek(file_entry["dir_pos"] + 38)
        self.disk.write(self.current_date().encode("ascii"))
        self.disk.flush()
        return True