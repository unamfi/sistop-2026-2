#!/usr/bin/python3

#Programa encargado de leer el superbloque de la imagen proporcionada
#Autores: Isaac Campos, Alejandro Martinez
#Fecha de realización: 15 Mayo 2026

from . import herramientas as h 

#Constantes del sistema de archivos mencionados en el planteamiento
#Se usan para validar que la imagen recibida corresponda al formato esperado.
NOM_FS = "FiUnamFS"
#En caso de que la img tenga por versión 24-2 cambiarla aquí.
VER_FS = "26-2"

TAM_SECTOR = 512
NUM_SECT_CLUSTER = 4
TAM_CLUSTER = TAM_SECTOR * NUM_SECT_CLUSTER

#El directorio inicia en el cluster 1, ya que el cluster 0 contiene el superbloque.
CLUSTER_INI_DIR = 1

TAM_ENTRADA_DIR = 64

#Se define la clase para el superbloque.
#El superbloque contiene los datos generales del sistema de archivos:
#nombre, versión, etiqueta, tamaño de cluster y cantidad de clusters.
class SuperBloque:
    def __init__(self, ruta_img):
        self.ruta_img = ruta_img
        self.leerSuperbloque()

    #Lee el primer cluster de la imagen y obtiene los campos principales del superbloque.
    #También calcula los desplazamientos donde comienzan el directorio y la zona de datos.
    def leerSuperbloque(self):
        with open(self.ruta_img,'rb') as bin_img:
            #Se lee el primer cluster completo, porque ahí se encuentra el superbloque.
            sp_bloque = bin_img.read(TAM_CLUSTER)

            self.nombre = sp_bloque[5:14].decode('ascii').strip('\x00')
            self.version = sp_bloque[14:19].decode('ascii').strip('\x00')
            self.etiqueta = sp_bloque[20:36].decode('ascii').strip('\x00')

            self.tam_cluster = h.leerLe(sp_bloque[40:44])
            self.num_clusters_dir = h.leerLe(sp_bloque[50:54])
            self.num_clusters_tot = h.leerLe(sp_bloque[60:64])

            self.desp_dir = CLUSTER_INI_DIR * self.tam_cluster
            self.tam_dir = self.num_clusters_dir * self.tam_cluster
            self.desp_datos = (CLUSTER_INI_DIR + self.num_clusters_dir)*self.tam_cluster

            #La validación evita trabajar sobre una imagen que no corresponda a FiUnamFS.
            #Si el nombre o la versión no coinciden, se detiene la ejecución.
            if self.nombre != NOM_FS:
                raise RuntimeError(f"Nombre incorrecto: encontré '{self.nombre}' esperaba '{NOM_FS}'")
            if self.version != VER_FS:
                raise RuntimeError(f"Verión incorrecta: encontré '{self.version}' esperaba '{VER_FS}'")
            
