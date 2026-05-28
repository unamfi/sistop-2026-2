from datetime import datetime
from pathlib import Path
import struct # Libreria para trabajar con datos binarios, 
			  # permite convertir entre bytes y tipos de datos de Python.
from math import ceil


def directorio(data, infoSuperbloque):
	
	# Esta función tiene como objetivo la lectura y análisis del 
    # directorio de nuestro fiunamfs.img.
	
    # Args:
        # data: Contenido del archivo .img leído en bytes.
        # infoSuperbloque: Un diccionario con la información del superbloque,
        # que incluye el tamaño de los clusters y la ubicación del directorio raíz. 
	
    # Returns:
        # Una lista de archivos encontrados en el directorio, con su información relevante 
        # (nombre, tamaño, etc.).
		
	cluster_size = infoSuperbloque['cluster_size']
	num_clusters = infoSuperbloque['num_clusters']

	start = cluster_size # Como sabemos que el cluster 0 es el superbloque, 
						 # el directorio comienza en el cluster 1. 
	
	dir_size = num_clusters * cluster_size # Calculamos el tamaño total del directorio.

	end = start + (dir_size) # El directorio ocupa un número de clusters, 
												# por lo que calculamos el final sumando el tamaño 
												# total del directorio al inicio.
	
	infoDirectorio = data[start:end] # Obtenemos los bytes correspondientes al directorio.
	entry_size = 64 # Cada entrada del directorio ocupa 64 bytes.

	num_entries=dir_size//entry_size # Calculamos el número de entradas dividiendo 
									 # el tamaño total del directorio entre el tamaño 
									 # de cada entrada.

	files= [] # Lista para almacenar la información de los archivos ocupados encontrados en el directorio.

	for i in range(num_entries):
		entry_start = i * entry_size
		entry_data = infoDirectorio[entry_start:entry_start + entry_size] # Bytes de la entrada actual.
		file_type = chr(entry_data[0]) # El primer byte indica el tipo de archivo (-, /).
		if file_type=="-":
			files.append(entry_data) # Si el tipo de archivo es "-", lo consideramos un archivo regular y 
									 # lo agregamos a la lista de archivos.
	
	return files # Devolvemos la lista de archivos encontrados en el directorio.

def superbloque(data):
	# En la función superbloque leemos y parseamos el superbloque de nuestro fiunamfs.img
	# Recordemos que en el superbloque tenemos datos de identificacion del sistema 
	# de archivos, como el tamaño de los clusters, el número de clusters que mide el directorio, etc.

	# Args:
        # data: Contenido del archivo .img leído en bytes.
	
    # .hex() convierte los bytes a una representación hexadecimal, 
	# lo que facilita la lectura y comparación de los datos binarios.
	id_bytes = data[0:4].hex()	
	
	
    # Decodificamos los bytes 5-13 a texto usando ASCII, ignorando errores y eliminando 
	# los caracteres nulos al final.
	fileName = data[5:13].decode('ascii', errors='ignore').rstrip('\x00')
	
    # Versión del sistema de archivos, obtenida de los bytes 14-18, decodificada de manera 
    # similar al nombre del volumen.
	version = data[14:18].decode('ascii', errors='ignore').rstrip('\x00')


	# Nuevamente aplicamos una decodificación similar para obtener la versión del sistema de archivos.
	volumen = data[20:35].decode('ascii', errors='ignore').rstrip('\x00')
	

	# De los bytes 20-36 obtenemos el nombre del volumen, aplicando el mismo proceso.
	# "<" = Little-endian
    # "I" = Entero 4 bytes (ID)
	# Para obtener el tamaño del cluster, utilizamos struct.unpack con el formato '<I', 
	# que indica que queremos interpretar los bytes como un entero sin signo de 4 bytes en
	# formato little-endian. El resultado es una tupla, por lo que accedemos al primer elemento con [0].
	cluster_size = struct.unpack('<I', data[40:44])[0] 

    # De manera similar, obtenemos el número de clusters que mide el directorio
	# utilizando struct.unpack con el mismo formato.
	num_clusters = struct.unpack('<I', data[50:54])[0]
	

    # Nos indica el número total de clusters que tiene la unidad completa.
	clusters_unidad = struct.unpack('<I', data[60:64])[0]
	

	return {'id_bytes': id_bytes, 
		 	'fileName': fileName, 
			'version': version, 
			'volumen': volumen, 
			'cluster_size': cluster_size, 
			'num_clusters': num_clusters, 
			'clusters_unidad': clusters_unidad}


