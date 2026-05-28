import os
import struct
import threading
import math
from datetime import datetime
##En este archivo se declaran las clases prinicipales para ekl funcionamiento del programa. 

##Autores: Bello Sánchez Santiago Arath y López Romero David Baruc 
class File:
    """
    Clase que representa un archivo individual dentro del sistema FiUnamFS.
    Almacena los metadatos extraídos de la entrada del directorio y permite acceder a su contenido.
    """
    def __init__(self, name: str, size: int, initial_cluster: int, creation_date: str, update_date: str, dir_path: str ) -> None:
        self.tam_cluster = 2048  # Tamaño de clúster estático por defecto
        self.name = name
        self.size= size
        self.initial_cluster = initial_cluster
        self.creation_date = self._fecha_formato(creation_date) 
        self.update_date = self._fecha_formato(update_date) 
        self.dir_path = dir_path  # Ruta a la imagen del sistema de archivos (.img)

    def _fecha_formato(self, date:str) -> str:
        """
        Toma la cadena de fecha cruda (AAAAMMDDHHMMSS) y la formatea
        a una versión más legible (AAAA-MM-DD HH:MM:SS).
        """
        year = date[:4]
        month = date[4:6]
        day = date[6:8]
        hour = date[8:10]
        minute = date[10:12]
        second = date[12:14]

        new_date = f"{year}-{month}-{day} {hour}:{minute}:{second}"
        return new_date
    
    def obtener_contenido(self) -> bytes:
        
        if self.size < self.tam_cluster * 4:
            posicion_inicial = self.initial_cluster * self.tam_cluster
            with open(self.dir_path, 'rb') as file:
                file.seek(posicion_inicial)
                return file.read(self.size) 

 
        # División lógica del archivo en fragmentos (chunks) para aislar las operaciones 
        # de entrada/salida (I/O). Permite paralelizar la lectura bloqueante en disco 
        # utilizando múltiples hilos, los cuales escriben concurrentemente sobre un 
        # arreglo de bytes pre-asignado en memoria sin solaparse.
        num_hilos = 4
        chunk_size = math.ceil(self.size / num_hilos)
        resultado = bytearray(self.size)

        def leer_chunk(inicio_bytes: int, size_a_leer: int):
            pos_fisica = (self.initial_cluster * self.tam_cluster) + inicio_bytes
            with open(self.dir_path, 'rb') as file:
                file.seek(pos_fisica)
                datos = file.read(size_a_leer)
      
                resultado[inicio_bytes : inicio_bytes + size_a_leer] = datos

        hilos = []
        for i in range(num_hilos):
            inicio_bytes = i * chunk_size
            if inicio_bytes >= self.size:
                break 
            
       
            size_a_leer = min(chunk_size, self.size - inicio_bytes)
            
            hilo = threading.Thread(target=leer_chunk, args=(inicio_bytes, size_a_leer))
            hilos.append(hilo)
            hilo.start()
            
        for hilo in hilos:
            hilo.join()
            
        return bytes(resultado)

    def mostrar_informacion(self) -> None:
        """Imprime los metadatos del archivo en consola."""
        print("=== INFORMACIÓN DEL ARCHIVO ===")
        print(f"Nombre:           {self.name}")
        print(f"Tamaño:           {self.size} bytes")
        print(f"Cluster Inicial:  {self.initial_cluster}")
        print(f"Fecha Creación:   {self.creation_date}")
        print(f"Fecha Modificación: {self.update_date}")
        print(f"Ruta Directorio:  {self.dir_path}")
        print("===============================")
    
