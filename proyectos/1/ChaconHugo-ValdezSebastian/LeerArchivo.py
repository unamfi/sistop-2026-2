# ============================================================
# Proyecto: Micro sistema de archivos multihilos - FiUnamFS
# Autor(es): Hugo Chacon, Sebastian Valdez
# Fecha: 21/05/2026
#
# Descripción:
# Implementación básica de un sistema de archivos FiUnamFS.
#
# El programa permite:
#
# 1. Leer y validar el superbloque
# 2. Listar archivos del directorio
# 3. Copiar archivos desde FiUnamFS hacia la computadora
# 4. Copiar archivos desde la computadora hacia FiUnamFS
# 5. Eliminar archivos
# 6. Uso de concurrencia mediante hilos
# 7. Sincronización usando mutex (Lock)
#
# ============================================================

import os
import struct
import math
import threading
import queue
from datetime import datetime

# ============================================================
# CONFIGURACIONES GENERALES
# ============================================================

# Ruta de la imagen del sistema de archivos
IMG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "fiunamfs.img"
)

# Tamaño de cluster
# 4 sectores * 512 bytes = 2048 bytes
CLUSTER_SIZE = 2048

# Tamaño de cada entrada del directorio
ENTRY_SIZE = 64

# Directorio:
# clusters 1 al 8
DIR_START_CLUSTER = 1
DIR_CLUSTER_COUNT = 8

# Offset inicial del directorio
DIR_START_OFFSET = DIR_START_CLUSTER * CLUSTER_SIZE

# Tamaño total del directorio
DIR_SIZE = DIR_CLUSTER_COUNT * CLUSTER_SIZE

# Primer cluster de datos
DATA_START_CLUSTER = 9

# ============================================================
# MECANISMOS DE SINCRONIZACIÓN
# ============================================================

# Lock para proteger acceso concurrente al .img
fs_lock = threading.Lock()

# Cola para comunicación entre hilos
log_queue = queue.Queue()

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def log(mensaje):
    """
    Agrega mensajes a la cola de logs.
    El hilo logger los imprimirá concurrentemente.
    """
    log_queue.put(mensaje)


def logger_thread():
    """
    Hilo encargado de imprimir eventos del sistema.
    Funciona concurrentemente con el menú principal.
    """
    while True:
        mensaje = log_queue.get()

        if mensaje == "EXIT":
            break

        print(f"\n[LOG] {mensaje}")


def formatear_fecha(cadena_fecha):
    """
    Convierte una fecha:
        20260108182600

    A:
        2026-01-08 18:26:00
    """

    if len(cadena_fecha) < 14:
        return "Fecha inválida"

    anio = cadena_fecha[0:4]
    mes = cadena_fecha[4:6]
    dia = cadena_fecha[6:8]
    hora = cadena_fecha[8:10]
    minuto = cadena_fecha[10:12]
    segundo = cadena_fecha[12:14]

    return f"{anio}-{mes}-{dia} {hora}:{minuto}:{segundo}"


def obtener_fecha_actual():
    """
    Retorna fecha actual en formato requerido por FiUnamFS:
    AAAAMMDDHHMMSS
    """

    return datetime.now().strftime("%Y%m%d%H%M%S")


# ============================================================
# SUPERBLOQUE
# ============================================================

def analizar_superbloque():
    """
    Lee y valida el superbloque del sistema de archivos.
    """

    with fs_lock:

        with open(IMG_PATH, "rb") as f:

            superbloque = f.read(CLUSTER_SIZE)

            print("\n========== SUPERBLOQUE ==========\n")

            # 0-4
            caracteres = superbloque[0:4].decode('ascii')
            print(f"0-4   -> Caracteres: {caracteres}")

            # 5-13
            fs_id = superbloque[5:13].decode('ascii')
            print(f"5-13  -> Identificador: {fs_id}")

            if fs_id != "FiUnamFS":
                print("[ERROR] Sistema inválido")
                return

            # 14-19
            version = superbloque[14:19].decode('ascii')
            print(f"14-19 -> Version: {version}")

            # 20-36
            etiqueta = superbloque[20:36].decode('ascii')
            print(f"20-36 -> Etiqueta: {etiqueta}")

            # 40-44
            cluster_size = struct.unpack('<I', superbloque[40:44])[0]
            print(f"40-44 -> Tamaño cluster: {cluster_size}")

            # 50-54
            dir_clusters = struct.unpack('<I', superbloque[50:54])[0]
            print(f"50-54 -> Clusters directorio: {dir_clusters}")

            # 60-64
            total_clusters = struct.unpack('<I', superbloque[60:64])[0]
            print(f"60-64 -> Clusters totales: {total_clusters}")

            print("\n=================================\n")


