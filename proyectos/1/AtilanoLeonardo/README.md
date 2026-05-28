# Proyecto Final: Sistema de Archivos Multihilos (FiUnamFS)

**Universidad Nacional Autónoma de México** \
**Facultad de Ingeniería** \
**Materia:** Sistemas Operativos \
**Alumno:** Leonardo Atilano Velázquez  
**Profesor:** Gunnar Eyal Wolf Iszaevich \
**Fecha de Entrega:** 21 de Mayo de 2026  


## 1. Introducción

Este proyecto es el trabajo final  para poder evaluar de forma práctica las últimas dos unidades de la materia: **Sistemas de Archivos** y **Administración de Procesos**. 

El objetivo principal fue construir un programa en Python capaz de manipular, leer, meter, sacar y borrar archivos de un disco duro virtual simulado. Este "disco" es un archivo con formato especial llamado `fiunamfs.img` que sigue las reglas de un sistema de archivos plano llamado `FiUnamFS`.

Para que el proyecto cumpla con la parte de procesos, el programa no se ejecuta de forma lineal (donde una sola línea de código espera a la otra). En su lugar, el código divide sus tareas en **componentes concurrentes (hilos)** que trabajan al mismo tiempo y se comunican sus estados mediante mecanismos de sincronización para evitar que la pantalla se congele mientras el disco está ocupado trabajando.

## 2. ¿Cómo está organizado el "Disco Virtual" --> 'fiunamfs.img' ?

Para entender cómo funciona el código, primero hay que comprender cómo está organizado el archivo `fiunamfs.img`. La computadora ve a este archivo simplemente como un bloque de datos plano de 1440 Kilobytes (el tamaño de un disquete antiguo). Este programa actúa como un "mini sistema operativo" que sabe exactamente qué significa cada byte dentro de ese bloque.

La superficie del disco simulado se divide en **sectores de 512 bytes**. Para trabajar de forma más eficiente, el sistema agrupa los sectores de 4 en 4, creando bloques llamados **Clústeres (cada clúster mide 2048 bytes)**. El disco completo tiene exactamente 720 clústeres ordenados del 0 al 719, organizados de la siguiente manera:

* **Clúster 0 (El Superbloque):** Es la "portada" o tarjeta de presentación del disco. Los primeros bytes contienen la palabra mágica `FiUnamFS` y la versión (ej. `26-2` o `24-2`). El programa revisa esta portada al iniciar; si no dice el nombre correcto, rechaza el disco para evitar corromper los datos. También guarda metadatos como el tamaño del clúster y el tamaño total de la unidad.
* **Clústeres 1 al 8 (El Directorio Plano):** Es el "índice" del cuaderno. Al ser un sistema plano, no existen las carpetas ni las subcarpetas; todos los archivos viven en una única lista gigante. El espacio del directorio permite guardar un máximo de **256 archivos**. Cada "cajón" o entrada del índice mide exactamente **64 bytes** y contiene la credencial del archivo (nombre, tamaño en bytes, en qué clúster empieza y las fechas de creación y modificación).
* **Clústeres 9 al 719 (Espacio de Datos):** Es la bodega del disco. Aquí es donde se escriben los bytes reales de los archivos que inyectamos (como imágenes, PDFs o textos). El espacio se asigna de forma **contigua**, lo que significa que si un archivo ocupa 3 clústeres, estos tienen que estar completamente juntos, uno seguido del otro.

### Estructura de cada entrada en el Directorio (Los 64 bytes)
Cuando el programa lee el índice, sabe exactamente en qué posición buscar cada dato del archivo gracias a los siguientes límites de bytes (offsets):
* `Byte 0:` Tipo de archivo (Si tiene un signo `-` el archivo está activo, si tiene una diagonal `/` significa que ese cajón está vacío y disponible).
* `Bytes 1 al 15:` Nombre del archivo (Tiene un límite estricto de 15 caracteres. Si el nombre es más corto, se rellena con espacios en blanco).
* `Bytes 16 al 19:` Tamaño real del archivo en bytes (Guardado como entero de 32 bits en formato *Little Endian*).
* `Bytes 20 al 23:` Clúster inicial donde empiezan sus datos reales en la bodega (Entero de 32 bits en *Little Endian*).
* `Bytes 30 al 44:` Hora y fecha de creación (`AAAAMMDDHHMMSS`).
* `Bytes 50 al 64:` Hora y fecha de la última modificación (`AAAAMMDDHHMMSS`).