def imprimir_archivos(files):
		# La función imprimir archivos nos decodifica las entradas del directorio, 
		# brindandonos información sobre los archivos almacenados.

		# Args:
			# files: Lista de archivos encontrados en el directorio, con su información relevante.

		for entry_data in files:
			file_type = chr(entry_data[0]) # El primer byte indica el tipo de archivo (-, /).	
			file_name = entry_data[1:15].decode('ascii', errors='ignore').rstrip('\x00') # Bytes 1-15 para el nombre del archivo.
			# Bytes 16-20 para el tamaño del archivo.
			file_size = struct.unpack('<I', entry_data[16:20])[0] 

			# Bytes 20-24 para el primer cluster del archivo.
			first_cluster = struct.unpack('<I', entry_data[20:24])[0] 

			# Bytes 30-44 para la fecha de creación.
			creation_time = entry_data[30:44].decode('ascii', errors='ignore').rstrip('\x00')

			# Bytes 50-64 para la fecha de modificación.
			modification_time = entry_data[50:64].decode('ascii', errors='ignore').rstrip('\x00')
			print(f"Archivo: {file_name}")
			print(f"  Tipo: {file_type}")
			print(f"  Tamaño: {file_size} bytes")
			print(f"  Primer cluster: {first_cluster}")
			print(f"  Fecha de creación: {creation_time}")
			print(f"  Fecha de modificación: {modification_time}")

def clusters_ocupados(archivos):
    # Esta función nos devuelve los numeros de clusters ocupados para todos los archivos que encuentre.
    # Ejemplos: si algún archivo ocupa los clusters 9, 10 y 11, esta función nos regresa [9, 10, 11].

    # Args:
        # archivos: Lista de los archivos ocupados, con su información (tamaño, cluster inicial, etc.)

    ocupados = set()

    for archivo in archivos:
        start_cluster = struct.unpack('<I', archivo[20:24])[0] # Cluster inicial del archivo
        file_size = struct.unpack('<I', archivo[16:20])[0] # Tamaño del archivo en bytes

        # Un cluster mide 4 sectores de 512 bytes, es decir, 2048 bytes.
        cluster_size = 2048
        # Calculamos el número de clusters necesarios para almacenar el archivo, redondeando hacia arriba.
        clusters_necesarios = ceil(file_size / cluster_size)
        
        # Marcar todos los clusters ocupados por este archivo
        for i in range(clusters_necesarios):
            ocupados.add(start_cluster + i)

    return ocupados


def available_clusters(archivos, neededClusters, totalClusters):
    # Función que nos indica los clusters contiguos disponibles para almacenar un nuevo archivo.

    # Args:
        # archivos: Lista de los archivos existentes
        # neededClusters: Número de clusters necesarios para almacenar el nuevo archivo.
        # totalClusters: Número total de clusters disponibles en el sistema de archivos.
    
    # Returns:
        # Nos regresa el número del primer cluster disponible 

    # Recordemos que el cluster 0 es el superbloque, y los clusters 1-8
    # están ocupados por el directorio, por lo que el primer cluster disponible
    # para almacenar archivos es el cluster 9.
    start = 9

    ocupados = clusters_ocupados(archivos)

    for j in range(start, totalClusters):
        # Verificar si hay espacio desde start hasta start+clusters_necesarios
        ok = True
        for i in range(neededClusters):
            if (j + i) in ocupados or (j + i) >= totalClusters:
                ok = False
                break
        
        if ok:
            return j  # Encontramos espacio! Y retornamos el número del primer cluster disponible.
    
    return None  # No hay espacio suficiente


def find_directory_entry(data, superbloque_info):
    # Función dedicada a encontrar la primera entrada vacía en el directorio, para poder 
    # mapear un nuevo archivo.

    # Args:
        # data: Contenido del archivo .img leído en bytes.
        # superbloque_info: Diccionario con la información del superbloque, 
        # que incluye el tamaño de los clusters y la ubicación del directorio raíz.
    
    # Returns:
        # El número de la entrada vacía encontrada, o None si no hay entradas vacías D:

    cluster_size = superbloque_info['cluster_size']
    dir_clusters = superbloque_info['num_clusters']

    dir_start = cluster_size
    dir_size = dir_clusters * cluster_size
    dir_data = data[dir_start:dir_start + dir_size]
    entry_size = 64
    num_entries = dir_size // entry_size

    for i in range(num_entries):
        entry_start = i * entry_size
        entry_data = dir_data[entry_start:entry_start + entry_size]
        
        # Byte 0: Tipo de archivo
        file_type = chr(entry_data[0])
        
        # Si el tipo de archivo es '/', consideramos esta entrada como vacía.
        if file_type == '/':
            return i  # Retornamos el número de la entrada vacía encontrada.
        
    return None  # No hay entradas vacías disponibles.




