"""
logica utilizada para interpretar la imagen FiUnamFS
"""

from pathlib import Path
from datetime import datetime

from disco import Disco
from constantes import (
    NOMBRE_SISTEMA, VERSION, TAM_CLUSTER,
    CLUSTER_INICIO_DIRECTORIO,
    CLUSTER_FINAL_DIRECTORIO,
    TAM_ENTRADA_DIRECTORIO,
    CLUSTER_INICIO_DATOS,
    TOTAL_CLUSTERS,
    TAM_NOMBRE_ARCHIVO
)
from entrada_directorio import EntradaDirectorio
from sincronizacion import Sincronizacion

"""
clase que representa el sistema de archivos contenido en la imagen
"""
class FiUnamFS:
    def __init__(self, ruta_imagen, sincronizacion=None):
        self.ruta_imagen = ruta_imagen
        self.disco = Disco(ruta_imagen)
        
        if sincronizacion is None:
            self.sincronizacion = Sincronizacion()
        else:
            self.sincronizacion = sincronizacion
    
    """
    funcion que lee una cadena ASCII de la imagen usando un rango [inicio,fin)
    """
    def leer_cadena(self, inicio, fin):
        datos = self.disco.leer_bytes(inicio, fin - inicio)
        
        return datos.decode("ascii").strip("\x00").strip()
    
    """
    valida que la imagen sea la correspondiente a FiUnamFS con la version 2026-2
    """
    def validar_superbloque(self):
        nombre_sistema = self.leer_cadena(5,13)
        version = self.leer_cadena(14,18)
        
        if nombre_sistema != NOMBRE_SISTEMA:
            print(f"Error: sistema de archivos incorrecto: '{nombre_sistema}'")
            return False
        
        if version != VERSION:
            print(f"Error: version de sistema de archivos incorrecta: '{version}'")
            return False
        
        return True
    
    """
    lectura de todas las entradas del directorio FiUnamFS
    """
    def leer_directorio(self):
        entradas = []
        
        offset_directorio = CLUSTER_INICIO_DIRECTORIO * TAM_CLUSTER
        tamano_directorio = (CLUSTER_FINAL_DIRECTORIO 
                             - CLUSTER_INICIO_DIRECTORIO + 1) * TAM_CLUSTER
        
        datos_directorio = self.disco.leer_bytes(offset_directorio, tamano_directorio)
        
        total_entradas = tamano_directorio // TAM_ENTRADA_DIRECTORIO
        
        for indice in range(total_entradas):
            inicio = indice * TAM_ENTRADA_DIRECTORIO
            fin = inicio + TAM_ENTRADA_DIRECTORIO
            
            datos_entrada = datos_directorio[inicio:fin]
            entrada = EntradaDirectorio.crear_entrada_directorio(datos_entrada, indice)
            
            entradas.append(entrada)
        
        return entradas
    
    """
    se regresa una lisata con los archivos existentes en FiUnamFS
    """
    def listar_archivos(self):
        with self.sincronizacion.bloqueo_disco:
            self.sincronizacion.notificar("Leyendo directorio FiUnamFS")
            
            entradas = self.leer_directorio()
            archivos = []
            
            for entrada in entradas:
                if entrada.es_archivo():
                    archivos.append(entrada)
            
            self.sincronizacion.notificar("Directorio leido correctamente")
            return archivos
    
    """
    busca un archivo del directorio de FiUnamFS, regresando la entrada del directorio
    si es que el archivo existe, o sino regresa un None
    """
    def buscar_archivo(self, nombre_archivo):
        entradas = self.listar_archivos()
        
        for entrada in entradas:
            if entrada.nombre_archivo == nombre_archivo:
                return entrada
        return None
    
    """
    lee el contenido del archivo de FiUnamFS , donde se tiene que:
    nombre_archivo: nombre del archivo
    cantidad_bytes: cantidad maxima de bytes a leer
    desplazamiento: posicion inicial dentro del archivo
    """
    def leer_archivo(self, nombre_archivo, cantidad_bytes=None, desplazamiento=0):
        with self.sincronizacion.bloqueo_disco:
            self.sincronizacion.notificar(f"Leyendo el archivo '{nombre_archivo}'")
            
            entrada = self.buscar_archivo(nombre_archivo)
            
            if entrada is None:
                print(f"Error: el archivo '{nombre_archivo}' no existe")
                return None
            
            if desplazamiento >= entrada.tamano:
                return b""
            
            if cantidad_bytes is None or desplazamiento + cantidad_bytes > entrada.tamano:
                cantidad_bytes = entrada.tamano - desplazamiento
            
            offset_archivo = entrada.cluster_inicial * TAM_CLUSTER
            offset_lectura = offset_archivo + desplazamiento
            
            contenido = self.disco.leer_bytes(offset_lectura, cantidad_bytes)
            
            self.sincronizacion.notificar(f"Archivo '{nombre_archivo}' leido "
                                          "correctamente")
            
            return contenido
    
    """
    copia un archivo que pertenece a FiUnamFS hacia un directorio local
    """
    def copiar_archivo(self, nombre_archivo, ruta_destino):
        entrada = self.buscar_archivo(nombre_archivo)
        
        if entrada is None:
            print(f"Error: el archivo '{nombre_archivo}' no existe")
            return False
        
        contenido = self.leer_archivo(nombre_archivo)
        if contenido is None:
            return None
        
        if not ruta_destino.exists():
            print(f"Error: no existe el directorio '{ruta_destino}'")
            return False
        
        if not ruta_destino.is_dir():
            print(f"Error: la ruta '{ruta_destino}' no es un directorio")
            return False
        
        ruta_salida = ruta_destino / entrada.nombre_archivo
        
        with open(ruta_salida, "wb") as archivo_salida:
            archivo_salida.write(contenido)
        
        print(f"El archivo '{nombre_archivo}' fue copiado correctamente")
        return True
    
    """
    elimina un archivo de FiUnamFS, lo hace marcando su entrada de directorio como vacia
    """
    def eliminar_archivo(self, nombre_archivo):
        with self.sincronizacion.bloqueo_disco:
            self.sincronizacion.notificar(f"Eliminando archivo '{nombre_archivo}'")
            entrada = self.buscar_archivo(nombre_archivo)
            
            if entrada is None:
                print(f"Error: el archivo '{nombre_archivo}' no existe")
                return False
            
            offset_directorio = CLUSTER_INICIO_DIRECTORIO * TAM_CLUSTER
            offset_entrada = offset_directorio + (entrada.indice * TAM_ENTRADA_DIRECTORIO)
            
            datos_vacios = EntradaDirectorio.bytes_entrada_vacia()
            
            self.disco.escribir_bytes(offset_entrada, datos_vacios)
            
            self.sincronizacion.notificar(f"La entrada archivo '{nombre_archivo}'"
                                          " fue marcada como vacia")
            print(f"El archivo '{nombre_archivo}' fue eliminado de forma correcta")
            
            return True
    
    """
    calcula cuatos clusters necesita un archivo por su tamano
    """
    def calcular_clusters_necesarios(self, tamano):
        if tamano == 0:
            return 0
        return (tamano + TAM_CLUSTER - 1) // TAM_CLUSTER
    
    """
    busca un entrada libre dentro del directorio
    """
    def buscar_entrada_libre(self):
        entradas = self.leer_directorio()
        
        for entrada in entradas:
            if entrada.esta_vacia():
                return entrada.indice
        return None
    
    """
    obtiene los clusters que estan ocupados por los archivos actuales
    """
    def obtener_clusters_ocupados(self):
        ocupados = set()
        
        for entrada in self.listar_archivos():
            clusters = self.calcular_clusters_necesarios(entrada.tamano)
            
            for cluster in range(entrada.cluster_inicial, 
                                 entrada.cluster_inicial + clusters):
                ocupados.add(cluster)
        
        return ocupados
    
    """
    obtiene espacio libre que sea contiguo y suficiente para guardar el nuevo archivo
    """
    def buscar_espacio_vacio(self, clusters_necesarios):
        if clusters_necesarios == 0:
            return CLUSTER_INICIO_DATOS
        
        ocupados = self.obtener_clusters_ocupados()
        ultimo_inicio = TOTAL_CLUSTERS - clusters_necesarios
        
        for cluster_inicio in range(CLUSTER_INICIO_DATOS, ultimo_inicio + 1):
            libre = True
            
            for desplazamiento in range(clusters_necesarios):
                if cluster_inicio + desplazamiento in ocupados:
                    libre = False
                    break
            
            if libre:
                return cluster_inicio
        return None
    
    """
    copia un archivo local a FiUnamFS
    """
    def insertar_archivo(self, ruta_archivo_local):
        ruta_archivo_local = Path(ruta_archivo_local)
        
        if not ruta_archivo_local.exists():
            print(f"Error: el archivo '{ruta_archivo_local}' no existe")
            return False
        
        if not ruta_archivo_local.is_file():
            print(f"Error: la ruta '{ruta_archivo_local}' no es un archivo")
            return False
        
        nombre_archivo = ruta_archivo_local.name
        
        with open(ruta_archivo_local, "rb") as archivo:
            contenido = archivo.read()
        
        return self.insertar_archivo_desde_bytes(nombre_archivo, contenido)
    
    """
    inserta un archivo en FiUnamFS por su nombre y contenido en bytes
    """
    def insertar_archivo_desde_bytes(self, nombre_archivo, contenido, 
                                     fecha_creacion=None):
        with self.sincronizacion.bloqueo_disco:
            self.sincronizacion.notificar(f"Insertando archivo '{nombre_archivo}'"
                                          " en FiUnamFS")
            
            try:
                nombre_archivo.encode("ascii")
            except UnicodeEncodeError:
                print("Error: el nombre del archivo debe pertenecer al subconjunto ASCII"
                      " de 7 bits")
                return False
            
            if len(nombre_archivo) > TAM_NOMBRE_ARCHIVO:
                print("Error: el nombre del archivo no puede ser mayor a "
                      f"{TAM_NOMBRE_ARCHIVO}")
                return False
            
            if self.buscar_archivo(nombre_archivo) is not None:
                print(f"Error: el archivo '{nombre_archivo}' ya existe en el directorio")
                return False
            
            tamano = len(contenido)
            clusters_necesarios = self.calcular_clusters_necesarios(tamano)
            
            indice_entrada = self.buscar_entrada_libre()
            
            if indice_entrada is None:
                print("Error: no hay entradas libres en el directorio")
                return False
            
            cluster_inicial = self.buscar_espacio_vacio(clusters_necesarios)
            
            if cluster_inicial is None:
                print("Error: no hay espacio contiguo suficiente")
                return False
            
            if clusters_necesarios > 0:
                offset_datos = cluster_inicial * TAM_CLUSTER
                tamano_reservado = clusters_necesarios * TAM_CLUSTER
                datos_a_escribir = contenido.ljust(tamano_reservado, b"\x00")
                
                self.disco.escribir_bytes(offset_datos, datos_a_escribir)
            
            fecha_actual = datetime.now().strftime("%Y%m%d%H%M%S")
            if fecha_creacion is None:
                fecha_creacion = fecha_actual
            
            entrada_bytes = EntradaDirectorio.bytes_archivo(
                nombre_archivo,
                tamano,
                cluster_inicial,
                fecha_creacion,
                fecha_actual
            )
            
            offset_directorio = CLUSTER_INICIO_DIRECTORIO * TAM_CLUSTER
            offset_entrada = offset_directorio + (indice_entrada * TAM_ENTRADA_DIRECTORIO)
            
            self.disco.escribir_bytes(offset_entrada, entrada_bytes)
            
            self.sincronizacion.notificar("Insercion realizada exitosamente")
            return True
    
    """
    reemplza un archivo que ya existe en FiUnamFS con un nuevo contenido en bytes
    """
    def reemplazar_archivo_desde_bytes(self, nombre_archivo, contenido):
        with self.sincronizacion.bloqueo_disco:
            self.sincronizacion.notificar(f"Remplazando archivo '{nombre_archivo}'"
                                          " en FiUnamFS")
            
            entrada = self.buscar_archivo(nombre_archivo)
            
            if entrada is None:
                print(f"Error: el archivo '{nombre_archivo}' no existe")
                return False
            
            fecha_creacion = entrada.fecha_creacion
            
            offset_directorio = CLUSTER_INICIO_DIRECTORIO * TAM_CLUSTER
            offset_entrada = offset_directorio + (entrada.indice * TAM_ENTRADA_DIRECTORIO)
            
            datos_vacios = EntradaDirectorio.bytes_entrada_vacia()
            self.disco.escribir_bytes(offset_entrada, datos_vacios)
            
            if not self.insertar_archivo_desde_bytes(nombre_archivo, contenido, 
                                                     fecha_creacion):
                entrada_original = EntradaDirectorio.bytes_archivo(
                    nombre_archivo,
                    entrada.tamano,
                    entrada.cluster_inicial,
                    entrada.fecha_creacion,
                    entrada.fecha_modificacion
                )
                
                self.disco.escribir_bytes(offset_entrada, entrada_original)
                print(f"Error: no se pudo reemplazar el archivo '{nombre_archivo}'")
                return False
            
            self.sincronizacion.notificar(f"El archivo '{nombre_archivo}'"
                                          " fue reemplazado")
            
            return True
