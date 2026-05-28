# Proyecto SO - Micro sistema de archivos multihilos

## Autores

- Adrián Axel Arzate Ríos - **GitHub: @AxlBoy11th**
- David Díaz Antunez - **GitHub: @Cuervy117**

## Objetivos

El objetivo principal de este proyecto es implementar un micro sistema de archivos compatible con `FiUnamFS`, utilizando Python y FUSE para permitir que una imagen de disco pueda montarse como un directorio dentro del sistema operativo.

Los objetivos específicos del proyecto son:

1. Leer e interpretar correctamente la estructura interna de una imagen `fiunamfs.img`.
2. Listar los archivos almacenados dentro del sistema de archivos `FiUnamFS`.
3. Copiar archivos desde `FiUnamFS` hacia el sistema operativo anfitrión.
4. Copiar archivos desde el sistema operativo anfitrión hacia `FiUnamFS`.
5. Eliminar archivos almacenados dentro de `FiUnamFS`.
6. Implementar operaciones concurrentes mediante hilos.
7. Utilizar mecanismos de sincronización para evitar inconsistencias al acceder o modificar la imagen del sistema de archivos.
8. Probar el sistema usando comandos comunes de Linux como `ls`, `cp`, `cat` y `rm`.

## Introducción

`FiUnamFS` es un sistema de archivos simple diseñado con fines académicos para comprender cómo se organiza la información dentro de un dispositivo de almacenamiento. En este proyecto, el dispositivo físico se simula mediante un archivo de imagen llamado `fiunamfs.img`.

El sistema de archivos trabaja con una estructura sencilla: un superbloque, un directorio plano y una zona de datos. A partir de esta organización, el programa debe ser capaz de localizar archivos, leer su contenido, escribir nuevos archivos y eliminar entradas existentes.

Para facilitar el uso del sistema, la implementación utiliza FUSE, una herramienta que permite crear sistemas de archivos en espacio de usuario. Gracias a esto, la imagen `fiunamfs.img` puede montarse en una carpeta normal del sistema operativo y manipularse con comandos comunes de terminal.

Este enfoque permite probar el sistema de archivos de forma práctica, ya que el usuario puede interactuar con la imagen como si fuera un directorio real. Además, el proyecto incorpora hilos y mecanismos de sincronización para reforzar los temas vistos en clase sobre sistemas de archivos, concurrencia y administración de procesos.

## Requerimientos del Sistema

### Windows

El proyecto no fue probado de forma nativa en Windows.

Debido a que la implementación utiliza FUSE, la ejecución principal está pensada para sistemas Linux. Para trabajar en Windows se recomienda utilizar un entorno Linux mediante alguna de las siguientes opciones:

- WSL2 con una distribución Linux.
- Una máquina virtual con Linux.
- Una instalación de Linux en una partición separada.

En Windows, el flujo recomendado es ejecutar el proyecto dentro del entorno Linux y seguir los mismos pasos indicados en la sección de Linux.

### Linux

El proyecto fue probado en Linux.

Dependencias necesarias:

- Python 3
- FUSE
- fusepy
- pip
- venv

Instalación de paquetes del sistema en Linux:

```bash
sudo pacman -S fuse2 python-pip
```

Creación del entorno virtual:

```bash
python -m venv .venv
source .venv/bin/activate
```

Instalación de dependencias de Python:

```bash
pip install -r requerimientos.txt
```

Ejecución del programa:

```bash
mkdir -p mnt
python main.py mnt ../fiunamfs.img
```

Donde:

- `mnt` es el directorio vacío donde se montará el sistema de archivos.
- `../fiunamfs.img` es la imagen del sistema de archivos proporcionada para el proyecto.

Para desmontar el sistema de archivos:

```bash
fusermount -u mnt
```

Si el comando anterior falla:

```bash
sudo umount mnt
```

## Explicación del Código

### Sistema FiUnamFS proporcionado por el profesor

`FiUnamFS` es un micro sistema de archivos usado como caso de estudio para practicar conceptos de sistemas de archivos y concurrencia.