def paste(img_path, archivo_local, nombre_destino=None):
    # Función principal para copiar un archivo desde el sistema de archivos local al sistema 
    # de archivos Fiunamfs.

    # Args:
        # img_path: Ruta al archivo .img de Fiunamfs.  
        # archivo_local: Ruta al archivo local que queremos copiar dentro de Fiunamfs.
        # nombre_destino: Nombre que queremos darle al archivo dentro de Fiunamfs. 
        # Si no se especifica, se usará el mismo nombre del archivo local.

    # Returns:
        # Un mensaje indicando el resultado de la operación (éxito o error).    
    
    # Primero validamos que el archivo local existe
    local_file = Path(archivo_local)
    if not local_file.exists():
        print(f"¡Error! El archivo local '{archivo_local}' no existe")
        return False
    
    # Leemos el contenido del archivo local
    with open(archivo_local, 'rb') as f:
        contenido_local = f.read()
    
    # Determinamos el nombre de destino
    if nombre_destino is None:
        nombre_destino = local_file.name
    
    img_file = Path(img_path)

    if not img_file.exists():
        print(f"ERROR! El archivo '{img_path}' no existe :()")
        return False

    with open(img_path, 'rb') as f:
        data = bytearray(f.read()) 
    
    superbloque_info = superbloque(data)

    if superbloque_info['fileName'] != 'FiUnamFS':
        print(f"ERROR! No es un sistema FiUnamFS válido")
        return False
    
    cluster_size = superbloque_info['cluster_size']
    total_clusters = superbloque_info['clusters_unidad']

    tamaño_archivo = len(contenido_local)

    # Calculamos el número de clusters necesarios para almacenar el nuevo archivo.
    clusters_necesarios = ceil(tamaño_archivo / cluster_size)
    print("\n============ Información para el pegado del archivo ===================")
    print(f"Clusters necesarios: {clusters_necesarios}")

    archivos = directorio(data, superbloque_info)
    
    entrada_libre = find_directory_entry(data, superbloque_info)

    if entrada_libre is None:   
        print("¡Error! No hay entradas libres en el directorio para mapear el nuevo archivo.")
        return False   
    
    print(f"Entrada libre encontrada: #{entrada_libre}")

    primer_cluster = available_clusters(archivos, clusters_necesarios, total_clusters)

    if primer_cluster is None:
        print(f"ERROR! No hay suficiente espacio contiguo en el sistema de archivos")
        print(f"Se necesitan {clusters_necesarios} clusters consecutivos")
        return False
    
    print(f"Clusters libres encontrados: {primer_cluster} a {primer_cluster + clusters_necesarios - 1}")
    print("=======================================================================\n")

    print(f"- Escribiendo datos en clusters...")
    posicion_datos = primer_cluster * cluster_size

    # Escribimos el contenido del archivo local en el área de datos del sistema de archivos,
    # comenzando desde el cluster disponible que encontramos.
    data[posicion_datos:posicion_datos + tamaño_archivo] = contenido_local

    print(f"   {tamaño_archivo} bytes escritos en posición {posicion_datos}")
    print(f"- Actualizando la entrada del directorio...")

    # Calculamos la posición de la entrada en el directorio

    dir_start = cluster_size
    entry_size = 64
    posicion_entrada = dir_start + (entrada_libre * entry_size)

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S")  # Ej: "20260517143000"

    # Construir la entrada del directorio (64 bytes)
    entrada = bytearray(64)

    entrada[0] = ord('-')  # Tipo de archivo: '-' para archivos ocupados

    nombre_bytes = nombre_destino.encode('ascii')
    entrada[1:1+len(nombre_bytes)] = nombre_bytes
    # Rellenar el resto del nombre con ceros
    for i in range(1 + len(nombre_bytes), 16):
        entrada[i] = 0
    
    entrada[16:20] = struct.pack('<I', tamaño_archivo)
    entrada[20:24] = struct.pack('<I', primer_cluster)
    timestamp_bytes = timestamp.encode('ascii')
    entrada[30:30+len(timestamp_bytes)] = timestamp_bytes

    entrada[50:50+len(timestamp_bytes)] = timestamp_bytes

    data[posicion_entrada:posicion_entrada + 64] = entrada
    print(f"- Guardando cambios en {img_path}...")

    try:
        with open(img_path, 'wb') as f:
            f.write(data)
        
        print(f"\n¡Archivo copiado exitosamente!")
        print(f"   Nombre: {nombre_destino}")
        print(f"   Tamaño: {tamaño_archivo} bytes")
        print(f"   Cluster inicial: {primer_cluster}")
        print(f"   Entrada del directorio: #{entrada_libre}")
        print(f"   Fecha: {timestamp}")
        
        return True
        
    except Exception as e:
        print(f"Error al guardar el archivo .img: {e}")
        return False
    

