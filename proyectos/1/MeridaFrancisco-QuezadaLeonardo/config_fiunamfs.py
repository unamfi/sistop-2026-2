# config_fiunamfs.py

# Tamaños generales
TAM_SECTOR = 512
SECTORES_POR_CLUSTER = 4
TAM_CLUSTER_ESPERADO = TAM_SECTOR * SECTORES_POR_CLUSTER

# Directorio
CLUSTER_DIRECTORIO_INICIO = 1
TAM_ENTRADA_DIRECTORIO = 64

# Identificación del sistema
NOMBRE_FS_ESPERADO = "FiUnamFS"

# Tu imagen de ejemplo parece ser 24-2, aunque la especificación diga 26-2
VERSIONES_VALIDAS = ["24-2", "26-2"]

# Offsets del superbloque según la especificación que ya probaste
OFFSET_NOMBRE_FS = 5
OFFSET_VERSION = 14
OFFSET_ETIQUETA = 20
OFFSET_TAM_CLUSTER = 40
OFFSET_CLUSTERS_DIRECTORIO = 50
OFFSET_CLUSTERS_TOTALES = 60

# Tipos de entrada
TIPO_ARCHIVO = "-"
TIPO_LIBRE = "/"
NOMBRE_ENTRADA_LIBRE = "###############"