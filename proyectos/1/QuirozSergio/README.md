# FiUnamFS — Cliente multihilos

## Autor
Quiroz Salazar Sergio — UNAM FI, 2026-2.

---

## Descripción

`fiunamfs.py` es un programa en Python que permite interactuar con imágenes de disco
que siguen la especificación **FiUnamFS**: un sistema de archivos plano de asignación
contigua, almacenado en un pseudodispositivo de 1440 KB (tamaño de diskette).

### Operaciones implementadas

| # | Operación | Descripción |
|---|-----------|-------------|
| 1 | `list` | Lista el contenido del directorio |
| 2 | `copy-out` | Copia un archivo del FS hacia tu PC |
| 3 | `copy-in` | Copia un archivo de tu PC hacia el FS |
| 4 | `delete` | Elimina un archivo del FS |
| 5 | Multihilos | Todas las operaciones corren en un hilo de trabajo separado, sincronizado con el hilo de control mediante `threading.Lock` y `threading.Event` |

---

## Entorno y dependencias

- **Lenguaje:** Python 3.10+ (usa `list[dict]` como type hint nativo)
- **Módulos:** únicamente de la biblioteca estándar:
  - `struct` — empaquetar/desempaquetar enteros little-endian de 32 bits
  - `threading` — hilos, Lock, Event
  - `os`, `sys`, `datetime` — utilidades
- **No requiere instalación de paquetes externos.**

Verificar versión de Python:
```bash
python3 --version   # debe ser >= 3.10
```

---

## Instalación / Preparación

```bash
# Clonar / descomprimir el repositorio
cd fiunamfs-project/

# No se requiere compilación. El programa se ejecuta directamente.
```

---

## Uso

```
python3 fiunamfs.py <imagen.img> <comando> [argumentos]
```

### Listar el directorio

```bash
python3 fiunamfs.py fiunamfs.img list
```

Salida ejemplo:
```
Nombre           Tamaño   Cluster  Creado               Modificado
──────────────────────────────────────────────────────────────────────
README.org        30 KB        10  2026-05-12 21:32:40  2026-05-12 21:32:40
logo.png         123 KB        26  2026-05-12 21:32:40  2026-05-12 21:32:40
mensaje.jpg      176 KB        88  2026-05-12 21:32:40  2026-05-12 21:32:40

3 archivo(s)
```

### Copiar un archivo del FS a tu PC

```bash
python3 fiunamfs.py fiunamfs.img copy-out README.org ./README.org
python3 fiunamfs.py fiunamfs.img copy-out logo.png   /tmp/logo.png
```

### Copiar un archivo de tu PC al FS

```bash
python3 fiunamfs.py fiunamfs.img copy-in ./mi_archivo.txt notas.txt
python3 fiunamfs.py fiunamfs.img copy-in ./foto.jpg       foto.jpg
```

### Eliminar un archivo del FS

```bash
python3 fiunamfs.py fiunamfs.img delete notas.txt
```

---

## Estrategia de sincronización entre hilos

El programa usa **dos hilos concurrentes** que se comunican su estado:

```
Hilo principal (control/UI)          Hilo de trabajo (I/O)
─────────────────────────            ──────────────────────
 Crea SharedState                    
 Lanza hilo de trabajo   ────────►   Ejecuta la operación sobre el FS
 state.listo.wait()  ◄── bloquea     (con fs._fs_lock adquirido)
                                     Deposita resultado en state
                                     state.listo.set()  ──────►
 (desbloquea)                        
 Lee state.resultado                 
 (o relanza state.error)             
```

### Mecanismos usados

| Mecanismo | Clase Python | Rol |
|-----------|-------------|-----|
| **Exclusión mutua sobre el archivo** | `threading.Lock` (`FiUnamFS._fs_lock`) | Garantiza que sólo un hilo lea/escriba la imagen a la vez |
| **Exclusión mutua sobre el estado compartido** | `threading.Lock` (`SharedState.lock`) | Protege `resultado` y `error` de condiciones de carrera |
| **Señalización** | `threading.Event` (`SharedState.listo`) | El hilo de trabajo señala al hilo de control que terminó, sin busy-wait |

Esta arquitectura permite escalar fácilmente a múltiples operaciones concurrentes
(p. ej. un servidor que atiende varios clientes) sin cambiar la lógica de `FiUnamFS`.

---

## Estructura del proyecto

