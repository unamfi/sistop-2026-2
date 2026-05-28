"""
Proyecto (Micro) sistema de archivos multihiloss
Autores: 
    - Gonzalez Falcon Luis Adrían
    - Lopez Morales Fernando Samuel
ENtrega 2026-05-21
"""
import struct
import os
import math
import datetime

class FiUnamFS:
    
    # #TODO Leer del superbloque!!
    # Constantes importantes de los requerimientos
    #TAMANO_CLUSTER = 2048
    #TAMANO_ENTRADA_DIR = 64
    #CLUSTERS_DIRECTORIO = 8
    # Ver documentación para enteder de donde salen los valores
    __TAMANO_ENTRADA_DIR = 64
    #Formato como printf en C, o el formateo en print(f'')
    FORMATO_ENTRADA = "<c15sII6x14s6x14s"
    # Ver documentación para entender el valor y razon de cada símbolo

    def __init__(self, ruta_imagen):
        # prueba primer imagen
        self.ruta_imagen = ruta_imagen
        self.archivo = None
        self.lock = None

        # Variables privadas (se llenarán al conectar)
        self.__NOMBRE_DISCO = None
        self.__VERSION_SISTEMA_ARCHIVOS = None
        self.__ETIQUETA_DISCO = None
        self.__TAMANO_CLUSTER = None
        self.__CLUSTERS_DIRECTORIO = None
        self.__CLUSTERS_UNIDAD = None
        

    def _obtener_mapa_clusters(self):
        """
        Recorre el directorio y crea una lista booleana representando los 720 clusters para ver cuales están disponibles
        true = ocupado, false = libre
        Devuelve adeḿas la posición (en bytes) de la primera entrada libre en el directorio
        """

        # Inicializamos los 720 clusters como libres (False)
        mapa_clusters = [False] * self.__CLUSTERS_UNIDAD
        
        # El Superbloque (Cluster 0) y el Directorio (1 al 8) se marcan ocupados
        clusters_superbloque = 1 + self.__CLUSTERS_DIRECTORIO
        for i in range(clusters_superbloque):
            mapa_clusters[i] = True
            
        inicio_directorio = self.__TAMANO_CLUSTER * 1
        total_entradas = (self.__CLUSTERS_DIRECTORIO * self.__TAMANO_CLUSTER) // self.__TAMANO_ENTRADA_DIR
        
        nombres_existentes = []
        
        posicion_entrada_libre = -1
        self.archivo.seek(inicio_directorio)
        
        for i in range(total_entradas):
            posicion_actual = inicio_directorio + (i * self.__TAMANO_ENTRADA_DIR)
            self.archivo.seek(posicion_actual)
            entrada_bytes = self.archivo.read(self.__TAMANO_ENTRADA_DIR)
            
            if len(entrada_bytes) < self.__TAMANO_ENTRADA_DIR:
                break
                
            datos = struct.unpack(self.FORMATO_ENTRADA, entrada_bytes)
            #print(f"Queeee: {datos}")
            tipo_archivo = datos[0].decode('ascii', errors='ignore')
            
            if tipo_archivo == '-':
                nombre = datos[1].decode('ascii', errors='ignore').strip('\x00 ').replace('#', '')
                nombres_existentes.append(nombre)
                
                #Se calculan cuantos clusters ocupa para marcarlos
                tamano = datos[2]
                cluster_inicial = datos[3]
                clusters_ocupados = math.ceil(tamano / self.__TAMANO_CLUSTER)  #debe ser mayor para caber sin problemas
                
                for c in range(cluster_inicial, cluster_inicial + clusters_ocupados):
                    if c < self.__CLUSTERS_UNIDAD:
                        mapa_clusters[c] = True
                        
            elif tipo_archivo == '/' and posicion_entrada_libre == -1:
                # Guardamos la ubicación de la primera entrada vacía que veamos
                posicion_entrada_libre = posicion_actual
                
        return mapa_clusters, posicion_entrada_libre, nombres_existentes

    def _buscar_espacio_contiguo(self, mapa_clusters, clusters_necesarios):
        
        #Busca secuencialmente en el mapa de clusters un espacio con suficientes clusters libres consecutivos. Retorna el cluster inicial o -1 si no hay espacio
        
        contador_consecutivos = 0
        cluster_inicio_candidato = -1
        
        # Se empieza a buscar desde el CLuster 9 (Zona de datos)
        for i in range(9, len(mapa_clusters)):
            if not mapa_clusters[i]: # Si está disponible
                if contador_consecutivos == 0:
                    cluster_inicio_candidato = i
                contador_consecutivos += 1
                
                if contador_consecutivos == clusters_necesarios:
                    return cluster_inicio_candidato
            else:
                # No se cumple el número de clusters consecutivos, por lo que continuamos a la siguiente iteración
                contador_consecutivos = 0
                cluster_inicio_candidato = -1
                
        return -1 # No se encontró espacio suficiente

    # por ahora hace la conexión a la imagen (#CAMBIAR)
    def conectar(self):

       # Verifica si el archivo existe en la ruta indicada
        if not os.path.exists(self.ruta_imagen):
            raise FileNotFoundError(f"El archivo de imagen '{self.ruta_imagen}' no existe en esta ruta.")
        
        self.archivo = open(self.ruta_imagen, 'r+b')
        #print(f"[+] Conectado exitosamente a la imagen: {self.ruta_imagen}")
        self.validar_superbloque()


    def validar_superbloque(self):

        if not self.archivo:
            raise ConnectionError("No hay un archivo abierto") # se teine que llamar primero a conectar()
            
        self.archivo.seek(0)
        superbloque = self.archivo.read(64)
        
        # Extracción de bytes
        
        identificacion = superbloque[5:14].strip(b'\x00')
        version = superbloque[14:19].strip(b'\x00')
        etiqueta = superbloque[20:36].strip(b'\x00')
    
        #print(f"Verificando info del SUperbloque: Iden: {identificacion}, v.: {version}")
        
        if identificacion != b'FiUnamFS':
            self.desconectar()
            raise ValueError(f"Error: {identificacion} no es el disco correcto :(")
            
        # Se aceptara '24-2' (la que tiene el profe) o '26-2' (como debe ser)
        if version not in (b'24-2', b'26-2'):
            self.desconectar()
            raise ValueError(f"Error: Versión {version} no soportada :(")
        
        self.__NOMBRE_DISCO = identificacion
        self.__VERSION_SISTEMA_ARCHIVOS = version
        self.__ETIQUETA_DISCO = etiqueta
        self.__TAMANO_CLUSTER = struct.unpack("<I", superbloque[40:44])[0]
        self.__CLUSTERS_DIRECTORIO = struct.unpack("<I", superbloque[50:54])[0]
        self.__CLUSTERS_UNIDAD = struct.unpack("<I", superbloque[60:64])[0]
        #print("OK")
        return True

    
    # Listar los contenidos del directorio

    def listar_directorio(self):
        # IMPLEMENTAR DIRECTAMENTE EN FUSE

        if not self.archivo:
            raise ConnectionError("No hay un archivo abierto")

        #print("\n------- Contenido:")
        #print(f"{'Nombre':<15} | {'Tamaño (Bytes)':<14} | {'Cluster Inicial':<15} | {'Fecha Creación'}")
        #print("-----------------------------------------------------")

        #El directorio empieza en el byte 2048: CLuster 1
        inicio_directorio = self.__TAMANO_CLUSTER * 1
        self.archivo.seek(inicio_directorio)

        # Calcula el total de entradas posibles (256)
        total_entradas = (self.__CLUSTERS_DIRECTORIO * self.__TAMANO_CLUSTER) // self.__TAMANO_ENTRADA_DIR
        archivos_encontrados = 0

        archivos_encontrados = {}

        for _ in range(total_entradas):
            entrada_bytes = self.archivo.read(self.__TAMANO_ENTRADA_DIR)
            
            #Por seguridad, si leemos menos de 64 bytes salimos del bucle
            if len(entrada_bytes) < self.__TAMANO_ENTRADA_DIR:
                break

            #USANDO FORMATO DECLARADO EN CONSTANTES IMPORTANTES
            datos = struct.unpack(self.FORMATO_ENTRADA, entrada_bytes)
            
            #Extraemos primer byte: tipo de archivo
            tipo_archivo = datos[0].decode('ascii', errors='ignore')

            # '-': con contenido, '/': vacío
            if tipo_archivo == '-':
                nombre = datos[1].decode('ascii', errors='ignore').strip('\x00 ').replace('#', '')
                
                # Conversión de formato FiUnamFS a UNIX Epoch Timestamp
                try:
                    str_creacion = datos[4].decode('ascii', errors='ignore').strip('\x00 ')
                    dt_creacion = datetime.datetime.strptime(str_creacion, '%Y%m%d%H%M%S')
                    
                    epoch_creacion = int(dt_creacion.timestamp())
                except ValueError:
                    epoch_creacion = 0
                    
                try:
                    str_modif = datos[5].decode('ascii', errors='ignore').strip('\x00 ')
                    dt_modif = datetime.datetime.strptime(str_modif, '%Y%m%d%H%M%S')
                    epoch_modif = int(dt_modif.timestamp())



                except ValueError:
                    epoch_modif = 0

                archivos_encontrados[nombre] = {
                    'tamano': datos[2],
                    'cluster': datos[3],
                    'c_time': epoch_creacion,
                    'm_time': epoch_modif
                }

        return archivos_encontrados



    def copiar_al_exterior(self, nombre_fiunamfs, ruta_destino_local):
        # Copia un archivo desde FiUnamFS hacia local
        if not self.archivo:
            raise ConnectionError("No hay un archivo abierto")

        # Buscar el archivo en el directorio
        inicio_directorio = self.__TAMANO_CLUSTER * 1
        self.archivo.seek(inicio_directorio)
        total_entradas = (self.__CLUSTERS_DIRECTORIO * self.__TAMANO_CLUSTER) // self.__TAMANO_ENTRADA_DIR
        
        encontrado = False
        tamano_archivo = 0
        cluster_inicial = 0

        for _ in range(total_entradas):
            entrada_bytes = self.archivo.read(self.__TAMANO_ENTRADA_DIR)
            if len(entrada_bytes) < self.__TAMANO_ENTRADA_DIR:
                break

            datos = struct.unpack(self.FORMATO_ENTRADA, entrada_bytes)
            tipo_archivo = datos[0].decode('ascii', errors='ignore')

            if tipo_archivo == '-':
                nombre_actual = datos[1].decode('ascii', errors='ignore').strip('\x00 ').replace('#', '')
                
                # Linealmente recorremos, lo encontramos y rompemos bucle guardando datos
                if nombre_actual == nombre_fiunamfs:
                    tamano_archivo = datos[2]
                    cluster_inicial = datos[3]
                    encontrado = True
                    break

        if not encontrado:
            #print(f"Error: El archivo '{nombre_fiunamfs}' no existe dentro de FiUnamFS")
            return False

        # Extrae los datos y los escribirlos en local
        byte_inicio = cluster_inicial * self.__TAMANO_CLUSTER
        self.archivo.seek(byte_inicio)
        
        # Lee los bytes exactos que mide el archivo
        datos_archivo = self.archivo.read(tamano_archivo)

        # Escribe los bytes en un nuevo archivo en local
        try:
            with open(ruta_destino_local, 'wb') as f_destino:
                f_destino.write(datos_archivo)
            #print(f"Archivo: '{nombre_fiunamfs}' copiado con exito como '{ruta_destino_local}'")
            return True
        except IOError as e:
            #print(f"Error al guardar el archivo en local: {e}")
            return False


    def leer_bytes_archivo(self, nombre_fiunamfs, size, offset):

        #Lee una porción del rchivo desde la imagen, actúa en base a la petición "read" de FUSE

        if not self.archivo:
            raise ConnectionError("No hay un archivo abierto")

        archivos_existentes = self.listar_directorio()
        
        if nombre_fiunamfs not in archivos_existentes:
            raise FileNotFoundError(f"El archivo '{nombre_fiunamfs}' no existe")

        meta = archivos_existentes[nombre_fiunamfs]
        tamano_real = meta['tamano']
        cluster_inicial = meta['cluster']

        # no debe dejar más allá del EOF
        if offset >= tamano_real:
            return b''

        if offset + size > tamano_real:
            size = tamano_real - offset
        posicion_fisica = (cluster_inicial * self.__TAMANO_CLUSTER) + offset

        self.archivo.seek(posicion_fisica)
        datos_crudos = self.archivo.read(size)

        return datos_crudos

    def copiar_al_interior(self, ruta_origen_local, nombre_fiunamfs):
        # Copiar un archivo de local a FIUnamFS

        if not self.archivo:
            raise ConnectionError("No hay un archivo abierto.")

        if not os.path.exists(ruta_origen_local):
            #print(f"Error: El archivo local '{ruta_origen_local}' no existe")
            return False

        # Medir el archivo y calcular lo que se necesita
        tamano_archivo = os.path.getsize(ruta_origen_local)
        clusters_necesarios = math.ceil(tamano_archivo / self.__TAMANO_CLUSTER) # Es importante ceil() para que de 'un cluster más' si es que no es exacto
        
        # Obtener mapa de la memoria
        mapa_clusters, posicion_entrada_libre, nombres_existentes = self._obtener_mapa_clusters()
        if nombre_fiunamfs in nombres_existentes:
            #print(f"Error. Ya existe un archivo llamado {nombre_fiunamfs}")
            return False
        if posicion_entrada_libre == -1:
            #print("Error: El directorio está lleno\n-- No caben más archivos")
            return False
            
        # Buscar espacio contiguo
        cluster_inicial = self._buscar_espacio_contiguo(mapa_clusters, clusters_necesarios)
        
        if cluster_inicial == -1 or (cluster_inicial + clusters_necesarios > self.__CLUSTERS_UNIDAD):
            #print("Error: No hay suficiente espacio contiguo en el disco")
            return False
            
        # Escribir los datos en la zona de datos
        byte_inicio_datos = cluster_inicial * self.__TAMANO_CLUSTER
        try:
            with open(ruta_origen_local, 'rb') as f_origen:
                datos_a_escribir = f_origen.read()
                
            self.archivo.seek(byte_inicio_datos)
            self.archivo.write(datos_a_escribir)
        except IOError as e:
            #print(f"Error al leer el archivo local: {e}")
            return False

        # Actualizar entrada en el directorio
        fecha_actual = datetime.datetime.now().strftime('%Y%m%d%H%M%S').encode('ascii')
        nombre_bytes = nombre_fiunamfs.encode('ascii')
        
        # struct.pack llena con nulos los espacios que sobren en el nombre
        nueva_entrada = struct.pack(
            self.FORMATO_ENTRADA,
            b'-',
            nombre_bytes,
            tamano_archivo,
            cluster_inicial,
            fecha_actual,
            fecha_actual
        )

        self.archivo.seek(posicion_entrada_libre)
        self.archivo.write(nueva_entrada)
        
        #print(f"Archivo '{ruta_origen_local}' insertado como '{nombre_fiunamfs}' exitosamente")
        #print(f"    -> Ocupa {clusters_necesarios} clusters, empezando en el cluster {cluster_inicial}")
        return True

    def escribir_desde_buffer(self, nombre_fiunamfs, datos_bytes):

        #Guarda bloque de bytes continuos, diseñado para trabajar con FUSE y release.
        if not self.archivo:
            raise ConnectionError("No hay un archivo abierto.")

        tamano_archivo = len(datos_bytes)
        clusters_necesarios = math.ceil(tamano_archivo / self.__TAMANO_CLUSTER)

        if clusters_necesarios > self.__CLUSTERS_UNIDAD:
            raise ValueError("El archivo excede la capacidad total del sistema.")

        mapa_clusters, posicion_entrada_libre, nombres_existentes = self._obtener_mapa_clusters()
        
        # Si el archivo existe, se sobreescribe
        if nombre_fiunamfs in nombres_existentes:
            self.eliminar_archivo(nombre_fiunamfs)
            #Se recalcula el mapa aprovechar el espacio
            mapa_clusters, posicion_entrada_libre, nombres_existentes = self._obtener_mapa_clusters()

        if posicion_entrada_libre == -1:
            raise IOError("El directorio está lleno. No caben más archivos.")
            
        cluster_inicial = self._buscar_espacio_contiguo(mapa_clusters, clusters_necesarios)
        
        if cluster_inicial == -1 or (cluster_inicial + clusters_necesarios > self.__CLUSTERS_UNIDAD):
            raise IOError("No hay suficiente espacio contiguo (Fragmentación).")
            
        # Escritura de los datos
        byte_inicio_datos = cluster_inicial * self.__TAMANO_CLUSTER
        self.archivo.seek(byte_inicio_datos)
        self.archivo.write(datos_bytes)

        # Creación de la entrada en el directorio
        fecha_actual = datetime.datetime.now().strftime('%Y%m%d%H%M%S').encode('ascii')
        nombre_bytes = nombre_fiunamfs.encode('ascii')
        
        nueva_entrada = struct.pack(
            self.FORMATO_ENTRADA,
            b'-',                  
            nombre_bytes,          
            tamano_archivo,        
            cluster_inicial,       
            fecha_actual,          
            fecha_actual           
        )

        self.archivo.seek(posicion_entrada_libre)
        self.archivo.write(nueva_entrada)
        
        return True

    

        # Eliminar archivo de la imagen
    def eliminar_archivo(self, nombre_fiunamfs):
        if not self.archivo:
            raise ConnectionError("No hay una archivo abierto")

        inicio_directorio = self.__TAMANO_CLUSTER * 1
        total_entradas = (self.__CLUSTERS_DIRECTORIO * self.__TAMANO_CLUSTER) // self.__TAMANO_ENTRADA_DIR
        
        for i in range(total_entradas):
            posicion_entrada = inicio_directorio + (i * self.__TAMANO_ENTRADA_DIR)
            self.archivo.seek(posicion_entrada)
            entrada_bytes = self.archivo.read(self.__TAMANO_ENTRADA_DIR)
            
            if len(entrada_bytes) < self.__TAMANO_ENTRADA_DIR:
                break

            datos = struct.unpack(self.FORMATO_ENTRADA, entrada_bytes)
            tipo_archivo = datos[0].decode('ascii', errors='ignore')

            if tipo_archivo == '-':
                nombre_actual = datos[1].decode('ascii', errors='ignore').strip('\x00 ').replace('#', '')
                
                if nombre_actual == nombre_fiunamfs:
                    # Ubicar el cursor en la posicion del archivo
                    self.archivo.seek(posicion_entrada)
                    
                    #Se sobreescriben los bytes
                    nuevo_tipo = b'/'
                    nuevo_nombre = b'###############'
                    
                    #Se escribe en el disco
                    self.archivo.write(nuevo_tipo + nuevo_nombre)
                    
                    #print(f"Eliminando archivo {nombre_fiunamfs}")
                    return True

        raise FileNotFoundError(f"El archivo '{nombre_fiunamfs}' no existe")
        

    def desconectar(self):
        if self.archivo and not self.archivo.closed:
            self.archivo.close()
            #print("Archivo de imagen cerrado")
