# Micro Sistema de Archivos Multihilos - FiUnamFS

## Descripción

Este proyecto implementa una versión básica y didáctica del sistema de archivos **FiUnamFS**, diseñado para interactuar con una imagen de disco (`.img`). El programa simula las operaciones fundamentales de un sistema de archivos real y permite gestionar archivos de manera interactiva a través de una terminal.

El objetivo principal de esta práctica es aplicar conceptos clave de sistemas operativos como la **estructuración de almacenamiento**, **manipulación de bytes mediante offsets** y el control de **concurrencia y sincronización** al acceder a un recurso compartido.

---

## Características

El sistema soporta las siguientes operaciones a través de un menú interactivo:

* **Analizar superbloque:** Lee y valida los metadatos principales del sistema de archivos (identificador, tamaño de cluster, número de clusters, etc.).
* **Listar directorio:** Recorre de forma secuencial las entradas del directorio para mostrar de manera organizada los archivos válidos con sus respectivos tamaños, clusters iniciales y fechas de creación/modificación.
* **Copiar desde FiUnamFS hacia la computadora:** Busca un archivo en la imagen del disco, extrae sus bytes secuencialmente y lo reconstruye en el sistema operativo local.
* **Copiar desde la computadora hacia FiUnamFS:** Valida espacio contiguo disponible en los clusters de datos y entradas libres en el directorio para añadir un archivo local a la imagen.
* **Eliminar archivo:** Realiza un borrado lógico marcando la entrada del directorio como libre, permitiendo que el espacio sea reutilizable para futuras escrituras.

---

## Lenguaje y entorno

Para resolver el problema usamos **Python 3**, utilizando exclusivamente bibliotecas estándar del lenguaje para asegurar la portabilidad:
* `struct`: Para desempaquetar datos binarios estructuras del superbloque y del directorio (`<I` para enteros de 32 bits en *little-endian*).
* `threading`: Para la ejecución paralela y el control de hilos concurrentes.
* `queue`: Para implementar un canal de comunicación seguro entre hilos de tipo FIFO.
* `os` y `math`: Para la manipulación de rutas del sistema y cálculos matemáticos de asignación de bloques.

### Requisitos
* Python 3 instalado.
* Archivo de imagen de disco con formato válido nombrado `fiunamfs.img` ubicado en la ruta relativa correcta (`../fiunamfs.img`).

---

## Cómo ejecutar el programa

1. Abrir una terminal.
2. Navegar a la carpeta donde se encuentra el archivo `LeerArchivo.py`.

```bash
cd ruta/de/la/carpeta
python 3 LeerArchivo.py