# ============================================================
# LISTAR DIRECTORIO
# ============================================================

def listar_directorio():
    """
    Recorre todas las entradas del directorio
    y muestra los archivos válidos.
    """

    with fs_lock:

        with open(IMG_PATH, "rb") as f:

            f.seek(DIR_START_OFFSET)

            directorio = f.read(DIR_SIZE)

            print("\n================ DIRECTORIO ================\n")

            print(
                f"{'Nombre':<16} | "
                f"{'Tamaño':<10} | "
                f"{'Cluster':<10} | "
                f"{'Creación':<20} | "
                f"{'Modificación':<20}"
            )

            print("-" * 95)

            for i in range(0, DIR_SIZE, ENTRY_SIZE):

                entrada = directorio[i:i + ENTRY_SIZE]

                tipo = entrada[0:1]

                # Ignorar entradas vacías
                if tipo != b'-':
                    continue

                # Nombre
                nombre = entrada[1:16].split(b'\x00')[0]
                nombre = nombre.decode('ascii').strip()

                # Tamaño
                tamano = struct.unpack('<I', entrada[16:20])[0]

                # Cluster inicial
                cluster_inicial = struct.unpack('<I', entrada[20:24])[0]

                # Fecha creación
                fecha_creacion = entrada[30:44].decode('ascii').strip()
                fecha_creacion = formatear_fecha(fecha_creacion)

                # Fecha modificación
                fecha_mod = entrada[50:64].decode('ascii').strip()
                fecha_mod = formatear_fecha(fecha_mod)

                print(
                    f"{nombre:<16} | "
                    f"{tamano:<10} | "
                    f"{cluster_inicial:<10} | "
                    f"{fecha_creacion:<20} | "
                    f"{fecha_mod:<20}"
                )

            print("\n============================================\n")


# ============================================================
# BUSCAR ARCHIVO EN DIRECTORIO
# ============================================================

def buscar_archivo(nombre_archivo):
    """
    Busca un archivo dentro del directorio.

    Retorna:
        (entrada, posicion)
    o
        (None, None)
    """

    with open(IMG_PATH, "rb") as f:

        for i in range(0, DIR_SIZE, ENTRY_SIZE):

            pos = DIR_START_OFFSET + i

            f.seek(pos)

            entrada = f.read(ENTRY_SIZE)

            if entrada[0:1] != b'-':
                continue

            nombre = entrada[1:16].split(b'\x00')[0]
            nombre = nombre.decode('ascii').strip()

            if nombre == nombre_archivo:
                return entrada, pos

    return None, None


# ============================================================
# COPIAR DESDE FiUnamFS HACIA LA COMPUTADORA
# ============================================================

def copiar_desde_fs(nombre_archivo, destino):
    """
    Extrae un archivo desde FiUnamFS
    hacia la computadora.
    """

    with fs_lock:

        entrada, _ = buscar_archivo(nombre_archivo)

        if entrada is None:
            print("[ERROR] Archivo no encontrado")
            return

        tamano = struct.unpack('<I', entrada[16:20])[0]

        cluster_inicial = struct.unpack('<I', entrada[20:24])[0]

        with open(IMG_PATH, "rb") as f:

            offset = cluster_inicial * CLUSTER_SIZE

            f.seek(offset)

            datos = f.read(tamano)

        with open(destino, "wb") as salida:
            salida.write(datos)

        print("[OK] Archivo copiado correctamente")

        log(f"Archivo extraído: {nombre_archivo}")


# ============================================================
# OBTENER CLUSTERS OCUPADOS
# ============================================================

def obtener_clusters_ocupados():
    """
    Retorna lista de clusters ocupados.
    """

    ocupados = []

    with open(IMG_PATH, "rb") as f:

        for i in range(0, DIR_SIZE, ENTRY_SIZE):

            pos = DIR_START_OFFSET + i

            f.seek(pos)

            entrada = f.read(ENTRY_SIZE)

            if entrada[0:1] != b'-':
                continue

            tamano = struct.unpack('<I', entrada[16:20])[0]

            cluster_inicial = struct.unpack('<I', entrada[20:24])[0]

            clusters_usados = math.ceil(tamano / CLUSTER_SIZE)

            for c in range(cluster_inicial,
                           cluster_inicial + clusters_usados):

                ocupados.append(c)

    return ocupados


# ============================================================
# BUSCAR CLUSTERS LIBRES CONTIGUOS
# ============================================================

def buscar_espacio_libre(clusters_necesarios):
    """
    Busca espacio contiguo libre dentro del FS.
    """

    ocupados = obtener_clusters_ocupados()

    cluster_actual = DATA_START_CLUSTER

    while True:

        libre = True

        for i in range(clusters_necesarios):

            if (cluster_actual + i) in ocupados:
                libre = False
                break

        if libre:
            return cluster_actual

        cluster_actual += 1


