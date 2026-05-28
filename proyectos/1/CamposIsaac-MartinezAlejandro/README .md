# Proyecto

Proyecto de Sistemas Operativos para montar y manipular una imagen de disco `FiUnamFS` usando Python y FUSE.

**Autores:**  Campos Cortes Isaac y  Martinez Pérez Alejandro

**Materia:** Sistemas Operativos
**Profesor:** Gunnar Eyal Wolf Iszaevich
**Lenguaje:** Python 3

---

## Descripción

Este proyecto implementa un micro sistema de archivos llamado `FiUnamFS`. El programa recibe una imagen de disco, por ejemplo `fiunamfs.img`, la interpreta y la monta en un directorio vacío mediante FUSE.

Una vez montada la imagen, se pueden usar comandos normales del sistema operativo, como `ls`, `cp` y `rm`, para trabajar con los archivos que están dentro de `FiUnamFS`.

Ejemplo general:

```bash
ls montaje
cp montaje/README.org .
cp prueba.txt montaje/
rm montaje/prueba.txt
```

---

## Objetivos del proyecto

El programa desarrollado debe permitir:

1. Listar los contenidos del directorio de `FiUnamFS`.
2. Copiar uno de los archivos de dentro de `FiUnamFS` hacia el sistema operativo.
3. Copiar un archivo de la computadora hacia `FiUnamFS`.
4. Eliminar un archivo de `FiUnamFS`.
5. Contar con por lo menos dos hilos de ejecución operando concurrentemente y comunicando su estado mediante mecanismos de sincronización.

---

## Requisitos antes de ejecutar

El proyecto está pensado para ejecutarse en Linux o en un entorno compatible con FUSE, como WSL en Windows.

Se necesita tener instalado:

- Python 3.
- FUSE o libfuse.
- La biblioteca de Python para FUSE.
- La imagen `fiunamfs.img`.
- Un directorio vacío para montar el sistema de archivos.

### Instalación sugerida en Ubuntu/Debian

```bash
sudo apt update
sudo apt install python3 python3-pip fuse libfuse2 python3-fuse
```

Si `python3-fuse` no está disponible en tu sistema, se puede intentar instalar con `pip`:

```bash
sudo apt install python3-dev pkg-config libfuse-dev
python3 -m pip install fuse-python
```

Para verificar que el módulo de FUSE esté disponible:

```bash
python3 -c "import fuse; print('FUSE disponible')"
```

---



---

## Directorio de montaje

Antes de ejecutar el programa se debe crear un directorio vacío. Este directorio será el punto donde FUSE mostrará el contenido de la imagen.

```bash
mkdir montaje
```

Es importante que `montaje/` esté vacío. Si se monta FiUnamFS sobre una carpeta que ya tiene archivos, esos archivos no se borran, pero quedan ocultos mientras el sistema esté montado.

---

## Ejecución

Desde la carpeta principal del proyecto:

```bash
python3 main.py fiunamfs.img montaje
```

Mientras el programa esté corriendo, el sistema de archivos estará montado en la carpeta `montaje/`.

---

## Uso

### 1. Listar archivos

```bash
ls -la montaje
```

Con la imagen de prueba deberían aparecer los archivos:

```text
README.org
logo.png
mensaje.jpg
```

---

### 2. Copiar desde FiUnamFS hacia el sistema operativo

Para extraer un archivo desde la imagen:

```bash
cp montaje/README.org .
```

También se puede copiar a una carpeta:

```bash
mkdir extraidos
cp montaje/logo.png extraidos/
```

---

### 3. Copiar desde el sistema operativo hacia FiUnamFS

Primero se puede crear un archivo de prueba:

```bash
echo "Archivo de prueba" > prueba.txt
```

Después se copia al directorio montado:

```bash
cp prueba.txt montaje/
```

Para revisar que se agregó correctamente:

```bash
ls -la montaje
```

---

### 4. Eliminar un archivo de FiUnamFS

```bash
rm montaje/prueba.txt
```

Después de eliminarlo, se puede verificar con:

```bash
ls -la montaje
```

---

## Desmontar el sistema de archivos

Cuando termines de usar el programa, desmonta la carpeta:

```bash
umount montaje
```

Si no permite desmontar, revisa que ninguna terminal esté ubicada dentro de `montaje/`.

---

## Archivos principales

### `main.py`

Es el archivo principal. Usa FUSE para conectar las operaciones del sistema operativo con el código del proyecto.