El sistema se almacena dentro de una imagen llamada `fiunamfs.img`, la cual simula un disco. En lugar de modificar un dispositivo físico real, el programa lee y escribe directamente sobre este archivo binario.

La estructura general del sistema es la siguiente:

- Un superbloque al inicio de la imagen.
- Un directorio plano, sin subdirectorios.
- Una zona de datos donde se guarda el contenido de los archivos.

El superbloque contiene información general del sistema, como la firma `FiUnamFS`, la versión, la etiqueta del volumen, el tamaño de los clústeres, el número de clústeres del directorio y el número total de clústeres.

El directorio está formado por entradas de tamaño fijo. Cada entrada guarda la información necesaria para localizar un archivo: tipo, nombre, tamaño, clúster inicial, fecha de creación y fecha de modificación.

Como el sistema es de asignación contigua, cada archivo se guarda en una secuencia continua de clústeres. Por esta razón, al crear o copiar un archivo hacia `FiUnamFS`, el programa debe buscar espacio libre suficiente en la imagen.

### `main.py`

Este archivo es el punto de entrada del programa.

Su función principal es preparar la ejecución del sistema de archivos. Para ello, recibe desde la terminal dos argumentos:

- `mount_point`: directorio vacío donde se montará el sistema.
- `image_file`: archivo de imagen que contiene el sistema `FiUnamFS`.

Ejemplo:

```bash
python main.py mnt ../fiunamfs.img
```

Dentro de este archivo se crea un objeto `DiskWorker`, que funciona como hilo encargado de las operaciones de entrada y salida sobre la imagen. Después se inicializa la clase `FiUnamFS`, que contiene las operaciones del sistema de archivos.

Finalmente, `main.py` monta el sistema usando FUSE. Mientras el programa está corriendo, el contenido de `fiunamfs.img` puede consultarse desde el directorio `mnt`.

También se incluye una sección `finally` para detener correctamente el hilo `DiskWorker` cuando el sistema se desmonta o cuando ocurre un error.

### `fiunamfs.py`

Este archivo contiene la implementación principal del sistema de archivos.

La clase principal es `FiUnamFS`, que hereda de las clases necesarias de FUSE para responder a operaciones del sistema operativo como listar, leer, crear, escribir y eliminar archivos.

Sus responsabilidades principales son:

- Leer y validar el superbloque.
- Verificar que la imagen corresponda a un sistema `FiUnamFS`.
- Leer los metadatos principales de la imagen.
- Interpretar las entradas del directorio.
- Mantener una caché en memoria con los archivos encontrados.
- Construir un mapa de clústeres libres y ocupados.
- Responder a las operaciones que FUSE recibe desde el sistema operativo.

#### `_mount_filesystem()`

Esta función se ejecuta al iniciar el sistema.

Lee los primeros bytes de la imagen para obtener el superbloque. A partir de esa información valida la firma del sistema de archivos, obtiene la etiqueta del volumen, el tamaño del clúster, el número de clústeres del directorio y el número total de clústeres.

Después llama a las funciones encargadas de leer el directorio y construir el mapa de espacio libre.

#### `_parse_directory()`

Esta función recorre los clústeres del directorio.

Cada entrada del directorio mide 64 bytes. La función revisa cada entrada para determinar si está libre u ocupada. Cuando encuentra un archivo válido, extrae su nombre, tamaño, clúster inicial y fechas.

La información encontrada se guarda en `self.directory`, que funciona como una caché en memoria para consultar los archivos de manera más rápida.

#### `_build_free_space_map()`

Esta función construye un mapa de ocupación de clústeres.

Primero marca como ocupados los clústeres reservados para el superbloque y el directorio. Después revisa los archivos encontrados en el directorio y marca como ocupados los clústeres que utiliza cada archivo.

Este mapa permite saber qué partes de la imagen están libres para guardar nuevos archivos.

#### `find_free_clusters()`

Esta función busca una secuencia continua de clústeres libres.

Es necesaria porque `FiUnamFS` utiliza asignación contigua. Esto significa que un archivo no puede guardarse en clústeres separados, sino que necesita un bloque continuo de espacio.