class FiUnamFS:
    """
    Clase principal que gestiona el sistema de archivos FiUnamFS.
    Se encarga de montar la imagen, validar su estructura y mapear los archivos internos.
    """
    def __init__(self, path: str):
        self.path = path
        self.etiqueta = ""
        self.tam_cluster = 0
        self.clusters_dir = 0
        self.clusters_unity = 0
        self.archivos_validos = {} ##Diccionario con el nombre de los archivos existentes y su cluster inicial.
        self.lista_archivos = [] ##Lista con loas archivos existentes en el sistema
        self.mapDirectorio = {} ## Clave: Nombre del archivo , Valor: Ubicacion exacta(En que byte se encuentra la entrada del archivo en cuestión)
       
        # Al instanciar, se intenta montar (validar) el sistema. Si falla, lanza excepción.
        if not self.upload():
            raise Exception("No se pudo montar el sistema de archivos: Falló la validación.")
        

    def mapear_directorio(self):
        """
        Escanea la sección del directorio dentro de la imagen del sistema de archivos,
        leyendo entradas de 64 bytes para extraer los archivos válidos y crear objetos File.
        """
        self.archivos_validos = {} 
        self.lista_archivos = [] 
        self.mapDirectorio = {}
        offset_dir = 1 * self.tam_cluster
        
        total_entradas = self.clusters_dir * (self.tam_cluster // 64)
        print("\n--- ESCANEANDO DIRECTORIO (CON HILOS) ---")
        
        # Exclusión mutua (Mutex) requerida para evitar condiciones de carrera (Race Conditions).
        # Garantiza que múltiples hilos no corrompan los diccionarios compartidos al insertar 
        # metadatos simultáneamente durante el mapeo paralelo.
        lock = threading.Lock()
        
        def escanear_seccion(inicio: int, fin: int):
            with open(self.path, 'rb') as file:
                for index_entrada in range(inicio, fin):
                    file.seek(offset_dir + (index_entrada * 64))
                    entrada = file.read(64)
                    if not entrada: break
                    
                    if entrada[0] == 45: # Código ASCII para '-'
                        nombre_bytes = entrada[1:16].split(b'\x00')[0] 
                        nombre = nombre_bytes.decode('ascii').strip('#').strip()
                        
                        size = struct.unpack('<I', entrada[16:20])[0]
                        cluster_ini = struct.unpack('<I', entrada[20:24])[0]
                        c_date = entrada[30:44].decode('ascii').strip('\x00').strip()
                        u_date = entrada[50:64].decode('ascii').strip('\x00').strip()
                        
                        nuevo_archivo = File(
                            name=nombre, 
                            size=size, 
                            initial_cluster=cluster_ini, 
                            creation_date=c_date, 
                            update_date=u_date, 
                            dir_path=self.path
                        )
                        
                        with lock:
                            self.mapDirectorio[nombre] = offset_dir + (index_entrada * 64)
                            self.archivos_validos[nombre] = cluster_ini
                            self.lista_archivos.append(nuevo_archivo)
                            print(f"Archivo: {nombre:<15} | Cluster Inicial: {cluster_ini}")

        num_hilos = 4
        entradas_por_hilo = total_entradas // num_hilos
        hilos = []

        for i in range(num_hilos):
            inicio = i * entradas_por_hilo
            fin = total_entradas if i == num_hilos - 1 else (i + 1) * entradas_por_hilo
            
            hilo = threading.Thread(target=escanear_seccion, args=(inicio, fin))
            hilos.append(hilo)
            hilo.start()

        for hilo in hilos:
            hilo.join()

        print(f"-----------------------------\nDirectorio mapeado: {len(self.archivos_validos)} archivos encontrados.\n")


    def copia_TO_MyPC(self, path:str , file: File ) -> bool: # El path debe de ser la dirección hacia donde se busca insertar el archivo.
        """
        Extrae un archivo del sistema FiUnamFS y lo guarda en el sistema de archivos local del usuario.
        """
        if not os.path.exists(path + f'/{file.name}'):
            content = file.obtener_contenido() 
            try:
                with open(path + f'/{file.name}', 'wb') as new_file:
                    new_file.write(content)
                print(f"¡Éxito! '{file.name}' copiado a tu PC.")
                return True
            except Exception as e:
                print(f"Error al guardar en PC: {e}")
                return False
        print(f"Error: El archivo '{file.name}' ya existe en el destino.")
        return False
    
    def _buscar_espacio_libre(self, file_size: int) -> int:
        """
        Implementa el algoritmo de asignación contigua para el sistema de archivos.
        
        Calcula la cantidad de clústeres necesarios para el archivo y escanea los rangos 
        de clústeres actualmente ocupados (ordenados ascendentemente). Busca el primer hueco 
        fragmentado entre archivos existentes que sea lo suficientemente grande para alojar 
        el nuevo archivo. Si no hay huecos, verifica el espacio libre al final del volumen.
        Retorna el clúster inicial disponible o -1 si hay desbordamiento de disco.
        """
        clusters_necesarios = math.ceil(file_size / self.tam_cluster)
        
        rangos_ocupados = []
        for archivo in self.lista_archivos:
            c_ini = archivo.initial_cluster
            c_fin = c_ini + math.ceil(archivo.size / self.tam_cluster)
            rangos_ocupados.append((c_ini, c_fin))
            
        rangos_ocupados.sort()
        cluster_actual = 1 + self.clusters_dir
        
        for c_ini, c_fin in rangos_ocupados:
            if cluster_actual + clusters_necesarios <= c_ini:
                return cluster_actual 
            cluster_actual = max(cluster_actual, c_fin)
            
        if cluster_actual + clusters_necesarios <= self.clusters_unity:
            return cluster_actual
            
        return -1 

    def _buscar_entrada_directorio_libre(self) -> int:
        """
        Escanea físicamente el área del directorio (a partir del clúster 1) en bloques de 64 bytes 
        buscando la primera entrada de metadatos disponible.
        
        Una entrada se considera libre si está completamente vacía (lectura nula) o si su primer 
        byte indica un registro eliminado lógicamente (distinto del código ASCII 45 '-').
        Retorna el offset exacto en bytes (dirección física) para sobreescribir la nueva entrada.
        """
        offset_dir = 1 * self.tam_cluster
        total_entradas = self.clusters_dir * (self.tam_cluster // 64)
        
        with open(self.path, 'rb') as file:
            file.seek(offset_dir)
            for i in range(total_entradas):
                entrada = file.read(64)
                if not entrada or entrada[0] != 45: 
                    return offset_dir + (i * 64)
                    
        return -1 

    def copia_TO_FiUnamFS(self, ruta_local: str) -> bool:
        """
        Orquesta la inserción de un archivo externo hacia el volumen FiUnamFS.
        
        Coordina las estructuras lógicas solicitando espacio contiguo (_buscar_espacio_libre) 
        y una ranura en el directorio (_buscar_entrada_directorio_libre). Una vez asegurado 
        el espacio, inyecta la carga útil binaria en los clústeres asignados y empaqueta los 
        metadatos del archivo (nombre ajustado a 15 bytes, tamaños y fechas en timestamp) 
        usando la estructura de 64 bytes en little-endian requerida por el estándar.
        """
        if not os.path.exists(ruta_local):
            print(f"Error: El archivo local '{ruta_local}' no existe.")
            return False
            
        nombre_archivo = os.path.basename(ruta_local)
        if len(nombre_archivo) > 15:
            print("Error: El nombre del archivo excede los 15 caracteres permitidos.")
            return False

        tam_archivo = os.path.getsize(ruta_local)
        
        cluster_inicial = self._buscar_espacio_libre(tam_archivo)
        if cluster_inicial == -1:
            print("Error: No hay espacio suficiente en FiUnamFS.")
            return False
            
        offset_entrada = self._buscar_entrada_directorio_libre()
        if offset_entrada == -1:
            print("Error: No hay más espacio en el directorio.")
            return False
            
        try:
            with open(ruta_local, 'rb') as f_local:
                datos = f_local.read()
                
            with open(self.path, 'r+b') as fs:
                fs.seek(cluster_inicial * self.tam_cluster)
                fs.write(datos)
                
                nombre_bytes = nombre_archivo.ljust(15).encode('ascii')
                fecha_str = datetime.now().strftime("%Y%m%d%H%M%S").encode('ascii')
                
                entrada_directorio = bytearray(64)
                entrada_directorio[0:1] = b'-'                             
                entrada_directorio[1:16] = nombre_bytes                    
                entrada_directorio[16:20] = struct.pack('<I', tam_archivo) 
                entrada_directorio[20:24] = struct.pack('<I', cluster_inicial) 
                entrada_directorio[30:44] = fecha_str                      
                entrada_directorio[50:64] = fecha_str                      
                
                fs.seek(offset_entrada)
                fs.write(entrada_directorio)
                
            print(f"\n¡Éxito! '{nombre_archivo}' copiado a FiUnamFS correctamente.")
            self.mapear_directorio() 
            return True
            
        except Exception as e:
            print(f"Error al escribir en FiUnamFS: {e}")
            return False

    def upload(self) -> bool:
        """
        Valida la integridad del superbloque (clúster 0) asegurando que la imagen montada 
        corresponde a un volumen FiUnamFS válido. 
        
        Realiza una verificación en tres capas:
        1. Firma de bytes nulos iniciales.
        2. Nombre del sistema de archivos ('FiUnamFS') codificado en ASCII.
        3. Compatibilidad de versión ('24-2').
        Si la validación es exitosa, extrae la geometría del disco (tamaño de clúster, 
        clústeres de directorio y totales) desempaquetando los enteros en formato little-endian (<I).
        """
        try:
            with open(self.path, 'rb') as file:
                file.seek(0)
                if file.read(4) != b'\x00\x00\x00\x00':
                    print('Archivo no válido. CAPA 1')
                    return False
                print('Capa 1 EXITOSA')

                file.seek(5)
                f13 = file.read(8)
                if f13.decode('ascii') != 'FiUnamFS':
                    print('Sistema no válido. CAPA 2')
                    return False
                print("Capa 2 EXITOSA_Sistema válido")

                file.seek(14)
                f18 = file.read(4)
                version_leida = f18.decode('ascii')
                if version_leida != '24-2': 
                    print(f'Version incompatible ({version_leida}). CAPA 3')
                    return False
                print("Capa 3 EXITOSA_Version compatible")

                file.seek(20)
                self.etiqueta = file.read(15).decode('ascii').strip()

                file.seek(40)
                self.tam_cluster = struct.unpack('<I', file.read(4))[0]

                file.seek(50)
                self.clusters_dir = struct.unpack('<I', file.read(4))[0]

                file.seek(60)
                self.clusters_unity = struct.unpack('<I', file.read(4))[0]

                return True

        except FileNotFoundError:
            print(f"Error: El archivo {self.path} no existe.")
            return False
        except Exception as e:
            print(f"Error inesperado: {e}")
            return False
    
    def _eliminarArchivo(self, nameFile: str) -> bool:
        """
        Ejecuta un borrado lógico (soft-delete) sobre un archivo del sistema.
        
        Por eficiencia, el sistema no reescribe los clústeres de datos con ceros (borrado físico). 
        En su lugar, localiza la dirección física (offset) de la entrada del directorio y aplica 
        una máscara de invalidación (b'/' seguida de '#') sobre el nombre del archivo. 
        Finalmente, purga las referencias en las estructuras de datos dinámicas en memoria 
        para liberar el espacio contiguo para futuras inserciones.
        """
        if nameFile not in self.archivos_validos: 
            print("No existe archivo con nombre:", nameFile)
            return False 

        byte_inicio = self.mapDirectorio.get(nameFile)
        if byte_inicio is None:
            print("Error: El archivo está en la lista pero no se encontró su dirección física.")
            return False

        try:
            with open(self.path, 'rb+') as file:
                file.seek(byte_inicio)
                marca_borrado = b'/' + b'#' * 14  
                file.write(marca_borrado)
        
            # Limpieza en memoria
            del self.archivos_validos[nameFile]
            del self.mapDirectorio[nameFile]
            self.lista_archivos = [f for f in self.lista_archivos if f.name != nameFile]

            print(f"Archivo '{nameFile}' eliminado exitosamente.")
            return True

        except FileNotFoundError:
            print(f"Error: El archivo del sistema de archivos ({self.path}) no existe.")
            return False
        except Exception as e:
            print(f"Error inesperado al escribir en el disco: {e}")
            return False

    def __str__(self):
        return (f"--- FiUnamFS Info ---\n"
                f"Etiqueta: {self.etiqueta}\n"
                f"Tamaño Clúster: {self.tam_cluster} bytes\n"
                f"Clústers Directorio: {self.clusters_dir}\n"
                f"Clústers Totales: {self.clusters_unity}\n"
                f"---------------------")

"""
# ==========================================
# CASO DE PRUEBA
# ==========================================



if __name__ == "__main__":
    ruta_disco = '/Users/santiagobello/Downloads/fiunamfs.img'
    ruta_imagen_local = '/Users/santiagobello/Downloads/IMG_1757.jpg' 
    ruta_destino_local = '/Users/santiagobello/Downloads' 

    try:
        print("Montando el sistema de archivos...")
        disco = FiUnamFS(ruta_disco)
        print(disco)
        
        # ----------------------------------------------------------------------
        # REQUISITO 1 & 5: Listar los contenidos del directorio
        # (Opera con 4 hilos concurrentes que comunican su estado con un Lock)
        # ----------------------------------------------------------------------
        print("\n[PASO 1] Listar los contenidos del directorio...")
        disco.mapear_directorio() 
        
        # ----------------------------------------------------------------------
        # REQUISITO 2: Copiar uno de los archivos de dentro del FiUnamFS hacia tu sistema
        # ----------------------------------------------------------------------
        print("\n[PASO 2] Copiando un archivo desde FiUnamFS hacia la PC...")
        if disco.lista_archivos:
            # Tomamos el primer archivo disponible en el cluster para extraerlo
            archivo_prueba = disco.lista_archivos[0]
            print(f"Archivo seleccionado para descargar: {archivo_prueba.name}")
            disco.copia_TO_MyPC(ruta_destino_local, archivo_prueba)
        else:
            print("No se encontraron archivos en FiUnamFS para copiar al sistema.")
            
        # ----------------------------------------------------------------------
        # REQUISITO 3: Copiar un archivo de tu computadora hacia tu FiUnamFS
        # ----------------------------------------------------------------------
        print("\n[PASO 3] Copiando archivo de la computadora (IMG_1757.jpg) hacia FiUnamFS...")
        if os.path.exists(ruta_imagen_local):
            disco.copia_TO_FiUnamFS(ruta_imagen_local)
        else:
            print(f"Error: No se encontró el archivo local en la ruta: {ruta_imagen_local}")

        # ----------------------------------------------------------------------
        # REQUISITO 4: Eliminar un archivo del FiUnamFS (README.org)
        # ----------------------------------------------------------------------
        print("\n[PASO 4] Eliminando archivo del FiUnamFS...")
        archivo_a_borrar = "README.org"
        disco._eliminarArchivo(archivo_a_borrar)
        
        # ----------------------------------------------------------------------
        # VERIFICACIÓN FINAL
        # ----------------------------------------------------------------------
        print("\n--- VERIFICACIÓN DE ESTADO FINAL DEL DISCO ---")
        disco.mapear_directorio()

        print("Diccionario mapDirectorio actualizado:")
        for key, values in disco.mapDirectorio.items():
            print('llave:', key ,'| valor byte:', values)

    except Exception as e:
        print(f"Hubo un error general durante la ejecución de las pruebas: {e}")
        """