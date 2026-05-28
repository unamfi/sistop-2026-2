import struct
import os
import struct
from threads import cola_logs

CLUSTER_SIZE = 2048
DIRECTORIO_OFFSET = CLUSTER_SIZE
ENTRADA_SIZE = 64

class FiUnamFS:

    def __init__(self, ruta):
        self.ruta = ruta

    def listar_archivos(self):
        archivos = []

        with open(self.ruta, "rb") as disco:
            for i in range(256):
                offset = DIRECTORIO_OFFSET + (i * ENTRADA_SIZE)
                disco.seek(offset)
                entrada = disco.read(ENTRADA_SIZE)
                tipo = chr(entrada[0])
                if tipo == "-":
                    nombre = entrada[1:16].decode(
                        "ascii"
                    ).replace('\x00', '').strip()
                    tamaño = struct.unpack(
                        "<I",
                        entrada[16:20]
                    )[0]
                    cluster_inicial = struct.unpack(
                        "<I",
                        entrada[20:24]
                    )[0]
                    archivos.append({
                        "nombre": nombre,
                        "tamaño": tamaño,
                        "cluster": cluster_inicial,
                        "offset": offset
                    })

        return archivos

    def mostrar_archivos(self):
        archivos = self.listar_archivos()

        print("\n=== Archivos disponibles ===\n")

        for archivo in archivos:
            print(
                f"- {archivo['nombre']} "
                f"({archivo['tamaño']} bytes)"
            )

    def copiar_desde_fs(self):
        self.mostrar_archivos()

        nombre_archivo = input(
            "\nArchivo a copiar: "
        )

        archivos = self.listar_archivos()

        with open(self.ruta, "rb") as disco:
            for archivo in archivos:
                if archivo["nombre"] == nombre_archivo:
                    inicio = archivo["cluster"] * CLUSTER_SIZE
                    disco.seek(inicio)
                    datos = disco.read(archivo["tamaño"])
                    with open(nombre_archivo, "wb") as salida:
                        salida.write(datos)
                    print("\nArchivo copiado correctamente")
                    return

        print("\nArchivo no encontrado")
        cola_logs.put(
            f"Archivo copiado desde FiUnamFS: {nombre_archivo}"
        )


    def eliminar_archivo(self):
        self.mostrar_archivos()

        nombre_archivo = input(
            "\nArchivo a eliminar: "
        )

        archivos = self.listar_archivos()

        with open(self.ruta, "r+b") as disco:
            for archivo in archivos:
                if archivo["nombre"] == nombre_archivo:
                    disco.seek(archivo["offset"])
                    disco.write(b'/')
                    print("\nArchivo eliminado correctamente")
                    return

        print("\nArchivo no encontrado")
        cola_logs.put(
            f"Archivo eliminado: {nombre_archivo}"
        )

    def buscar_entrada_vacia(self):

        with open(self.ruta, "rb") as disco:
            for i in range(256):
                offset = DIRECTORIO_OFFSET + (i * ENTRADA_SIZE)
                disco.seek(offset)
                entrada = disco.read(ENTRADA_SIZE)
                tipo = chr(entrada[0])
                if tipo == "/":
                    return offset
        return None
    
    def buscar_siguiente_cluster_libre(self):

        archivos = self.listar_archivos()

        ultimo_cluster = 9

        for archivo in archivos:
            clusters_ocupados = (
                archivo["tamaño"] + CLUSTER_SIZE - 1
            ) // CLUSTER_SIZE
            final = (
                archivo["cluster"] + clusters_ocupados
            )
            if final > ultimo_cluster:
                ultimo_cluster = final

        return ultimo_cluster
    
    def copiar_hacia_fs(self):

        print("\n=== Archivos disponibles en la carpeta ===\n")

        archivos_locales = []

        for archivo in os.listdir():
            if archivo == self.ruta:
                continue
            if archivo.endswith(".py"):
                continue
            if os.path.isfile(archivo):
                archivos_locales.append(archivo)
                print(f"- {archivo}")
        nombre_archivo = input(
            "\nArchivo a copiar: "
        )
        if nombre_archivo not in archivos_locales:
            print("\nEse archivo no existe")
            return
        if len(nombre_archivo) > 15:
            print("\nNombre demasiado largo")
            return
        try:
            with open(nombre_archivo, "rb") as archivo_local:
                datos = archivo_local.read()
        except:
            print("\nNo se pudo abrir el archivo")
            return
        
        tamaño = len(datos)

        entrada_libre = self.buscar_entrada_vacia()

        if entrada_libre is None:
            print("\nNo hay entradas libres")
            return

        cluster_libre = self.buscar_siguiente_cluster_libre()

        with open(self.ruta, "r+b") as disco:
            inicio = cluster_libre * CLUSTER_SIZE
            disco.seek(inicio)
            disco.write(datos)
            disco.seek(entrada_libre)
            disco.write(b'-')
            nombre = nombre_archivo.ljust(15)
            disco.write(nombre.encode("ascii"))
            disco.write(
                struct.pack("<I", tamaño)
            )
            disco.write(
                struct.pack("<I", cluster_libre)
            )
            fecha = "20250517120000"
            disco.write(fecha.encode("ascii"))
            disco.write(fecha.encode("ascii"))
            restante = 64 - (
                1 + 15 + 4 + 4 + 14 + 14
            )
            disco.write(b'\x00' * restante)

        print("\nArchivo copiado hacia FiUnamFS")
        cola_logs.put(
            f"Archivo copiado hacia FiUnamFS: {nombre_archivo}"
        )