Si no hay suficiente espacio disponible, la función genera un error de falta de espacio.

#### `getattr()`

Esta función responde cuando el sistema operativo solicita los atributos de un archivo o directorio.

Por ejemplo, cuando se ejecuta:

```bash
ls -la mnt
```

FUSE necesita saber si cada elemento es un archivo o un directorio, cuál es su tamaño y cuáles son sus fechas. Esta función entrega esa información.

#### `readdir()`

Esta función permite listar los archivos del sistema.

Cuando el usuario ejecuta:

```bash
ls mnt
```

FUSE llama a `readdir()`. La función devuelve las entradas `.` y `..`, además de los nombres de los archivos almacenados en `self.directory`.

#### `read()`

Esta función permite leer el contenido de un archivo.

Cuando el usuario ejecuta un comando como:

```bash
cat mnt/README.org
```

o copia un archivo desde `FiUnamFS` hacia Linux, FUSE llama a `read()`.

La función calcula la posición real del archivo dentro de la imagen usando el clúster inicial, el tamaño del clúster y el desplazamiento solicitado. Después pide al `DiskWorker` que lea los bytes necesarios.

#### `create()`

Esta función crea una nueva entrada en el directorio.

Se ejecuta cuando el usuario copia un archivo nuevo hacia `mnt` o crea un archivo dentro del sistema montado.

La función valida que el nombre no exceda el límite permitido, revisa que el archivo no exista previamente y busca una ranura libre en el directorio. Después escribe una nueva entrada con tamaño inicial cero.

#### `write()`

Esta función escribe datos dentro de la imagen.

Cuando se copia un archivo desde Linux hacia `FiUnamFS`, FUSE envía fragmentos de datos a `write()`.

La función calcula cuántos clústeres necesita el archivo, busca espacio libre si el archivo aún no tiene clúster asignado, escribe los datos en la imagen y actualiza el tamaño y la fecha de modificación en el directorio.

#### `unlink()`

Esta función elimina un archivo del sistema `FiUnamFS`.

Cuando el usuario ejecuta:

```bash
rm mnt/archivo.txt
```

FUSE llama a `unlink()`.

La función localiza la entrada del archivo en el directorio, la marca como libre usando el marcador correspondiente y libera los clústeres que ocupaba el archivo dentro del mapa de espacio en memoria.

#### `_find_free_dir_slot()`

Esta función busca una entrada libre dentro del directorio.

Se utiliza cuando se necesita crear un nuevo archivo. Si no encuentra espacio disponible en el directorio, genera un error indicando que el directorio está lleno.

#### `_update_dir_entry()`

Esta función actualiza en disco la entrada de directorio correspondiente a un archivo.

Se utiliza principalmente después de escribir datos, porque el tamaño del archivo, el clúster inicial y la fecha de modificación pueden cambiar.

### `worker.py`

Este archivo implementa el hilo encargado de trabajar directamente con la imagen `fiunamfs.img`.

La clase principal es `DiskWorker`, que hereda de `threading.Thread`. Su objetivo es separar las operaciones de entrada y salida del resto del sistema.

El `DiskWorker` utiliza una cola de tareas. La clase `FiUnamFS` coloca solicitudes en la cola y el `DiskWorker` las procesa una por una.

Las operaciones principales que realiza son:

- Leer un clúster completo.
- Escribir un clúster completo.
- Leer una cantidad específica de bytes desde una posición de la imagen.

#### `run()`

Esta función es el ciclo principal del hilo.

Abre la imagen en modo lectura y escritura binaria. Después espera tareas en la cola. Cuando recibe una tarea, la procesa y marca la tarea como terminada.

Si recibe `None`, el hilo interpreta que debe detenerse.

#### `_process_task()`

Esta función procesa cada tarea recibida.

Dependiendo del tipo de tarea, puede realizar una lectura de clúster, una escritura de clúster o una lectura de bytes. Para hacerlo utiliza operaciones como `seek()`, `read()` y `write()` sobre la imagen.

#### `_submit_sync()`

Esta función permite enviar una tarea al `DiskWorker` y esperar a que termine.

