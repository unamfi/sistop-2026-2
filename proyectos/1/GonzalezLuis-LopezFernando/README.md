# Proyecto: (Micro) Sistema de Archivos Multihilos - FiUnamFS

>Diseño e implementación de un sistema de archivos virtual y multihilos que manipula un archivo imagen (disco virtual) llamado `fiunamfs.img`. Esto para la asignatura `0840`: "*Sistemas Operativos*" de la carrera de Ingeniería en Computación de la Facultad de Ingeniería de la Universidad Nacional Autónoma de México.
# Autores
- González Falcón Luis Adrián
- López Morales Fernando Samuel

| Contenido                                                                               |
| --------------------------------------------------------------------------------------- |
| [Descripción](#Descripción)                                                             |
| [Requisitos](#Requisitos)                                                               |
| [Secuencia de ejecución](#Secuencia%20de%20ejecución)                                   |
| [Ejemplos de Uso](#Ejemplos%20de%20Uso)                                                 |
| [Estrategia principal seguida](#Estrategia%20principal%20seguida)                       |
| [Lógica principal e Implementación](#Lógica%20principal%20e%20Implementación)           |
| [Comandos útiles durante el desarrollo](#Comandos%20útiles%20durante%20el%20desarrollo) |

---
# Descripción
El programa  implementa 4 funcionalidades inherentes de un sistema de archivos:
1. Lista contenidos del directorio
2. Copia un archivo $a$ originario del `FiUnamFS` hacia el sistema del usuario
3. Copia un archivo $b$ originario del sistema del usuario hacia dentro de `FiUnamFS`[^1]
4. Elimina un archivo cualquiera $v$ dentro de `FiUnamFS`
- Además, maneja una lógica de 2 hilos: hilo principal y trabajador, para manejar concurrencia sobre un elemento de memoria (el disco en sí)
- Finalmente, como interfaz implementa el módulo de FUSE, que permite montar el disco en un directorio y ejecutar los comandos convencionales para las 3 acciones anteriores: `ls`, `cp`, `rm` para manejar las 4 funcionalidades

El software proporciona una capa funcional completa que permite interactuar con el almacenamiento virtualizado mediante llamadas nativas del sistema operativo anfitrión (Linux)  a través de **FUSE (Filesystem in Userspace)**, delegando las peticiones concurrentes del espacio de kernel hacia un proceso seguro en el espacio de usuario, el cual coordina las lecturas y escrituras atómicas en el medio binario sin comprometer la integridad global de la unidad virtual.

## Desglose del mapa de memoria y estructuras de datos
El sistema `FiUnamFS` organiza la información del almacenamiento virtual en bloques lógicos llamados **Clusters**.

El tamaño base de cada **cluster** está parametrizado dinámicamente por la lectura inicial, pero el diseño de referencia establece un estándar de **2048 bytes** por bloque. 

El almacenamiento completo está dividido de manera estricta en tres grandes regiones: 
- Superbloque
- Directorio
- Zona de Datos

>Es importante notar que los números enteros están en formato *little-endian*, lo que significa que los primeros bits que aparezcan (izquierda a derecha) son los menos significativos.
>Así, la secuencia `0008 0000` es realmente: `0800`, que si convertimos de hexadecimal a decimal da $2048$.

### El Superbloque (Cluster 0)
Ocupa los primeros **2048** bytes del disco virtual (Cluster 0). Su propósito es almacenar los metadatos globales de la unidad, permitiendo identificar la firma del sistema de archivos, su versión y las dimensiones físicas de sus particiones estructurales. 

A continuación se detalla el mapa de memoria del Superbloque:

| Rango de Bytes | Tamaño (Bytes) | Descripción Semántica                                                                                                          |
| :------------- | :------------: | :----------------------------------------------------------------------------------------------------------------------------- |
| **0 – 4**      |       5        | Cuatro bytes de control iniciales (`\x00\x00\x00\x00`).                                                                        |
| **5 – 13**     |       9        | Firma de identificación del sistema de archivos. Valida estrictamente que contenga la cadena exacta `FiUnamFS`.                |
| **14 – 18**    |       5        | Versión de la implementación. Valida de forma exacta la cadena de texto `26-2` para mitigar riesgos de corrupción estructural. |
| **20 – 35**    |       16       | Etiqueta del volumen (Texto arbitrario de interés exclusivo para el usuario).                                                  |
| **40 – 44**    |       4        | Tamaño del cluster en bytes (Almacenado en formato Little Endian).                                                             |
| **50 – 54**    |       4        | Número de clusters asignados formalmente para medir y contener el directorio de la unidad (Little Endian).                     |
| **60 – 64**    |       4        | Número total de clusters que mide la unidad completa (Little Endian).                                                          |

Para la imagen original `FIUnamFS.img`, usando el [comando `xxd`](#Ver%20el%20mapa%20de%20memoria%20con%20`xxd`) se puede visualizar de manera directa el rango de bytes del **superbloque**
![](Anexos/Pasted%20image%2020260521221630.png)

### El Directorio (Del Cluster 1 al 8)
La región del directorio está ubicada de manera contigua inmediatamente después del superbloque. Su dimensión se define dinámicamente por el parámetro de clusters del directorio indicado en el superbloque (típicamente 8 clusters). La información interna se divide de forma fija en registros homogéneos denominados **Entradas de Directorio**, donde cada registro tiene una longitud exacta de **64 bytes**. 

El formato estructurado binario sigue de forma estricta la convención de empaquetado del lenguaje C:
```python
FORMATO_ENTRADA = "<c15sII6x14s6x14s"
```
distribuido minuciosamente bajo el siguiente mapa de memoria:

| Rango de Bytes, ambos extremos incluyentes | Tamaño (Bytes) | Formato `struct` | Propósito Estructural                                                                                                                                          |
| :----------------------------------------- | :------------: | :--------------: | :------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **0**                                      |       1        |       `c`        | **Tipo de entrada:** El carácter `-` representa un archivo regular activo, mientras que el carácter `/` indica una entrada vacía o eliminada de manera lógica. |
| **1 – 14**                                 |       15       |      `15s`       | **Nombre del archivo:** Nombre en formato ASCII, rellenado internamente con caracteres `#` o nulos de ser menor al límite.                                     |
| **16 – 19**                                |       4        |       `I`        | **Tamaño del archivo:** Entero de 32 bits sin signo en formato Little Endian que almacena el peso exacto del archivo expresado en bytes.                       |
| **20 – 23**                                |       4        |       `I`        | **Cluster inicial:** Entero de 32 bits sin signo en formato Little Endian que apunta al índice del bloque físico donde comienzan los datos del archivo.        |
| **24 – 29**                                |       6        |       `6x`       | Se ignoran                                                                                                                                                     |
| **30 – 43**                                |       14       |      `14s`       | **Fecha de creación:** Cadena ASCII que representa la fecha y hora bajo el formato compacto y cronológico `AAAAMMDDHHMMSS`.                                    |
| **44 – 49**                                |       6        |       `6x`       | Se ignoran                                                                                                                                                     |
| **50 – 63**                                |       14       |      `14s`       | **Fecha de modificación:** Cadena ASCII que indica la fecha de última modificación bajo el mismo formato cronológico `AAAAMMDDHHMMSS`.                         |
Note como en el siguiente mapa de memoria, se aprencian los nombres de los 3 archivos que se encuentran en el `fiunamfs.img` original:
- `README.org`
- `logo.png`
- `mensaje.jpg`
![](Anexos/Pasted%20image%2020260521222000.png)
### Zona de Datos
Aquí se guardan todos los datos (binarios) de los archivos listados en [el directorio)](#El%20Directorio%20(Del%20Cluster%201%20al%208))

# Requisitos
>El programa fue desarrollado y escrito para sistemas Linux, con **distribuciones basadas en Arch**

El equipo donde se va a ejecutar el programa debe tener:
- Python 3
- [Modulo de Fuse en python](#Modulo%20de%20Fuse%20en%20python)
## Entornos y dependencias
### Modulo de Fuse en python
Para instalar, escribir en una línea de comandos:
```bash
sudo pacman -S python-fuse
```

Esto instalará el módulo de python necesario para poder ejecutar el programa.

# Secuencia de ejecución
>Una vez que se cubren los [Requisitos](#Requisitos), se pueden ejecutar los siguientes comandos en dicho orden para poder ejecutar el sistema de archivos:

1. Crear el punto de montaje virtual
```
mkdir mnt
```
2. Ejecutar pasando como argumento el punto de montaje
```bash
python3 main.py mnt
```
3. Ahora ya puedes ejecutar `ls`, `cp`, `rm` sobre `mnt`, pues se espera que lo que se haga dentro de mnt es como si se hiciese a `fiunamfs.img`

>OJO: Esto fuerza al usuario a tener que abrir otra terminal para poder moverse y hacer cosas en el directorio, si se quiere hacer todo en la misma terminal:

```bash
python3 main.py mnt &
```
## Secuencia de desmonteo
Para terminar el programa de manera correcta:
```bash
umount mnt
```
siendo `mnt` el directorio donde se monto en los pasos anteriores
# Ejemplos de Uso
## Listar directorio
>Con `-la`
![](Anexos/Pasted%20image%2020260521233118.png)

## Copiar de PC a disco
![](Anexos/Pasted%20image%2020260521233232.png)
>Note como con el [comando `xxd`](#Ver%20el%20mapa%20de%20memoria%20con%20`xxd`) podemos ver en el rango de 2048 a 2048+640, 10 entradas del directorio (pues 1 mide 64). En ella se ve el codigo.py insertado.

![](Anexos/Pasted%20image%2020260521233403.png)
>Se puede comprobar que haciendo las matemáticas correctas de little endian, el comando `xxd` en los rangos de la imagen de arriba, mapean exactamente el archivo en [Zona de Datos](#Zona%20de%20Datos) así como lo indica su entrada en la imagen anterior. Note el contenido totalmente legible.

### Otro ejemplo con pdf
![](Anexos/Pasted%20image%2020260521233543.png)

>Es importante notar que el pdf:
>- Tiene un nombre corto
>- Su tamaño no es muy grande
>De lo contrario, no se podría insertar en el disco

![](Anexos/Pasted%20image%2020260521233719.png)

>Note que inclusive el pdf se puede abrir (desde mnt) en un navegador

## Copiar de Disco a PC
![](Anexos/Pasted%20image%2020260521233906.png)

![](Anexos/Pasted%20image%2020260521233910.png)

>Note que el contenido está integro


## Eliminar archivo
![](Anexos/Pasted%20image%2020260521233932.png)
>El archivo se ha borrado, se confirma con un `ls`

### Otro ejemplo
![](Anexos/Pasted%20image%2020260521234024.png)
![](Anexos/Pasted%20image%2020260521234029.png)

### Mapa de memoria con todos los archivos borrados
![](Anexos/Pasted%20image%2020260521234447.png)
>Note el `/` al principio de todas las entradas, indicando que ya no hay archivo allí

# Estrategia principal seguida
Se tienen 2 archivos: 
- `fiunamfs.py`: para lógica
- `main.py`: maneja hilos y FUSE

Se priorizaron en el siguiente orden las tareas:
- Con interfaz en Línea de comando
	- Lógica (4 funcionalidades de un sistema de archivos)
	- Pasar a lógica con hilos
- Con FUSE integrado
	- Traducir lo necesario de cada funcionalidad para que FUSE y linux pudiesen entender

# Lógica principal e Implementación
## Principales funcionalidades
El sistema funciona mediante la implementación de *productor-consumidor*. La interfaz de FUSE recibe las peticiones del sistema operativo y mediante las variables globales y la sincronización, se delegan los procesos a **hilo_trabajador** el cual es el responsble de manipular directamente la imagen de disco.
Dentro de ***fiunamfs.py*** Se realizaron cuatro implementaciones los cuales se describen a continuación:
### 1. Listar directorio.
Se posiciona en el cluster 1 de la imagen, donde recorre de forma secuencial las 256 entradas posibles calculadas en base a los 8 cluster que cuenta la imagen. Se desempaqueta con formato \<c15sII6x14s6x14s en cada  registro. Si el tipo de archivo es -, parsea metadatos como el tamaño, cluster inicial y realiza las conversiones de fecha.
#### Para FUSE
FUSE entra en las llamadas tipo *ls*. El método readdir de la clase FiUnamFS_FUSE realiza la orden de "listar_fuse", donde se despierta el hilo trabajador y espera el diccionario de resultados. Después, mediante *yield*, inserta las entradas . y .. al sistema operativo.

### 2. Copiar del Disco al PC
Recurre a la función *leer_bytes_archivo* donde recibe el nombre del archivo, su tamaño en bytes y el offset. Valida la existencia, calcula la posición física real en el disco usando la siguiente fórmula
$$\text{Posición Física} = (\text{Cluster Inicial} \times \text{Tamaño Cluster}) + \text{Offset}$$
Después lee y retorna la cadena de bytes solicitada sin exceder el fin del archivo.
#### Para FUSE
En FUSE se vincula directamente al método *read*. Cada vez que se intenta leer un archivo, FUSE solicita fragmentos específicos. Se empaquetan mediante la función "leer_fuse" y retorna los bytes devueltos por el hilo TRABAJADOR.


### 3. Copiar del PC al Disco
Se recurre la función "escribir_desde_buffer", este recibe un bloque entero de bytes junto al nombre deseado. Si el archivo existe, se elimina para reajustar el mapa. Calcula los cluster necesarios y busca espacio contiguo suficiente donde pueda caber. Si lo encuentra, escribe los bytes directamente.
#### Para FUSE
Se integra un método llamado "buffers_escritura" donde las operaciones *truncate, create o write* van moldeando el buffer y se efectúan en el momento que el sistema operativo realiza **release**, mediante el hilo TRABAJADOR se implementan los datos en la imagen.


### 4. Eliminar Archivo
Se realiza mediante la función *eliminar_archivo*. Se realiza una busqueda lineal sobre las entradas del directorio. Cuando se encuentra el nombre del archivo, se posiciona en el inicio de la entrada y sobreescribe los primeros 16 bytes, se sustituye el nombre del archivo con caracteres # . Esto va a invalidar el archivo par alas lecturas posteriores y libera espacio de forma automática.
#### Para FUSE
FUSE aparece cuando el usuario ejecuta un comando para borrar como "rm". Se mapea mediante el método *unlink*, donde manda la instrucción *eliminar_fuse* con el nombre del archivo y espera la confirmación del hilo TRABAJADOR, donde retorna 0 si todo salió bien, o error si el archivo no existe.

## FUSE

| Material utilizado para entender FUSE                                                                                                                        |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [Clase del 28 de abril del semestre 2026-2](https://www.youtube.com/watch?v=7XZVRWwX1Ec)                                                                     |
| [Aprendiendo y enseñando a escribir sistemas de archivos en espacio de usuario con FUSE y Python - Gunnar Wolf](https://www.youtube.com/watch?v=2t9EvJaKVac) |
| [Gitlab FUSE Wolf](https://gitlab.com/gunnarwolf/fuse_in_python_guide)                                                                                       |

| Funcionalidad Principal                                        | Método FUSE        | ¿Por qué el SO lo llama?                                                 | ¿Qué implementamos / re-definimos?                                                                                                            |
| :------------------------------------------------------------- | :----------------- | :----------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------- |
| **Copiar PC $\rightarrow$ Disco** <br>*(Escritura / Creación)* | `create` / `mknod` | Notifica la creación de un nuevo archivo.                                | Inicializa un buffer en memoria RAM (`b''`) para ese archivo en el diccionario `buffers_escritura`.                                           |
|                                                                | `truncate`         | Prepara el archivo para ser modificado o sobreescrito.                   | Limpia o reinicia el buffer del archivo en RAM a vacío.                                                                                       |
|                                                                | `write`            | Envía el archivo en ráfagas (pedazos de bytes) asíncronas.               | Concatena los bytes entrantes (`buf`) en la posición correcta (`offset`) dentro del buffer en RAM, sin tocar el disco aún.                    |
|                                                                | `release`          | Avisa que terminó de enviar datos y cierra el archivo.                   | **Detonante:** Envía la orden `"escribir_fuse"` al hilo trabajador con el buffer completo para guardarlo en la imagen física y libera la RAM. |
| **Listar Directorio** <br>*(Metadatos e Inspección)*           | `getattr`          | Interroga los atributos (tamaño, permisos, fechas) de una ruta.          | Revisa si el archivo está en RAM o pide `"listar_fuse"` al trabajador. Retorna un objeto `st` con permisos simulados y metadatos reales.      |
|                                                                | `readdir`          | Solicita los elementos contenidos dentro de una carpeta.                 | Pide la lista al hilo trabajador y usa `yield` para entregarle al sistema operativo el contenido junto con `.` y `..`.                        |
| **Copiar Disco $\rightarrow$ PC** <br>*(Lectura)*              | `open`             | Verifica si el archivo se puede abrir para lectura.                      | Retorna `0` (éxito) para darle luz verde al sistema operativo.                                                                                |
|                                                                | `read`             | Pide fragmentos exactos (`size`) desde una posición (`offset`).          | Envía la orden `"leer_fuse"` al trabajador para extraer los bytes físicos exactos del disco virtual y los retorna.                            |
| **Eliminar Archivo**                                           | `unlink`           | Se detona al usar el comando `rm` para borrar un archivo.                | Limpia la ruta (quita el `/`) y delega la orden `"eliminar_fuse"` al hilo trabajador para invalidar la entrada.                               |
| **Compatibilidad**                                             | `chmod` / `chown`  | Intentos de comandos externos (como `cp -p`) de cambiar dueños/permisos. | Retornan `0` siempre. Engañan al SO indicando éxito para evitar bloqueos por "Operación no permitida".                                        |
## Mecanismo de sincronización
Para este proyecto se la **Señalización**, donde se emplean dos semaforos iniciados en 0 (`sem_orden_pendiente` y `sem_orden_terminada`) . FUSE envía una orden y despierta al hilo secundario.
Se protege el acceso al disco `fiunamfs.img` mediante ***mutex***, esto evita condiciones de carrera si se intenta acceder al disco dos veces al mismo tiempo, por ejemplo para listar elementos y borrar un archivo.

## Acerca del módulo de FUSE
Para poder usar FUSE, se requiere un *punto de montaje*, para esto:
1. Creamos una carpeta vacía que servirá como portal al disco `fiunamfs.img`:
```bash
mkdir mnt
```
2. Ejecutamos el script pasandole como argumento la carpeta anteriormente creada:
```bash
python3 fiunamfs_fuse.py mnt
```

Ahora podemos navegar esta carpeta como si fuera el disco, siendo que si ejecutamos por ejemplo `ls -l`, estaremos listando el contenido dentro de `fiunamfs.img`


---
# Comandos útiles durante el desarrollo

## Ver el mapa de memoria con `xxd`
>Durante el desarrollo, antes de implementar cualquier función o clase, inspeccionamos el mapa de memoria del archivo imagen para entender bien lo que estaba pasando con el Superbloque, el directorio, etc

```bash
xxd -s 2048 -l 640 fiunamfs.img
```

>El comando anterior muestra el mapa de memoria del directorio, para las primeras 10 entradas 

**Forma general**
```bash
xxd -s <byte_inicial> -l <cantidad_de_bytes> <archivo_a_leer> | less
```

De esta forma pudimos inspeccionar las entradas de los directorios y con `| less` la parte de datos (que tiende a ser más extensa).

### Explorar el contenido de un archivo de acuerdo a:

Sean:
- $s_v$: tamaño del archivo $v$
- $C_{i_{v}}$: : cluster inicial del archivo $v$

Todos en `bytes`
El rango del contenido de un archivo es: $[C_{i_{v}}, C_{i_{v}} + s_v]$

```bash
xxd -s <c_i_v> -l <s_v> fiunamfs.img | less
```

[^1]: FiUnamFS se refiere al archivo `.img`
