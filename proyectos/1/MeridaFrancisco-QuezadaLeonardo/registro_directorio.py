# registro_directorio.py

import struct

from config_fiunamfs import (
    TAM_ENTRADA_DIRECTORIO,
    TIPO_LIBRE,
    NOMBRE_ENTRADA_LIBRE
)


class RegistroDirectorio:
    def __init__(self, datos, indice):
        self.datos = datos
        self.indice = indice

        self.tipo = self._leer_texto(0, 1)
        self.nombre = self._leer_texto(1, 16)

        self.tamanio = struct.unpack("<I", datos[16:20])[0]
        self.cluster_inicial = struct.unpack("<I", datos[20:24])[0]

        # Según la especificación: creación 30–44 y modificación 50–64
        self.fecha_creacion = self._leer_texto(30, 44)
        self.fecha_modificacion = self._leer_texto(50, 64)

    def _leer_texto(self, inicio, fin):
        return (
            self.datos[inicio:fin]
            .decode("ascii", errors="ignore")
            .replace("\x00", "")
            .strip()
        )

    def esta_libre(self):
        return (
            self.tipo == TIPO_LIBRE
            or self.nombre == NOMBRE_ENTRADA_LIBRE
            or self.nombre == ""
        )

    def es_archivo_valido(self):
        return not self.esta_libre()

    def __str__(self):
        return (
            f"{self.nombre} | "
            f"{self.tamanio} bytes | "
            f"cluster {self.cluster_inicial}"
        )