Usa un `threading.Event` para sincronizar el hilo principal con el hilo trabajador. El hilo que solicita la operación queda esperando hasta que el `DiskWorker` termina y activa el evento.

Esta parte es importante para la sincronización del proyecto, porque permite que las operaciones sobre la imagen se realicen de forma controlada.

#### `read_cluster()`

Solicita al `DiskWorker` leer un clúster completo de 2048 bytes.

#### `write_cluster()`

Solicita al `DiskWorker` escribir un clúster completo. Si los datos son menores al tamaño del clúster, se rellenan con ceros.

#### `read_bytes()`

Solicita al `DiskWorker` leer una cantidad específica de bytes desde una posición exacta de la imagen.

#### `stop()`

Detiene el hilo trabajador.

Cambia el estado de ejecución y coloca una tarea `None` en la cola para desbloquear el hilo en caso de que esté esperando nuevas tareas.

### `requerimientos.txt`

Este archivo contiene la dependencia principal de Python necesaria para ejecutar el proyecto:

```text
fusepy==3.0.1
```

`fusepy` permite que Python se comunique con FUSE y pueda implementar operaciones de sistema de archivos en espacio de usuario.

### `.gitignore`

Este archivo sirve para evitar que se suban al repositorio archivos temporales o generados durante la ejecución del proyecto.

Por ejemplo, se recomienda ignorar elementos como:

- Entornos virtuales.
- Archivos `__pycache__`.
- Archivos de prueba.
- Copias temporales de la imagen.
- Directorios de montaje.

## Pruebas

## Conclusiones
## Pruebas

Para realizar las pruebas se montó la imagen `fiunamfs.img` en un directorio llamado `mnt`. De esta forma fue posible interactuar con el sistema de archivos usando comandos comunes de Linux.

### Preparación del entorno de pruebas

Para evitar modificar directamente la imagen original, se recomienda trabajar con una copia:

```bash
cp ../fiunamfs.img ./fiunamfs-prueba.img
mkdir -p mnt
python main.py mnt ./fiunamfs-prueba.img
```

Mientras el programa se encuentra en ejecución, se abre otra terminal en la misma carpeta del proyecto para probar las operaciones sobre el directorio `mnt`.

### Operación 1: Listar archivos

Comando utilizado:

```bash
ls -la mnt
```

Resultado obtenido:

```text
logo.png
mensaje.jpg
README.org
```

Con esta prueba se verificó que el sistema puede leer correctamente el directorio de `FiUnamFS` y mostrar los archivos almacenados dentro de la imagen.

### Operación 2: Copiar un archivo desde FiUnamFS hacia Linux

Comando utilizado:

```bash
cp mnt/README.org README_copiado.org
ls -la README_copiado.org
```

Resultado esperado:

El archivo `README_copiado.org` debe aparecer en la carpeta del proyecto como una copia del archivo almacenado dentro de `FiUnamFS`.

Esta prueba verifica que el sistema puede leer el contenido de un archivo dentro de la imagen y copiarlo hacia el sistema operativo anfitrión.

### Operación 3: Copiar un archivo desde Linux hacia FiUnamFS

Comandos utilizados:

```bash
echo "hola desde arch" > prueba.txt
cp prueba.txt mnt/prueba.txt
ls -la mnt
cat mnt/prueba.txt
```

Resultado esperado:

El archivo `prueba.txt` debe aparecer dentro del directorio montado `mnt` y su contenido debe ser:

```text
hola desde arch
```

Esta prueba verifica que el sistema puede crear una nueva entrada en el directorio de `FiUnamFS`, asignar espacio dentro de la imagen y escribir el contenido del archivo.

### Operación 4: Eliminar un archivo dentro de FiUnamFS

Comandos utilizados:

```bash
rm mnt/prueba.txt
ls -la mnt
```

Resultado esperado:

El archivo `prueba.txt` ya no debe aparecer dentro de `mnt`.

Esta prueba verifica que el sistema puede eliminar una entrada del directorio y liberar el espacio correspondiente dentro del sistema de archivos.

### Casos extremos

