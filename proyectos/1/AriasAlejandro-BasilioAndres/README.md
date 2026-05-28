# FiUnamFS — Micro sistema de archivos de asignación contigua

**Materia:** Sistemas Operativos 2026-2  
**Autores:** Alejandro Arias y Andrés Basilio  
**Facultad de Ingeniería, UNAM**

---

## Descripción general

FiUnamFS es un sistema de archivos plano y de asignación contigua que opera
directamente sobre una imagen binaria de 1,440 KB (exactamente 1,474,560 bytes),
simulando un diskette tradicional. El programa permite listar, extraer, insertar
y eliminar archivos, además de montar la imagen como un sistema de archivos
virtual en Linux mediante FUSE.

---

## Arquitectura del disco

La superficie del pseudodispositivo se divide en **clusters de 2,048 bytes**
(4 sectores de 512 bytes cada uno), lo que da un total de 720 clusters
numerados del 0 al 719.

| Región | Clusters | Descripción |
|---|---|---|
| Superbloque | 0 | Metadatos del volumen |
| Directorio plano | 1 – 8 | Hasta 256 entradas de 64 bytes |
| Zona de datos | 9 – 719 | Contenido de los archivos |

### Superbloque

Los primeros 64 bytes del cluster 0 se deserializan con la cadena de formato
`struct` `<5x9s5s1x16s4xI6xI6xI`. Los `x` no son campos; son bytes de
alineación (padding) que exige la especificación para respetar los offsets
exactos de cada campo. El prefijo `<` fuerza interpretación little-endian
para todos los enteros de 32 bits, tal como indica la spec.

Al abrir la imagen se validan obligatoriamente la firma `FiUnamFS` y la versión
`26-2`. Si cualquiera de las dos no coincide, el programa aborta sin modificar
el disco.

### Directorio plano

Cada una de las 256 entradas ocupa exactamente 64 bytes y se deserializa con
`<1s15sII6x14s6x14s`. El primer byte indica el tipo: `-` (0x2D) para archivos
activos y `/` (0x2F) para entradas libres. Cuando se borra un archivo, su
entrada se sobreescribe con un *tombstone*: tipo `/` y nombre
`###############` (15 almohadillas), conservando los datos en disco hasta que
un `defrag` los descarte.

---

## Asignación contigua y desfragmentación

La asignación contigua simplifica radicalmente la lectura y escritura —basta
con conocer el cluster inicial y el tamaño del archivo para acceder a todos
sus bloques— pero introduce un problema clásico: la **fragmentación externa**.
Después de varios ciclos de inserción y borrado, el espacio libre queda
disperso en huecos que individualmente son demasiado pequeños para alojar
archivos nuevos, aunque en conjunto sumen suficiente capacidad.

### Búsqueda de hueco (`cp_in`)

Al insertar un archivo calculamos `ceil(tamaño / 2048)` clusters necesarios y
recorremos linealmente la zona de datos buscando el primer bloque de clusters
*consecutivos* libres. Si no existe ninguno, el sistema rechaza la operación y
sugiere ejecutar `-defrag` antes de reintentar.

### Algoritmo de desfragmentación (`defrag`)

1. Se obtiene la lista de archivos activos y se ordena por `start_cluster`
   ascendente.
2. Se inicializa un puntero `current_free_cluster = 9` (primer cluster de
   datos).
3. Por cada archivo: si ya está en `current_free_cluster` se avanza el puntero
   sin mover nada; si está más adelante, se copian sus clusters al destino y
   se actualiza su entrada de directorio en disco.
4. Al terminar, todos los clusters desde `current_free_cluster` hasta el 719
   se rellenan con bytes nulos (`\x00`), eliminando cualquier resto de
   archivos borrados.

El orden ascendente por `start_cluster` garantiza que la ventana de destino
siempre está detrás de la ventana de origen, por lo que nunca se solapan
durante la copia.

---

## Integración FUSE

El módulo `fuse_ops.py` implementa la clase `FiUnamFSFuse`, que hereda de
`Operations` de la librería `fusepy` y traduce las llamadas del VFS de Linux
a las operaciones internas del sistema.

### El reto de `write`

