PROYECTO 1 - MéridaFrancisco - QuezadaLeonardo


#  PROYECTO SITEMA DE ARCHIVOS

## DESCRIPCION

En este proyecto implementamos una versión funcional del microsistema de archivos FiUnamFS. El objetivo fue poder leer, modificar y administrar los archivos almacenados dentro de esa imagen respetando la estructura indicada en la especificación.

Primero nos enfocamos en entender cómo estaba organizada la imagen. Para esto implementamos la clase ImagenFiUnamFS, que se encarga de abrir el archivo .img, validar el superbloque y obtener datos importantes como el tamaño del cluster, la cantidad de clusters del directorio y el número total de clusters del sistema.

Después agregamos la lectura del directorio. Como FiUnamFS utiliza un directorio plano, cada entrada se interpreta de forma individual a partir de bloques de 64 bytes. Para manejar mejor esta información, implementamos la clase RegistroDirectorio, que representa cada archivo con sus datos principales: nombre, tamaño, cluster inicial y fechas.

Una vez que logramos listar correctamente los archivos, agregamos las operaciones principales del sistema. Implementamos la lectura de archivos desde la imagen, la copia de archivos del sistema local hacia FiUnamFS y la eliminación lógica de archivos. Para copiar archivos hacia la imagen también agregamos la búsqueda de entradas libres en el directorio y la búsqueda de clusters contiguos disponibles, ya que FiUnamFS almacena los archivos usando asignación contigua.


## ARCHIVOS UTILIZADOS

### config_fiunamfs.py
En este archivo agregamos las constantes principales del sistema de archivos. Aquí se definen valores como el tamaño del sector, el tamaño del cluster, los offsets del superbloque, el tamaño de cada entrada del directorio y los valores usados para identificar entradas libres o archivos válidos

### registro_directorio.py

En este archivo implementamos la clase RegistroDirectorio, que representa una entrada del directorio de FiUnamFS.

Cada entrada del directorio mide 64 bytes, por lo que esta clase se encarga de interpretar esos bytes, y obtener datos como el nombre del archivo, tamaño y cluster inicial

### imagen_fiunamfs.py

Aquí implementamos la clase ImagenFiUnamFS, encargada de abrir la imagen .img, validar el superbloque, leer el directorio y realizar las operaciones principales sobre los archivos.
También usamos un RLock para proteger el acceso a la imagen cuando se hacen operaciones de lectura o escritura.

### trabajador.py

Este archivo se usa para la interfaz gráfica.

Aquí agregamos un hilo trabajador que recibe tareas desde la ventana, como listar, copiar, extraer o eliminar archivos. La idea es que la interfaz no haga directamente las operaciones, para evitar que se congele.

La comunicación entre la interfaz y el trabajador se hace mediante colas

### interfaz.py

En este archivo implementamos la interfaz gráfica usando tkinter.

La interfaz muestra una lista con los archivos almacenados en FiUnamFS y permite realizar operaciones mediante botones:

- actualizar lista;
- extraer archivo;
- copiar archivo hacia FiUnamFS;
- eliminar archivo.

Esta interfaz usa trabajador.py para ejecutar las operaciones en un hilo separado.

### FUSE.py

Este archivo implementa el montaje de FiUnamFS usando FUSE.

Con este archivo podemos montar la imagen en una carpeta (en este caso usamos la carpeta montaje) y usar comandos normales del sistema, como: ls, cat, cp y rm.

## ESTRUCTURA DE FiunamFS

FiUnamFS trabaja sobre una imagen binaria de tamaño fijo. Se divide en 

 ZONA | DESCRIPCION |
| ------------- | ------------- |
| Cluster 0 | Superbloque |
| Cluster 1-8 | Directorio para guardar las entradas de los archivos |
| El resto | Zona de datos |

### superbloque 

 OFFSET | DESCRIPCION |
| ------------- | ------------- |
| 5 | Nombre del sistema |
| 14 | Version de la imagen |
| 20 | Etiqueta del volumen |
| 40 | Tamaño del cluster |
| 50 | Cantida de clusters del directorio |
| 60 | Total de clusters de la imagen |

Los valores numéricos se leen como enteros de 32 bits en formato little endian, por lo que en Python se utilizamos struct.unpack("<I", ...).

### Formato de entrada de directorio 
Cada entrada del directorio mide 64 bytes. En cada una se almacena la información necesaria para localizar y leer un archivo dentro de la imagen.

 Bytes | DESCRIPCION |
| ------------- | ------------- |
| 0 | Tipo de entrada. Si es . es archivo, y / indica entrada libre |
| 1-15 | Nombre del archivo en ASCII |
| 16-19 | Tamaño del archivo en bytes |
| 20-23 | Cluster inicial del archivo |
| 30-43 | Fecha de creación |
| 50-63 |Fecha de modificación |