```
fiunamfs-project/
├── fiunamfs.py      # Código fuente principal
├── fiunamfs.img     # Imagen de disco de ejemplo (no se versiona en producción)
├── README.md        # Este archivo
└── .gitignore       # Excluye *.img, __pycache__, etc.
```

---

## Especificación FiUnamFS (resumen)

| Campo | Offset | Tamaño | Descripción |
|-------|--------|--------|-------------|
| Magic | 0 | 5 B | `\x00\x00\x00\x00\x00` |
| Nombre FS | 5 | 9 B | `"FiUnamFS"` |
| Versión | 14 | 5 B | `"24-2"` |
| Etiqueta | 20 | 16 B | Texto libre |
| Tamaño cluster | 40 | 4 B | u32 LE (2048) |
| Clusters dir | 50 | 4 B | u32 LE (8) |
| Total clusters | 60 | 4 B | u32 LE (720) |

**Entrada de directorio (64 bytes):**

| Campo | Offset | Tamaño | Descripción |
|-------|--------|--------|-------------|
| Tipo | 0 | 1 B | `'-'` (archivo) / `'/'` (vacío) |
| Nombre | 1 | 15 B | ASCII, rellenado con espacios |
| Tamaño | 16 | 4 B | u32 LE, en bytes |
| Cluster inicial | 20 | 4 B | u32 LE |
| Fecha creación | 30 | 15 B | `AAAAMMDDHHMMSS` |
| Fecha modificación | 50 | 15 B | `AAAAMMDDHHMMSS` |

# Evdencias

----------
PS C:\Users\sergi\OneDrive\Desktop\FiUnamFS> python fiunamfs.py fiunamfs.img list
Nombre               Tamaño  Cluster  Creado               Modificado
──────────────────────────────────────────────────────────────────────────────
README.org            30 KB       10  2026-05-12 21:32:40  2026-05-12 21:32:40
logo.png             123 KB       26  2026-05-12 21:32:40  2026-05-12 21:32:40
mensaje.jpg          176 KB       88  2026-05-12 21:32:40  2026-05-12 21:32:40

3 archivo(s)


-----------
PS C:\Users\sergi\OneDrive\Desktop\FiUnamFS> python fiunamfs.py fiunamfs.img copy-out README.org README.org
Copiando 'README.org' → 'README.org' ...
Listo. 30 KB escritos en 'README.org'
PS C:\Users\sergi\OneDrive\Desktop\FiUnamFS> dir


    Directory: C:\Users\sergi\OneDrive\Desktop\FiUnamFS


Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
-a---l         5/20/2026  10:08 PM        1474560 fiunamfs.img
-a---l         5/20/2026  10:50 PM          18552 fiunamfs.py
-a---l         5/20/2026  10:52 PM          31094 README.org


-----------
PS C:\Users\sergi\OneDrive\Desktop\FiUnamFS> python fiunamfs.py fiunamfs.img copy-in hola.txt hola.txt
Copiando 'hola.txt' → FiUnamFS:'hola.txt' ...
Listo. 'hola.txt' agregado al sistema de archivos.


-----------
PS C:\Users\sergi\OneDrive\Desktop\FiUnamFS> python fiunamfs.py fiunamfs.img list
Nombre               Tamaño  Cluster  Creado               Modificado
──────────────────────────────────────────────────────────────────────────────
README.org            30 KB       10  2026-05-12 21:32:40  2026-05-12 21:32:40
hola.txt               10 B        9  2026-05-20 22:54:32  2026-05-20 22:54:32
logo.png             123 KB       26  2026-05-12 21:32:40  2026-05-12 21:32:40
mensaje.jpg          176 KB       88  2026-05-12 21:32:40  2026-05-12 21:32:40

4 archivo(s)


-----------
PS C:\Users\sergi\OneDrive\Desktop\FiUnamFS> python fiunamfs.py fiunamfs.img delete hola.txt
Eliminando 'hola.txt' ...
Listo. 'hola.txt' eliminado del sistema de archivos.
PS C:\Users\sergi\OneDrive\Desktop\FiUnamFS> python fiunamfs.py fiunamfs.img list
Nombre               Tamaño  Cluster  Creado               Modificado
──────────────────────────────────────────────────────────────────────────────
README.org            30 KB       10  2026-05-12 21:32:40  2026-05-12 21:32:40
logo.png             123 KB       26  2026-05-12 21:32:40  2026-05-12 21:32:40
mensaje.jpg          176 KB       88  2026-05-12 21:32:40  2026-05-12 21:32:40

3 archivo(s)
PS C:\Users\sergi\OneDrive\Desktop\FiUnamFS>