## 3. Funcionamiento del Código y Arquitectura Multihilos

Para cumplir con los requerimientos de la unidad de procesos, el programa implementa un modelo de diseño clásico en sistemas operativos llamado **Productor-Consumidor**. En lugar de tener un solo bloque de código haciendo todo, dividí el programa en dos "ayudantes" independientes:

### A) El Hilo Principal (La Interfaz de Usuario / UI)
Es el hilo que arranca el programa. Su única función en la vida es pintar el menú interactivo en la pantalla (Listar, Copiar a PC, Inyectar, Borrar, Salir) y esperar a que el usuario teclee una opción. Este hilo no toca el archivo `fiunamfs.img` ni hace operaciones matemáticas. Cuando tú eliges una opción (por ejemplo, Borrar), el Hilo Principal empaqueta tu solicitud y la avienta dentro de una "tubería" segura llamada **Cola (`queue.Queue`)**, quedándose suspendido inmediatamente a la espera de una respuesta.

### B) El Hilo Trabajador (`FSWorker`)
Es un hilo secundario que se ejecuta de manera paralela en el fondo de la computadora (`daemon=True`). Este hilo está programado para monitorear constantemente la cola de tareas. En cuanto ve que el Hilo Principal dejó un "paquete" en la cola, el Trabajador se activa, abre el flujo hacia el archivo `fiunamfs.img`, realiza todas las operaciones de lectura o escritura de bytes de forma aislada y segura, y vuelve a cerrar el archivo.

### C) Mecanismos de Sincronización (`threading.Event`)
¿Cómo se comunican estos dos hilos para no chocar o intentar leer el disco al mismo tiempo? Usamos un mecanismo de sincronización llamado **Eventos**. 
Cuando el Hilo Principal manda una tarea a la cola, activa un candado invisible con `.wait()` que lo deja "dormido". Cuando el Hilo Trabajador termina de escribir o leer los clústeres del disco virtual, detona el evento usando `.set()`. Esta señal "despierta" al Hilo Principal instantáneamente, avisándole que los datos del disco ya están actualizados y que ya es seguro volver a imprimir el menú en la pantalla. Esto garantiza una sincronización perfecta y limpia entre la interfaz y el almacenamiento.


## 4. Detalles Importantes de Implementación

El código fue desarrollado de una forma lógica, priorizando resolver las reglas del problema mediante algoritmos sencillos y claros, simulando un proceso de desarrollo iterativo paso a paso:

* **El manejo del texto en 8 bits (Latin-1):** Uno de los retos más grandes fue que Python maneja texto moderno (UTF-8 o ASCII estándar de 7 bits). Al intentar leer el disco de prueba, si el archivo contenía algún acento o byte especial en las fechas, el programa colapsaba lanzando letras rojas de error (`UnicodeDecodeError`). Para solucionarlo, se cambió la decodificación de texto a `latin-1`. Este códec acepta los 8 bits completos sin quejarse, permitiendo que el programa lea cualquier carácter extraño o metadato del disco original sin romperse.
* **Conversión Little Endian:** La computadora guarda los números al revés de como los leemos los humanos. Por ejemplo, el número de clúster `9` se almacena internamente en bytes como `(9, 0, 0, 0)`. Para traducir esto de bytes rústicos a números enteros de Python que podamos usar en las operaciones, implementamos la función `struct.unpack('<I', ...)`, que se encarga de voltear los bytes de forma automática.
* **Listar Contenidos (Opción 1):** El hilo trabajador viaja al byte 2048 (donde empieza el directorio). Va leyendo pedazos de 64 bytes uno por uno. Revisa el primer byte: si ve un signo `-`, sabe que es un archivo activo; extrae las letras del nombre, limpia los espacios vacíos, traduce el tamaño y el clúster inicial y mete los datos en una lista limpia que el menú despliega como una tabla ordenada.
* **Extraer Archivo a la PC (Opción 2):** El programa busca el nombre del archivo dentro de la lista del directorio. Cuando lo encuentra, toma su clúster inicial y lo multiplica por 2048 para saber en qué byte exacto del archivo `.img` están escondidos los datos. Salta a esa posición, lee exactamente la cantidad de bytes que marca su tamaño (ni un byte más, ni uno menos) y fabrica un archivo real y físico en la carpeta de la computadora del usuario usando los flujos normales de escritura.
* **Inyectar Archivo al Disco (Opción 3):** Es la función más laboriosa porque el almacenamiento es **contiguo**. El programa primero mide el archivo real en tu computadora y calcula cuántos clústeres de 2048 bytes va a necesitar. Luego, crea un "mapa" en la memoria (un arreglo de 720 posiciones booleanas) donde marca como `True` los primeros 9 clústeres (reservados para el sistema) y los clústeres que ya están ocupados por otros archivos de la lista. Después, recorre el mapa buscando el primer "hueco" de clústeres libres que estén completamente juntos y seguidos. Si encuentra el espacio y hay un hueco libre en el índice del directorio, copia los bytes del archivo real en esa zona del disco virtual y llena los 64 bytes de metadatos en el índice actualizando la hora del sistema.
* **Borrar Archivo (Opción 4):** Para eliminar, el programa realiza un **borrado lógico**. Reescribir o formatear toda la bodega de datos de un archivo sería un proceso muy tardado e ineficiente. En su lugar, el hilo trabajador localiza la entrada de 64 bytes del archivo en el directorio y simplemente sobreescribe el primer byte poniendo una diagonal `/` y rellenando el nombre con la cadena de bloques `###############`. Para el sistema, el archivo ha dejado de existir y queda invisible, y sus clústeres quedan marcados como libres para ser sobreescritos por un nuevo archivo en el futuro.


