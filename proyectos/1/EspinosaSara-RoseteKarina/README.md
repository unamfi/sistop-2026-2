# Proyecto 1: Sistema de archivos multihilos "FiUnamFS"


## Integrantes

- EsEspinosa González Sara Sofia
- Rosete Mazano Karina Lizeth

------------------------------------------------------------------------

# 1. Especificaciones del proyecto

El proyecto implementa un microsistema de archivos basado en FiUnamFS usando el archivo `fiunamfs.img` como disco virtual.

Las funciones implementadas son:

1.  Listar contenidos.
2.  Copiar archivos desde FiUnamFS a la PC.
3.  Copiar archivos desde la PC a FiUnamFS.
4.  Eliminar archivos.
5.  Implementar hilos concurrentes sincronizados.

------------------------------------------------------------------------
# 2. Estrategia de implementación

Para facilitar el desarrollo y mantenimiento del proyecto, se decidió dividir la solución en módulos independientes, donde cada archivo tiene una responsabilidad específica.

La implementación se realizó directamente sobre el archivo:

```text
fiunamfs.img
```

Este archivo funciona como un disco virtual y contiene toda la información del sistema de archivos. El programa no genera estructuras adicionales fuera del archivo, sino que trabaja directamente sobre los datos almacenados en él.

Las operaciones de lectura y escritura se realizan mediante acceso binario utilizando funciones del lenguaje C.

Funciones utilizadas:

```c
fopen()
fseek()
fread()
fwrite()
fclose()
```

Estas funciones permiten desplazarse a posiciones específicas dentro del archivo y leer o modificar directamente los bytes correspondientes.

---

## Organización del proyecto

La estructura final del proyecto quedó organizada de la siguiente manera:

```text
Proyecto/

│
├── src/
│   ├── main.c
│   ├── fiunamfs.c
│   ├── fiunamfs.h
│   └── fuse_main.c
│
├── fiunamfs.img
├── README.md
├── .gitignore
└── Makefile
```

Descripción de cada archivo:

### main.c

Contiene la lógica principal del programa.

Responsabilidades:

- Mostrar el menú al usuario.
- Recibir entradas desde teclado.
- Crear solicitudes.
- Inicializar hilos.
- Administrar sincronización.
- Enviar tareas a la cola compartida.

Este módulo no realiza operaciones directas sobre el disco virtual; únicamente coordina el funcionamiento general.

---

### fiunamfs.c

Implementa todas las operaciones relacionadas con el sistema de archivos.

Responsabilidades:

- Abrir el archivo de disco virtual.
- Validar nombre y versión de FiUnamFS.
- Leer entradas del directorio.
- Buscar archivos.
- Localizar espacio disponible.
- Copiar archivos hacia el equipo local.
- Copiar archivos hacia FiUnamFS.
- Eliminar archivos.
- Actualizar información del directorio.

La mayoría de las operaciones importantes del proyecto se implementaron en este módulo.

---

### fiunamfs.h

Archivo de encabezado utilizado para compartir estructuras y funciones entre módulos.

Contiene:

- Definición de estructuras.
- Constantes.
- Tamaños de directorio.
- Tipos de datos.
- Prototipos de funciones.

Esto evita duplicación de código y permite una estructura más organizada.

---

### fuse_main.c

Este archivo contiene la integración con FUSE para Linux.

Su función es permitir que:

```text
fiunamfs.img
```

pueda montarse como un directorio normal del sistema operativo.

Durante el desarrollo se trabajó principalmente en Windows, por lo que FUSE se dejó aislado mediante:

```c
#ifdef __linux__
...
#endif
```

De esta forma:

Windows:

- Ignora el código FUSE
- Ejecuta únicamente el programa principal

Linux:

- Activa integración con FUSE
- Permite montar el sistema de archivos

---

## Implementación del manejo de archivos

El programa trabaja directamente sobre el directorio de FiUnamFS.

Para listar archivos:

1. Se abre el archivo "fiunamfs.img".
2. Se localiza el inicio del directorio.
3. Se recorren las entradas una por una.
4. Se leen atributos:

