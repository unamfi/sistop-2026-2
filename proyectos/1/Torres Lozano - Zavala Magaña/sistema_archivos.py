# Aquí está toda la lógica para leer y modificar una imagen FiUnamFS.
# Este módulo no sabe nada de la interfaz de usuario, solo expone
# operaciones sobre el sistema de archivos.

import os
import math
import struct
import threading
from datetime import datetime

from entrada_directorio import FileEntry, CLUSTER_SIZE

# Constantes según las especificación de FiUnamFS

NOMBRE_FS      = "FiUnamFS"  # Lo que debe decir el superbloque para ser válido

# La especificación del proyecto indican que usaremos la versión "26-2", pero la imagen
# de ejemplo que proporcionó el profesor en el repositorio es "24-2"
# en su superbloque. En caso de que sea un error ara no quedarnos
# sin poder probar el programa, aceptamos ambas versiones.
VERSIONES_VALIDAS = {"26-2", "24-2"}

TAMANO_ENTRADA = 64          # Bytes por entrada de directorio (fijo en la spec)
INICIO_DIR     = CLUSTER_SIZE  # El directorio empieza en el cluster 1, justo después del superbloque

# Offsets dentro del superbloque.
# Los primeros 5 bytes son nulos (\x00), luego viene el nombre del FS.
# Lo verificamos leyendo el .img byte a byte con un script de diagnóstico.
OFFSET_NOMBRE       = 5   # Aquí empieza la cadena "FiUnamFS"
OFFSET_VERSION      = 14  # Aquí empieza la cadena de versión
OFFSET_ETIQUETA     = 20  # Etiqueta del volumen (texto libre)
OFFSET_TAM_CLUSTER  = 40  # Entero de 32 bits: tamaño de cluster en bytes
OFFSET_CLUSTERS_DIR = 50  # Entero de 32 bits: cuántos clusters mide el directorio
OFFSET_TOTAL        = 60  # Entero de 32 bits: total de clusters del volumen

# Marcadores del primer byte de cada entrada del directorio
ENTRADA_ARCHIVO = "-"  # 0x2D: hay un archivo aquí
ENTRADA_LIBRE   = "/"  # 0x2F: espacio disponible para un nuevo archivo

def validar_imagen(ruta: str) -> bool:
    """
    Verifica que el .img sea un FiUnamFS válido antes de hacer cualquier cosa.

    Leemos el nombre del sistema de archivos y la versión desde el superbloque
    y los comparamos con los valores esperados. Si no coinciden, es mejor no
    tocar el archivo para no corromper datos de otro sistema.
    """
    try:
        with open(ruta, "rb") as img:
            img.seek(OFFSET_NOMBRE)
            nombre = img.read(8).decode("ascii").strip()
            if nombre != NOMBRE_FS:
                return False

            img.seek(OFFSET_VERSION)
            version = img.read(4).decode("ascii").strip()
            return version in VERSIONES_VALIDAS
    except (OSError, UnicodeDecodeError):
        return False