def find_file(data, filename, superbloque_info):
    # En esta función buscamos un archivo específico dentro del directorio de Fiunamfs.img,
    # utilizando la información del superbloque para entender cómo está estructurado 
    # el sistema de archivos.

    # Args:
        # data: Contenido del archivo .img leído en bytes.
        # filename: El nombre del archivo que queremos encontrar dentro de Fiunamfs.img
        # superbloque_info: Un diccionario con la información del superbloque, 
        # que incluye el tamaño de los clusters y la ubicación del directorio raíz.

    # Returns:
        # Diccionario con la información del archivo encontrado (tamaño, primer cluster, etc.) 
        # o None si el archivo no se encuentra.
    
    cluster_size = superbloque_info['cluster_size']
    dir_clusters = superbloque_info['num_clusters']

    # Recordemos que el directorio empieza en el cluster 1.
    dir_start = cluster_size
    dir_size = dir_clusters * cluster_size
    dir_data = data[dir_start:dir_start + dir_size]

    # Cada entrada mide 64 bytes
    entry_size = 64
    num_entries = dir_size // entry_size

    # Comenzamos a iterar sobre las diferentes entradas, hasta encontrar el archivo
    # o hasta terminar de revisar todas las entradas del directorio.
    for i in range(num_entries):
        entry_start = i * entry_size
        entry_data = dir_data[entry_start:entry_start + entry_size]
        
        # Byte 0: Tipo de archivo
        file_type = chr(entry_data[0])
        
        # Saltamos a otra entrada, si el archivo está vacío
        if file_type == '/':
            continue
        
        # Bytes 1-16: Nombre del archivo
        entry_filename = entry_data[1:15].decode('ascii', errors='ignore').rstrip('\x00').rstrip()
        
        # ¿Es el archivo que buscamos?
        if entry_filename == filename:
            # Bytes 16-20: Tamaño del archivo
            file_size = struct.unpack('<I', entry_data[16:20])[0]
            
            # Bytes 20-24: Cluster inicial
            start_cluster = struct.unpack('<I', entry_data[20:24])[0]
            
            # Bytes 30-44: Fecha de creación
            creation_time = entry_data[30:44].decode('ascii', errors='ignore').rstrip('\x00')
            
            # Bytes 50-64: Fecha de modificación
            modification_time = entry_data[50:64].decode('ascii', errors='ignore').rstrip('\x00')
            
            return {
                'filename': entry_filename,
                'size': file_size,
                'start_cluster': start_cluster,
                'creation_time': creation_time,
                'modification_time': modification_time,
                'entry_index': i
            }
    
    return None