Aquí se implementan operaciones como:

- `readdir`: listar archivos.
- `getattr`: obtener información de archivos y directorios.
- `read`: leer archivos desde la imagen.
- `write`: escribir contenido en archivos.
- `create`: crear archivos nuevos.
- `unlink`: eliminar archivos.
- `open`: validar apertura de archivos.

### `fiunamfs/superbloque.py`

Lee y valida el superbloque de la imagen. De ahí obtiene datos como el nombre del sistema de archivos, versión, etiqueta, tamaño de cluster y ubicación del directorio.

### `fiunamfs/entrada.py`

Representa una entrada del directorio. Cada entrada guarda información de un archivo: nombre, tamaño, cluster inicial, fecha de creación y fecha de modificación.

También convierte las entradas entre bytes de la imagen y objetos que Python puede manejar de forma más clara.

### `fiunamfs/disco.py`

Maneja las operaciones principales sobre la imagen:

- cargar el directorio;
- listar archivos;
- buscar archivos;
- leer archivos;
- escribir archivos;
- sobrescribir archivos;
- eliminar archivos;
- actualizar el directorio en la imagen.

### `fiunamfs/herramientas.py`

Contiene funciones auxiliares para trabajar con enteros en formato little endian y fechas en el formato usado por `FiUnamFS`.

---

## Sincronización e hilos

El proyecto usa hilos para cumplir con el requisito de concurrencia y para separar la actualización del disco de las operaciones principales.

En el módulo `disco.py` se usan:

- `threading.Thread`: crea un hilo auxiliar para atender actualizaciones pendientes.
- `threading.RLock`: protege las operaciones que modifican información compartida.
- `threading.Condition`: permite avisar al hilo auxiliar cuando hay cambios que deben escribirse en la imagen.

Cuando se crea, modifica o elimina un archivo, se agrega una operación pendiente y se notifica al hilo de escritura. Ese hilo actualiza el directorio dentro de `fiunamfs.img`.

Esto evita que varias operaciones escriban al mismo tiempo sobre la imagen y ayuda a mantener consistente el directorio.

---

## Formato FiUnamFS usado

La imagen `fiunamfs.img` representa un disco de 1440 KB. Su estructura general es:

```text
Cluster 0       -> superbloque
Clusters 1 a 8  -> directorio
Resto           -> datos de archivos
```

Características principales:

- Usa cadenas ASCII.
- Usa enteros de 32 bits en formato little endian.
- Cada entrada del directorio mide 64 bytes.
- Maneja un directorio plano, sin subdirectorios.
- Los archivos se almacenan de forma contigua.
- Las entradas libres se identifican con `/` y el nombre `###############`.

---

## Pruebas recomendadas

Se recomienda hacer pruebas con una copia de la imagen original:

```bash
cp fiunamfs.img fiunamfs_prueba.img
mkdir montaje
python3 main.py fiunamfs_prueba.img montaje
```

En otra terminal:

```bash
ls -la montaje
mkdir extraidos
cp montaje/README.org extraidos/
cp montaje/logo.png extraidos/
echo "prueba de escritura" > prueba.txt
cp prueba.txt montaje/
ls -la montaje
rm montaje/prueba.txt
ls -la montaje
```

Al terminar:

```bash
umount montaje
```

---

## Errores comunes

### Falta el módulo `fuse`

Si aparece un error como:

```text
ModuleNotFoundError: No module named 'fuse'
```

instala la biblioteca de FUSE para Python y vuelve a probar.

### El directorio de montaje no existe

Crea el directorio antes de ejecutar:

```bash
mkdir montaje
```

### El directorio de montaje no está vacío

Usa una carpeta vacía para evitar confusiones durante el montaje.

### No se puede desmontar

Cierra cualquier terminal que esté dentro de `montaje/` y ejecuta:

```bash
fusermount -u montaje
```



## Notas

La imagen usada en las pruebas puede indicar versión `24-2`, aunque el planteamiento menciona `26-2`. En el código se valida la versión esperada por la imagen entregada para evitar modificar un sistema de archivos que no corresponda al formato usado durante el desarrollo. Durante el desarrollo se validó para la versión `24-2`, en la versión final se cambió para seguir lo solicitado en el planteamiento del proyecto. En caso de que se presente un mensaje mencionando una versión incorrecta se puede cambiar la versión verificada en `superbloque.py`