La asignación contigua no permite crecer un archivo dinámicamente: para
reservar espacio hay que conocer el tamaño total de antemano. El kernel de
Linux, sin embargo, entrega los datos en múltiples llamadas a `write` sin
indicar el tamaño final hasta que el proceso cierra el descriptor.

Resolvimos esto con un **buffer en memoria**: `create` inicializa un
`bytearray` indexado por ruta, `write` acumula cada fragmento en su offset
correcto dentro de ese buffer, y `release` —que FUSE invoca cuando el último
descriptor del archivo se cierra— vuelca el buffer completo a un archivo
temporal en el host y llama a `cp_in` para insertarlo en la imagen usando toda
la lógica de búsqueda de huecos y padding que ya teníamos. El temporal se
borra inmediatamente después.

Este esquema también resuelve de forma natural el `truncate(path, 0)` que el
VFS emite al abrir con `O_TRUNC`: simplemente redimensiona el buffer en memoria
sin tocar el disco.

### Operaciones implementadas

| Llamada FUSE | Comportamiento |
|---|---|
| `getattr` | Directorio raíz con `S_IFDIR`; archivos con `S_IFREG \| 0o644` y timestamps convertidos de ASCII a Unix |
| `readdir` | Devuelve `.`, `..` y los nombres de todos los archivos activos |
| `read` | Lee los clusters del archivo y aplica el slice `[offset:offset+length]` |
| `create` / `write` / `release` | Pipeline de buffer en memoria descrito arriba |
| `unlink` | Borrado lógico via `rm` |

---

## Nota técnica: versión del superbloque

Durante las pruebas identificamos que el archivo `fiunamfs.img` incluido en el
repositorio tiene la cadena `24-2` en los bytes 14–18 del superbloque, en
lugar de `26-2` que corresponde al semestre en curso. Esto se debe a que la
imagen fue generada originalmente para el grupo 2024-2 y reutilizada sin
actualizar ese campo.

La constante `EXPECTED_VERSION` en `fiunamfs/superblock.py` define el valor
que se valida al abrir la imagen. Para trabajar con la imagen de referencia del
repositorio basta con cambiar esa línea a `'24-2'`; en producción —o si se
genera una imagen nueva— debe conservarse `'26-2'` tal como lo exige la
especificación.

---

## Manual de uso

### Requisitos

```bash
pip install -r requirements.txt
```

> **Nota:** `fusepy` requiere que `libfuse` esté instalada en el sistema.
> En distribuciones basadas en Debian/Ubuntu: `sudo apt install fuse`.

### Comandos disponibles

Todos los comandos se ejecutan desde el directorio
`proyectos/1/AriasAlejandro-BasilioAndres/`.

```bash
# Listar archivos en el sistema
python main.py ../fiunamfs.img -ls

# Extraer un archivo del FiUnamFS al host
python main.py ../fiunamfs.img -cp_out README.org ./README_extraido.org

# Insertar un archivo del host al FiUnamFS
python main.py ../fiunamfs.img -cp_in ./mi_archivo.txt mi_archivo.txt

# Eliminar un archivo del FiUnamFS
python main.py ../fiunamfs.img -rm mi_archivo.txt

# Desfragmentar el disco
python main.py ../fiunamfs.img -defrag

# Montar la imagen como sistema de archivos virtual
mkdir -p mivirtualusb
python main.py ../fiunamfs.img -mount mivirtualusb

# En otra terminal, desmontar
fusermount -u mivirtualusb
```

### Estructura del proyecto

```
AriasAlejandro-BasilioAndres/
├── main.py               # Punto de entrada y multiplexor de comandos
├── requirements.txt
└── fiunamfs/
    ├── exceptions.py     # Jerarquía de errores del sistema
    ├── disk.py           # I/O binario sobre el .img (Fase 1)
    ├── superblock.py     # Deserialización y validación del superbloque (Fase 1)
    ├── directory.py      # Motor del directorio plano (Fase 2)
    ├── filesystem.py     # Operaciones de alto nivel: ls, cp, rm, defrag (Fases 3–5)
    └── fuse_ops.py       # Integración FUSE (Fase 6)
```
