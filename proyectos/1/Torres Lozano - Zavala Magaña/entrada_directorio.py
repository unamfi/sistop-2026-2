"""
Este módulo representa una entrada del directorio de FiUnamFS.
Cada archivo que existe en el sistema ocupa exactamente 64 bytes
en el área de directorio, y aquí definimos cómo leerlos e interpretarlos.
"""

import os
import math
import struct

# Cada cluster mide 4 sectores de 512 bytes = 2048 bytes.
# Todos los archivos del sistema se almacenan en bloques de este tamaño,
# así que aunque un archivo pese 1 byte, ocupa un cluster completo.
TAMANO_CLUSTER = 2048
CLUSTER_SIZE = TAMANO_CLUSTER  # Alias para compatibilidad con sistema_archivos.py


class FileEntry:
    """
    Representa una entrada del directorio de FiUnamFS.

    Guarda los metadatos de un archivo: nombre, tamaño, en qué cluster
    empieza y sus fechas. Los datos reales del archivo no están aquí,
    sino en los clusters de datos que le corresponden.
    """

    def __init__(
        self,
        name: str,
        size: int,
        initial_cluster: int,
        creation_date: str,
        update_date: str,
        img_path: str,
    ) -> None:
        self.name            = name
        self.size            = size
        self.initial_cluster = initial_cluster  # Dónde empiezan los datos en el disco
        self.creation_date   = self._formatear_fecha(creation_date)
        self.update_date     = self._formatear_fecha(update_date)
        self.img_path        = img_path  # Necesitamos la ruta para poder leer el .img

    def __str__(self) -> str:
        return self.name

    def copy_to_system(self, directorio_destino: str) -> bool:
        """
        Copia el archivo desde la imagen FiUnamFS hacia un directorio
        en la computadora local.

        Primero construimos la ruta destino, verificamos que no exista ya,
        leemos el contenido del .img y lo escribimos en disco.
        Retorna True si todo salió bien, False si algo falló.
        """
        ruta_destino = os.path.join(directorio_destino, self.name)

        # Para que no sobreescribimos archivos que ya existan en el destino
        if os.path.exists(ruta_destino):
            return False

        contenido = self._leer_contenido()
        if contenido is None:
            return False

        try:
            with open(ruta_destino, "wb") as archivo_nuevo:
                archivo_nuevo.write(contenido)
            return True
        except OSError:
            return False

    def clusters_used(self) -> tuple[int, list[int]]:
        """
        Devuelve cuántos clusters ocupa este archivo y cuáles son.

        FiUnamFS usa asignación contigua, o sea que los clusters de un
        archivo siempre son consecutivos. Si el archivo empieza en el
        cluster 6 y ocupa 3 clusters, usa los clusters 6, 7 y 8.
        """
        # math.ceil porque aunque solo uses un byte extra, se necesita un cluster entero
        cantidad = math.ceil(self.size / TAMANO_CLUSTER)
        lista_clusters = list(range(self.initial_cluster, self.initial_cluster + cantidad))
        return cantidad, lista_clusters

    def _leer_contenido(self) -> bytes | None:
        """
        Lee los bytes del archivo directamente desde la imagen .img.

        El offset en bytes donde empieza el archivo se calcula multiplicando
        el número de cluster inicial por el tamaño de cluster. Luego leemos
        exactamente 'size' bytes, que es lo que ocupa el archivo real.
        """
        desplazamiento = self.initial_cluster * TAMANO_CLUSTER
        try:
            with open(self.img_path, "rb") as img:
                img.seek(desplazamiento)
                return img.read(self.size)
        except OSError:
            return None

    @staticmethod
    def _formatear_fecha(crudo: str) -> str:
        """
        Convierte la fecha del formato compacto del FS a algo legible.

        El sistema guarda las fechas como 14 dígitos pegados sin separadores,
        por ejemplo '20260108182600'. Aquí las convertimos a '2026-01-08 18:26:00'
        para que sea más fácil leerlas en la interfaz.
        """
        if len(crudo) < 14:
            return "Fecha inválida"
        return (
            f"{crudo[0:4]}-{crudo[4:6]}-{crudo[6:8]} "
            f"{crudo[8:10]}:{crudo[10:12]}:{crudo[12:14]}"
        )