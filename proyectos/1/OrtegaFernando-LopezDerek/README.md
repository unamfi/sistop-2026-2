# Proyecto: FiUnamFS - (26-2)

## Autores

- **Ortega Ayala Fernando**
- **López Granados Derek André**

---

## Descripción

FiUnamFS es un sistema de archivos diseñado para la Facultad de Ingeniería de la UNAM.
En esta versión, el proyecto se ha consolidado como un **Driver de Sistema de Archivos nativo** basado en FUSE (_Filesystem in Userspace_).

Esto permite que la imagen de disco (`fiunamfs.img`) sea montada como un volumen estándar en el sistema operativo Linux/WSL, permitiendo la interacción mediante comandos nativos del shell (`ls`, `cp`, `rm`, `cat`) con integridad garantizada.

---

## Entorno y Dependencias

- **Sistema operativo:** Linux / WSL2
- **Lenguaje:** Python 3.x
- **Dependencias:** `fusepy`
- **Instalación de dependencia:**

```bash
pip install fusepy
```

- **Módulos estándar utilizados:**
  - `struct`
  - `threading`
  - `datetime`
  - `stat`
  - `errno`
  - `os`
  - `sys`

---

## Estructura del Proyecto

- `fuse_main.py`Driver principal que implementa la API de FUSE y gestiona las peticiones del Kernel.
- `filesystem.py`Motor lógico encargado de la manipulación de bytes, gestión de clusters, metadata y seguridad.
- `fiunamfs.img`
  Imagen binaria del sistema de archivos.

---

# Cómo ejecutar

## 1. Preparación

Tener instalada la librería `fusepy`:

```bash
pip install fusepy
```

---

## 2. Montaje

Para exponer el sistema de archivos al sistema operativo, ejecutar el driver en una terminal dedicada:

```bash
python3 fuse_main.py fiunamfs.img ./mnt
```

---

## 3. Operaciones

Una vez montado, se puede interactuar con el sistema desde cualquier otra terminal:

| Requisito       | Comando nativo                       | Resultado esperado                                     |
| --------------- | ------------------------------------ | ------------------------------------------------------ |
| Listar          | `ls -la ./mnt`                       | Muestra el contenido del directorio raíz               |
| Copiar DESDE FS | `cp ./mnt/archivo.txt ./destino.txt` | Extrae el archivo al host con integridad total         |
| Copiar HACIA FS | `cp ./archivo_local.txt ./mnt`       | Crea el archivo en el sistema virtual                  |
| Eliminar        | `rm ./mnt/archivo.txt`               | Libera la entrada del directorio y el cluster asociado |
| Metadatos       | `stat ./mnt/archivo.txt`             | Despliega información correcta del archivo             |

---

# Arquitectura y Concurrencia

## Sincronización mediante Locking

Para garantizar la integridad de los datos ante accesos concurrentes, el motor `filesystem.py` implementa un mecanismo de exclusión mutua:

- Se utiliza `threading.Lock()` para serializar todas las operaciones críticas:
  - `escribir_bytes_archivo`
  - `eliminar_archivo`
  - `leer_bytes_archivo`

- Aunque FUSE maneja múltiples hilos de forma nativa cuando el Kernel recibe peticiones, nuestro `Lock` garantiza que la imagen física (`.img`) no sufra condiciones de carrera (_Race Conditions_) o corrupción de punteros.

---

## Modelo de Flujo de Datos

### Lectura

Mediante `read` (vía FUSE), el motor realiza un `seek` calculado al cluster correspondiente y entrega los bytes exactos al Kernel.

### Escritura

Mediante `create` y `write`, los datos se almacenan en un buffer en memoria y se persisten en el disco durante el `release` del archivo, asegurando que la escritura sea atómica y segura.

---

# Especificaciones Técnicas

## Codificación

Campos numéricos (tamaño, clusters) en **little endian de 32 bits (`<I`)**.

## Layout

- **Directorio raíz:**Comienza en offset `2048` con `256` entradas de `64 bytes`.
- **Datos:**Asignación contigua a partir del cluster `9`.
- **Tamaño de cluster:**
  `2048 bytes`

## Integridad

El driver valida el superbloque (nombre `"FiUnamFS"` y versión) antes de permitir cualquier operación de montaje.

---

# Notas

Este proyecto cumple con los estándares POSIX al integrarse vía FUSE, permitiendo compatibilidad total con las utilidades de línea de comandos de Linux.