Además de las operaciones principales, se consideran los siguientes casos extremos para comprobar la estabilidad del sistema.

#### Archivo inexistente

Comando:

```bash
cat mnt/noexiste.txt
```

Resultado esperado:

El sistema debe indicar que el archivo no existe y no debe terminar de forma inesperada.

#### Nombre de archivo demasiado largo

Comandos:

```bash
echo "prueba" > archivo_con_nombre_demasiado_largo.txt
cp archivo_con_nombre_demasiado_largo.txt mnt/
```

Resultado esperado:

El sistema debe rechazar el archivo o manejar el error correctamente, ya que `FiUnamFS` maneja nombres de archivo con longitud limitada.

#### Copiar directorios

Comandos:

```bash
mkdir carpeta_prueba
cp -r carpeta_prueba mnt/
```

Resultado esperado:

El sistema no debe permitir copiar directorios, ya que `FiUnamFS` maneja un directorio plano y no contempla subdirectorios.

#### Archivo duplicado

Comandos:

```bash
echo "primera version" > repetido.txt
cp repetido.txt mnt/repetido.txt
cp repetido.txt mnt/repetido.txt
```

Resultado esperado:

El sistema debe evitar inconsistencias al intentar copiar un archivo con un nombre que ya existe dentro de `FiUnamFS`.

#### Falta de espacio

Prueba recomendada:

Copiar archivos grandes hacia `mnt` hasta superar el espacio disponible dentro de la imagen.

Resultado esperado:

El sistema debe rechazar la escritura cuando no exista espacio suficiente y no debe corromper la imagen del sistema de archivos.

### Limpieza después de pruebas

Al terminar las pruebas se desmonta el sistema de archivos:

```bash
fusermount -u mnt
```

En caso de error:

```bash
sudo umount mnt
```

Después se eliminan los archivos temporales:

```bash
rm -f prueba.txt README_copiado.org fiunamfs-prueba.img
rm -rf carpeta_prueba
```

Finalmente, se revisa el estado del repositorio:

```bash
git status
```

El resultado esperado es:

```text
nothing to commit, working tree clean
```

## Conclusiones

El desarrollo de este proyecto permitió comprender de manera práctica cómo se organiza internamente un sistema de archivos. A diferencia del uso cotidiano de archivos y carpetas desde el sistema operativo, en este proyecto fue necesario trabajar directamente con una imagen binaria, interpretar su superbloque, recorrer su directorio y ubicar el contenido de los archivos dentro de la zona de datos.

El uso de FUSE facilitó la interacción con `FiUnamFS`, ya que permitió montar la imagen como si fuera un directorio normal del sistema. Gracias a esto, operaciones comunes como `ls`, `cp`, `cat` y `rm` pudieron utilizarse para probar el funcionamiento del sistema de archivos.

También se reforzó la importancia de la sincronización en operaciones concurrentes. Al trabajar con una imagen compartida, es necesario evitar que dos operaciones modifiquen al mismo tiempo la estructura del sistema de archivos, ya que esto podría provocar inconsistencias o corrupción de datos.

Una parte interesante del desarrollo se relaciona con la exposición realizada sobre **GPU y sistemas operativos**. En ambos casos se observa que no todos los componentes de software funcionan de la misma forma en todos los sistemas operativos. Así como en el tema de GPU existen dependencias, controladores y capas de compatibilidad específicas para cada entorno, en este proyecto se observó que herramientas como FUSE están pensadas principalmente para sistemas tipo UNIX/Linux.

Esto muestra la importancia de considerar la naturaleza del sistema operativo al desarrollar software de bajo nivel. La compatibilidad no depende únicamente del lenguaje de programación, sino también de las bibliotecas disponibles, el tipo de sistema de archivos, las llamadas al sistema y la forma en que cada sistema operativo maneja recursos como archivos, permisos y dispositivos.

En conclusión, el proyecto permitió integrar temas de sistemas de archivos, procesos, concurrencia y compatibilidad entre sistemas operativos. Además, ayudó a comprender que el diseño de software cercano al sistema depende fuertemente del entorno donde se ejecuta.
