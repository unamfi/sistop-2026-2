# imagen_fiunamfs.py
# Clase principal para leer y modificar la imagen de FiUnamFS.

import os
import struct
import threading
import math
import time

from config_fiunamfs import (
    OFFSET_NOMBRE_FS,
    OFFSET_VERSION,
    OFFSET_ETIQUETA,
    OFFSET_TAM_CLUSTER,
    OFFSET_CLUSTERS_DIRECTORIO,
    OFFSET_CLUSTERS_TOTALES,
    NOMBRE_FS_ESPERADO,
    VERSIONES_VALIDAS,
    CLUSTER_DIRECTORIO_INICIO,
    TAM_ENTRADA_DIRECTORIO
)

from registro_directorio import RegistroDirectorio


class ImagenFiUnamFS:
    def __init__(self, ruta_imagen):
        if not os.path.exists(ruta_imagen):
            raise FileNotFoundError(f"No existe la imagen: {ruta_imagen}")

        self.ruta_imagen = ruta_imagen

        # Se abre en modo binario porque se trabaja directamente con bytes.
        # Además usamos r+b porque se necesita leer y también modificar la imagen.
        self.disco = open(ruta_imagen, "r+b")

        # FUSE y la interfaz pueden hacer operaciones mientras el programa está activo.
        # El RLock evita que dos operaciones modifiquen la imagen al mismo tiempo.
        self.lock = threading.RLock()

        self.nombre_fs = ""
        self.version = ""
        self.etiqueta = ""
        self.tam_cluster = 0
        self.clusters_directorio = 0
        self.clusters_totales = 0
        self.cluster_datos_inicio = 0

        self.cargar_superbloque()

    # Lectura y escritura

    def leer_bytes(self, offset, cantidad):
        self.disco.seek(offset)
        return self.disco.read(cantidad)

    def escribir_bytes(self, offset, datos):
        self.disco.seek(offset)
        self.disco.write(datos)
        self.disco.flush()

    def leer_entero_32(self, offset):
        datos = self.leer_bytes(offset, 4)

        # Los enteros de FiUnamFS se guardan en little endian.
        return struct.unpack("<I", datos)[0]

    def leer_cadena(self, offset, cantidad):
        return (
            self.leer_bytes(offset, cantidad)
            .decode("ascii", errors="ignore")
            .replace("\x00", "")
            .strip()
        )

    # Superbloque

    def cargar_superbloque(self):
        # El superbloque se valida primero para no modificar una imagen
        # que no corresponda al sistema de archivos esperado.
        self.nombre_fs = self.leer_cadena(OFFSET_NOMBRE_FS, 8)
        self.version = self.leer_cadena(OFFSET_VERSION, 4)
        self.etiqueta = self.leer_cadena(OFFSET_ETIQUETA, 16)

        self.tam_cluster = self.leer_entero_32(OFFSET_TAM_CLUSTER)
        self.clusters_directorio = self.leer_entero_32(OFFSET_CLUSTERS_DIRECTORIO)
        self.clusters_totales = self.leer_entero_32(OFFSET_CLUSTERS_TOTALES)

        if self.nombre_fs != NOMBRE_FS_ESPERADO:
            raise ValueError("La imagen no corresponde a FiUnamFS.")

        if not any(v in self.version for v in VERSIONES_VALIDAS):
            raise ValueError(f"Versión no soportada: {self.version}")

        # La zona de datos empieza después del superbloque y del directorio.
        self.cluster_datos_inicio = (
            CLUSTER_DIRECTORIO_INICIO + self.clusters_directorio
        )

    # Directorio

    def offset_directorio(self):
        return CLUSTER_DIRECTORIO_INICIO * self.tam_cluster

    def cantidad_entradas_directorio(self):
        bytes_directorio = self.clusters_directorio * self.tam_cluster
        return bytes_directorio // TAM_ENTRADA_DIRECTORIO

    def offset_entrada_directorio(self, indice):
        return self.offset_directorio() + indice * TAM_ENTRADA_DIRECTORIO

    def leer_registros(self):
        registros = []

        inicio = self.offset_directorio()
        total = self.cantidad_entradas_directorio()

        # El directorio está formado por entradas de 64 bytes.
        # Cada entrada se interpreta como un RegistroDirectorio.
        for indice in range(total):
            offset = inicio + indice * TAM_ENTRADA_DIRECTORIO
            datos = self.leer_bytes(offset, TAM_ENTRADA_DIRECTORIO)
            registros.append(RegistroDirectorio(datos, indice))

        return registros

    def listar_archivos(self):
        with self.lock:
            return [
                registro
                for registro in self.leer_registros()
                if registro.es_archivo_valido()
            ]

    def buscar_archivo(self, nombre):
        for registro in self.leer_registros():
            if registro.es_archivo_valido() and registro.nombre == nombre:
                return registro

        return None


    # Lectura de archivos

    def leer_archivo(self, nombre, size=None, offset=0):
        with self.lock:
            registro = self.buscar_archivo(nombre)

            if registro is None:
                raise FileNotFoundError(f"No existe el archivo: {nombre}")

            if offset >= registro.tamanio:
                return b""

            if size is None:
                size = registro.tamanio - offset
            else:
                size = min(size, registro.tamanio - offset)

            # Como FiUnamFS usa asignación contigua, el contenido se lee
            # a partir del cluster inicial registrado en el directorio.
            posicion = registro.cluster_inicial * self.tam_cluster + offset
            return self.leer_bytes(posicion, size)

    def extraer_archivo(self, nombre_fs, ruta_salida):
        contenido = self.leer_archivo(nombre_fs)

        with open(ruta_salida, "wb") as salida:
            salida.write(contenido)

    # Búsqueda de espacio

    def buscar_entrada_libre(self):
        for registro in self.leer_registros():
            if registro.esta_libre():
                return registro.indice

        return None

    def clusters_ocupados_por_archivo(self, registro):
        return math.ceil(registro.tamanio / self.tam_cluster)

    def obtener_clusters_ocupados(self):
        ocupados = set()

        for registro in self.leer_registros():
            if registro.es_archivo_valido():
                clusters_usados = self.clusters_ocupados_por_archivo(registro)

                # Se marca todo el rango ocupado por cada archivo.
                for cluster in range(
                    registro.cluster_inicial,
                    registro.cluster_inicial + clusters_usados
                ):
                    ocupados.add(cluster)

        return ocupados

    def buscar_bloque_libre(self, clusters_necesarios):
        ocupados = self.obtener_clusters_ocupados()

        cluster_actual = self.cluster_datos_inicio
        ultimo_posible = self.clusters_totales - clusters_necesarios

        while cluster_actual <= ultimo_posible:
            bloque_libre = True

            # No basta con encontrar clusters libres separados.
            # El archivo necesita un bloque completo de clusters juntos.
            for i in range(clusters_necesarios):
                if cluster_actual + i in ocupados:
                    bloque_libre = False
                    break

            if bloque_libre:
                return cluster_actual

            cluster_actual += 1

        return None

    # Escritura y eliminación

    def eliminar_archivo(self, nombre):
        with self.lock:
            registro = self.buscar_archivo(nombre)

            if registro is None:
                raise FileNotFoundError(f"No existe el archivo: {nombre}")

            offset = self.offset_entrada_directorio(registro.indice)

            # La eliminación es lógica: se libera la entrada del directorio.
            # Los datos anteriores quedan en la zona de datos hasta ser reutilizados.
            entrada_vacia = bytearray(TAM_ENTRADA_DIRECTORIO)
            entrada_vacia[0:1] = b"/"
            entrada_vacia[1:16] = b"###############"

            self.escribir_bytes(offset, entrada_vacia)

    def guardar_archivo(self, nombre, contenido):
        with self.lock:
            try:
                nombre.encode("ascii")
            except UnicodeEncodeError:
                raise ValueError("El nombre debe usar solamente caracteres ASCII.")

            if len(nombre) > 15:
                raise ValueError("El nombre del archivo no puede superar 15 caracteres.")

            if self.buscar_archivo(nombre) is not None:
                raise ValueError(f"Ya existe un archivo llamado {nombre}.")

            indice_libre = self.buscar_entrada_libre()

            if indice_libre is None:
                raise RuntimeError("No hay entradas libres en el directorio.")

            tamanio = len(contenido)
            clusters_necesarios = math.ceil(tamanio / self.tam_cluster)

            cluster_inicial = self.buscar_bloque_libre(clusters_necesarios)

            if cluster_inicial is None:
                raise RuntimeError("No hay espacio contiguo suficiente.")

            # Primero se guarda el contenido y después se registra en el directorio.
            offset_datos = cluster_inicial * self.tam_cluster
            self.escribir_bytes(offset_datos, contenido)

            nueva_entrada = bytearray(TAM_ENTRADA_DIRECTORIO)

            nueva_entrada[0:1] = b"-"
            nueva_entrada[1:16] = nombre.ljust(15).encode("ascii")
            nueva_entrada[16:20] = struct.pack("<I", tamanio)
            nueva_entrada[20:24] = struct.pack("<I", cluster_inicial)

            fecha_actual = time.strftime("%Y%m%d%H%M%S").encode("ascii")
            nueva_entrada[30:44] = fecha_actual
            nueva_entrada[50:64] = fecha_actual

            offset_entrada = self.offset_entrada_directorio(indice_libre)
            self.escribir_bytes(offset_entrada, nueva_entrada)

    def copiar_a_fiunamfs(self, ruta_local, nombre_fs=None):
        if not os.path.exists(ruta_local):
            raise FileNotFoundError(f"No existe el archivo local: {ruta_local}")

        if nombre_fs is None:
            nombre_fs = os.path.basename(ruta_local)

        with open(ruta_local, "rb") as archivo:
            contenido = archivo.read()

        self.guardar_archivo(nombre_fs, contenido)

    def reemplazar_archivo(self, nombre, contenido):
        with self.lock:
            # FUSE usa esta operación cuando se modifica un archivo existente.
            if self.buscar_archivo(nombre) is not None:
                self.eliminar_archivo(nombre)

            self.guardar_archivo(nombre, contenido)

    def calcular_espacio_disponible(self):
        with self.lock:
            ocupados = self.obtener_clusters_ocupados()

            total_clusters_datos = self.clusters_totales - self.cluster_datos_inicio
            clusters_usados = len(ocupados)

            clusters_libres = total_clusters_datos - clusters_usados
            bytes_libres = clusters_libres * self.tam_cluster

            return clusters_libres, bytes_libres

    def cerrar(self):
        self.disco.close()