## 5. Análisis de Resultados del Disco de Prueba

Al someter el archivo de referencia original `fiunamfs.img` a la prueba de listado (Opción 1) del gestor finalizado, el programa decodificó e interpretó la existencia de **3 archivos ocultos** guardados dentro del volumen virtual. Los resultados arrojados por la consola son los siguientes:

| Nombre del Archivo | Tamaño (Bytes) | Clúster Inicial | Fecha de Modificación |
| :--- | :--- | :--- | :--- |
| `README.org` | 31,094 | 10 | 12 de Mayo de 2026 (21:32:40) |
| `logo.png` | 126,423 | 26 | 12 de Mayo de 2026 (21:32:40) |
| `mensaje.jpg` | 180,080 | 88 | 12 de Mayo de 2026 (21:32:40) |

### Sobre el manejo de extensiones:
Durante el desarrollo y pruebas de inyección se observó un comportamiento clave del sistema plano: dentro de `FiUnamFS` **no existe el concepto automático de extensión de archivo** (como `.txt` o `.jpg`) como lo conocemos en Windows. El espacio del nombre son simplemente 15 caracteres planos. 

Si al inyectar un archivo nuevo (Opción 3) el usuario lo nombra simplemente como `saludo`, el archivo se guardará con ese nombre exacto a secas. Por lo tanto, para extraerlo (Opción 2) o borrarlo (Opción 4), se debe escribir únicamente `saludo`. En el caso de los archivos que venían de fábrica (como `mensaje.jpg`), se debe escribir el nombre completo con todo y el `.jpg` porque la persona que armó ese disco escribió textualmente esos caracteres dentro del espacio del nombre. El programa requiere que seamos un espejo exacto de lo que aparezca en la columna "Nombre" del listado para poder operar.


## 6. Instrucciones de Ejecución y Pruebas en PyCharm
### Pasos para la ejecución
1. Abre la terminal integrada de PyCharm (o la terminal de su sistema posicionada en la carpeta del proyecto).
2. Ejecuta el gestor con el siguiente comando:
   ```bash
   python fiunamfs_manager.py

### Requisitos previos
* Tener instalado Python 3.8 o superior en el sistema.
* Contar con el IDE PyCharm de JetBrains.
* Colocar el archivo de imagen de prueba `fiunamfs.img` en la carpeta raíz del proyecto, exactamente al mismo nivel físico que mi script de código, en este caso yo le puse `fiunamfs_manager.py`.

## 7. Conclusión

La realización de este proyecto final me permitió comprender de una manera práctica conceptos abstractos que suelen quedarse solo en la teoría, como la concurrencia en la administración de procesos y el control detallado del almacenamiento a bajo nivel. 

Diseñar e implementar el gestor para el formato `FiUnamFS` sirvió para comprender que los sistemas de archivos que utilizamos todos los días (como NTFS o ext4) no son cajas negras de magia, sino estructuras de datos lógicas sumamente estrictas que operan leyendo y escribiendo bytes crudos en posiciones físicas muy específicas del hardware. Resolver de forma manual la asignación de espacio contiguo, lidiar con las restricciones del formato en Little Endian y aplicar soluciones como el borrado lógico en las entradas del directorio, nos da una perspectiva real de ingeniería sobre cómo se gestiona el almacenamiento en un sistema operativo real.

