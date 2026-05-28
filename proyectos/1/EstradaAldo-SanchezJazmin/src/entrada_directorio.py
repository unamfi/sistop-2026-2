"""
una entrada del directorio de FiUnamFS
"""

from constantes import ENTRADA_VACIA, TIPO_ARCHIVO, TIPO_ENTRADA_VACIA
import struct

"""
clase que representa una entrada de 64 bytes contenida en el sistema de archivos
"""
class EntradaDirectorio:
    def __init__(self, tipo, nombre, tamano, 
                cluster_inicial, fecha_creacion, 
                fecha_modificacion, indice):
        self.tipo = tipo
        self.nombre_archivo = nombre
        self.tamano = tamano
        self.cluster_inicial = cluster_inicial
        self.fecha_creacion = fecha_creacion
        self.fecha_modificacion = fecha_modificacion
        self.indice = indice
    
    """
    crear una entrada del directorio a partir de 64 bytes en crudo
    """
    @classmethod
    def crear_entrada_directorio(cls, datos, indice):
        tipo = datos[0:1].decode("ascii", errors="ignore")
        nombre_archivo = datos[1:16].decode("ascii",errors="ignore").strip("\x00").strip()
        
        tamano = struct.unpack("<I", datos[16:20])[0]
        cluster_inicial = struct.unpack("<I", datos[20:24])[0]
        
        fecha_creacion = datos[30:44].decode("ascii",errors="ignore").strip("\x00").strip()
        fecha_modificacion = datos[50:64].decode("ascii",errors="ignore").strip("\x00").strip()
        
        return cls(
            tipo,
            nombre_archivo,
            tamano,
            cluster_inicial,
            fecha_creacion,
            fecha_modificacion,
            indice
        )
    
    """
    indica si la entrada del directorio esta vacia
    """
    def esta_vacia(self):
        return self.tipo == TIPO_ENTRADA_VACIA or self.nombre_archivo == ENTRADA_VACIA
    
    """
    indica si la entrada es un archivo valido
    """
    def es_archivo(self):
        return self.tipo == TIPO_ARCHIVO and not self.esta_vacia()
    
    """
    genera los 64 bytes correspondientes a una entrada vacia
    """
    @staticmethod
    def bytes_entrada_vacia():
        datos = bytearray(64)
        
        datos[0:1] = TIPO_ENTRADA_VACIA.encode("ascii")
        datos[1:16] = ENTRADA_VACIA.encode("ascii")
        
        return bytes(datos)
    
    """
    genera los 64 bytes que corresponden a una entrada de archivo al directorio
    """
    @staticmethod
    def bytes_archivo(nombre_archivo, tamano, cluster_inicial, 
                      fecha_creacion, fecha_modificacion):
        datos = bytearray(64)
        
        nombre_bytes = nombre_archivo.encode("ascii")
        datos[0:1] = TIPO_ARCHIVO.encode("ascii")
        datos[1:16] = nombre_bytes.ljust(15, b" ")
        
        datos[16:20] = struct.pack("<I", tamano)
        datos[20:24] = struct.pack("<I", cluster_inicial)
        
        datos[30:44] = fecha_creacion.encode("ascii")
        datos[50:64] = fecha_modificacion.encode("ascii")
        
        return bytes(datos)