def extraer(data, filename, nombre_salida=None):
	# Args:
        # filename: El nombre del archivo que queremos extraer de Fiunamfs.img
        # nombre_salida: Nombre con el que queremos guardar el archivo extraído 
        # en nuestro sistema operativo.
        # data: El contenido del archivo .img leído en bytes.
        
    # Returns: 
        # True si la extracción fue exitosa. False si falló.
	
    superbloque_info = superbloque(data) # Obtenemos la información del superbloque.
    cluster_size = superbloque_info['cluster_size']

    file_info = find_file(data, filename, superbloque_info)  

    if file_info is None:
        print(f"Error: Archivo '{filename}' no encontrado en el sistema de archivos")
        return False

    print(f"¡Archivo encontrado!")
    print(f"Tamaño: {file_info['size']} bytes")
    print(f"Cluster inicial: {file_info['start_cluster']}")
    print(f"Creado: {file_info['creation_time']}")
    print(f"Modificado: {file_info['modification_time']}")
    
    # Calculamos la posición en bytes donde empiezan los datos que buscamos
    # Fórmula: cluster × tamaño_del_cluster
    data_start = file_info['start_cluster'] * cluster_size
    data_end = data_start + file_info['size']

    # Extraemos los bytes correspondientes al archivo que queremos copiar.
    file_data = data[data_start:data_end]

    # Checamos que la cantidad de bytes sea la correcta.
    if len(file_data) != file_info['size']:
        print(f"Advertencia: Se esperaban {file_info['size']} bytes, " f"pero se leyeron {len(file_data)} bytes")

    if nombre_salida is None:
        nombre_salida = filename
    
    output_file = Path(nombre_salida)

    # Puede pasar que el archivo ya exista, así que preguntamos al usuario si desea sobrescribirlo.
    if output_file.exists():
        response = input(f"El archivo '{nombre_salida}' ya existe. ¿Sobrescribir? (s/n): ")
        if response.lower() != 's':
            print("Operación cancelada")
            return False
        

    # Escribimos el archivo (copiamos de Fiunamfs.img a nuestro sistema operativo).
    try:
        with open(nombre_salida, 'wb') as f:
            f.write(file_data)
        
        print(f"Archivo extraído exitosamente a: {nombre_salida}")
        print(f"Tamaño: {len(file_data)} bytes")
        return True
        
    except Exception as e:
        print(f"Error al escribir el archivo: {e}")
        return False


def borrar(img_path, filename):
    
    # Elimina un archivo de FiUnamFS modificando su entrada en el directorio
    # para marcarla como libre. Los clusters de datos asociados se liberan automáticamente.
    
    # Args:
        # img_path: Ruta al archivo .img de FiUnamFS.
        # filename: Nombre del archivo que se desea eliminar.
    # Returns:
        # True si el archivo se eliminó con éxito, False en caso contrario.
    
    img_file = Path(img_path)
    if not img_file.exists():
        print(f"ERROR! El archivo '{img_path}' no existe.")
        return False

    # Leemos todo el disco emulado en un bytearray modificable
    with open(img_path, 'rb') as f:
        data = bytearray(f.read())

    # Validamos el superbloque para no corromper otro tipo de archivos
    superbloque_info = superbloque(data)
    if superbloque_info['fileName'] != 'FiUnamFS':
        print("ERROR! No es un sistema FiUnamFS válido.")
        return False

    # Buscamos el archivo en el directorio
    file_info = find_file(data, filename, superbloque_info)
    if file_info is None:
        print(f"Error: El archivo '{filename}' no existe en el sistema de archivos.")
        return False

    print("\n============ Información del eliminado del archivo ===================")
    print(f"Archivo '{filename}' encontrado.")
    print(f"  Entrada de directorio: #{file_info['entry_index']}")
    print(f"  Cluster inicial: {file_info['start_cluster']}")
    print(f"  Tamaño: {file_info['size']} bytes")
    print("======================================================================\n")


    # Calculamos la posición exacta en bytes de la entrada de 64 bytes
    cluster_size = superbloque_info['cluster_size']
    entry_size = 64
    posicion_entrada = cluster_size + (file_info['entry_index'] * entry_size)

    # Construimos la entrada vacía según la especificación:
    # Byte 0: '/' para indicar entrada vacía
    # Bytes 1-15: '###############' para el nombre
    # Resto de los bytes (16-63): Los llenamos con ceros (\x00)
    entrada_vacia = bytearray(64)
    entrada_vacia[0] = ord('/')
    entrada_vacia[1:16] = b'###############'
    
    # Aplicamos los cambios en el búfer de memoria
    data[posicion_entrada:posicion_entrada + entry_size] = entrada_vacia

    print("- Actualizando el directorio en el disco...")
    
    # Guardamos los cambios de regreso al archivo .img
    try:
        with open(img_path, 'wb') as f:
            f.write(data)
        
        print(f"\n¡Archivo '{filename}' eliminado exitosamente!")
        return True
        
    except Exception as e:
        print(f"Error crítico al guardar los cambios en el archivo .img: {e}")
        return False