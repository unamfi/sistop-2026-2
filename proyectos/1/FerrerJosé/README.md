# FiUnamFS - Micro Sistema de Archivos

## Autor

Nombre: Ferrer Cordero José Manuel   
Curso: Sistemas Operativos  
Unidad: Sistemas de archivos y Administración de procesos  

---

## Descripción del Proyecto

Este proyecto implementa un micro-sistema de archivos llamado **FiUnamFS**, basado en la especificación proporcionada en clase.

El sistema simula un disco tipo diskette de 1440 KB almacenado en un archivo binario (`fiunamfs.img`) y permite realizar las siguientes operaciones:

- Listar archivos (`ls`)
- Copiar archivos del sistema local hacia FiUnamFS (`copyin`)
- Copiar archivos de FiUnamFS hacia el sistema local (`copyout`)
- Eliminar archivos del sistema (`rm`)

El sistema utiliza asignación contigua y mantiene un directorio plano ubicado en los clusters 1–8.

---

## Arquitectura

El sistema se compone de:

- Un archivo binario que representa el disco.
- Un superbloque en el cluster 0.
- Un directorio plano en clusters 1–8.
- Área de datos a partir del cluster 9.

Cada entrada de directorio ocupa 64 bytes y contiene:

- Tipo de archivo
- Nombre
- Tamaño
- Cluster inicial
- Timestamp de creación
- Timestamp de modificación

---

## Concurrencia y Sincronización

El programa implementa dos hilos de ejecución:

### Worker Thread
Encargado de ejecutar la operación solicitada (ls, copyin, copyout, rm).

### Logger Thread
Encargado de registrar el estado del sistema antes y después de cada operación.

### Mecanismos de sincronización utilizados

- `threading.Lock()` → Protege el acceso al archivo del disco para evitar condiciones de carrera.
- `Queue()` → Permite comunicación segura entre el worker y el logger.

El uso del Lock garantiza exclusión mutua en operaciones de lectura/escritura del disco.

## Requisitos del Entorno

- Python
- Sistema probado en Windows 10 / PowerShell
- No requiere librerías externas

## Cómo ejecutar

### Inicializar el disco

```bash
python init_disk.py