class FiUnamFS:
    """
    Clase principal para interactuar con una imagen FiUnamFS.

    Al crear una instancia, lee los metadatos del superbloque para saber
    el tamaño de cluster, cuántos clusters ocupa el directorio y cuántos
    hay en total. Con eso calcula cuántas entradas de directorio existen.

    Las escrituras están protegidas por un Lock para evitar que dos hilos
    corrompan el archivo si intentan escribir al mismo tiempo.
    """

    def __init__(self, ruta: str) -> None:
        self.ruta    = ruta
        self._candado = threading.Lock()  # Para proteger escrituras concurrentes

        # Leemos el superbloque para configurar el objeto
        self.nombre         = self._leer_cadena(OFFSET_NOMBRE, 8)
        self.version        = self._leer_cadena(OFFSET_VERSION, 4)
        self.etiqueta       = self._leer_cadena(OFFSET_ETIQUETA, 15)
        self.tam_cluster    = self._leer_entero(OFFSET_TAM_CLUSTER, 4)
        self.clusters_dir   = self._leer_entero(OFFSET_CLUSTERS_DIR, 4)
        self.total_clusters = self._leer_entero(OFFSET_TOTAL, 4)

        # Cuántas entradas de 64 bytes caben en el área del directorio
        self.max_entradas = (self.tam_cluster * self.clusters_dir) // TAMANO_ENTRADA


    # Operaciones

    def listar_archivos(self) -> list[FileEntry]:
        """
        Devuelve la lista de archivos que hay en el directorio.

        Para hacerlo más rápido, dividimos el directorio entre 8 hilos que
        leen en paralelo cada uno su fragmento. Como los fragmentos no se
        solapan, no hay conflicto al leer, pero sí necesitamos un candado
        para agregar los resultados a la lista compartida.

        La barrera manual (semáforo + contador) hace que el hilo principal
        espere a que todos los hilos de lectura terminen antes de retornar.
        """
        resultados: list[FileEntry] = []
        candado_resultados = threading.Lock()

        num_hilos = 8
        fragmento = self.max_entradas // num_hilos  # Entradas que le tocan a cada hilo

        # Llevamos la cuenta de cuántos hilos faltan por terminar.
        # Cuando llega a 0, el último hilo libera la barrera.
        pendientes   = [num_hilos]
        barrera      = threading.Semaphore(0)
        candado_cont = threading.Lock()

        def trabajador(indice_inicio: int):
            local = []
            for i in range(indice_inicio, indice_inicio + fragmento):
                entrada = self._leer_entrada(i)
                if entrada is not None:
                    local.append(entrada)

            # Sección: varios hilos podrían querer agregar a 'resultados'
            # al mismo tiempo, así que usamos el candado
            with candado_resultados:
                resultados.extend(local)

            # El último hilo en terminar libera la barrera para que
            # el hilo que llamó a listar_archivos() pueda continuar
            with candado_cont:
                pendientes[0] -= 1
                if pendientes[0] == 0:
                    barrera.release()

        hilos = [
            threading.Thread(target=trabajador, args=(i * fragmento,))
            for i in range(num_hilos)
        ]
        for hilo in hilos:
            hilo.start()

        barrera.acquire()  # Esperamos aquí hasta que todos los hilos terminen
        return resultados

    def copiar_a_local(self, nombre_archivo: str, directorio_destino: str) -> str:
        """
        Copia un archivo desde FiUnamFS hacia un directorio en la computadora.
        Retorna un mensaje indicando si la operación fue exitosa o no.
        """
        archivos = self.listar_archivos()
        for archivo in archivos:
            if archivo.name == nombre_archivo:
                if archivo.copy_to_system(directorio_destino):
                    return f'[OK] "{nombre_archivo}" copiado en "{directorio_destino}".'
                else:
                    return f'[Error] No se pudo copiar "{nombre_archivo}". Revisa que la ruta exista y el archivo no esté ya ahí.'
        return f'[Error] "{nombre_archivo}" no existe en FiUnamFS.'

    def copiar_desde_local(self, ruta_origen: str) -> str:
        """
        Copia un archivo desde la computadora hacia FiUnamFS.

        Antes de copiar validamos varias cosas:
          1 -> Que el archivo exista en la computadora.
          2 -> Que el nombre no pase de 14 caracteres (límite de la spec).
          3 -> Que solo use caracteres ASCII (FiUnamFS no soporta Unicode).
          4 -> Que no exista ya un archivo con ese nombre en FiUnamFS.
          5 -> Que haya clusters contiguos suficientes para los datos.
          6 -> Que haya una entrada libre en el directorio.
        """
        if not os.path.exists(ruta_origen):
            return "[Error] El archivo no existe en esa ruta."

        nombre_archivo = os.path.basename(ruta_origen)

        # El campo de nombre en el directorio mide 15 bytes, pero el byte 0
        # es el marcador '-', así que solo quedan 14 para el nombre real
        if len(nombre_archivo) > 14:
            return f'[Error] El nombre "{nombre_archivo}" supera los 14 caracteres permitidos.'

        if not nombre_archivo.isascii():
            return f'[Error] El nombre "{nombre_archivo}" contiene caracteres no ASCII.'

        for archivo in self.listar_archivos():
            if archivo.name == nombre_archivo:
                return f'[Error] Ya existe un archivo llamado "{nombre_archivo}" en FiUnamFS.'

        tamano_archivo  = os.path.getsize(ruta_origen)
        cluster_inicial = self._buscar_espacio_libre(tamano_archivo)
        if cluster_inicial is None:
            return "[Error] No hay espacio contiguo suficiente en FiUnamFS."

        # Escribir el contenido en los clusters de datos
        try:
            with open(ruta_origen, "rb") as origen:
                contenido = origen.read()

            desplazamiento = cluster_inicial * CLUSTER_SIZE
            with self._candado:
                with open(self.ruta, "rb+") as img:
                    img.seek(desplazamiento)
                    img.write(contenido)
        except OSError:
            return "[Error] Error al escribir los datos del archivo en la imagen."

        return self._escribir_entrada_directorio(ruta_origen, nombre_archivo, tamano_archivo, cluster_inicial)

    def eliminar_archivo(self, nombre_archivo: str) -> str:
        """
        Elimina un archivo marcando su entrada en el directorio como libre.

       
        Marcando la entrada como disponible con el carácter /
        para que ese espacio pueda usarse para nuevos archivos.
        """
        for i in range(self.max_entradas):
            nombre_crudo = self._leer_nombre_crudo(i)
            if nombre_crudo is None:
                continue

            # El byte 0 es el marcador '-', el nombre real empieza en el byte 1
            if nombre_crudo[1:].strip() == nombre_archivo:
                desplazamiento = INICIO_DIR + (i * TAMANO_ENTRADA)
                with self._candado:
                    try:
                        with open(self.ruta, "rb+") as img:
                            img.seek(desplazamiento)
                            # Sobreescribimos solo los 15 bytes del nombre
                            img.write("/##############".encode("ascii"))
                        return f'[OK] "{nombre_archivo}" eliminado correctamente.'
                    except OSError:
                        return f'[Error] No se pudo eliminar "{nombre_archivo}".'

        return f'[Error] "{nombre_archivo}" no existe en FiUnamFS.'

    # Métodos de lectura interna

    def _leer_cadena(self, offset: int, longitud: int) -> str:
        """Lee bytes desde el .img y los decodifica como texto ASCII."""
        with open(self.ruta, "rb") as img:
            img.seek(offset)
            return img.read(longitud).decode("ascii").strip()

    def _leer_entero(self, offset: int, longitud: int) -> int:
        """
        Lee un entero desde el .img en formato little-endian de 32 bits.

        <I en struct.unpack significa: little-endian, unsigned int de 32 bits.
        FiUnamFS guarda todos sus números en este formato.
        """
        with open(self.ruta, "rb") as img:
            img.seek(offset)
            (valor,) = struct.unpack("<I", img.read(longitud))
            return valor

    def _leer_nombre_crudo(self, indice: int) -> str | None:
        """
        Lee los primeros 15 bytes de la entrada indice del directorio.
        Retorna la cadena si hay un archivo activo (empieza con -), o None.
        """
        desplazamiento = INICIO_DIR + (indice * TAMANO_ENTRADA)
        try:
            with open(self.ruta, "rb") as img:
                img.seek(desplazamiento)
                nombre_crudo = img.read(15).decode("ascii")
            if nombre_crudo[0] == ENTRADA_ARCHIVO:
                return nombre_crudo
            return None
        except (OSError, UnicodeDecodeError):
            return None

    def _leer_entrada(self, indice: int) -> FileEntry | None:
        """
        Lee una entrada completa del directorio y construye un FileEntry.

        Estructura de cada entrada de 64 bytes según la especificación:
          Byte  0      → tipo: - si hay archivo, / si está libre
          Bytes 1-14   → nombre del archivo (14 caracteres)
          Bytes 16-19  → tamaño en bytes (little-endian 32 bits)
          Bytes 20-23  → cluster inicial (little-endian 32 bits)
          Bytes 30-43  → fecha de creación (14 chars: AAAAMMDDHHMMSS)
          Bytes 50-63  → fecha de modificación (14 chars: AAAAMMDDHHMMSS)

        Retorna None si la entrada está libre o no se puede leer.
        """
        desplazamiento = INICIO_DIR + (indice * TAMANO_ENTRADA)
        try:
            with open(self.ruta, "rb") as img:
                img.seek(desplazamiento)
                nombre_crudo = img.read(15).decode("ascii")

                if nombre_crudo[0] != ENTRADA_ARCHIVO:
                    return None

                img.seek(desplazamiento + 16)
                (tamano,) = struct.unpack("<I", img.read(4))

                img.seek(desplazamiento + 20)
                (cluster,) = struct.unpack("<I", img.read(4))

                img.seek(desplazamiento + 30)
                fecha_creacion = img.read(14).decode("ascii")

                img.seek(desplazamiento + 50)
                fecha_modificacion = img.read(14).decode("ascii")

            return FileEntry(
                name=nombre_crudo[1:].strip(),
                size=tamano,
                initial_cluster=cluster,
                creation_date=fecha_creacion,
                update_date=fecha_modificacion,
                img_path=self.ruta,
            )
        except (OSError, UnicodeDecodeError, struct.error):
            return None


    # Métodos de escritura interna

    def _buscar_espacio_libre(self, tamano_archivo: int) -> int | None:
        """
        Busca clusters contiguos libres donde quepa el archivo.

        FiUnamFS usa asignación contigua, así que todos los clusters de un
        archivo tienen que ser consecutivos. Este método:
          1. Marca como reservados los clusters del superbloque y directorio.
          2. Marca como ocupados los clusters de archivos que ya existen.
          3. Busca la primera secuencia contigua del tamaño necesario.

        Retorna el número del primer cluster disponible, o None si no hay espacio.
        """
        clusters_necesarios = math.ceil(tamano_archivo / CLUSTER_SIZE)

        reservados = set(range(self.clusters_dir + 1))  # Superbloque + directorio
        ocupados   = set()
        for archivo in self.listar_archivos():
            _, lista = archivo.clusters_used()
            ocupados.update(lista)

        libres = [
            c for c in range(self.total_clusters)
            if c not in reservados and c not in ocupados
        ]

        # Buscamos la primera secuencia de clusters_necesarios números consecutivos
        for i in range(len(libres) - clusters_necesarios + 1):
            if all(libres[i + j] == libres[i] + j for j in range(clusters_necesarios)):
                return libres[i]

        return None

    def _escribir_entrada_directorio(
        self, ruta_origen: str, nombre_archivo: str, tamano_archivo: int, cluster: int
    ) -> str:
        """
        Escribe los metadatos del nuevo archivo en la primera entrada libre del directorio.

        Los campos se escriben según los offsets de la especificación:
          - 15 bytes: marcador - + nombre rellenado con espacios a la derecha
          - 4 bytes:  tamaño en little-endian
          - 4 bytes:  cluster inicial en little-endian
          - 14 bytes: fecha de creación (tomada del archivo original en la PC)
          - 14 bytes: fecha de modificación (tomada del archivo original en la PC)
        """
        for i in range(self.max_entradas):
            desplazamiento = INICIO_DIR + (i * TAMANO_ENTRADA)
            try:
                with open(self.ruta, "rb") as img:
                    img.seek(desplazamiento)
                    marcador = img.read(1).decode("ascii")
            except (OSError, UnicodeDecodeError):
                continue

            if marcador != ENTRADA_LIBRE:
                continue

            # Preparar cada campo según la especificación
            nombre_relleno      = ("-" + nombre_archivo).ljust(15).encode("ascii")
            tamano_empaquetado  = struct.pack("<I", tamano_archivo)
            cluster_empaquetado = struct.pack("<I", cluster)
            fecha_creacion      = datetime.fromtimestamp(
                os.path.getctime(ruta_origen)).strftime("%Y%m%d%H%M%S").encode("ascii")
            fecha_modificacion  = datetime.fromtimestamp(
                os.path.getmtime(ruta_origen)).strftime("%Y%m%d%H%M%S").encode("ascii")

            # Escritura protegida por el candado para evitar corrupción
            with self._candado:
                try:
                    with open(self.ruta, "rb+") as img:
                        img.seek(desplazamiento);      img.write(nombre_relleno)
                        img.seek(desplazamiento + 16); img.write(tamano_empaquetado)
                        img.seek(desplazamiento + 20); img.write(cluster_empaquetado)
                        img.seek(desplazamiento + 30); img.write(fecha_creacion)
                        img.seek(desplazamiento + 50); img.write(fecha_modificacion)
                    return f'[OK] "{nombre_archivo}" copiado a FiUnamFS exitosamente.'
                except OSError:
                    return "[Error] Error al escribir la entrada en el directorio."

        return "[Error] No hay entradas libres en el directorio de FiUnamFS."