Los valores numéricos se leen como enteros de 32 bits en formato little endian, por lo que en Python se utilizamos struct.unpack("<I", ...).

Las entradas libres también se identifican porque el campo de nombre contiene: ##########################

Esta estructura fue necesaria para implementar las operaciones principales del proyecto. Para listar archivos, se recorren las entradas del directorio. Para leer un archivo, se toma su cluster inicial y su tamaño. Para copiar un archivo nuevo hacia FiUnamFS, primero se busca una entrada libre y después se localiza un bloque contiguo de clusters disponibles. Para eliminar un archivo, se marca su entrada como libre.

## FORMAS DE USO

Para interactuar con el sistema agregamos dos formas.

La primera fue una interfaz gráfica usando tkinter. En esta interfaz mostramos la lista de archivos dentro de la imagen y agregamos botones para actualizar, extraer, copiar y eliminar archivos. 

También agregamos un hilo trabajador para la interfaz gráfica. Con esto, el hilo principal mantiene activa la ventana, mientras que el hilo secundario realiza las operaciones sobre la imagen. Esta decisión nos ayudó a evitar que la interfaz se congelara al copiar o extraer archivos.

La segunda forma de uso fue mediante FUSE. Implementamos un módulo que permite montar la imagen en una carpeta. De esta manera podemos usar comandos normales del sistema, como:

1. ls montaje
2. cat montaje/README.org
3. cp archivo.txt montaje/
4. rm montaje/archivo.txt

## CONCURRENCIA

Para manejar la concurrencia agregamos un RLock dentro de la clase ImagenFiUnamFS. Esto fue necesario porque tanto la interfaz gráfica como FUSE pueden ejecutar operaciones de lectura o escritura sobre la imagen. El candado evita que dos operaciones modifiquen el archivo .img al mismo tiempo.

En la interfaz gráfica, además, usamos colas para comunicar el hilo principal con el hilo trabajador. El hilo principal envía tareas como listar, copiar, extraer o eliminar, y el hilo trabajador las procesa y regresa el resultado a la ventana.

## Requisitos de uso

Desarrollamos el proyecto en en un entorno Linux (UBUNTU).

### Uso de interfaz gráfica. 

Para este caso, únicamente es necesario usar 

``` python3 interfaz.py ```

### Para uso con FUSE 

Primero se deben instalar las dependencias necesarias:

Nosotros probamos hacer la instalación y el uso del archivo FUSE.py en un entorno virtual. Con las siguientes instrucciones puede ser instalado :

``` 
sudo apt install python3-venv
python3 -m venv venv
source venv/bin/activate
pip install fusepy
```

Y debe existir un directorio en donde se pueda montar la imagen. En este caso incluimos la carpeta montaje para ello.


Posteriormente, se ejecuta el archivo FUSE.py de la forma:

``` 
python3 FUSE.py fiunamfs.img montaje
```

Esto congela la terminal. Para poder usar el monatje realizado, abrir otra terminal en la misma carpeta. A partir de ahí, se puede usar el montaje en el directorio "montaje" para interactuar con la imagen.

Se pueden usar instrucciones como

``` 
ls montaje
cat montaje/README.org | head
cp <archivo> montaje/
rm montaje/<archivo> 
```
### EJEMPLO DE USO

### Implementación con interfaz gŕafica "python3 interfaz.py"

![](https://github.com/franciscomeridaserralde/Repositorio-Clase-sistop-2026-2/blob/main/proyecto/FUSE/imagenes_readme/EjecucionInterfaz.png?raw=true)

Extracción de archivo:

Comrpobación:

![](https://github.com/franciscomeridaserralde/Repositorio-Clase-sistop-2026-2/blob/main/proyecto/FUSE/imagenes_readme/Comprobacion.png?raw=true)

### Implementación con FUSE

Primero se tiene que hacer la instalación de FUSE en un entorno virtual

![](https://github.com/franciscomeridaserralde/Repositorio-Clase-sistop-2026-2/blob/main/proyecto/FUSE/imagenes_readme/EntornoVirtualFuse.png?raw=true)

Posteriormente, abrir otra terminal en el mismo directorio, y se pueden realizar acciones como las siguientes 

![](https://github.com/franciscomeridaserralde/Repositorio-Clase-sistop-2026-2/blob/main/proyecto/FUSE/imagenes_readme/EjemplosFUSE.png?raw=true)

## Archivos extraidos de la imagen

![](https://github.com/franciscomeridaserralde/Repositorio-Clase-sistop-2026-2/blob/main/proyecto/FUSE/imagenes_readme/logo.png?raw=true)

![](https://github.com/franciscomeridaserralde/Repositorio-Clase-sistop-2026-2/blob/main/proyecto/FUSE/imagenes_readme/mensaje.jpg?raw=true)





