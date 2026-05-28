# Proyecto: Micro Sistema de Archivos Multihilos

**Integrantes:**
- González Martínez Fernando
- Quezada Olivares Emir

## Instrucciones de ejecución

El proyecto fue desarrollado en **Python 3**. Para la interfaz FUSE se requiere instalación adicional (ver más abajo). La ejecución directa en terminal no requiere dependencias externas.

---

### Ejecución directa en terminal

Permite ejecutar y observar cada operación de forma independiente. Dentro del directorio del proyecto, para ejecutarse cada módulo se debe seguir la siguiente convención:

```bash
# Listar archivos en el disco
python3 main.py <img> list

# Extraer un archivo del disco a tu sistema
python3 main.py <img> extract <archivo> [salida]

# Copiar un archivo de tu sistema al disco
python3 main.py <img> paste <local> [destino]

# Eliminar un archivo del disco
python3 main.py <img> delete <archivo>
```
- \<img> Ruta relativa al documento .img
- \<archivo\>  Nombre del archivo dentro de FiUnamFS
- \<local\> Ruta al archivo en tu sistema
- \<archivo\>  Nombre dentro de FiUnamFS
- [salida] Ruta de destino local  (opcional, default: mismo nombre)
- [destino]  Nombre dentro de FiUnamFS     (opcional, default: mismo nombre)


**Ejemplos concretos:**

```bash
python3 main.py fiunamfs.img list
python3 main.py fiunamfs.img extract foto.jpg
python3 main.py fiunamfs.img extract foto.jpg copia.jpg
python3 main.py fiunamfs.img paste "/home/user/doc.pdf" DOCUMENTO.PDF
python3 main.py fiunamfs.img delete viejo.txt
```

---

### Ejecución con FUSE

FUSE (*Filesystem in Userspace*) permite montar el `.img` como una unidad real del sistema operativo. Una vez montado, puedes navegar su contenido desde tu gestor de archivos como si fuera una USB externa, abrir archivos directamente, arrastrarlos, y eliminarlos, sin usar ningún comando especial.

#### Paso 1: Instalar el núcleo de FUSE en tu sistema operativo

* **Linux (Ubuntu/Debian):** Es nativo, únicamente hay que asegurarse que se tengan las librerías base:
  ```bash
  sudo apt-get install fuse libfuse2
  ```
* **macOS:** Necesitas instalar `macFUSE`. Consulta las instrucciones en [osxfuse.github.io](https://osxfuse.github.io).
* **Windows:** FUSE es un estándar UNIX. Para Windows existe **WinFSP**. Consulta su repositorio oficial en [github.com/winfsp/winfsp](https://github.com/winfsp/winfsp).

#### Paso 2: Instalar `fusepy`

Para la instalación mediante entorno virtual (recomendada):

```bash
# 1. Crea el entorno virtual
python3 -m venv venv
# 2. Actívalo
source venv/bin/activate
# 3. Instala fusepy de forma segura
pip install fusepy
```

#### Paso 3: Montar el sistema de archivos

> Se recomienda crear una carpeta nueva como punto de montaje. Intentar montar sobre un directorio existente con contenido generará un error.

```bash
mkdir punto_de_montaje
python3 interfazFUSE.py <img> <punto_de_montaje>
```
**Ejemplo concreto**
```bash
python3 interfazFUSE.py fiunamfs.img /home/fernando/Desktop/"FUSE test"
```

El proceso quedará corriendo en esa terminal. Desde ese momento, `punto_de_montaje/` se comporta como una unidad del sistema: puedes abrirla desde tu gestor de archivos, arrastrar archivos hacia adentro o afuera, y verlos reflejarse en el `.img` en tiempo real. Desde otra terminal también puedes operar con comandos estándar:

```bash
ls punto_de_montaje/
cp ./nuevo.txt punto_de_montaje/
rm punto_de_montaje/viejo.txt
```

Para desmontar, presiona `Ctrl+C` en la terminal donde corre `interfazFUSE.py`, o ejecuta desde otra terminal:

```bash
fusermount -u <punto_de_montaje>
```

---

## Funcionamiento


### Concurrencia - Patrón Monitor con dos hilos

El programa usa **dos hilos de ejecución** que se comunican mediante un `threading.Condition`:

* **Hilo principal** - Ejecuta la operación solicitada. Al completar cualquier escritura (`paste` o `delete`), notifica al monitor llamando a `monitor.notificar(operacion)`, lo que adquiere el `Condition`, registra la operación y llama a `condition.notify()`.
* **Hilo monitor** - Permanece dormido en `condition.wait_for()`. Al recibir la notificación despierta, consulta el estado actual del disco mediante `estado_disco()` e imprime un diagnóstico con el número de archivos y clusters libres. Luego vuelve a dormir hasta la próxima escritura.

Al terminar el programa, `monitor.detener()` señala al hilo que debe salir y espera con `hilo.join()` a que termine limpiamente, garantizando que ningún diagnóstico quede a la mitad.