- Nombre
- Tamaño
- Cluster inicial
- Fecha de creación
- Fecha de modificación

5. Se muestran únicamente entradas válidas.

---

## Implementación de copia desde FiUnamFS hacia el equipo

Para extraer un archivo:

1. El usuario selecciona el archivo.
2. Se busca la entrada correspondiente.
3. Se obtiene:

- Tamaño
- Cluster inicial

4. Se calcula la posición real dentro del disco virtual.
5. Se leen los datos.
6. Se crea un archivo nuevo en el equipo.
7. Se escriben los datos extraídos.

---

## Implementación de copia desde el equipo hacia FiUnamFS

Para agregar un archivo:

1. Se abre el archivo local.
2. Se obtiene su tamaño.
3. Se busca una entrada libre en el directorio.
4. Se busca un espacio libre dentro del área de datos.
5. Se copian los datos.
6. Se crea una nueva entrada de directorio.
7. Se actualiza la información:

- Nombre
- Tamaño
- Cluster inicial
- Fechas

---

## Implementación de eliminación

La eliminación se realiza modificando únicamente la entrada correspondiente del directorio.

Proceso:

1. Se localiza el archivo.
2. Se marca la entrada como libre.
3. El nombre se reemplaza con:

```text
###############
```

4. El espacio queda disponible para futuras inserciones.

---

## Implementación de concurrencia

Para cumplir con los requisitos del proyecto se utilizó un modelo Productor–Consumidor.

El sistema utiliza dos hilos:

### Hilo principal

Responsabilidades:

- Mostrar menú
- Leer entradas
- Crear solicitudes
- Insertar tareas en cola

### Hilo trabajador

Responsabilidades:

- Obtener tareas pendientes
- Ejecutar operaciones reales sobre FiUnamFS

La comunicación ocurre mediante una cola compartida.

Funcionamiento:

```text
Usuario
    ↓
Hilo principal
    ↓
Cola compartida
    ↓
Mutex
    ↓
Variable de condición
    ↓
Hilo trabajador
```

Este esquema evita bloquear la interfaz durante operaciones sobre el disco virtual.

------------------------------------------------------------------------

# 3. Sincronización utilizada

Se utilizaron:

## pthread_mutex_t

- Protege consola
- Protege cola compartida
- Evita condiciones de carrera

## pthread_cond_t

- Suspende el trabajador hasta que haya tareas

Flujo:

Usuario\
↓\
Hilo principal\
↓\
Cola compartida\
↓\
Mutex\
↓\
Hilo trabajador

------------------------------------------------------------------------

# 4. Entorno y dependencias

Sistema operativo:

- Windows 10/11

Editor:

- Visual Studio Code

Compilador:

- MinGW-w64 GCC

Bibliotecas:

- stdio.h
- stdlib.h
- string.h
- pthread.h
- stdint.h
- time.h

Dependencia opcional:

``` c
fuse3/fuse.h
```

------------------------------------------------------------------------

# 5. Integración FUSE

Durante el desarrollo se trabajó principalmente en Windows, mientras que FUSE quedó disponible para Linux.

## Windows

FUSE no se instala de forma nativa, así que para evitar errores se aisló `fuse_main.c`:

``` c
#ifdef __linux__
...
#endif
```

Compilación:

``` bash
gcc main.c fiunamfs.c -o fiunamfs.exe -lpthread
```

Ejecución:

``` bash
fiunamfs.exe ..\fiunamfs.img
```

## Linux

Instalar:

``` bash
sudo apt install libfuse3-dev
```

Compilar:

``` bash
gcc main.c fiunamfs.c fuse_main.c -o fiunamfs -lpthread -lfuse3
```

Crear punto de montaje:

``` bash
mkdir mnt
```

Ejecutar:

``` bash
./fiunamfs fiunamfs.img mnt -f
```

------------------------------------------------------------------------

# 7. Comentarios finales

Se logró implementar todas las funciones solicitadas junto con sincronización mediante hilos. La parte más compleja fue la manipulación de archivos binarios y la coordinación entre hilos para evitar conflictos sobre recursos compartidos.