# ============================================================
# BUSCAR ENTRADA LIBRE EN DIRECTORIO
# ============================================================

def buscar_entrada_libre():
    """
    Busca una entrada vacía en el directorio.
    """

    with open(IMG_PATH, "rb") as f:

        for i in range(0, DIR_SIZE, ENTRY_SIZE):

            pos = DIR_START_OFFSET + i

            f.seek(pos)

            entrada = f.read(ENTRY_SIZE)

            if entrada[0:1] == b'/':
                return pos

    return None


# ============================================================
# COPIAR ARCHIVO HACIA FiUnamFS
# ============================================================

def copiar_hacia_fs(ruta_local):
    """
    Copia un archivo de la computadora
    hacia FiUnamFS.
    """

    with fs_lock:

        if not os.path.exists(ruta_local):
            print("[ERROR] Archivo no encontrado")
            return

        nombre = os.path.basename(ruta_local)

        # Validar tamaño nombre
        if len(nombre) > 15:
            print("[ERROR] Nombre demasiado largo")
            return

        # Leer archivo local
        with open(ruta_local, "rb") as f:
            datos = f.read()

        tamano = len(datos)

        clusters_necesarios = math.ceil(tamano / CLUSTER_SIZE)

        # Buscar espacio libre
        cluster_libre = buscar_espacio_libre(clusters_necesarios)

        # Buscar entrada libre
        entrada_libre = buscar_entrada_libre()

        if entrada_libre is None:
            print("[ERROR] Directorio lleno")
            return

        fecha = obtener_fecha_actual()

        # Crear entrada
        entrada = bytearray(64)

        # Tipo
        entrada[0:1] = b'-'

        # Nombre
        entrada[1:16] = nombre.encode().ljust(15, b'\x00')

        # Tamaño
        entrada[16:20] = struct.pack('<I', tamano)

        # Cluster inicial
        entrada[20:24] = struct.pack('<I', cluster_libre)

        # Fecha creación
        entrada[30:44] = fecha.encode()

        # Fecha modificación
        entrada[50:64] = fecha.encode()

        with open(IMG_PATH, "r+b") as f:

            # Escribir datos
            f.seek(cluster_libre * CLUSTER_SIZE)

            f.write(datos)

            # Escribir entrada directorio
            f.seek(entrada_libre)

            f.write(entrada)

        print("[OK] Archivo copiado a FiUnamFS")

        log(f"Archivo agregado: {nombre}")


# ============================================================
# ELIMINAR ARCHIVO
# ============================================================

def eliminar_archivo(nombre_archivo):
    """
    Elimina un archivo del directorio.

    NOTA:
    Los datos permanecen físicamente,
    únicamente se marca la entrada como libre.
    """

    with fs_lock:

        entrada, pos = buscar_archivo(nombre_archivo)

        if entrada is None:
            print("[ERROR] Archivo no encontrado")
            return

        entrada = bytearray(entrada)

        # Marcar como vacío
        entrada[0:1] = b'/'

        with open(IMG_PATH, "r+b") as f:

            f.seek(pos)

            f.write(entrada)

        print("[OK] Archivo eliminado")

        log(f"Archivo eliminado: {nombre_archivo}")


# ============================================================
# MENÚ PRINCIPAL
# ============================================================

def menu():
    """
    Interfaz principal del programa.
    """

    while True:

        print("\n=========== FiUnamFS ===========")
        print("1. Analizar superbloque")
        print("2. Listar directorio")
        print("3. Copiar desde FiUnamFS")
        print("4. Copiar hacia FiUnamFS")
        print("5. Eliminar archivo")
        print("6. Salir")
        print("================================")

        opcion = input("Seleccione una opción: ")

        # ====================================================

        if opcion == "1":

            analizar_superbloque()

        # ====================================================

        elif opcion == "2":

            listar_directorio()

        # ====================================================

        elif opcion == "3":

            nombre = input("Nombre archivo en FiUnamFS: ")

            destino = input("Ruta destino: ")

            copiar_desde_fs(nombre, destino)

        # ====================================================

        elif opcion == "4":

            ruta = input("Ruta archivo local: ")

            copiar_hacia_fs(ruta)

        # ====================================================

        elif opcion == "5":

            nombre = input("Nombre archivo a eliminar: ")

            eliminar_archivo(nombre)

        # ====================================================

        elif opcion == "6":

            log("EXIT")

            print("Saliendo...")

            break

        # ====================================================

        else:

            print("[ERROR] Opción inválida")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # Crear hilo logger
    hilo_logger = threading.Thread(
        target=logger_thread,
        daemon=True
    )

    hilo_logger.start()

    # Ejecutar menú
    menu()