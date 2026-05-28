# Proyecto Final - FiUnamFS

## Integrantes
- Martinez Sanchez Hans
- Blancas Diaz Isaias

---

## Descripción

Este proyecto implementa un micro sistema de archivos llamado FiUnamFS.

El programa permite:

- Leer el superbloque
- Listar archivos del directorio
- Copiar archivos desde el sistema de archivos
- Eliminar archivos
- Ejecutar tareas concurrentes utilizando hilos
- Sincronizar acceso al sistema mediante mutex

---

## Requisitos

- Python 3.10+
- Linux / WSL Ubuntu

---

## Archivos principales

- `main.py` -> Menú principal
- `filesystem.py` -> Manejo del sistema de archivos
- `sync_manager.py` -> Manejo de concurrencia
- `fiunamfs.img` -> Imagen del sistema de archivos

---

## Ejecución

```bash
python3 main.py
```

---

## Funciones implementadas

### 1. Lectura del superbloque
Lee la información principal del sistema FiUnamFS.

### 2. Listado de directorio
Muestra los archivos almacenados en el sistema.

### 3. Copia de archivos
Permite copiar archivos desde FiUnamFS al sistema local.

### 4. Eliminación de archivos
Marca entradas del directorio como eliminadas.

### 5. Concurrencia
Se implementan hilos para monitoreo y copia de archivos.

### 6. Sincronización
Se utiliza `threading.Lock()` para evitar conflictos entre hilos.

---

## Estrategia de sincronización

El proyecto utiliza mutex mediante `threading.Lock()` para proteger el acceso concurrente al archivo `.img`.

Esto evita corrupción de datos durante operaciones simultáneas.

---

## Estado del proyecto

Proyecto funcional y estable.
